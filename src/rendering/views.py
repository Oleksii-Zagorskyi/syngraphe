"""The *View* tab: the text of the version the reader may see (DL-0209), rendered with its clause
numbers, headed by its number and the canonical edition's (DL-0352); beside it the outline of
that text, the appendices and attachments that version lists and its generated views — the role
directory and *see also* — in the page's side panes (DL-0356, DL-0448). The
historical page of any version the reader's ceiling reaches, with its attachments and its export,
and the comparison of two (DL-0195, DL-0208) — of two versions, or of two documents and the list's
start to it (DL-0452); the export dialog and its jobs."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

import pygit2
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.response import HttpResponseBase
from django.shortcuts import render
from django.utils import timezone
from django.utils.cache import patch_cache_control
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from audit.record import record
from documents import bundle, gitstore
from documents.models import Document, Version
from documents.parts import appendices, attachments
from documents.path import frame
from editing.diffview import changed_lines
from editing.numbering import number_of
from editing.past_authors import ask, authors_at, by_author
from editions.visible import visible as visible_to
from identity.models import User, UserPreference
from identity.views.preferences import (
    OUTLINE_WIDTH,
    OUTLINE_WIDTH_MAX,
    OUTLINE_WIDTH_MIN,
    PANEL_WIDTH,
    PANEL_WIDTH_MAX,
    PANEL_WIDTH_MIN,
)
from rendering import appendix, mentions, reading
from rendering.outline import anchor_clauses, outline
from rendering.renderer import labelled, render_tokens
from shell.views import not_found

logger = logging.getLogger(__name__)

# What a document whose repository or rows disagree raises on the way to its text; the reader is
# answered as for a document that does not exist, and the fault is logged for the operator.
UNREADABLE = (pygit2.GitError, LookupError, ObjectDoesNotExist, ValueError)


def view_context(
    request: HttpRequest,
    document: Document,
    *,
    version: Version | None = None,
    number: str | None = None,
    authors: Callable[[int], dict[int, str] | None] | None = None,
    before: Version | None = None,
) -> dict[str, Any] | None:
    """What the tab shows — or, with `version`, what the historical page shows of a version the
    caller resolved through the reader's ceiling, and its `number` (DL-0195) — or `None` when
    there is nothing the person may be shown. `authors`, given the lines before the body, names
    each body line's edit author; its answer, or `None` while there is none, is `authors`. With
    `before`, the version before the one shown, only the blocks changed against it are named
    (DL-0504)."""
    try:
        if version is None:
            visible = visible_to(request.user, document)
            if visible is None:
                return None
            shown, number, stance, canonical = (
                visible.version,
                visible.number,
                visible.stance,
                visible.canonical,
            )
        else:
            shown, stance, canonical = version, "", None
            number = number or number_of(document, version)
        tenant = request.tenant  # type: ignore[attr-defined]
        repo = gitstore.open_repository(tenant.number, document.number)
        text = gitstore.read(repo, "document.md", shown.commit_sha).decode("utf-8")
        _, body = bundle.parse(text)
        listed = appendices(shown)
        texts = appendix.read_at(repo, shown, listed)
    except UNREADABLE:
        logger.exception("a document's text could not be read", extra={"document": document.number})
        return None
    tokens = labelled(body)
    headings = outline(tokens)
    anchor_clauses(tokens)
    named = authors(text[: len(text) - len(body)].count("\n")) if authors else None
    if named:
        changed: set[int] | None = None
        if before is not None:
            try:
                earlier = gitstore.read(repo, "document.md", before.commit_sha).decode("utf-8")
                changed = changed_lines(bundle.parse(earlier)[1].split("\n"), body.split("\n"))
            except UNREADABLE:
                # The version before only tells what changed: without it the text is drawn
                # unnamed, never answered as missing.
                logger.exception(
                    "a document's text could not be read", extra={"document": document.number}
                )
                changed = set()
        by_author(tokens, named, changed=changed)
    # The mentions read once, from the tokens of every text, and the generated views over the
    # body and each appendix, derived from the version shown (DL-0448).
    reader, views = appendix.generated(
        request,
        document,
        repo,
        shown,
        tokens,
        texts,
        at_version=number if version is not None else None,
    )
    return {
        "version_number": number,
        "version_stance": stance,
        "canonical_number": canonical,
        "appendices": listed,
        "attachments": attachments(shown),
        "headings": headings,
        **panes(request),
        # Raw HTML is off and every value escaped.
        "text": mark_safe(render_tokens(tokens, context=reader)),  # noqa: S308
        "authors": named,
        "has_text": bool(body.strip()),
        **views,
    }


def panes(request: HttpRequest) -> dict[str, Any]:
    """The widths the person keeps for the outline and the panel, their bounds, and whether the
    person keeps each collapsed (DL-0195, DL-0526) — read in one query."""
    kept = dict(
        UserPreference.objects.filter(user=cast(User, request.user), key__in=PANE_KEYS).values_list(
            "key", "value"
        )
    )
    return {
        "outline_width": _width(
            kept.get("outline_width"), OUTLINE_WIDTH, OUTLINE_WIDTH_MIN, OUTLINE_WIDTH_MAX
        ),
        "outline_bounds": (OUTLINE_WIDTH_MIN, OUTLINE_WIDTH_MAX),
        "panel_width": _width(
            kept.get("panel_width"), PANEL_WIDTH, PANEL_WIDTH_MIN, PANEL_WIDTH_MAX
        ),
        "panel_bounds": (PANEL_WIDTH_MIN, PANEL_WIDTH_MAX),
        "outline_shut": kept.get("outline_shut") == "on",
        "panel_shut": kept.get("panel_shut") == "on",
    }


PANE_KEYS = ("outline_width", "panel_width", "outline_shut", "panel_shut")


def _width(kept: str | None, default: int, least: int, most: int) -> int:
    if kept and kept.isdigit() and least <= int(kept) <= most:
        return int(kept)
    return default


def _declared_at(repo: Any, commit: str, document: Document) -> list[Any]:
    """The roles, actions and terms `commit` declares; none where it holds no `entities.yaml`, or
    one that does not read — logged, and every role span then listed as undeclared."""
    from documents import entities
    from editing.holds import entities_at

    return entities.readable(entities_at(repo, commit), document.number) or []


def _kept(request: HttpRequest, key: str, default: int, least: int, most: int) -> int:
    """The width the person keeps for a pane, or the default."""
    kept = (
        UserPreference.objects.filter(user=cast(User, request.user), key=key)
        .values_list("value", flat=True)
        .first()
    )
    if kept and kept.isdigit() and least <= int(kept) <= most:
        return int(kept)
    return default


# --- the historical page (DL-0195, DL-0208) -----------------------------------------------------


def _version(
    request: HttpRequest, number: int, version_number: str
) -> tuple[Document, Version, Any] | None:
    """The document, the version `version_number` names when the reader's ceiling reaches it, and
    that ceiling, read once for the request (`review.history.ceiling`); `None` wherever the
    answer is *nothing to show*."""
    from documents.views import readable_document
    from review.history import ceiling

    document = readable_document(request, number, methods=(request.method or "GET",))
    if document is None or request.method not in ("GET", "POST"):
        return None
    try:
        past = ceiling(request.user, document)
        version = past.version(version_number)
    except UNREADABLE:
        logger.exception("a document's history could not be read", extra={"document": number})
        return None
    return (document, version, past) if version is not None else None


@never_cache
@login_required
def historical(request: HttpRequest, number: int, version_number: str) -> HttpResponse:
    """One version, read only, in a window of its own: the banner, the reading view and its
    outline, the appendices and attachments at that version, *Export*, and *compare with* the
    other versions the reader may see. Never editable."""
    if request.method != "GET":
        return not_found(request)
    found = _version(request, number, version_number)
    if found is None:
        return not_found(request)
    from review.views.pending import show_author

    document, version, past = found
    asking = show_author(request.user)
    reach = past.reachable()
    # The version before this one in the reader's reach (DL-0209); none for the first within it.
    at = next((k for k, (_, v) in enumerate(reach) if v.pk == version.pk), None)
    shown = view_context(
        request,
        document,
        version=version,
        number=past.number(version),
        authors=(lambda offset: authors_at(document, version, offset)) if asking else None,
        before=reach[at - 1][1] if asking and at else None,
    )
    if shown is None:
        return not_found(request)
    # A version without its edit authors is asked of the worker; a blank body has none by design.
    waiting = asking and shown["authors"] is None and shown["has_text"]
    if waiting:
        ask(request.tenant.number, document, version)  # type: ignore[attr-defined]
    others = [n for n, v in reach if v.pk != version.pk]
    context = {
        **shown,
        "document": document,
        "frame": frame(
            request,
            document,
            here="",
            at=shown["version_number"],
            shown=shown["version_number"],
        ),
        "version_path": f"/document/{document.number}/version/{shown['version_number']}/",
        "others": others[::-1],
        "show_author": asking,
        "authors_waiting": waiting,
    }
    return render(request, "rendering/historical.html", context)


@never_cache
@login_required
def historical_attachment(
    request: HttpRequest, number: int, version_number: str, part: int
) -> HttpResponseBase:
    """An attachment as the version lists it, under its original name, never opened by the
    platform (DL-0342, DL-0421); whatever may not be served answers as a missing document."""
    if request.method != "GET":
        return not_found(request)
    found = _version(request, number, version_number)
    if found is None:
        return not_found(request)
    document, version, _past = found
    from documents.views import serve_attachment

    return serve_attachment(request, document, version, part)


@never_cache
@login_required
def compare(request: HttpRequest, number: int) -> HttpResponse:
    """Two versions on a page of their own (ST-0033, DL-0208, DL-0233): the newer one's whole
    text with its changes against the older marked in place, whichever order they were asked in;
    the attachments of both, each file at each version and whether it changed; *previous* and
    *next* on every pair, stepping out of it among the versions the reader may see (DL-0508).
    Both versions resolve through the reader's ceiling, read once; one version asked against
    itself, by one number or two, opens that version's page; a reader who may see one version is
    offered no comparison. With `with`, two documents instead, in the reader's order
    (`_compare_documents`, DL-0452)."""
    from documents.parts import changed_between
    from documents.views import readable_document
    from editing.diffview import render_changes
    from review.history import ceiling

    document = readable_document(request, number)
    if document is None:
        return not_found(request)
    # Another document named (DL-0452); both are named on the list before a pair is drawn, so
    # an empty one is nothing to show (DL-0520). A `to` belongs to the second document the
    # choosers showed, `was`: typed over, that `to` is dropped.
    other = request.GET.get("with")
    if other is not None:
        if other == "":
            return not_found(request)
        to = request.GET.get("to", "")
        if request.GET.get("was", other) != other:
            to = ""
        return _compare_documents(request, document, other, to)
    asked = request.GET.get("from", ""), request.GET.get("to", "")
    try:
        past = ceiling(request.user, document)
        seen = past.reachable()
        pair = [past.version(n) for n in asked]
    except UNREADABLE:
        logger.exception("a document's history could not be read", extra={"document": number})
        return not_found(request)
    position = {version.pk: i for i, (_n, version) in enumerate(seen)}
    found = [v for v in pair if v is not None and v.pk in position]
    if len(found) < 2:
        return not_found(request)
    if found[0].pk == found[1].pk:
        only = seen[position[found[0].pk]][0]
        return HttpResponseRedirect(f"/document/{document.number}/version/{only}/")
    i, j = sorted(position[v.pk] for v in found)
    (older_number, older), (newer_number, newer) = seen[i], seen[j]
    tenant = request.tenant  # type: ignore[attr-defined]
    try:
        repo = gitstore.open_repository(tenant.number, document.number)
        _, older_body = bundle.parse(gitstore.read(repo, "document.md", older.commit_sha).decode())
        _, newer_body = bundle.parse(gitstore.read(repo, "document.md", newer.commit_sha).decode())
    except UNREADABLE:
        logger.exception("a document's text could not be read", extra={"document": number})
        return not_found(request)

    def link(a: int, b: int) -> str:
        return f"/document/{document.number}/compare/?from={seen[a][0]}&to={seen[b][0]}"

    context = {
        "document": document,
        "frame": frame(request, document, here="", pair=(older_number, newer_number)),
        "older": older_number,
        "newer": newer_number,
        "older_link": _version_link(document, older_number),
        "newer_link": _version_link(document, newer_number),
        "numbers": [n for n, _v in seen],
        "previous": link(i - 1, i) if i > 0 else "",
        "next": link(j, j + 1) if j + 1 < len(seen) else "",
        "parts": changed_between(older, newer),
        "older_appendices": appendices(older),
        "newer_appendices": appendices(newer),
        # Rendered from text the whitelist accepted, by the renderer that escapes it.
        "changes": mark_safe(  # noqa: S308
            render_changes(
                older_body.encode("utf-8"),
                newer_body.encode("utf-8"),
                context=reading.context(
                    request.user,
                    document,
                    older_body,
                    newer_body,
                    images=reading.committed_images(document),
                    sides=(older_number, newer_number),
                ),
            )
        ),
    }
    return render(request, "rendering/compare.html", context)


def _compare_documents(
    request: HttpRequest, first: Document, other: str, asked_to: str
) -> HttpResponse:
    """Two documents compared (ST-0064, DL-0452): the second's whole text at `to` marked against
    the first's at `from`, in the reader's order, each version resolved through its own document's
    ceiling and missing ones taken as that document's newest the reader reaches; each document's
    attachments at its version, unpaired. The same document named twice: its own comparison."""
    from urllib.parse import urlencode

    from documents.views import readable_document
    from editing.diffview import render_changes
    from review.history import ceiling

    asked_from = request.GET.get("from", "")
    if not (other.isascii() and other.isdigit() and len(other) <= 9):
        return not_found(request)
    second = None
    if int(other) != first.number:
        second = readable_document(request, int(other))
        if second is None:
            return not_found(request)
    try:
        first_past = ceiling(request.user, first)
        first_seen = first_past.reachable()
        if second is None:
            # The document named as its own second: its own comparison, a missing side its
            # newest version the reader reaches.
            newest = first_seen[-1][0] if first_seen else ""
            pair = urlencode({"from": asked_from or newest, "to": asked_to or newest})
            return HttpResponseRedirect(f"/document/{first.number}/compare/?{pair}")
        older = first_past.version(asked_from) if asked_from else None
        if not asked_from and first_seen:
            older = first_seen[-1][1]
        if older is None:
            return not_found(request)
        # Named by its number now, as the chooser and the historical page name it.
        asked_from = first_past.number(older)
        context: dict[str, Any] = {
            "first": first,
            "document": first,
            "second": second,
            "older": asked_from,
            "first_numbers": [n for n, _v in first_seen],
        }
        second_past = ceiling(request.user, second)
        second_seen = second_past.reachable()
        newer = second_past.version(asked_to) if asked_to else None
        if not asked_to and second_seen:
            newer = second_seen[-1][1]
        if newer is None:
            return not_found(request)
        asked_to = second_past.number(newer)
        tenant = request.tenant  # type: ignore[attr-defined]
        older_body = _body(tenant.number, first, older)
        newer_body = _body(tenant.number, second, newer)
        context |= {
            "newer": asked_to,
            "frame": frame(
                request, first, here="", shown=f"{asked_from} → #{second.number} {asked_to}"
            ),
            "first_link": _document_link(first),
            "older_link": _version_link(first, asked_from),
            "second_link": _document_link(second),
            "newer_link": _version_link(second, asked_to),
            "second_numbers": [n for n, _v in second_seen],
            "first_attachments": attachments(older),
            "second_attachments": attachments(newer),
            "first_appendices": appendices(older),
            "second_appendices": appendices(newer),
            # Rendered from text the whitelist accepted, by the renderer that escapes it.
            "changes": mark_safe(  # noqa: S308
                render_changes(
                    older_body.encode("utf-8"),
                    newer_body.encode("utf-8"),
                    context=_two_documents_context(
                        request.user,
                        (first, asked_from, older_body),
                        (second, asked_to, newer_body),
                    ),
                )
            ),
        }
    except UNREADABLE:
        logger.exception(
            "two documents' history could not be read",
            extra={"document": first.number, "with": other},
        )
        return not_found(request)
    return render(request, "rendering/compare_documents.html", context)


def _two_documents_context(
    user: Any, first: tuple[Any, str, str], second: tuple[Any, str, str]
) -> Any:
    """The render context of two documents' text: each side's images from its own document — an
    image the second's text shows from the second, any other from the first — and the mentions
    followed where the reader may read their target, except the two documents compared: the
    reader is on both, each linked in the banner, as a document's mention of itself is never
    followed (DL-11-012)."""
    from documents import images
    from rendering import reading

    (one, one_number, one_body), (other, other_number, other_body) = first, second
    shown = {r.src for r in images.referenced({"document.md": other_body})}
    from_one, from_other = reading.committed_images(one), reading.committed_images(other)
    compared = {one.number, other.number}
    found = [m for m in mentions.targets(one_body, other_body) if m.number not in compared]
    return reading.context(
        user,
        other,
        one_body,
        other_body,
        images=lambda src: from_other(src) if src in shown else from_one(src),
        sides=(f"#{one.number} {one_number}", f"#{other.number} {other_number}"),
        found=found,
    )


def _document_link(document: Document) -> str:
    return format_html('<a href="/document/{}/">#{}</a>', document.number, document.number)


def _body(tenant: int, document: Document, version: Version) -> str:
    repo = gitstore.open_repository(tenant, document.number)
    _, body = bundle.parse(gitstore.read(repo, "document.md", version.commit_sha).decode())
    return body


@never_cache
@login_required
def compare_start(request: HttpRequest) -> HttpResponse:
    """`GET /compare/?first=a&second=b`, the list's *Compare documents…*: to the comparison's own
    address, `/document/a/compare/?with=b`; *nothing to show* unless the reader may open both."""
    from documents.views import readable_document

    numbers = [request.GET.get("first", ""), request.GET.get("second", "")]
    if not all(n.isascii() and n.isdigit() and len(n) <= 9 for n in numbers):
        return not_found(request)
    first, second = (readable_document(request, int(n)) for n in numbers)
    if first is None or second is None:
        return not_found(request)
    return HttpResponseRedirect(f"/document/{first.number}/compare/?with={second.number}")


def _version_link(document: Document, number: str) -> str:
    """A version's number as a link to its historical page, which opens in a window of its own
    (DL-0195)."""
    return format_html(
        '<a href="/document/{}/version/{}/" target="_blank" rel="noopener">{}</a>',
        document.number,
        number,
        number,
    )


# --- export (DL-0172, DL-0193, DL-0241) --------------------------------------------------------


def _offers_and_parts(
    user: Any, document: Document, version: Version | None = None, past: Any = None
) -> tuple[list[Any], bool, bool]:
    """The views the person may export — the one at `version` from a historical page — each
    marked by whether its texts show images; whether any offered export would hold attachments,
    and whether any would hold appendices — a version's lists, or the holder's draft's."""
    from rendering.export.compose import offer_lists, offers, with_images

    offered = with_images(offers(user, document, version=version, past=past), document, user)
    lists = [offer_lists(offer, document, user) for offer in offered]
    return offered, any(files for _a, files in lists), any(texts for texts, _f in lists)


@never_cache
@login_required
def export(request: HttpRequest, number: int, version_number: str | None = None) -> HttpResponse:
    """The export dialog, and the job it asks for: *what*, *format*, *view* and *changes* by the
    person's rights; a request writes the job row, then queues it, then shows its progress. From a
    historical page, the dialog at that version alone (DL-0195, DL-0208)."""
    from documents.views import readable_document

    document: Document | None
    version: Version | None = None
    past: Any = None
    if version_number is None:
        document = readable_document(request, number, methods=("GET", "POST"))
    else:
        found = _version(request, number, version_number)
        document, version, past = found if found is not None else (None, None, None)
    if document is None:
        return not_found(request)
    try:
        offered, parts, appendices = _offers_and_parts(request.user, document, version, past)
    except UNREADABLE:
        logger.exception("a document's versions could not be read", extra={"document": number})
        return not_found(request)
    if not offered:
        return not_found(request)
    # The export page's heading names the version to be exported, the first offered until a view
    # is chosen (DL-0519); at a version, that version's point.
    context: dict[str, Any] = {
        "document": document,
        "frame": (
            frame(request, document, here="export", shown=offered[0].number)
            if version is None
            # By the number its history gives it, as the version's own page names it: an alias
            # in the address stands on the version's point.
            else frame(
                request, document, here="", at=past.number(version), shown=past.number(version)
            )
        ),
        "offers": offered,
        "parts": parts,
        "appendices": appendices,
        "action": request.path,
    }
    if request.method == "GET":
        return render(request, "rendering/export.html", context)
    chosen = _chosen(request, document, offered, parts)
    if isinstance(chosen, str) or _waiting(request, document):
        # One export at a time per person and document: a second waits for the first.
        if not isinstance(chosen, str):
            chosen = _("Your previous export of this document is still being made.")
        context["refusal"] = chosen
        return render(request, "rendering/export.html", context, status=400)
    job = _queued(request, document, chosen, at_version=version is not None)
    if job is None:
        context["refusal"] = _("Your previous export of this document is still being made.")
        return render(request, "rendering/export.html", context, status=400)
    return HttpResponseRedirect(f"/document/{document.number}/export/{job.pk}/")


def _waiting(request: HttpRequest, document: Document) -> bool:
    from documents.reconcile import EXPORT_ABANDONED
    from rendering.models import ExportJob, ExportState

    recent = timezone.now() - EXPORT_ABANDONED
    return ExportJob.objects.filter(
        document=document,
        requested_by=cast(User, request.user),
        state=ExportState.QUEUED,
        created_at__gte=recent,
    ).exists()


def _chosen(
    request: HttpRequest, document: Document, offered: list[Any], parts: bool
) -> dict[str, Any] | str:
    """What the form chose, checked against what was offered; a message where it cannot stand.
    Appendices chosen without the document always go separate: the dialog disables the mode, and
    so never posts it, when the document is not chosen (DL-0207)."""
    from rendering.export.compose import offer_lists
    from rendering.models import ExportAppendices, ExportChanges, ExportFormat

    by_view = {offer.view.value: offer for offer in offered}
    offer = by_view.get(request.POST.get("view", ""))
    include_document = request.POST.get("document") == "on"
    include_attachments = parts and request.POST.get("attachments") == "on"
    include_appendices = request.POST.get("appendices") == "on"
    # A format is the document's and the appendices': the dialog disables it, and so never posts
    # it, when neither is chosen. The files go out as stored; the stored value is only the default.
    writes = include_document or include_appendices
    fmt = request.POST.get("format", "") if writes else ExportFormat.PDF.value
    if offer is None or fmt not in ExportFormat.values:
        return _("Choose a view and a format.")
    if not writes and not include_attachments:
        return _("Nothing is chosen to export.")
    appendices, attachments = offer_lists(offer, document, request.user)
    if include_appendices and not appendices:
        if not include_document and not include_attachments:
            return _("The chosen version has no appendices: nothing is left to export.")
        return _("The chosen version has no appendices; untick them to export the rest.")
    if include_attachments and not attachments:
        if not writes:
            return _("The chosen version has no attachments: nothing is left to export.")
        if not include_document:
            return _("The chosen version has no attachments; untick them to export the rest.")
        return _("The chosen version has no attachments; untick them to export the document.")
    mode = ExportAppendices.NONE
    if include_appendices:
        posted = request.POST.get("appendices_mode")
        mode = (
            ExportAppendices(posted)
            if include_document and posted in (ExportAppendices.EMBEDDED, ExportAppendices.SEPARATE)
            else ExportAppendices.EMBEDDED
            if include_document
            else ExportAppendices.SEPARATE
        )
    marked = (
        writes
        and request.POST.get(f"changes-{offer.view.value}") == ExportChanges.MARKED
        and offer.baseline is not None
        and fmt != ExportFormat.MARKDOWN
    )
    return {
        "offer": offer,
        "format": fmt,
        "document": include_document,
        "attachments": include_attachments,
        "appendices": mode,
        "changes": ExportChanges.MARKED if marked else ExportChanges.CLEAN,
    }


def _queued(
    request: HttpRequest, document: Document, chosen: dict[str, Any], *, at_version: bool = False
) -> Any:
    """The job written, audited, and queued once its row is committed."""
    from django.db import transaction

    from rendering.models import ExportChanges, ExportJob

    tenant = request.tenant  # type: ignore[attr-defined]
    offer = chosen["offer"]
    marked = chosen["changes"] == ExportChanges.MARKED
    with transaction.atomic():
        # One export at a time per person and document: the check and the insert under the
        # person's own row, so two requests at once cannot both pass it.
        User.objects.select_for_update().filter(pk=cast(User, request.user).pk).first()
        if _waiting(request, document):
            return None
        job = ExportJob.objects.create(
            document=document,
            version=offer.version,
            include_document=chosen["document"],
            include_attachments=chosen["attachments"],
            appendices=chosen["appendices"],
            format=chosen["format"],
            view=offer.view,
            changes=chosen["changes"],
            baseline_version=offer.baseline if marked else None,
            requested_by=cast(User, request.user),
            at_version=at_version,
        )
        record(
            actor=cast(User, request.user),
            action="document.exported",
            obj=document,
            before=None,
            after={
                "number": document.number,
                "export": str(job.pk),
                "view": offer.view.value,
                "format": job.format,
                "changes": job.changes,
                "commit": offer.version.commit_sha,
            },
            tenant=tenant,
        )
        job_id = str(job.pk)
        transaction.on_commit(lambda: _send(tenant.number, job_id))
    return job


def _send(tenant_number: int, job_id: str) -> None:
    """Queue a job whose row is committed. A broker that refuses it is logged, not shown: the row
    stands, and the reconciler queues it again (`export_stuck`)."""
    from rendering.tasks import render_export

    try:
        render_export.delay(tenant_number, job_id)
    except Exception:
        logger.exception("an export could not be queued", extra={"export": job_id})


def _own_job(request: HttpRequest, number: int, job_id: str) -> Any:
    """The person's own job on a document they may read, or `None`."""
    from documents.views import readable_document
    from rendering.models import ExportJob

    document = readable_document(request, number)
    if document is None:
        return None
    from rendering.export.compose import still_permitted

    try:
        job = ExportJob.objects.select_related("document", "requested_by").get(
            pk=job_id, document=document, requested_by=cast(User, request.user)
        )
    except (ExportJob.DoesNotExist, ValueError, ValidationError):
        return None
    # A right lost since the job was asked for takes its file with it.
    try:
        return job if still_permitted(job) else None
    except UNREADABLE:
        return None


@never_cache
@login_required
def export_status(request: HttpRequest, number: int, job_id: str) -> HttpResponse:
    """A job's progress: polled while it is queued, the download once done, the reason if it
    failed. Only its requester sees it."""
    from rendering.export.job import artifact

    job = _own_job(request, number, job_id)
    if job is None:
        return not_found(request)
    from rendering.export.compose import number_of

    # The job's page names the version being exported as it was asked for (DL-0519).
    context = {
        "document": job.document,
        "frame": frame(
            request,
            job.document,
            here="export",
            shown=number_of(job.document, job.version, job.view),
        ),
        "job": job,
        "file": artifact(job),
    }
    template = "rendering/export_status.html" if request.htmx else "rendering/export_job.html"  # type: ignore[attr-defined]
    return render(request, template, context)


DOWNLOAD_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown; charset=utf-8",
    ".zip": "application/zip",
}


@never_cache
@login_required
def export_download(request: HttpRequest, number: int, job_id: str) -> HttpResponseBase:
    """The job's file under its name, while it is kept."""
    from rendering.export.job import artifact

    job = _own_job(request, number, job_id)
    path = artifact(job) if job is not None else None
    if path is None:
        return not_found(request)
    # Named, never guessed from the file name: a host may know no type for `.docx`.
    response = FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename=path.name,
        content_type=DOWNLOAD_TYPES.get(path.suffix, "application/octet-stream"),
    )
    response["X-Content-Type-Options"] = "nosniff"
    patch_cache_control(response, private=True)
    return response

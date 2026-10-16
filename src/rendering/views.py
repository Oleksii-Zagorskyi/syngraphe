"""The *View* tab: the text of the version the reader may see (DL-0209), rendered with its clause
numbers, headed by its number and the canonical edition's (DL-0352); beside it the outline of
that text and the attachments that version lists, in the page's side panes (DL-0356). The
historical page of any version the reader's ceiling reaches, with its attachments and its export,
and the comparison of two (DL-0195, DL-0208); the export dialog and its jobs."""

from __future__ import annotations

import logging
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
from documents.parts import attachments
from editing.numbering import number_of
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
from rendering import reading
from rendering.outline import outline
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
) -> dict[str, Any] | None:
    """What the tab shows — or, with `version`, what the historical page shows of a version the
    caller resolved through the reader's ceiling, and its `number` (DL-0195) — or `None` when
    there is nothing the person may be shown."""
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
    except UNREADABLE:
        logger.exception("a document's text could not be read", extra={"document": document.number})
        return None
    tokens = labelled(body)
    headings = outline(tokens)
    reader = reading.context(
        request.user, document, body, images=reading.committed_images(document)
    )
    return {
        "version_number": number,
        "version_stance": stance,
        "canonical_number": canonical,
        "attachments": attachments(shown),
        "headings": headings,
        "outline_width": _kept(
            request, "outline_width", OUTLINE_WIDTH, OUTLINE_WIDTH_MIN, OUTLINE_WIDTH_MAX
        ),
        "outline_bounds": (OUTLINE_WIDTH_MIN, OUTLINE_WIDTH_MAX),
        "panel_width": _kept(request, "panel_width", PANEL_WIDTH, PANEL_WIDTH_MIN, PANEL_WIDTH_MAX),
        "panel_bounds": (PANEL_WIDTH_MIN, PANEL_WIDTH_MAX),
        # Raw HTML is off and every value escaped.
        "text": mark_safe(render_tokens(tokens, context=reader)),  # noqa: S308
    }


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
    outline, the attachments at that version, *Export*, and *compare with* the other versions the
    reader may see. Never editable."""
    if request.method != "GET":
        return not_found(request)
    found = _version(request, number, version_number)
    if found is None:
        return not_found(request)
    document, version, past = found
    shown = view_context(request, document, version=version, number=past.number(version))
    if shown is None:
        return not_found(request)
    others = [n for n, v in past.reachable() if v.pk != version.pk]
    context = {
        **shown,
        "document": document,
        "version_path": f"/document/{document.number}/version/{shown['version_number']}/",
        "others": others[::-1],
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
    *next* on a pair consecutive among the content versions the reader may see (DL-0361). Both
    versions resolve through the reader's ceiling, read once; one version asked against itself, by
    one number or two, opens that version's page; a reader who may see one version is offered no
    comparison."""
    from documents.parts import changed_between
    from documents.views import readable_document
    from editing.diffview import render_changes
    from review.history import ceiling

    document = readable_document(request, number)
    if document is None:
        return not_found(request)
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

    consecutive = j == i + 1
    context = {
        "document": document,
        "older": older_number,
        "newer": newer_number,
        "older_link": _version_link(document, older_number),
        "newer_link": _version_link(document, newer_number),
        "numbers": [n for n, _v in seen],
        "consecutive": consecutive,
        "previous": link(i - 1, i) if consecutive and i > 0 else "",
        "next": link(j, j + 1) if consecutive and j + 1 < len(seen) else "",
        "parts": changed_between(older, newer),
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
) -> tuple[list[Any], bool]:
    """The views the person may export — the one at `version` from a historical page — each
    marked by whether its text shows images, and whether any offered version has attachments."""
    from documents.models import PartIndex, PartKind
    from rendering.export.compose import offers, with_images

    offered = with_images(offers(user, document, version=version, past=past), document, user)
    parts = PartIndex.objects.filter(
        version__in=[offer.version for offer in offered], kind=PartKind.ATTACHMENT
    ).exists()
    return offered, parts


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
        offered, parts = _offers_and_parts(request.user, document, version, past)
    except UNREADABLE:
        logger.exception("a document's versions could not be read", extra={"document": number})
        return not_found(request)
    if not offered:
        return not_found(request)
    context: dict[str, Any] = {
        "document": document,
        "offers": offered,
        "parts": parts,
        "action": request.path,
    }
    if request.method == "GET":
        return render(request, "rendering/export.html", context)
    chosen = _chosen(request, offered, parts)
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


def _has_attachments(version: Any) -> bool:
    from documents.models import PartIndex, PartKind

    return PartIndex.objects.filter(version=version, kind=PartKind.ATTACHMENT).exists()


def _chosen(request: HttpRequest, offered: list[Any], parts: bool) -> dict[str, Any] | str:
    """What the form chose, checked against what was offered; a message where it cannot stand."""
    from rendering.models import ExportChanges, ExportFormat

    by_view = {offer.view.value: offer for offer in offered}
    offer = by_view.get(request.POST.get("view", ""))
    include_document = request.POST.get("document") == "on"
    include_attachments = parts and request.POST.get("attachments") == "on"
    # A format is the document's alone: the dialog disables it, and so never posts it, when the
    # document is not chosen. The files go out as stored; the stored value is only the default.
    fmt = request.POST.get("format", "") if include_document else ExportFormat.PDF.value
    if offer is None or fmt not in ExportFormat.values:
        return _("Choose a view and a format.")
    if not include_document and not include_attachments:
        return _("Nothing is chosen to export.")
    if include_attachments and not _has_attachments(offer.version):
        if not include_document:
            return _("The chosen version has no attachments: nothing is left to export.")
        return _("The chosen version has no attachments; untick them to export the document.")
    marked = (
        include_document
        and request.POST.get(f"changes-{offer.view.value}") == ExportChanges.MARKED
        and offer.baseline is not None
        and fmt != ExportFormat.MARKDOWN
    )
    return {
        "offer": offer,
        "format": fmt,
        "document": include_document,
        "attachments": include_attachments,
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
    context = {"document": job.document, "job": job, "file": artifact(job)}
    template = "rendering/export_status.html" if request.htmx else "rendering/export_job.html"  # type: ignore[attr-defined]
    return render(request, template, context)


@never_cache
@login_required
def export_download(request: HttpRequest, number: int, job_id: str) -> HttpResponseBase:
    """The job's file under its name, while it is kept."""
    from rendering.export.job import artifact

    job = _own_job(request, number, job_id)
    path = artifact(job) if job is not None else None
    if path is None:
        return not_found(request)
    response = FileResponse(path.open("rb"), as_attachment=True, filename=path.name)
    response["X-Content-Type-Options"] = "nosniff"
    patch_cache_control(response, private=True)
    return response

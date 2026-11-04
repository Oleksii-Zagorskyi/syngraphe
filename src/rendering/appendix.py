"""An appendix's own page (DL-0443, DL-0444): the document's frame for one appendix of the version
its reader may see — the appendix's outline, its text numbered from 1 with nothing in front, the
document's parts and generated views in the read-only panel, the tabs DL-0443 gives it, and none of
the document's acts; the same frame for an appendix of a past version, read only under the
historical banner; and two appendices compared on a page of their own, in one document or across
two (DL-0187, DL-0208). And the streams that bring a version's appendices into the generated views
(DL-0073): each appendix's places named by its title and linked to its page.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from markdown_it.token import Token

from access.rights import rights_on_many
from documents import gitstore
from documents.models import Document, Version
from documents.parts import Appendix, appendices, attachments
from documents.path import frame as document_frame
from documents.views import readable_document
from editions.visible import visible as visible_to
from rendering import directory, mentions, reading
from rendering.outline import anchor_clauses, outline
from rendering.renderer import RenderContext, labelled, render_tokens
from shell.views import not_found

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Shown:
    """One appendix of a version, its text read and labelled."""

    appendix: Appendix
    tokens: list[Token]


def _text_at(repo: Any, version: Version, appendix: Appendix) -> str | None:
    """`appendix`'s text as `version` holds it; `None`, logged, where its file is missing — the
    reconciler reports it (`part_missing`)."""
    path = f"appendices/{appendix.number}.md"
    try:
        return gitstore.read(repo, path, version.commit_sha).decode("utf-8")
    except KeyError:
        logger.error(
            "a listed appendix without its file",
            extra={"commit": version.commit_sha, "file": path},
        )
        return None


def read_at(repo: Any, version: Version, listed: Sequence[Appendix]) -> list[Shown]:
    """Each appendix `listed` as `version` holds its text, labelled; one whose file is missing is
    left out."""
    texts = ((appendix, _text_at(repo, version, appendix)) for appendix in listed)
    return [Shown(appendix, labelled(text)) for appendix, text in texts if text is not None]


def streams(
    document: Document,
    body: list[Token],
    shown: Sequence[Shown],
    *,
    at_version: str | None = None,
    elsewhere: bool = False,
) -> list[directory.Stream]:
    """The texts the generated views read: the body first, then each appendix in its list's order,
    its places named by its title — the title stands for its number (DL-0177, DL-0444) — and
    linked to the appendix's page, or to it at `at_version`. `elsewhere`, on a page that does not
    show the body, links the body's places to the page that does."""
    base = f"/document/{document.number}/" + (f"version/{at_version}/" if at_version else "")
    return [
        directory.Stream(body, link=base if elsewhere else ""),
        *(
            directory.Stream(
                one.tokens,
                link=f"{base}appendix/{one.appendix.number}/",
                label=f"{one.appendix.title}, ",
            )
            for one in shown
        ),
    ]


def generated(
    request: HttpRequest,
    document: Document,
    repo: Any,
    version: Version,
    body: list[Token],
    shown: Sequence[Shown],
    *,
    at_version: str | None = None,
    elsewhere: bool = False,
) -> tuple[RenderContext, dict[str, Any]]:
    """The reader's context over the body and every appendix — their mentions read once — and the
    generated views over all of them, as the panel shows them (DL-0448); `elsewhere` as
    `streams` takes it."""
    from rendering.views import _declared_at

    found = [
        *mentions.targets_in(body),
        *(m for one in shown for m in mentions.targets_in(one.tokens)),
    ]
    reader = reading.context(
        request.user, document, images=reading.committed_images(document), found=found
    )
    declared = _declared_at(repo, version.commit_sha, document)
    return reader, {
        "roles": directory.roles(
            streams(document, body, shown, at_version=at_version, elsewhere=elsewhere),
            declared,
            context=reader,
        ),
        "see_also": mentions.see_also(
            request.user, found, own=document.number, reachable=reader.reachable
        ),
    }


def frame(
    request: HttpRequest,
    document: Document,
    version: Version,
    number: str,
    part: int,
    *,
    at_version: bool = False,
) -> dict[str, Any] | None:
    """What an appendix's page shows of appendix `part` at `version`, which the caller resolved
    through the reader's ceiling and numbers `number` — `at_version` for a past version's page,
    whose panel and generated views link at that version; `None` where that version does not
    list it or its text cannot be read."""
    from documents import bundle
    from rendering.views import UNREADABLE, panes

    listed = appendices(version)
    appendix = next((a for a in listed if a.number == part), None)
    if appendix is None:
        return None
    try:
        repo = gitstore.open_repository(request.tenant.number, document.number)  # type: ignore[attr-defined]
        _, body = bundle.parse(gitstore.read(repo, "document.md", version.commit_sha).decode())
        shown = read_at(repo, version, listed)
    except UNREADABLE:
        logger.exception("an appendix could not be read", extra={"document": document.number})
        return None
    own = next((one for one in shown if one.appendix.number == part), None)
    if own is None:
        return None
    anchor_clauses(own.tokens)
    reader, views = generated(
        request,
        document,
        repo,
        version,
        labelled(body),
        shown,
        at_version=number if at_version else None,
        elsewhere=True,
    )
    return {
        "appendix": appendix,
        "version_number": number,
        "headings": outline(own.tokens),
        "appendices": listed,
        "attachments": attachments(version),
        # Raw HTML is off and every value escaped.
        "text": mark_safe(render_tokens(own.tokens, context=reader)),  # noqa: S308
        **views,
        **panes(request),
    }


@never_cache
@login_required
def page(request: HttpRequest, number: int, part: int) -> HttpResponse:
    """`/document/<n>/appendix/<p>/`: appendix `p` of the version the reader may see (DL-0209);
    *Nothing to show here* for an appendix that version does not list, as for a document the
    reader may not read."""

    document = readable_document(request, number)
    if document is None:
        return not_found(request)
    visible = visible_to(request.user, document)
    if visible is None:
        return not_found(request)
    context = frame(request, document, visible.version, visible.number, part)
    if context is None:
        return not_found(request)
    rights = rights_on_many(request.user, [document.pk]).get(document.pk, frozenset())
    context.update(
        document=document,
        frame=document_frame(
            request,
            document,
            here="latest",
            appendix=part,
            subtitle=context["appendix"].title,
            rights=rights,
            seen=visible,
        ),
    )
    return render(request, "rendering/appendix.html", context)


@never_cache
@login_required
def historical(request: HttpRequest, number: int, version_number: str, part: int) -> HttpResponse:
    """`/document/<n>/version/<v>/appendix/<p>/`: appendix `p` as version `v` had it, read only,
    under the historical banner, with no tabs and no act (DL-0195), beside the version's page and
    its attachments; *Nothing to show here* past the reader's ceiling, read once, or for an
    appendix that version does not list."""
    from rendering.views import _version

    if request.method != "GET":
        return not_found(request)
    found = _version(request, number, version_number)
    if found is None:
        return not_found(request)
    document, version, past = found
    shown = past.number(version)
    context = frame(request, document, version, shown, part, at_version=True)
    if context is None:
        return not_found(request)
    context.update(
        document=document,
        frame=document_frame(
            request,
            document,
            here="",
            at=shown,
            shown=shown,
            appendix=part,
            subtitle=context["appendix"].title,
        ),
        version_path=f"/document/{document.number}/version/{shown}/",
    )
    return render(request, "rendering/appendix_historical.html", context)


PAIR_SIDE = re.compile(r"(?P<version>[0-9][0-9.\-]{0,40}):(?P<part>[1-9][0-9]{0,8})")


def _side(value: str) -> tuple[str, int] | None:
    """`<version>:<appendix>` as the pair's address names one side; `None` for anything else."""
    found = PAIR_SIDE.fullmatch(value)
    return (found["version"], int(found["part"])) if found else None


def _appendix_at(
    tenant: int, document: Document, version: Version, part: int
) -> tuple[Appendix, str] | None:
    """Appendix `part` as `version` lists it, and its text; `None` where it does not list it, or
    its file is missing — logged as `read_at` logs it; the reconciler reports it."""
    appendix = next((a for a in appendices(version) if a.number == part), None)
    if appendix is None:
        return None
    text = _text_at(gitstore.open_repository(tenant, document.number), version, appendix)
    return (appendix, text) if text is not None else None


@never_cache
@login_required
def compare(request: HttpRequest, number: int) -> HttpResponse:
    """`/document/<n>/compare/appendix/?from=<v>:<p>&to=<v>:<p>`: two appendices on a page of their
    own (DL-0187, DL-0208) — the newer side's appendix whole with its changes against the older's
    marked, whichever order they were asked in, each version through the reader's ceiling, read
    once, and each appendix in its version's list. With `with=<m>`, the `to` side is document
    `m`'s, each document and version gated as two documents compared are (DL-0452), and the
    `to` side is marked against the `from` side in the reader's order. Anything else answers
    *Nothing to show here*."""
    from editing.diffview import render_changes
    from rendering.views import (
        UNREADABLE,
        _document_link,
        _two_documents_context,
        _version_link,
    )
    from review.history import ceiling

    document = readable_document(request, number)
    sides = [_side(request.GET.get("from", "")), _side(request.GET.get("to", ""))]
    other = request.GET.get("with")
    if document is None or None in sides:
        return not_found(request)
    (from_number, from_part), (to_number, to_part) = cast(list[tuple[str, int]], sides)
    second = document
    if other is not None:
        if not (other.isascii() and other.isdigit() and len(other) <= 9):
            return not_found(request)
        found_second = readable_document(request, int(other))
        if found_second is None:
            return not_found(request)
        second = found_second
        if second.pk == document.pk:
            # The document named as its own second: its own pair, as its comparison is.
            other = None
    tenant = request.tenant.number  # type: ignore[attr-defined]
    try:
        first_past = ceiling(request.user, document)
        second_past = first_past if second.pk == document.pk else ceiling(request.user, second)
        from_version = first_past.version(from_number)
        to_version = second_past.version(to_number)
        if from_version is None or to_version is None:
            return not_found(request)
        older = _appendix_at(tenant, document, from_version, from_part)
        newer = _appendix_at(tenant, second, to_version, to_part)
        if older is None or newer is None:
            return not_found(request)
        from_number, to_number = first_past.number(from_version), second_past.number(to_version)
        pair = [
            (document, from_number, from_version, *older),
            (second, to_number, to_version, *newer),
        ]
        if other is None:
            # One document: the newer version shown whole, whichever order was asked.
            order = {v.pk: i for i, (_n, v) in enumerate(first_past.reachable())}
            if order.get(from_version.pk, -1) > order.get(to_version.pk, -1):
                pair.reverse()
    except UNREADABLE:
        logger.exception(
            "appendices could not be read", extra={"document": number, "with": other or ""}
        )
        return not_found(request)
    (one, one_number, _ov, one_appendix, one_text) = pair[0]
    (two, two_number, _nv, two_appendix, two_text) = pair[1]
    if other is None:
        context = reading.context(
            request.user,
            document,
            one_text,
            two_text,
            images=reading.committed_images(document),
            sides=(one_number, two_number),
        )
        back = f"/document/{document.number}/compare/?from={one_number}&to={two_number}"
    else:
        context = _two_documents_context(
            request.user, (one, one_number, one_text), (two, two_number, two_text)
        )
        back = (
            f"/document/{document.number}/compare/?from={one_number}"
            f"&with={second.number}&to={two_number}"
        )
    return render(
        request,
        "rendering/compare_appendix.html",
        {
            "document": document,
            "second": second if other is not None else None,
            "older": {
                "document": one,
                "number": one_number,
                "link": _version_link(one, one_number),
                "document_link": _document_link(one),
                "appendix": one_appendix,
            },
            "newer": {
                "document": two,
                "number": two_number,
                "link": _version_link(two, two_number),
                "document_link": _document_link(two),
                "appendix": two_appendix,
            },
            "back": back,
            # Rendered from text the whitelist accepted, by the renderer that escapes it.
            "changes": mark_safe(  # noqa: S308
                render_changes(one_text.encode(), two_text.encode(), context=context)
            ),
        },
    )

"""An appendix's own page (DL-0443, DL-0444): the document's frame for one appendix of the version
its reader may see — the appendix's outline, its text numbered from 1 with nothing in front, the
document's parts and generated views in the read-only panel, the tabs DL-0443 gives it, and none of
the document's acts. And the streams that bring a version's appendices into the generated views
(DL-0073): each appendix's places named by its title and linked to its page.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from markdown_it.token import Token

from access.rights import Right, rights_on_many
from documents import gitstore
from documents.models import Document, DocumentState, Version
from documents.parts import Appendix, appendices, attachments
from documents.views import readable_document
from editions.visible import visible as visible_to
from identity.models import User
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


def read_at(repo: Any, version: Version, listed: Sequence[Appendix]) -> list[Shown]:
    """Each appendix `listed` as `version` holds its text, labelled; one whose file is missing is
    left out and logged — the reconciler reports it (`part_missing`)."""
    found = []
    for appendix in listed:
        path = f"appendices/{appendix.number}.md"
        try:
            text = gitstore.read(repo, path, version.commit_sha).decode("utf-8")
        except KeyError:
            logger.error(
                "a listed appendix without its file",
                extra={"commit": version.commit_sha, "file": path},
            )
            continue
        found.append(Shown(appendix, labelled(text)))
    return found


def streams(
    document: Document,
    body: list[Token],
    shown: Sequence[Shown],
    *,
    at_version: str | None = None,
) -> list[directory.Stream]:
    """The texts the generated views read: the body first, then each appendix in its list's order,
    its places named by its title — the title stands for its number (DL-0177, DL-0444) — and
    linked to the appendix's page, or to it at `at_version`."""
    base = f"/document/{document.number}/" + (f"version/{at_version}/" if at_version else "")
    return [
        directory.Stream(body),
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
) -> tuple[RenderContext, dict[str, Any]]:
    """The reader's context over the body and every appendix — their mentions read once — and the
    generated views over all of them, as the panel shows them (DL-0448)."""
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
            streams(document, body, shown, at_version=at_version), declared, context=reader
        ),
        "see_also": mentions.see_also(
            request.user, found, own=document.number, reachable=reader.reachable
        ),
    }


def frame(
    request: HttpRequest, document: Document, version: Version, number: str, part: int
) -> dict[str, Any] | None:
    """What an appendix's page shows of appendix `part` at `version`, which the caller resolved
    through the reader's ceiling and numbers `number`; `None` where that version does not list it
    or its text cannot be read."""
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
    reader, views = generated(request, document, repo, version, labelled(body), shown)
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
    from editing import holds

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
    hold = holds.open_hold(document)
    context.update(
        document=document,
        tab="view",
        version_stance=visible.stance,
        canonical_number=visible.canonical,
        can_edit=Right.EDIT in rights and document.state == DocumentState.ACTIVE,
        holding=hold is not None and hold.user_id == cast(User, request.user).pk,
        view_listed=True,
    )
    return render(request, "rendering/appendix.html", context)

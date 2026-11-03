"""The corpus's pieces of a document's pages: the breadcrumb every tab draws, the *archived* tag
on the pages that draw no state tags, the act archiving or restoring the document, *Copy*, and
*Compare with another document*."""

from __future__ import annotations

import logging
from typing import Any, cast

from django import template
from django.utils.html import format_html
from django.utils.safestring import SafeString

from documents.models import Document, Folder
from identity.models import User

register = template.Library()
logger = logging.getLogger(__name__)


@register.simple_tag
def folder_crumbs(document: Document) -> list[Folder]:
    """The folders from the first level below the root down to the document's own, for the
    breadcrumb; empty for a document in the root. A reader of the document sees every folder
    above it (DL-0206)."""
    from documents.tree import Tree

    return Tree("").ancestry(document.folder)


# Where a page of the family stands on the path, from the page's own `tab`, for a page whose view
# passes no frame of its own — the finishing screen's waits among them.
TAB_HERE = {
    "view": "latest",
    "info": "info",
    "edit": "draft",
    "my-edits": "draft",
    "pending": "review",
    "history": "history",
}


@register.simple_tag(takes_context=True)
def document_frame(context: Any, document: Document) -> Any:
    """The frame of `document`'s page when its view passed none (`documents.path.frame`)."""
    from documents.holds import held_by
    from documents.path import frame

    request = context["request"]
    here = TAB_HERE.get(context.get("tab", ""), "")
    if here == "draft" and not held_by(document, request.user):
        here = "latest"
    return frame(request, document, here=here)


@register.simple_tag
def archived_tag(document: Document) -> SafeString | str:
    """The *archived* tag, for the historical, compare and export pages, which draw no state tags;
    nothing on an active document. The state tags' own markup (`review/state_tag.html`)."""
    from documents.models import DocumentState
    from review.state import LABELS, State

    if document.state != DocumentState.ARCHIVED:
        return ""
    return format_html(
        '<span class="tag" data-state="{}">{}</span>', State.ARCHIVED.value, LABELS[State.ARCHIVED]
    )


@register.inclusion_tag("documents/archive_act.html", takes_context=True)
def archive_act(context: dict[str, Any], document: Document) -> dict[str, Any]:
    """*Archive* on an active document, *Restore* on an archived one — to administrators alone;
    no confirmation, a restore undoing it (DL-0084)."""
    from access.views import administers

    return {
        "document": document,
        "shown": administers(context["request"]),
        "archived": document.state == "archived",
    }


@register.inclusion_tag("documents/copy_act.html", takes_context=True)
def copy_act(context: dict[str, Any], document: Document) -> dict[str, Any]:
    """*Copy*, to a holder of *create and edit* with a version of the document to offer; drawn
    disabled with its reason on an archived document (DL-0233)."""
    from access.rights import can_create
    from documents.copying import offered
    from rendering.views import UNREADABLE

    request = context["request"]
    tenant = getattr(request, "tenant", None)
    archived = document.state == "archived"
    shown = tenant is not None and can_create(request.user, tenant)
    if shown and not archived:
        try:
            shown = bool(offered(cast(User, request.user), document))
        except UNREADABLE:
            # A record that cannot be read costs the act, never the page; logged for the operator.
            logger.exception(
                "a document's versions could not be read", extra={"document": document.number}
            )
            shown = False
    return {"document": document, "shown": shown, "archived": archived}


@register.inclusion_tag("documents/compare_act.html", takes_context=True)
def compare_act(context: dict[str, Any], document: Document) -> dict[str, Any]:
    """*Compare with another document*: the picker, from the version the page shows (DL-0452);
    from the first document's newest version the reader reaches when that cannot be read."""
    from editions.visible import visible
    from rendering.views import UNREADABLE

    try:
        seen = visible(context["request"].user, document)
    except UNREADABLE:
        logger.exception(
            "a document's version could not be read", extra={"document": document.number}
        )
        seen = None
    return {"document": document, "shown": seen.number if seen is not None else ""}

"""The corpus's pieces of a document's pages: the breadcrumb every page draws, the frame's
fallback, the *archived* tag on the pages that draw no state tags, and the act archiving or
restoring the document."""

from __future__ import annotations

import logging
from typing import Any

from django import template
from django.utils.html import format_html
from django.utils.safestring import SafeString

from documents.models import Document, Folder

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

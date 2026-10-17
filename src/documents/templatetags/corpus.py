"""The corpus's pieces of a document's pages: the breadcrumb every tab draws, the *archived* tag
on the pages that draw no state tags, the act archiving or restoring the document, and *Copy*."""

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

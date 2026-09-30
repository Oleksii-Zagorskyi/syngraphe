"""The *View* tab: the text of the version the reader may see (DL-0209), rendered with its clause
numbers, headed by its number and the canonical edition's (DL-0352), and the attachments that
version lists (DL-0349)."""

from __future__ import annotations

import logging
from typing import Any

import pygit2
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.utils.safestring import mark_safe

from documents import bundle, gitstore
from documents.models import Document
from documents.parts import attachments
from editions.visible import visible as visible_to
from rendering.renderer import render

logger = logging.getLogger(__name__)

# What a document whose repository or rows disagree raises on the way to its text; the reader is
# answered as for a document that does not exist, and the fault is logged for the operator.
UNREADABLE = (pygit2.GitError, LookupError, ObjectDoesNotExist, ValueError)


def view_context(request: HttpRequest, document: Document) -> dict[str, Any] | None:
    """What the tab shows, or `None` when there is nothing the person may be shown."""
    try:
        visible = visible_to(request.user, document)
        if visible is None:
            return None
        tenant = request.tenant  # type: ignore[attr-defined]
        repo = gitstore.open_repository(tenant.number, document.number)
        text = gitstore.read(repo, "document.md", visible.version.commit_sha).decode("utf-8")
        _, body = bundle.parse(text)
    except UNREADABLE:
        logger.exception("a document's text could not be read", extra={"document": document.number})
        return None
    return {
        "version_number": visible.number,
        "version_stance": visible.stance,
        "canonical_number": visible.canonical,
        "attachments": attachments(visible.version),
        "text": mark_safe(render(body)),  # noqa: S308 — raw HTML is off, every value escaped
    }

"""The corpus's pieces of the document page's header, drawn by every tab extending it."""

from __future__ import annotations

from django import template

from documents.models import Document, Folder

register = template.Library()


@register.simple_tag
def folder_crumbs(document: Document) -> list[Folder]:
    """The folders from the first level below the root down to the document's own, for the
    breadcrumb; empty for a document in the root. A reader of the document sees every folder
    above it (DL-0206)."""
    from documents.tree import Tree

    return Tree("").ancestry(document.folder)

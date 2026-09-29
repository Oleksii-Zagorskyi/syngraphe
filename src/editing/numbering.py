"""The number of pending work (DL-0198, DL-0267, DL-0272): the last accepted number, a hyphen, and
the count of content versions since it. Before the first acceptance the accepted number is `0.0`,
and the `created` commit is not counted (DL-0268)."""

from __future__ import annotations

from documents.models import Document, Version, VersionKind

CONTENT = (VersionKind.EDIT, VersionKind.REVIEWER_EDIT)
BEFORE_ANY_ACCEPTANCE = "0.0"


def accepted(document: Document) -> str:
    """The base the pending number counts from. Only the base before a document's first
    acceptance, `0.0`, is derived here (DL-0272)."""
    return BEFORE_ANY_ACCEPTANCE


def content_versions(document: Document) -> int:
    """The content versions counted from that base."""
    return Version.objects.filter(document=document, kind__in=CONTENT).count()


def pending(document: Document) -> str:
    """The number the next content version will carry."""
    return f"{accepted(document)}-{content_versions(document) + 1}"


def latest(document: Document) -> str:
    """The number of the newest content version."""
    return f"{accepted(document)}-{content_versions(document)}"

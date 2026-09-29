"""Version numbers, derived and never stored as the record (DL-0183, DL-0198, DL-0267, DL-0272).

An acceptance is `N.M`: N the canonical editions before it, M the acceptances since the last one.
Pending work is the latest acceptance's number, a hyphen, and the count of content versions since
it; before the first acceptance that number is `0.0`, and the `created` commit is not counted
(DL-0268). The next acceptance's number is counted from the passport's sections, pending work
from the run; order within a document's history is read from git, since commit times share
seconds.
"""

from __future__ import annotations

from documents.models import Document, VersionKind

CONTENT = (VersionKind.EDIT, VersionKind.REVIEWER_EDIT)
BEFORE_ANY_ACCEPTANCE = "0.0"


def accepted(document: Document) -> str:
    """The number pending work counts from: the latest acceptance's, `0.0` before any."""
    from review.services import latest_acceptance

    acceptance = latest_acceptance(document)
    return acceptance.number if acceptance is not None else BEFORE_ANY_ACCEPTANCE


def content_versions(document: Document) -> int:
    """The content versions since the latest acceptance: the run, as the tab lists it."""
    from review.services import run

    return len(run(document))


def next_accepted(document: Document) -> str:
    """The number the document's next acceptance carries: `N` the editions made, `M` the
    acceptances since the latest one, plus one — `0.1` for the first (DL-0183) — read from the
    passport at the head."""
    from django.db import connection

    from documents import gitstore
    from review.services import next_number, passport_at
    from tenancy.schemas import current_tenant

    tenant_number = current_tenant(connection)
    if tenant_number is None:
        raise RuntimeError("a number is read inside a tenant's schema")
    repo = gitstore.open_repository(tenant_number, document.number)
    head = gitstore.head(repo)
    return next_number(passport_at(repo, head) if head is not None else [])


def pending(document: Document, *, ahead: int = 0) -> str:
    """The number the next content version will carry — or, with `ahead`, the one that many
    versions after it: a commit already made whose row is not derived yet."""
    return f"{accepted(document)}-{content_versions(document) + 1 + ahead}"


def latest(document: Document) -> str:
    """The number of the newest content version."""
    return f"{accepted(document)}-{content_versions(document)}"

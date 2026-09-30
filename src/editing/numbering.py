"""Version numbers, derived and never stored as the record (DL-0183, DL-0198, DL-0267, DL-0272).

An acceptance is `N.M`: N the canonical editions before it, M the acceptances since the last one; an
edition is `N.0`. Pending work is the later of the latest edition's and the latest acceptance's
number, a hyphen, and the count of content versions since it — `2.0-1` is the first version after
edition `2.0` (DL-0267); before the first acceptance that number is `0.0`, and the `created` commit
is not counted (DL-0268). The next acceptance's number is counted from the passport's sections,
pending work from the run; order within a document's history is read from git, since commit times
share seconds.
"""

from __future__ import annotations

from documents.models import Document, VersionKind

CONTENT = (VersionKind.EDIT, VersionKind.REVIEWER_EDIT)
BEFORE_ANY_ACCEPTANCE = "0.0"


def edition(document: Document) -> str | None:
    """The latest edition's number, or `None` before the first."""
    from editions.models import Edition
    from review.services import number_key

    numbers = Edition.objects.filter(version__document=document).values_list("number", flat=True)
    return max(numbers, key=number_key, default=None)


def accepted(document: Document) -> str:
    """The number pending work counts from: the later of the latest edition's and the latest
    acceptance's, `0.0` before either. The edition's version is the latest accepted one, so the
    run it counts is the same (DL-0267)."""
    from review.services import latest_acceptance, number_key

    acceptance = latest_acceptance(document)
    found = [n for n in (edition(document), acceptance and acceptance.number) if n]
    return max(found, key=number_key, default=BEFORE_ANY_ACCEPTANCE)


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

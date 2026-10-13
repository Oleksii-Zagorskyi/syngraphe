"""The document's state: a function of the rows, the repository and the rights, never a stored
column (ADR-0007, DL-0233, DL-0267).

A document whose linked groups hold no *accept* has no reviewer, whatever else is true; a frozen
one reads *frozen* beneath that (DL-0189). The tags that speak of pending work reach only those who
may see it; *frozen* reaches every reader, beside them (DL-0351).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from django.utils.translation import gettext_lazy as _

from access.rights import Right, rights_on_many
from documents import gitstore
from documents.models import Document, Version
from editing import holds
from review import services
from review.models import Acceptance

logger = logging.getLogger(__name__)


class State(StrEnum):
    # Nothing written since the `created` commit and nothing accepted: no tag.
    NEW = "new"
    AWAITING_REVIEW = "awaiting_review"
    ACCEPTED = "accepted"
    NO_REVIEWER_ASSIGNED = "no_reviewer_assigned"
    FROZEN = "frozen"
    # Nothing accepted or pending beyond the latest edition.
    CANONICAL = "canonical"


LABELS = {
    State.FROZEN: _("frozen"),
    State.AWAITING_REVIEW: _("awaiting review"),
    State.NO_REVIEWER_ASSIGNED: _("no reviewer assigned"),
}
# The states a tag shows, and to whom: pending work only to those who may see it (DL-0233).
PENDING_TAGS = frozenset({State.AWAITING_REVIEW, State.NO_REVIEWER_ASSIGNED})


def with_reviewer(document_ids: Iterable[Any]) -> set[Any]:
    """The documents a linked group holds *accept* on — granted, since nothing implies it — in
    one query, whoever the groups' members are."""
    from access.models import GroupRight

    ids = list(document_ids)
    return set(
        GroupRight.objects.filter(right=Right.ACCEPT, group__links__document_id__in=ids)
        .values_list("group__links__document_id", flat=True)
        .distinct()
    )


def _state_of(
    document: Document, reviewed: set[Any], latest: Acceptance | None, content: set[str]
) -> State:
    if document.pk not in reviewed:
        return State.NO_REVIEWER_ASSIGNED
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    head = gitstore.head(repo)
    if head is None:
        return State.NEW
    if latest is not None:
        base = services.accepted_sha(latest, document.number)
    else:
        base = str(next(iter(gitstore.history(repo))).id)
    if any(sha in content for sha in services.commits_after(repo, base, head)):
        return State.AWAITING_REVIEW
    return State.ACCEPTED if latest is not None else State.NEW


def since_edition(document_ids: Iterable[Any], latest: dict[Any, Acceptance]) -> set[Any]:
    """The documents whose latest edition came after their latest acceptance, in one query:
    what is accepted there is the edition."""
    from editions.models import Edition

    newest: dict[Any, str] = {}
    for document_id, number in Edition.objects.filter(
        version__document_id__in=list(document_ids)
    ).values_list("version__document_id", "number"):
        if document_id not in newest or services.number_key(number) > services.number_key(
            newest[document_id]
        ):
            newest[document_id] = number
    return {
        pk
        for pk, number in newest.items()
        if pk not in latest or services.number_key(number) > services.number_key(latest[pk].number)
    }


def frozen(document_ids: Iterable[Any]) -> set[Any]:
    """The documents a freeze is open on, in one query."""
    from editions.models import Freeze

    return set(
        Freeze.objects.filter(
            document_id__in=list(document_ids), ended_at__isnull=True
        ).values_list("document_id", flat=True)
    )


def _rows(documents: list[Document]) -> tuple[set[Any], dict[Any, Acceptance], dict[Any, set[str]]]:
    """What the review states of `documents` are read from, in three queries whatever their
    number: who has a reviewer, each document's latest acceptance, each document's content
    commits."""
    ids = [d.pk for d in documents]
    reviewed = with_reviewer(ids)
    latest: dict[Any, Acceptance] = {}
    for acceptance in Acceptance.objects.filter(version__document_id__in=ids).select_related(
        "version"
    ):
        known = latest.get(acceptance.version.document_id)
        if known is None or services.number_key(acceptance.number) > services.number_key(
            known.number
        ):
            latest[acceptance.version.document_id] = acceptance
    content: dict[Any, set[str]] = {pk: set() for pk in ids}
    for document_id, sha in Version.objects.filter(
        document_id__in=ids, kind__in=services.CONTENT
    ).values_list("document_id", "commit_sha"):
        content[document_id].add(sha)
    return reviewed, latest, content


def states(documents: Iterable[Document]) -> dict[Any, State]:
    """The state of each document, keyed by its primary key: *no reviewer assigned* first, then
    *frozen* while a freeze is open, then the review state — *canonical* where nothing is
    accepted or pending beyond the latest edition; five queries, then each document's
    repository."""
    documents = list(documents)
    reviewed, latest, content = _rows(documents)
    held_still = frozen(d.pk for d in documents)
    canonical = since_edition((d.pk for d in documents), latest)
    result: dict[Any, State] = {}
    for d in documents:
        found = _state_of(d, reviewed, latest.get(d.pk), content[d.pk])
        if found is State.ACCEPTED and d.pk in canonical:
            found = State.CANONICAL
        result[d.pk] = (
            State.FROZEN
            if d.pk in held_still and found is not State.NO_REVIEWER_ASSIGNED
            else found
        )
    return result


def any_awaiting(documents: Iterable[Document]) -> bool:
    """Whether any of `documents` awaits review, freeze or not: three queries, then one
    repository at a time until the first, passing over a document without a content commit
    unread. One whose record cannot be read is passed over with a warning, since every page asks
    this."""
    documents = list(documents)
    reviewed, latest, content = _rows(documents)
    for document in documents:
        if document.pk not in reviewed or not content[document.pk]:
            continue
        try:
            found = _state_of(document, reviewed, latest.get(document.pk), content[document.pk])
        except Exception:  # noqa: BLE001 — one unreadable record must not fail every page
            logger.warning(
                "a document's state could not be read", extra={"document": document.number}
            )
            continue
        if found is State.AWAITING_REVIEW:
            return True
    return False


def state(document: Document) -> State:
    """The state of one document."""
    return states([document])[document.pk]


def tags(user: Any, documents: Iterable[Document]) -> dict[Any, list[State]]:
    """The state tags each document shows `user`, in order: *frozen* to every reader of it, then
    a review state that speaks of pending work where the user holds *view pending*, which
    administrators do, computed only there (DL-0351). A document whose record cannot be read
    shows no review tag and is logged, never failing the page it appears on."""
    documents = list(documents)
    rights = rights_on_many(user, [d.pk for d in documents])
    seen = [d for d in documents if Right.VIEW_PENDING in rights.get(d.pk, frozenset())]
    held_still = frozen(d.pk for d in documents)
    shown: dict[Any, list[State]] = {
        d.pk: [State.FROZEN] if d.pk in held_still else [] for d in documents
    }
    reviewed, latest, content = _rows(seen)
    for document in seen:
        try:
            found = _state_of(document, reviewed, latest.get(document.pk), content[document.pk])
        except Exception:  # noqa: BLE001 — one unreadable record must not fail a shared page
            logger.exception(
                "a document's state could not be read", extra={"document": document.number}
            )
            continue
        if found in PENDING_TAGS:
            shown[document.pk].append(found)
    return shown

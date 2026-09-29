"""The document's state: a function of the rows, the repository and the rights, never a stored
column (ADR-0007, DL-0233, DL-0267).

A document whose linked groups hold no *accept* has no reviewer, whatever else is true; the tags
that speak of pending work reach only those who may see it.
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


LABELS = {
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


def _rows(documents: list[Document]) -> tuple[set[Any], dict[Any, Acceptance], dict[Any, set[str]]]:
    """What the states of `documents` are read from, in three queries whatever their number: who
    has a reviewer, each document's latest acceptance, each document's content commits."""
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
    """The state of each document, keyed by its primary key: three queries, then each document's
    repository."""
    documents = list(documents)
    reviewed, latest, content = _rows(documents)
    return {d.pk: _state_of(d, reviewed, latest.get(d.pk), content[d.pk]) for d in documents}


def state(document: Document) -> State:
    """The state of one document."""
    return states([document])[document.pk]


def tags(user: Any, documents: Iterable[Document]) -> dict[Any, State | None]:
    """The state tag each document shows `user`, or `None`. A state that speaks of pending work
    shows only where the user holds *view pending*, which administrators do, and is computed only
    there; a document whose record cannot be read shows none and is logged, never failing the
    page it appears on."""
    documents = list(documents)
    rights = rights_on_many(user, [d.pk for d in documents])
    seen = [d for d in documents if Right.VIEW_PENDING in rights.get(d.pk, frozenset())]
    shown: dict[Any, State | None] = {d.pk: None for d in documents}
    reviewed, latest, content = _rows(seen)
    for document in seen:
        try:
            found = _state_of(document, reviewed, latest.get(document.pk), content[document.pk])
        except Exception:  # noqa: BLE001 — one unreadable record must not fail a shared page
            logger.exception(
                "a document's state could not be read", extra={"document": document.number}
            )
            continue
        shown[document.pk] = found if found in PENDING_TAGS else None
    return shown

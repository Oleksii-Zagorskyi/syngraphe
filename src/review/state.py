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
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import formats, timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from access.rights import Right, rights_on_many
from documents import gitstore
from documents.models import Document, DocumentState, Version, VersionKind
from editing import holds
from review import services
from review.models import Acceptance

logger = logging.getLogger(__name__)


class State(StrEnum):
    # Nothing written since the `created` commit and nothing accepted: no tag.
    NEW = "new"
    AWAITING_REVIEW = "awaiting_review"
    # The run's reviewer returned it without accepting, and nothing was sent since (DL-0114).
    RETURNED = "returned"
    ACCEPTED = "accepted"
    NO_REVIEWER_ASSIGNED = "no_reviewer_assigned"
    FROZEN = "frozen"
    # Nothing accepted or pending beyond the latest edition.
    CANONICAL = "canonical"
    # Someone holds the document (ADR-0006), or has reserved it (ADR-0009): the hold's own facts,
    # shown as tags beside the review state, never instead of it.
    HELD = "held"
    RESERVED = "reserved"
    # Put away by an administrator; only administrators reach it (DL-0450).
    ARCHIVED = "archived"


LABELS = {
    State.ARCHIVED: _("archived"),
    State.FROZEN: _("frozen"),
    State.HELD: _("held"),
    State.AWAITING_REVIEW: _("awaiting review"),
    State.RETURNED: _("returned"),
    State.NO_REVIEWER_ASSIGNED: _("no reviewer assigned"),
}
# The states a tag shows, and to whom: pending work only to those who may see it (DL-0233).
PENDING_TAGS = frozenset({State.AWAITING_REVIEW, State.RETURNED, State.NO_REVIEWER_ASSIGNED})
# Who may learn who holds a document, on any hold: those it keeps from editing or reviewing, and
# administrators beside them (DL-0516).
NAMED_ON_A_HOLD = frozenset({Right.EDIT, Right.ACCEPT})


class Tag(NamedTuple):
    """One state tag as a list or the document page draws it: the state, and its words for this
    reader — the date and the name, where the reader may see them, folded in."""

    state: State
    label: str


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
    document: Document,
    reviewed: set[Any],
    latest: Acceptance | None,
    content: set[str],
    returns: set[str],
) -> State:
    if document.pk not in reviewed:
        return State.NO_REVIEWER_ASSIGNED
    since = _since(document, latest, content, returns)
    if since is None:
        return State.NEW
    if since and since[-1] in returns:
        # A return with no content version after it: the run is back with its authors.
        return State.RETURNED
    if any(sha in content for sha in since):
        return State.AWAITING_REVIEW
    return State.ACCEPTED if latest is not None else State.NEW


def _since(
    document: Document, latest: Acceptance | None, content: set[str], returns: set[str]
) -> list[str] | None:
    """The content and return commits since the latest acceptance, oldest first; `None` before
    the first commit."""
    repo = gitstore.open_repository(holds.tenant_number(), document.number)
    head = gitstore.head(repo)
    if head is None:
        return None
    if latest is not None:
        # From the acceptance's own commit: a return of the run it accepted lies before it.
        base = latest.version.commit_sha
    else:
        base = str(next(iter(gitstore.history(repo))).id)
    return [sha for sha in services.commits_after(repo, base, head) if sha in content | returns]


def returned(document: Document) -> bool:
    """Whether the run is back with its authors — a return with no content version after it —
    whether or not the document is frozen or has a reviewer, which the state reads first: the
    path marks a returned run as returned (DL-0518)."""
    _, latest, content, returns = _rows([document])
    since = _since(document, latest.get(document.pk), content[document.pk], returns[document.pk])
    if not since:
        return False
    return since[-1] in returns[document.pk]


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


class _Rows(NamedTuple):
    reviewed: set[Any]
    latest: dict[Any, Acceptance]
    content: dict[Any, set[str]]
    returns: dict[Any, set[str]]


def _rows(documents: list[Document]) -> _Rows:
    """What the review states of `documents` are read from, in three queries whatever their
    number: who has a reviewer, each document's latest acceptance, each document's content and
    return commits."""
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
    returns: dict[Any, set[str]] = {pk: set() for pk in ids}
    for document_id, sha, kind in Version.objects.filter(
        document_id__in=ids, kind__in=(*services.CONTENT, VersionKind.RETURN)
    ).values_list("document_id", "commit_sha", "kind"):
        (returns if kind == VersionKind.RETURN else content)[document_id].add(sha)
    return _Rows(reviewed, latest, content, returns)


def states(documents: Iterable[Document]) -> dict[Any, State]:
    """The state of each document, keyed by its primary key: *no reviewer assigned* first, then
    *frozen* while a freeze is open, then the review state — *canonical* where nothing is
    accepted or pending beyond the latest edition; five queries, then each document's
    repository."""
    documents = list(documents)
    reviewed, latest, content, returns = _rows(documents)
    held_still = frozen(d.pk for d in documents)
    canonical = since_edition((d.pk for d in documents), latest)
    result: dict[Any, State] = {}
    for d in documents:
        found = _state_of(d, reviewed, latest.get(d.pk), content[d.pk], returns[d.pk])
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
    reviewed, latest, content, returns = _rows(documents)
    for document in documents:
        if document.pk not in reviewed or not content[document.pk]:
            continue
        try:
            found = _state_of(
                document,
                reviewed,
                latest.get(document.pk),
                content[document.pk],
                returns[document.pk],
            )
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


def reserved_since(moment: Any) -> str:
    """The date a reservation began, in the display timezone and the active language's date
    format: the one form every page shows it in, converted here because a tag's label is
    already output."""
    local = timezone.localtime(moment, ZoneInfo(settings.DISPLAY_TIMEZONE))
    return formats.date_format(local, "j E Y")


def hold_tag(hold: Any, rights: frozenset[Right], *, administrator: bool) -> Tag:
    """The tag an open hold shows a reader with `rights`: the fact to everyone; the holder's name,
    on every hold, ordinary or reserved, to holders of *edit* or *accept* and to a tenant
    administrator or a platform administrator acting in the organisation (DL-0516, ADR-0007)."""
    from identity.naming import person

    named = administrator or bool(rights & NAMED_ON_A_HOLD)
    if hold.reserved_at is None:
        if named:
            return Tag(State.HELD, gettext("held by %(name)s") % {"name": person(hold.user)})
        return Tag(State.HELD, str(LABELS[State.HELD]))
    since = reserved_since(hold.reserved_at)
    if named:
        return Tag(
            State.RESERVED,
            gettext("reserved for editing by %(name)s, since %(date)s")
            % {"name": person(hold.user), "date": since},
        )
    return Tag(State.RESERVED, gettext("reserved for editing, since %(date)s") % {"date": since})


def tags(
    user: Any, documents: Iterable[Document], *, administrator: bool = False
) -> dict[Any, list[Tag]]:
    """The state tags each document shows `user`, in order: *archived* first, to the
    administrators who alone reach an archived document; *frozen* to every reader of it; *held*
    or *reserved for editing* to every reader, named by `hold_tag`'s rule, `administrator` saying
    whether the reader administers this organisation; then a review state that speaks of pending
    work where the user holds *view pending*, which administrators do, computed only there
    (DL-0351). The holds are read in one query whatever the number of documents. A document whose
    record cannot be read shows no review tag and is logged, never failing the page it appears
    on."""
    from documents.holds import open_holds

    documents = list(documents)
    rights = rights_on_many(user, [d.pk for d in documents])
    seen = [d for d in documents if Right.VIEW_PENDING in rights.get(d.pk, frozenset())]
    held_still = frozen(d.pk for d in documents)
    held = open_holds(d.pk for d in documents)
    shown: dict[Any, list[Tag]] = {}
    for d in documents:
        shown[d.pk] = [Tag(State.FROZEN, str(LABELS[State.FROZEN]))] if d.pk in held_still else []
        if d.state == DocumentState.ARCHIVED:
            shown[d.pk].insert(0, Tag(State.ARCHIVED, str(LABELS[State.ARCHIVED])))
        if d.pk in held:
            shown[d.pk].append(
                hold_tag(held[d.pk], rights.get(d.pk, frozenset()), administrator=administrator)
            )
    reviewed, latest, content, returns = _rows(seen)
    for document in seen:
        try:
            found = _state_of(
                document,
                reviewed,
                latest.get(document.pk),
                content[document.pk],
                returns[document.pk],
            )
        except Exception:  # noqa: BLE001 — one unreadable record must not fail a shared page
            logger.exception(
                "a document's state could not be read", extra={"document": document.number}
            )
            continue
        if found in PENDING_TAGS:
            shown[document.pk].append(Tag(found, str(LABELS[found])))
    return shown

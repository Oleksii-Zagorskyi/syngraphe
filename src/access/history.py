"""Who could read a document at a past moment, and the changes to access that led there, answered
by query from the append-only history (ST-0006, ASR-18; DL-0433, DL-0457, DL-0460, DL-0461,
DL-0468).

The answer reads history alone: the access changes, the memberships' history, the organisation's
state history, the archive events and the editions — never the current-state tables, which hold
only what is true now. Each answer costs a fixed number of queries: one per input, the latest row
per key found by `DISTINCT ON`, whatever the counts of groups, members and changes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection

from access.models import AccessChange, AccessGroup
from access.rights import GRID, LADDER, Right, implied
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from documents.models import Document
    from identity.models import User

CHANGES_SHOWN = 200
ARCHIVE_ACTIONS = ("document.archived", "document.restored")


@dataclass(frozen=True)
class Grant:
    """Who made the change that decides a link, a right or a member, and when."""

    at: datetime
    by: User | None
    actor_kind: str


@dataclass(frozen=True)
class Member:
    membership_id: uuid.UUID
    address: str
    # The membership's own state then — never the person's own block (DL-0435, DL-0398).
    state: str
    added: Grant


@dataclass(frozen=True)
class GroupThen:
    group: AccessGroup
    linked: Grant
    rights: tuple[tuple[Right, Grant], ...]
    reads: bool
    members: tuple[Member, ...]


@dataclass(frozen=True)
class Answer:
    document: Document
    at: datetime
    existed: bool
    archived: bool
    organisation_blocked: bool
    edition_existed: bool
    groups: tuple[GroupThen, ...]
    groups_reading: tuple[GroupThen, ...]
    people: frozenset[uuid.UUID]


@dataclass(frozen=True)
class Change:
    at: datetime
    by: User | None
    actor_kind: str
    kind: str
    action: str
    group_name: str
    document_number: int | None
    right: str
    member_address: str
    field: str
    before: str
    after: str


def moment_of_day(day: date) -> datetime:
    """The last microsecond of `day` in the installation's display timezone, in UTC: every change
    made that day counts (DL-0461)."""
    local = datetime.combine(day, time.max, tzinfo=ZoneInfo(settings.DISPLAY_TIMEZONE))
    return local.astimezone(UTC)


def readers_at(document: Document, at: datetime) -> Answer:
    """The groups linked to `document` at `at`, each with its rights and members then, and what
    else decided whether they could read it (DL-0457: administrators and an author-only creator
    are not listed)."""
    if document.created_at > at:
        return Answer(document, at, False, False, False, False, (), (), frozenset())
    links = _latest_links(document, at)
    rights = _latest_rights(list(links), at)
    members = _latest_members(list(links), at)
    states = _states([m.membership_id for m in members.values()], at)
    archived = _archived(document, at)
    blocked = _organisation_blocked(at)
    edition = _edition_existed(document, at)

    groups = []
    for group_id, (group, linked) in sorted(links.items(), key=lambda kv: kv[1][0].name):
        granted = sorted(
            ((right, grant) for (g, right), grant in rights.items() if g == group_id),
            key=lambda pair: GRID.index(pair[0]),
        )
        listed = sorted(
            (
                Member(m.membership_id, m.address, states.get(m.membership_id, m.state), m.added)
                for (g, _), m in members.items()
                if g == group_id
            ),
            key=lambda member: member.address,
        )
        reads = not archived and not blocked and _reads([r for r, _ in granted], edition)
        groups.append(GroupThen(group, linked, tuple(granted), reads, tuple(listed)))
    reading = tuple(g for g in groups if g.reads)
    people = frozenset(m.membership_id for g in reading for m in g.members if m.state == "active")
    return Answer(document, at, True, archived, blocked, edition, tuple(groups), reading, people)


def changes_until(
    at: datetime, *, document: Document | None = None, limit: int = CHANGES_SHOWN
) -> list[Change]:
    """The changes to access at or before `at`, newest first, at most `limit`: for `document`,
    its links, its groups' rights and members then, those members' states and its archiving; for
    no document, every change in the organisation (DL-0460)."""
    from identity.models import MembershipHistory

    access = AccessChange.objects.filter(at__lte=at).select_related(
        "group", "membership__user", "document", "by"
    )
    history = MembershipHistory.objects.filter(at__lte=at).select_related("membership__user", "by")
    archives = _archive_events().filter(at__lte=at)
    if document is not None:
        links = _latest_links(document, at)
        members = _latest_members(list(links), at)
        access = access.filter(
            _q(kind=AccessChange.Kind.LINK, document=document)
            | _q(kind__in=(AccessChange.Kind.RIGHT, AccessChange.Kind.MEMBER), group_id__in=links)
        )
        history = history.filter(
            field=MembershipHistory.Field.STATE,
            membership_id__in={m.membership_id for m in members.values()},
        )
        archives = archives.filter(object_id=document.pk)
    else:
        history = history.filter(membership__tenant__number=_organisation())
        archives = archives.filter(object_id__in=_documents_here())

    found = [_access_change(row) for row in access.order_by("-at")[:limit]]
    found += [_membership_change(row) for row in history.order_by("-at")[:limit]]
    found += _archive_changes(list(archives.order_by("-at")[:limit]))
    found.sort(key=lambda change: change.at, reverse=True)
    return found[:limit]


# --- the latest row per key ---------------------------------------------------------------------


@dataclass(frozen=True)
class _MemberThen:
    membership_id: uuid.UUID
    address: str
    state: str
    added: Grant


def _grant(row: Any) -> Grant:
    return Grant(row.at, row.by, row.actor_kind)


def _latest_links(document: Document, at: datetime) -> dict[uuid.UUID, tuple[AccessGroup, Grant]]:
    rows = (
        AccessChange.objects.filter(kind=AccessChange.Kind.LINK, document=document, at__lte=at)
        .select_related("group", "by")
        .order_by("group_id", "-at")
        .distinct("group_id")
    )
    return {
        row.group_id: (row.group, _grant(row))
        for row in rows
        if row.action == AccessChange.Action.ADDED
    }


def _latest_rights(groups: list[uuid.UUID], at: datetime) -> dict[tuple[uuid.UUID, Right], Grant]:
    if not groups:
        return {}
    rows = (
        AccessChange.objects.filter(kind=AccessChange.Kind.RIGHT, group_id__in=groups, at__lte=at)
        .select_related("by")
        .order_by("group_id", "right", "-at")
        .distinct("group_id", "right")
    )
    return {
        (row.group_id, Right(row.right)): _grant(row)
        for row in rows
        if row.action == AccessChange.Action.ADDED and row.right in Right
    }


def _latest_members(
    groups: list[uuid.UUID], at: datetime
) -> dict[tuple[uuid.UUID, uuid.UUID], _MemberThen]:
    if not groups:
        return {}
    rows = (
        AccessChange.objects.filter(kind=AccessChange.Kind.MEMBER, group_id__in=groups, at__lte=at)
        .select_related("membership__user", "by")
        .order_by("group_id", "membership_id", "-at")
        .distinct("group_id", "membership_id")
    )
    found = {}
    for row in rows:
        if row.action != AccessChange.Action.ADDED or row.membership is None:
            continue
        found[(row.group_id, row.membership.pk)] = _MemberThen(
            row.membership.pk, row.membership.user.email, row.membership.state, _grant(row)
        )
    return found


def _states(memberships: list[uuid.UUID], at: datetime) -> dict[uuid.UUID, str]:
    """Each membership's own state at `at`: the latest change's `after` at or before it, else the
    earliest later change's `before`; a membership with neither keeps its current state, which the
    caller holds."""
    from identity.models import MembershipHistory

    if not memberships:
        return {}
    rows = MembershipHistory.objects.filter(
        membership_id__in=memberships, field=MembershipHistory.Field.STATE
    )
    found = {
        row.membership_id: row.before
        for row in rows.filter(at__gt=at).order_by("membership_id", "at").distinct("membership_id")
    }
    found.update(
        (row.membership_id, row.after)
        for row in rows.filter(at__lte=at)
        .order_by("membership_id", "-at")
        .distinct("membership_id")
    )
    return found


def _organisation() -> int:
    """The number of the organisation whose schema the connection is set to."""
    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("the access history is read in an organisation's schema")
    return number


def _archived(document: Document, at: datetime) -> bool:
    latest = _archive_events().filter(object_id=document.pk, at__lte=at).order_by("-at").first()
    return latest is not None and latest.action == "document.archived"


def _organisation_blocked(at: datetime) -> bool:
    from tenancy.models import TenantState, TenantStateHistory

    latest = (
        TenantStateHistory.objects.filter(tenant__number=_organisation(), at__lte=at)
        .order_by("-at")
        .first()
    )
    return latest is not None and latest.after == TenantState.BLOCKED


def _edition_existed(document: Document, at: datetime) -> bool:
    from editions.models import Edition

    return Edition.objects.filter(version__document=document, approved_at__lte=at).exists()


def _reads(granted: list[Right], edition_existed: bool) -> bool:
    steps = [LADDER.index(r) for r in implied(granted) if r in LADDER]
    if not steps:
        return False
    return max(steps) > LADDER.index(Right.VIEW_CANONICAL) or edition_existed


# --- the changes --------------------------------------------------------------------------------


def _q(**lookups: Any) -> Any:
    from django.db.models import Q

    return Q(**lookups)


def _archive_events() -> Any:
    from audit.models import AuditEvent

    return AuditEvent.objects.filter(
        object_type="document", action__in=ARCHIVE_ACTIONS
    ).select_related("actor")


def _documents_here() -> Any:
    from documents.models import Document

    return Document.objects.values("pk")


def _change(row: Any, kind: str, **filled: Any) -> Change:
    blank: dict[str, Any] = {
        "action": "",
        "group_name": "",
        "document_number": None,
        "right": "",
        "member_address": "",
        "field": "",
        "before": "",
        "after": "",
    }
    return Change(row.at, row.by, row.actor_kind, kind, **{**blank, **filled})


def _access_change(row: AccessChange) -> Change:
    common = {"action": row.action, "group_name": row.group.name}
    if row.kind == AccessChange.Kind.LINK:
        number = row.document.number if row.document is not None else None
        return _change(row, "link", **common, document_number=number)
    if row.kind == AccessChange.Kind.RIGHT:
        return _change(row, "right", **common, right=row.right)
    address = row.membership.user.email if row.membership is not None else ""
    return _change(row, "member", **common, member_address=address)


def _membership_change(row: Any) -> Change:
    return _change(
        row,
        "membership",
        member_address=row.membership.user.email,
        field=row.field,
        before=row.before,
        after=row.after,
    )


def _archive_changes(events: list[Any]) -> list[Change]:
    """Each archive event as a change; the documents' numbers read in one query."""
    from documents.models import Document

    numbers = dict(
        Document.objects.filter(pk__in={e.object_id for e in events}).values_list("pk", "number")
    )
    return [
        Change(
            event.at,
            event.actor,
            event.actor_kind,
            "archive",
            "archived" if event.action == "document.archived" else "restored",
            "",
            numbers.get(event.object_id),
            "",
            "",
            "",
            "",
            "",
        )
        for event in events
    ]

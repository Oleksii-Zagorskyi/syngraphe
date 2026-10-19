"""The access history answered by query (ASR-18): who could reach a document at a moment, each
link, right and member with the change that decided it, and the changes up to that moment —
read from the history tables alone, never replayed.

History is made by inserting rows with an explicit `at`: the tables are append-only. People,
groups, documents and their histories are synthetic examples; addresses end in `@example.test`.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "access_history_editing_fixtures",
    Path(__file__).resolve().parents[1] / "editing" / "conftest.py",
)
assert _spec is not None and _spec.loader is not None
_editing = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _editing
_spec.loader.exec_module(_editing)

# The editing tests' fixture: a document with its repository, which an archive settles first.
new_document = _editing.new_document

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

USER = "user"
SYSTEM = "system"


def _at(
    day: int, hour: int = 12, minute: int = 0, second: int = 0, microsecond: int = 0
) -> datetime:
    """A moment of the synthetic month, in UTC."""
    return datetime(2026, 3, day, hour, minute, second, microsecond, tzinfo=UTC)


def _end(day: int) -> datetime:
    """The last microsecond of a day of the synthetic month, with the display timezone UTC."""
    return _at(day, 23, 59, 59, 999999)


def _dated(document: Any, created_at: datetime) -> Any:
    """`document` as created at `created_at`: the fixtures date it now, after the synthetic days."""
    from documents.models import Document

    Document.objects.filter(pk=document.pk).update(created_at=created_at)
    document.created_at = created_at
    return document


def _group(name: str, by: Any) -> Any:
    from access.models import AccessGroup

    return AccessGroup.objects.create(name=name, created_by=by, actor_kind=USER)


def _actor(by: Any) -> dict[str, Any]:
    return {"by": by, "actor_kind": SYSTEM if by is None else USER}


def _link(group: Any, document: Any, by: Any, at: datetime, action: str = "added") -> Any:
    from access.models import AccessChange

    return AccessChange.objects.create(
        kind="link", group=group, document=document, action=action, at=at, **_actor(by)
    )


def _right(group: Any, right: Any, by: Any, at: datetime, action: str = "added") -> Any:
    from access.models import AccessChange

    return AccessChange.objects.create(
        kind="right", group=group, right=right, action=action, at=at, **_actor(by)
    )


def _member(group: Any, membership: Any, by: Any, at: datetime, action: str = "added") -> Any:
    from access.models import AccessChange

    return AccessChange.objects.create(
        kind="member", group=group, membership=membership, action=action, at=at, **_actor(by)
    )


def _state(membership: Any, before: str, after: str, by: Any, at: datetime) -> Any:
    from identity.models import MembershipHistory

    return MembershipHistory.objects.create(
        membership=membership, field="state", before=before, after=after, at=at, **_actor(by)
    )


def _admin_flag(membership: Any, before: bool, after: bool, by: Any, at: datetime) -> Any:
    from identity.models import MembershipHistory

    return MembershipHistory.objects.create(
        membership=membership,
        field="is_tenant_admin",
        before=str(before),
        after=str(after),
        at=at,
        **_actor(by),
    )


def _organisation(tenant: Any, before: str, after: str, by: Any, at: datetime) -> Any:
    from tenancy.models import TenantStateHistory

    return TenantStateHistory.objects.create(
        tenant=tenant, before=before, after=after, by=by, at=at
    )


def _edition(document: Any, by: Any, approved_at: datetime) -> Any:
    """An edition's rows made directly: the content version, the approval's passport commit, the
    freeze the approval ended, and the edition approved at `approved_at`."""
    from documents.models import Version
    from editions.models import Edition, Freeze

    frozen_at = approved_at - timedelta(hours=1)
    content = Version.objects.create(
        document=document,
        commit_sha="a" * 40,
        author=by,
        summary="Synthetic edit",
        kind="edit",
        committed_at=frozen_at - timedelta(hours=1),
        created_by=by,
        actor_kind=USER,
    )
    approval = Version.objects.create(
        document=document,
        commit_sha="b" * 40,
        author=by,
        summary="Synthetic approval",
        kind="approval",
        committed_at=approved_at,
        created_by=by,
        actor_kind=USER,
    )
    freeze = Freeze.objects.create(
        document=document,
        frozen_by=by,
        frozen_at=frozen_at,
        ended_by_kind="made_canonical",
        ended_by=by,
        ended_at=approved_at,
    )
    return Edition.objects.create(
        version=content,
        approval_version=approval,
        freeze=freeze,
        number="1.0",
        approved_by=by,
        approved_at=approved_at,
    )


def _names(groups: Any) -> list[str]:
    return [then.group.name for then in groups]


def test_groups_rights_and_members_on_a_day(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Row 1: *Readers* linked on day 1, *Editors* on day 3 and unlinked on day 5; a member added
    on day 2, removed on day 4 and re-added on day 5 by another administrator; a right granted on
    day 1 and revoked on day 3. The end of days 2, 4 and 6 each answered exactly, every link,
    right and member with the actor and time of the change that decided it."""
    from access.rights import Right

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, second, _ = member_of("second.admin@example.test", is_tenant_admin=True)
    _, _, anna = member_of("anna.reader@example.test")
    _, _, bohdan = member_of("bohdan.reader@example.test")
    document = make_document(created_by=admin, author_only=False)

    with schema_context(migrated_tenant.number):
        _dated(document, _at(1, 0))
        readers = _group("Readers", admin)
        editors = _group("Editors", admin)
        _right(readers, Right.VIEW_ALL_HISTORY, admin, _at(1, 10, 0))
        _right(readers, Right.VIEW_ACCEPTED, admin, _at(1, 10, 5))
        _link(readers, document, admin, _at(1, 10, 10))
        _member(readers, bohdan, admin, _at(1, 10, 15))
        _member(readers, anna, admin, _at(2, 10))
        _right(editors, Right.EDIT, admin, _at(3, 10, 0))
        _link(editors, document, admin, _at(3, 10, 5))
        _right(readers, Right.VIEW_ALL_HISTORY, admin, _at(3, 10, 10), action="removed")
        _member(readers, anna, admin, _at(4, 10), action="removed")
        _link(editors, document, admin, _at(5, 10, 0), action="removed")
        _member(readers, anna, second, _at(5, 10, 5))

        from access.history import Answer, Grant, GroupThen, Member, readers_at

        day_2 = readers_at(document, _end(2))
        day_4 = readers_at(document, _end(4))
        day_6 = readers_at(document, _end(6))

    anna_then = Member(
        anna.id, "anna.reader@example.test", "active", Grant(_at(2, 10), admin, USER)
    )
    bohdan_then = Member(
        bohdan.id, "bohdan.reader@example.test", "active", Grant(_at(1, 10, 15), admin, USER)
    )
    readers_on_day_2 = GroupThen(
        group=readers,
        linked=Grant(_at(1, 10, 10), admin, USER),
        # As `GRID` orders them, not as they were granted.
        rights=(
            (Right.VIEW_ACCEPTED, Grant(_at(1, 10, 5), admin, USER)),
            (Right.VIEW_ALL_HISTORY, Grant(_at(1, 10, 0), admin, USER)),
        ),
        reads=True,
        # By address.
        members=(anna_then, bohdan_then),
    )
    assert day_2 == Answer(
        document=document,
        at=_end(2),
        existed=True,
        archived=False,
        organisation_blocked=False,
        edition_existed=False,
        groups=(readers_on_day_2,),
        groups_reading=(readers_on_day_2,),
        people=frozenset({anna.id, bohdan.id}),
    )

    editors_on_day_4 = GroupThen(
        group=editors,
        linked=Grant(_at(3, 10, 5), admin, USER),
        rights=((Right.EDIT, Grant(_at(3, 10, 0), admin, USER)),),
        reads=True,
        members=(),
    )
    readers_on_day_4 = GroupThen(
        group=readers,
        linked=Grant(_at(1, 10, 10), admin, USER),
        rights=((Right.VIEW_ACCEPTED, Grant(_at(1, 10, 5), admin, USER)),),
        reads=True,
        members=(bohdan_then,),
    )
    # By the group's name.
    assert day_4.groups == (editors_on_day_4, readers_on_day_4)
    assert day_4.groups_reading == (editors_on_day_4, readers_on_day_4)
    assert day_4.people == frozenset({bohdan.id})

    anna_again = Member(
        anna.id, "anna.reader@example.test", "active", Grant(_at(5, 10, 5), second, USER)
    )
    assert _names(day_6.groups) == ["Readers"]
    assert day_6.groups[0].members == (anna_again, bohdan_then)
    assert day_6.groups[0].rights == readers_on_day_4.rights
    assert day_6.people == frozenset({anna.id, bohdan.id})


def test_the_end_of_the_day_in_the_display_timezone(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any
) -> None:
    """Row 2: the moment of a day is its last microsecond in the display timezone, an aware UTC
    datetime; a change at 23:30 local counts, one at 00:10 the next day does not — although both
    fall on the same UTC day."""
    settings.DISPLAY_TIMEZONE = "Europe/Kyiv"
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(created_by=admin, author_only=False)

    with schema_context(migrated_tenant.number):
        _dated(document, _at(1, 0))
        readers = _group("Readers", admin)
        editors = _group("Editors", admin)
        # 23:30 on 10 March in Kyiv (UTC+2 in winter) and 00:10 on 11 March.
        _link(readers, document, admin, _at(10, 21, 30))
        _link(editors, document, admin, _at(10, 22, 10))

        from access.history import moment_of_day, readers_at

        moment = moment_of_day(date(2026, 3, 10))
        answer = readers_at(document, moment)

    assert moment == _at(10, 21, 59, 59, 999999)
    assert moment.tzinfo is UTC
    # Summer time, UTC+3: the zone's rule, not a fixed offset.
    assert moment_of_day(date(2026, 7, 1)) == datetime(2026, 7, 1, 20, 59, 59, 999999, tzinfo=UTC)
    assert _names(answer.groups) == ["Readers"]


def test_the_moment_of_an_edition(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    """Row 3: an edition's moment is its `approved_at` as it is; a change at that instant counts,
    one a microsecond later does not. The edition existed then, so a canonical-only group reads."""
    from access.rights import Right

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, reader = member_of("a.reader@example.test")
    document = make_document(created_by=admin, author_only=False)
    approved_at = _at(5, 14, 0, 0, 500000)
    later = approved_at + timedelta(microseconds=1)

    with schema_context(migrated_tenant.number):
        _dated(document, _at(1, 0))
        edition = _edition(document, admin, approved_at)
        readers = _group("Readers", admin)
        editors = _group("Editors", admin)
        _right(readers, Right.VIEW_CANONICAL, admin, _at(1, 10))
        _member(readers, reader, admin, _at(1, 10))
        _link(readers, document, admin, approved_at)
        _right(readers, Right.VIEW_ACCEPTED, admin, later)
        _link(editors, document, admin, later)

        from access.history import readers_at

        answer = readers_at(document, edition.approved_at)
        before = readers_at(document, approved_at - timedelta(microseconds=1))

    assert answer.at == approved_at
    assert answer.edition_existed is True
    assert _names(answer.groups) == ["Readers"]
    assert [right for right, _ in answer.groups[0].rights] == [Right.VIEW_CANONICAL]
    assert answer.groups[0].reads is True
    assert answer.people == frozenset({reader.id})
    # A microsecond before the approval: no edition yet, and the link not yet made.
    assert before.edition_existed is False
    assert before.groups == ()


def test_members_by_the_memberships_own_state(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Row 4: a membership blocked on day 2 and lifted on day 4 is listed *blocked* on day 3 and
    not counted, active again on day 5; a person who blocked their own account is listed *active*
    and counted — the membership's own state, never the person's block."""
    from access.rights import Right
    from identity.models import AccountBlockHistory

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, blocked = member_of("blocked.member@example.test")
    _, self_blocked_user, self_blocked = member_of("self.blocked@example.test")
    self_blocked_user.self_blocked = True
    self_blocked_user.save(update_fields=["self_blocked"])
    AccountBlockHistory.objects.create(
        user=self_blocked_user, action="self_blocked", by=self_blocked_user, at=_at(1, 9)
    )
    _state(blocked, "active", "blocked", admin, _at(2, 10))
    _state(blocked, "blocked", "active", admin, _at(4, 10))
    document = make_document(created_by=admin, author_only=False)

    with schema_context(migrated_tenant.number):
        _dated(document, _at(1, 0))
        readers = _group("Readers", admin)
        _right(readers, Right.VIEW_ACCEPTED, admin, _at(1, 10))
        _link(readers, document, admin, _at(1, 10))
        _member(readers, blocked, admin, _at(1, 10, 5))
        _member(readers, self_blocked, admin, _at(1, 10, 10))

        from access.history import readers_at

        day_3 = readers_at(document, _end(3))
        day_5 = readers_at(document, _end(5))

    assert [(m.address, m.state) for m in day_3.groups[0].members] == [
        ("blocked.member@example.test", "blocked"),
        ("self.blocked@example.test", "active"),
    ]
    assert day_3.people == frozenset({self_blocked.id})
    assert [(m.address, m.state) for m in day_5.groups[0].members] == [
        ("blocked.member@example.test", "active"),
        ("self.blocked@example.test", "active"),
    ]
    assert day_5.people == frozenset({blocked.id, self_blocked.id})


def test_a_state_before_the_first_later_row_and_the_current_state(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """A membership with no state row at or before the moment takes the `before` of its earliest
    later row; one with no state row at all takes its current state."""
    from access.rights import Right
    from identity.models import Membership, User

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, lifted_later = member_of("lifted.later@example.test")
    _, _, never_changed = member_of("never.changed@example.test")
    # A membership that began blocked and has no history: created so, never changed.
    began_blocked = Membership.objects.create(
        tenant=migrated_tenant,
        user=User.objects.create_user("began.blocked@example.test", "test-only-not-a-password"),
        state="blocked",
        actor_kind=SYSTEM,
    )
    # Its only rows come after day 3: the earliest says it was blocked before.
    _state(lifted_later, "blocked", "active", admin, _at(5, 10))
    _state(lifted_later, "active", "blocked", admin, _at(7, 10))
    document = make_document(created_by=admin, author_only=False)

    with schema_context(migrated_tenant.number):
        _dated(document, _at(1, 0))
        readers = _group("Readers", admin)
        _right(readers, Right.VIEW_ACCEPTED, admin, _at(1, 10))
        _link(readers, document, admin, _at(1, 10))
        for membership in (lifted_later, never_changed, began_blocked):
            _member(readers, membership, admin, _at(1, 10, 5))

        from access.history import readers_at

        day_3 = readers_at(document, _end(3))
        day_6 = readers_at(document, _end(6))

    assert [(m.address, m.state) for m in day_3.groups[0].members] == [
        ("began.blocked@example.test", "blocked"),
        ("lifted.later@example.test", "blocked"),
        ("never.changed@example.test", "active"),
    ]
    assert day_3.people == frozenset({never_changed.id})
    assert [(m.address, m.state) for m in day_6.groups[0].members] == [
        ("began.blocked@example.test", "blocked"),
        ("lifted.later@example.test", "active"),
        ("never.changed@example.test", "active"),
    ]
    assert day_6.people == frozenset({never_changed.id, lifted_later.id})


def test_administrators_and_the_creator_are_not_listed(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Row 5: a tenant administrator and an author-only creator are never listed unless a linked
    group holds them as members (DL-0457)."""
    from access.rights import Right

    _, admin, admin_membership = member_of("an.admin@example.test", is_tenant_admin=True)
    _, creator, _ = member_of("the.creator@example.test")
    _, _, reader = member_of("a.reader@example.test")
    document = make_document(created_by=creator, author_only=True)

    with schema_context(migrated_tenant.number):
        _dated(document, _at(1, 0))

        from access.history import readers_at

        author_only = readers_at(document, _end(1))

        readers = _group("Readers", admin)
        _right(readers, Right.VIEW_ACCEPTED, admin, _at(2, 10))
        _member(readers, reader, admin, _at(2, 10))
        _link(readers, document, admin, _at(2, 10, 5))
        linked = readers_at(document, _end(2))

        _member(readers, admin_membership, admin, _at(3, 10))
        held = readers_at(document, _end(3))

    assert author_only.existed is True
    assert author_only.groups == ()
    assert author_only.people == frozenset()

    assert [m.address for m in linked.groups[0].members] == ["a.reader@example.test"]
    assert linked.people == frozenset({reader.id})

    assert [m.address for m in held.groups[0].members] == [
        "a.reader@example.test",
        "an.admin@example.test",
    ]
    assert held.people == frozenset({reader.id, admin_membership.id})


def test_an_archived_document_reads_to_no_group(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Row 6: archived and restored through `documents.archive`, the instants before, between and
    after captured — the groups read, then `archived` and none reads, then they read again. The
    event is matched by the document's id: another document's archive in the same organisation
    is not this one's."""
    from access.models import DocumentGroup
    from access.rights import Right
    from documents import archive

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, reader = member_of("a.reader@example.test")
    document = new_document(admin, "Synthetic procedure")
    other = new_document(admin, "Synthetic other procedure")

    with schema_context(migrated_tenant.number):
        readers = _group("Readers", admin)
        readers.grant(Right.VIEW_ACCEPTED, by=admin)
        readers.add_member(reader, by=admin, email=False)
        DocumentGroup.link(document, readers, by=admin)
        DocumentGroup.link(other, readers, by=admin)
        assert archive.archive(other, admin) is True

        before = timezone.now()
        assert archive.archive(document, admin) is True
        between = timezone.now()
        assert archive.restore(document, admin) is True
        after = timezone.now()

        from access.history import readers_at

        answers = [readers_at(document, at) for at in (before, between, after)]

    assert [answer.archived for answer in answers] == [False, True, False]
    assert [_names(answer.groups) for answer in answers] == [["Readers"]] * 3
    assert [[then.reads for then in answer.groups] for answer in answers] == [
        [True],
        [False],
        [True],
    ]
    assert [_names(answer.groups_reading) for answer in answers] == [["Readers"], [], ["Readers"]]
    assert [answer.people for answer in answers] == [
        frozenset({reader.id}),
        frozenset(),
        frozenset({reader.id}),
    ]


def test_blocked_organisation_and_no_edition(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Row 7: the organisation blocked on day 2 — `organisation_blocked` and no group reads; before
    that, a document before its first edition reads to a group holding *view accepted* and not to
    one holding *view canonical* alone, `edition_existed` false. Another organisation's block is
    not this one's."""
    from access.rights import Right
    from tenancy.models import Tenant

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, accepted_reader = member_of("accepted.reader@example.test")
    _, _, canonical_reader = member_of("canonical.reader@example.test")
    other_organisation = Tenant.objects.create(name="Other Synthetic Org", actor_kind=SYSTEM)
    _organisation(other_organisation, "active", "blocked", None, _at(1, 8))
    _organisation(migrated_tenant, "active", "blocked", None, _at(2, 10))
    _organisation(migrated_tenant, "blocked", "active", None, _at(4, 10))
    document = make_document(created_by=admin, author_only=False)

    with schema_context(migrated_tenant.number):
        _dated(document, _at(1, 0))
        canonical = _group("Canonical readers", admin)
        readers = _group("Readers", admin)
        _right(canonical, Right.VIEW_CANONICAL, admin, _at(1, 10))
        _right(readers, Right.VIEW_ACCEPTED, admin, _at(1, 10))
        _member(canonical, canonical_reader, admin, _at(1, 10))
        _member(readers, accepted_reader, admin, _at(1, 10))
        _link(canonical, document, admin, _at(1, 10, 5))
        _link(readers, document, admin, _at(1, 10, 5))

        from access.history import readers_at

        day_1 = readers_at(document, _end(1))
        day_3 = readers_at(document, _end(3))
        day_5 = readers_at(document, _end(5))

    assert day_1.organisation_blocked is False
    assert day_1.edition_existed is False
    assert _names(day_1.groups) == ["Canonical readers", "Readers"]
    assert [then.reads for then in day_1.groups] == [False, True]
    assert _names(day_1.groups_reading) == ["Readers"]
    assert day_1.people == frozenset({accepted_reader.id})

    assert day_3.organisation_blocked is True
    assert _names(day_3.groups) == ["Canonical readers", "Readers"]
    assert [then.reads for then in day_3.groups] == [False, False]
    assert day_3.groups_reading == ()
    assert day_3.people == frozenset()

    assert day_5.organisation_blocked is False
    assert _names(day_5.groups_reading) == ["Readers"]


def test_a_document_not_yet_created(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Before the document's `created_at`, `existed` is false and every other field is empty or
    false — whatever the organisation's and the groups' history says."""
    from access.rights import Right

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, reader = member_of("a.reader@example.test")
    _organisation(migrated_tenant, "active", "blocked", None, _at(1, 10))
    document = make_document(created_by=admin, author_only=False)

    with schema_context(migrated_tenant.number):
        _dated(document, _at(5, 0))
        readers = _group("Readers", admin)
        _right(readers, Right.VIEW_ACCEPTED, admin, _at(1, 10))
        _member(readers, reader, admin, _at(1, 10))
        _link(readers, document, admin, _at(5, 10))

        from access.history import Answer, readers_at

        answer = readers_at(document, _end(3))

    assert answer == Answer(
        document=document,
        at=_end(3),
        existed=False,
        archived=False,
        organisation_blocked=False,
        edition_existed=False,
        groups=(),
        groups_reading=(),
        people=frozenset(),
    )


def test_a_re_added_link_right_and_member_carry_the_latest_grant(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """A link, right or member removed and added again carries the `Grant` of the latest `added`
    row — its actor and time — and one removed and not re-added is gone."""
    from access.rights import Right

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, second, _ = member_of("second.admin@example.test", is_tenant_admin=True)
    _, _, reader = member_of("a.reader@example.test")
    _, _, gone = member_of("gone.reader@example.test")
    document = make_document(created_by=admin, author_only=False)

    with schema_context(migrated_tenant.number):
        _dated(document, _at(1, 0))
        readers = _group("Readers", admin)
        _right(readers, Right.VIEW_ACCEPTED, admin, _at(1, 10))
        _right(readers, Right.VIEW_ACCEPTED, admin, _at(2, 10), action="removed")
        _right(readers, Right.VIEW_ACCEPTED, second, _at(3, 10))
        _right(readers, Right.VIEW_ALL_HISTORY, admin, _at(1, 10))
        _right(readers, Right.VIEW_ALL_HISTORY, admin, _at(2, 10), action="removed")
        _member(readers, reader, admin, _at(1, 10))
        _member(readers, reader, admin, _at(2, 10), action="removed")
        _member(readers, reader, second, _at(3, 10, 5))
        _member(readers, gone, admin, _at(1, 10))
        _member(readers, gone, admin, _at(2, 10), action="removed")
        _link(readers, document, admin, _at(1, 10))
        _link(readers, document, admin, _at(2, 10), action="removed")
        _link(readers, document, second, _at(3, 10, 10))

        from access.history import Grant, Member, readers_at

        day_2 = readers_at(document, _end(2))
        day_4 = readers_at(document, _end(4))

    assert day_2.groups == ()

    (readers_then,) = day_4.groups
    assert readers_then.linked == Grant(_at(3, 10, 10), second, USER)
    assert readers_then.rights == ((Right.VIEW_ACCEPTED, Grant(_at(3, 10), second, USER)),)
    assert readers_then.members == (
        Member(reader.id, "a.reader@example.test", "active", Grant(_at(3, 10, 5), second, USER)),
    )


def test_changes_newest_200(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    """Row 8: of more than 200 changes, the newest 200, newest first, for any document; for one
    document only its links, its linked groups' rights and members, those members' state rows and
    its own archive events — never another document's, another group's, or an administrator-flag
    row — the excluded rows dated among the newest so the cap alone could not hide them."""
    from access.models import DocumentGroup
    from access.rights import GRID, Right
    from documents import archive

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, reader = member_of("a.reader@example.test")
    document = new_document(admin, "Synthetic procedure")
    other = new_document(admin, "Synthetic other procedure")

    with schema_context(migrated_tenant.number):
        readers = _group("Readers", admin)
        hidden = _group("Hidden", admin)
        DocumentGroup.link(document, readers, by=admin)
        _member(readers, reader, admin, _at(1, 10))
        for index in range(244):
            right = GRID[index % len(GRID)]
            action = "added" if (index // len(GRID)) % 2 == 0 else "removed"
            _right(readers, right, admin, _at(2) + timedelta(minutes=index), action=action)
        # The rows the document's list leaves out, newer than every right change above.
        DocumentGroup.link(other, hidden, by=admin)
        _link(hidden, other, admin, _at(9, 10))
        _right(hidden, Right.VIEW_ACCEPTED, admin, _at(9, 10, 5))
        _admin_flag(reader, False, True, admin, _at(9, 10, 10))
        # A member's state row, which the document's list keeps, as new as those it leaves out.
        _state(reader, "active", "blocked", admin, _at(9, 10, 15))
        assert archive.archive(document, admin) is True
        assert archive.archive(other, admin) is True
        at = timezone.now()

        from access.history import CHANGES_SHOWN, changes_until

        every = changes_until(at)
        this = changes_until(at, document=document)
        few = changes_until(at, limit=5)

    assert CHANGES_SHOWN == 200
    assert len(every) == 200
    assert [change.at for change in every] == sorted((c.at for c in every), reverse=True)
    assert [(c.kind, c.document_number) for c in every[:2]] == [
        ("archive", other.number),
        ("archive", document.number),
    ]
    assert {c.group_name for c in every if c.kind == "right"} == {"Readers", "Hidden"}
    assert {c.field for c in every if c.kind == "membership"} == {"state", "is_tenant_admin"}

    assert len(this) == 200
    assert [change.at for change in this] == sorted((c.at for c in this), reverse=True)
    assert (this[0].kind, this[0].action, this[0].document_number) == (
        "archive",
        "archived",
        document.number,
    )
    assert {c.group_name for c in this if c.kind in ("link", "right", "member")} == {"Readers"}
    assert {c.document_number for c in this if c.kind in ("link", "archive")} == {document.number}
    assert {c.field for c in this if c.kind == "membership"} == {"state"}
    assert len(few) == 5
    assert few == every[:5]


def test_changes_until_fields_per_kind(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Each kind of change fills its own fields and leaves the rest `""` or `None`; the actor is the
    row's, a system row's `by` empty; a change after the moment is not listed; a document's list
    holds its linked group's rights and members and its members' state rows."""
    from access.models import DocumentGroup
    from access.rights import Right
    from audit.models import AuditEvent
    from documents import archive

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, reader = member_of("a.reader@example.test")
    document = new_document(admin, "Synthetic procedure")

    with schema_context(migrated_tenant.number):
        readers = _group("Readers", admin)
        DocumentGroup.link(document, readers, by=admin)
        linked = _link(readers, document, None, _at(1, 10))
        granted = _right(readers, Right.VIEW_ACCEPTED, admin, _at(1, 10, 5))
        revoked = _right(readers, Right.VIEW_ACCEPTED, admin, _at(1, 10, 10), action="removed")
        joined = _member(readers, reader, admin, _at(1, 10, 15))
        blocked = _state(reader, "active", "blocked", None, _at(1, 10, 20))
        promoted = _admin_flag(reader, False, True, admin, _at(1, 10, 25))
        assert archive.archive(document, admin) is True
        archived = AuditEvent.objects.get(action="document.archived", object_id=document.pk)
        at = timezone.now()
        _right(readers, Right.EDIT, admin, at + timedelta(seconds=1))

        from access.history import Change, changes_until

        every = changes_until(at)
        this = changes_until(at, document=document)

    def change(**fields: Any) -> Any:
        blank: dict[str, Any] = {
            "group_name": "",
            "document_number": None,
            "right": "",
            "member_address": "",
            "field": "",
            "before": "",
            "after": "",
        }
        return Change(**{**blank, **fields})

    expected_link = change(
        at=linked.at,
        by=None,
        actor_kind=SYSTEM,
        kind="link",
        action="added",
        group_name="Readers",
        document_number=document.number,
    )
    expected_granted = change(
        at=granted.at,
        by=admin,
        actor_kind=USER,
        kind="right",
        action="added",
        group_name="Readers",
        right="view_accepted",
    )
    expected_revoked = change(
        at=revoked.at,
        by=admin,
        actor_kind=USER,
        kind="right",
        action="removed",
        group_name="Readers",
        right="view_accepted",
    )
    expected_joined = change(
        at=joined.at,
        by=admin,
        actor_kind=USER,
        kind="member",
        action="added",
        group_name="Readers",
        member_address="a.reader@example.test",
    )
    expected_blocked = change(
        at=blocked.at,
        by=None,
        actor_kind=SYSTEM,
        kind="membership",
        action="",
        member_address="a.reader@example.test",
        field="state",
        before="active",
        after="blocked",
    )
    expected_promoted = change(
        at=promoted.at,
        by=admin,
        actor_kind=USER,
        kind="membership",
        action="",
        member_address="a.reader@example.test",
        field="is_tenant_admin",
        before="False",
        after="True",
    )
    expected_archived = change(
        at=archived.at,
        by=admin,
        actor_kind=USER,
        kind="archive",
        action="archived",
        document_number=document.number,
    )
    synthetic = [
        expected_archived,
        expected_promoted,
        expected_blocked,
        expected_joined,
        expected_revoked,
        expected_granted,
        expected_link,
    ]
    # The service's own link row, made now, is older than the archive and newer than the synthetic
    # rows.
    assert [c for c in every if c.at in {e.at for e in synthetic}] == synthetic
    assert all(c.at <= at for c in every)
    assert [c for c in this if c.at in {e.at for e in synthetic}] == [
        c for c in synthetic if c is not expected_promoted
    ]


def test_reading_follows_the_rights_each_includes(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """*Make canonical* includes *view accepted*, so its group reads before any edition; *view
    all history* alone reaches no step of the viewing ladder and reads nothing."""
    from access.history import readers_at

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        document = _dated(make_document(created_by=admin), _at(1, 0))
        approvers = _group("Approvers", admin)
        historians = _group("Historians", admin)
        _right(approvers, "make_canonical", admin, _at(1, 9))
        _right(historians, "view_all_history", admin, _at(1, 9))
        _link(approvers, document, admin, _at(1, 10))
        _link(historians, document, admin, _at(1, 10))

        answer = readers_at(document, _end(1))

    assert answer.edition_existed is False
    assert {then.group.name: then.reads for then in answer.groups} == {
        "Approvers": True,
        "Historians": False,
    }

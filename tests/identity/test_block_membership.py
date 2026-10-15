"""Blocking a membership and lifting the block (ST-0004, ST-0072, DL-0256, ASR-17): the block ends
every hold the person has in the organisations chosen, its draft kept and the document free; it
leaves their groups as they stood, so lifting it restores their reach; the organisation keeps an
active administrator unless the last one is its last active member; platform administrators are
told when a person stays active elsewhere or an organisation is left without an administrator, the
organisation's administrator neither; a person's own block is drawn nowhere and not lifted here
(DL-0398); a document being committed refuses the block; and the routes are closed to everyone but
the organisation's administrators.

People, organisations, groups and texts are synthetic examples; every address ends in
`@example.test`.
"""

from __future__ import annotations

import html
import importlib.util
import re
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from django.db import connection
from django.test import Client

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "identity_block_editing_fixtures",
    Path(__file__).resolve().parents[1] / "editing" / "conftest.py",
)
assert _spec is not None and _spec.loader is not None
_editing = importlib.util.module_from_spec(_spec)
# Registered before it runs, as `tests/access/test_revocation_window.py` loads its fixtures.
sys.modules[_spec.name] = _editing
_spec.loader.exec_module(_editing)

new_document = _editing.new_document
link_group = _editing.link_group

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
    pytest.mark.usefixtures("in_english"),
]

USERS = "/administration/tenant/users/"
LAST_ADMINISTRATOR = "The organisation's last active administrator cannot be blocked."
BUSY = "A document is being worked on. Try again in a moment."
PASSWORD = "test-only-not-a-password"
ROW = re.compile(r'<tr data-row="member"[^>]*>.*?</tr>', re.DOTALL)
INPUT = re.compile(r"<input\b[^>]*>", re.DOTALL)


def block_url(membership: Any) -> str:
    return f"{USERS}{membership.id}/block/"


def lift_url(membership: Any) -> str:
    return f"{USERS}{membership.id}/lift/"


def block(client: Client, membership: Any, *tenants: Any) -> Any:
    return client.post(
        block_url(membership), {"organisations": [str(tenant.number) for tenant in tenants]}
    )


def text_of(response: Any) -> str:
    return html.unescape(response.content.decode())


def row_of(page: str, email: str) -> str:
    [row] = [row for row in ROW.findall(page) if email in row]
    return str(row)


def organisation_boxes(page: str) -> dict[str, bool]:
    """The `organisations` checkboxes of a page: each one's value, and whether it is checked."""
    boxes: dict[str, bool] = {}
    for tag in INPUT.findall(page):
        if not re.search(r'\bname="organisations"', tag):
            continue
        assert re.search(r'\btype="checkbox"', tag), tag
        value = re.search(r'\bvalue="([^"]*)"', tag)
        assert value is not None, tag
        boxes[value.group(1)] = re.search(r"\schecked\b", tag) is not None
    return boxes


def audit_ids() -> set[Any]:
    from audit.models import AuditEvent

    return set(AuditEvent.objects.values_list("id", flat=True))


def written_since(seen: set[Any]) -> list[Any]:
    from audit.models import AuditEvent

    return list(AuditEvent.objects.exclude(id__in=seen))


def history_of(*memberships: Any) -> list[Any]:
    from identity.models import MembershipHistory

    return list(MembershipHistory.objects.filter(membership__in=memberships).order_by("at"))


def platform_notifications() -> list[Any]:
    from tenancy.models import PlatformNotification

    with schema_context(None):
        return list(PlatformNotification.objects.all())


def platform_administrator(email: str) -> Any:
    from identity.models import User

    return User.objects.create_user(email, PASSWORD, is_platform_admin=True)


def member_elsewhere(tenant: Any, user: Any, *, is_tenant_admin: bool = False) -> Any:
    from identity.models import Membership

    return Membership.objects.create(
        tenant=tenant, user=user, is_tenant_admin=is_tenant_admin, actor_kind="system"
    )


def client_on(host: str, user: Any) -> Client:
    from tenancy.middleware import invalidate_host_cache

    invalidate_host_cache()
    client = Client(headers={"host": host})
    client.force_login(user)
    return client


def a_domain(tenant: Any, host: str) -> None:
    from tenancy.models import TenantDomain

    TenantDomain.objects.create(tenant=tenant, host=host, is_default=True, actor_kind="system")


def holding(
    tenant: Any, new_document: Any, link_group: Any, admin: Any, user: Any, membership: Any
) -> tuple[Any, Any]:
    """A document the administrator created, linked to a group giving the member *edit*, and the
    hold the member took on it with its draft."""
    from access.rights import Right
    from editing import holds

    document = new_document(admin, "Synthetic leave procedure")
    link_group(document, [Right.EDIT], [membership], admin)
    with schema_context(tenant.number):
        hold = holds.take(document, user)
    return document, hold


def test_block_ends_the_hold_and_keeps_the_draft(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from documents.holds import is_held
    from editing.models import Draft

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, editor, membership = member_of("an.editor@example.test")
    document, hold = holding(
        migrated_tenant, new_document, link_group, admin_user, editor, membership
    )
    seen = audit_ids()

    response = block(admin, membership, migrated_tenant)

    assert response.status_code == 302
    assert response["Location"] == USERS
    membership.refresh_from_db()
    assert membership.state == "blocked"
    [row] = history_of(membership)
    assert (row.field, row.before, row.after, row.by_id) == (
        "state",
        "active",
        "blocked",
        admin_user.pk,
    )
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is not None
        assert hold.release_kind == "blocked"
        assert hold.released_by_id == admin_user.pk
        assert hold.release_reason == "blocked"
        assert Draft.objects.filter(hold=hold).exists()
        assert not is_held(document)
    events = written_since(seen)
    assert len([e for e in events if e.action == "membership.blocked"]) == 1
    [released] = [e for e in events if e.action == "document.hold_released"]
    assert released.after["release_kind"] == "blocked"


def test_asks_which_organisations_and_tells_the_platform(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    from identity.models import Membership
    from notifications.models import Notification
    from tenancy.models import Tenant

    first = migrated_tenant
    second = make_tenant_schema("Second Synthetic Org")
    third = Tenant.objects.create(
        name="Third Synthetic Org Elsewhere", state="active", actor_kind="system"
    )
    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    member_elsewhere(second, admin_user, is_tenant_admin=True)
    _, someone, in_first = member_of("some.one@example.test")
    in_second = member_elsewhere(second, someone)
    in_third = member_elsewhere(third, someone)
    watchers = [platform_administrator(f"platform.{n}@example.test") for n in (1, 2)]

    page = admin.get(block_url(in_first))

    assert page.status_code == 200
    body = text_of(page)
    assert "some.one@example.test" in body
    assert organisation_boxes(body) == {str(first.number): True, str(second.number): False}
    assert third.name not in body

    response = block(admin, in_first, first, second)

    assert response.status_code == 302
    assert response["Location"] == USERS
    states = dict(Membership.objects.filter(user=someone).values_list("tenant__number", "state"))
    assert states == {first.number: "blocked", second.number: "blocked", third.number: "active"}
    rows = history_of(in_first, in_second, in_third)
    assert sorted((r.membership_id, r.field, r.before, r.after) for r in rows) == sorted(
        [
            (in_first.pk, "state", "active", "blocked"),
            (in_second.pk, "state", "active", "blocked"),
        ]
    )
    told = platform_notifications()
    assert {n.event for n in told} == {"user_partially_blocked"}
    for watcher in watchers:
        facts = sorted(
            (n.facts for n in told if n.user_id == watcher.pk), key=lambda f: f["tenant"]
        )
        assert facts == [
            {"user": str(someone.pk), "tenant": first.number},
            {"user": str(someone.pk), "tenant": second.number},
        ]
    assert len(told) == 2 * len(watchers)
    for tenant in (first, second):
        with schema_context(tenant.number):
            assert not Notification.objects.filter(
                event__in=("user_partially_blocked", "tenant_without_admin")
            ).exists()


def test_last_administrator_cannot_be_blocked(migrated_tenant: Any, member_of: Any) -> None:
    from tenancy.models import PlatformNotification

    platform_administrator("platform.one@example.test")
    admin, _, own = member_of("t.admin@example.test", is_tenant_admin=True)
    _, _, other = member_of("some.one@example.test")

    page = admin.get(USERS)

    assert page.status_code == 200
    body = page.content.decode()
    mine = row_of(body, "t.admin@example.test")
    assert 'aria-disabled="true"' in mine
    assert block_url(own) not in mine
    assert LAST_ADMINISTRATOR in html.unescape(body)
    theirs = row_of(body, "some.one@example.test")
    assert f'href="{block_url(other)}"' in theirs
    assert 'aria-disabled="true"' not in theirs

    seen = audit_ids()
    forged = block(admin, own, migrated_tenant)

    assert forged.status_code == 200
    assert LAST_ADMINISTRATOR in text_of(forged)
    own.refresh_from_db()
    assert own.state == "active"
    assert history_of(own) == []
    assert written_since(seen) == []
    with schema_context(None):
        assert not PlatformNotification.objects.exists()


def test_last_member_may_block_themselves(migrated_tenant: Any, member_of: Any) -> None:
    watchers = [platform_administrator(f"platform.{n}@example.test") for n in (1, 2)]
    admin, admin_user, own = member_of("t.admin@example.test", is_tenant_admin=True)
    seen = audit_ids()

    response = block(admin, own, migrated_tenant)

    assert response.status_code == 302
    assert response["Location"] == USERS
    own.refresh_from_db()
    assert own.state == "blocked"
    [row] = history_of(own)
    assert (row.before, row.after, row.by_id) == ("active", "blocked", admin_user.pk)
    assert [e.action for e in written_since(seen)].count("membership.blocked") == 1
    told = platform_notifications()
    assert sorted((n.user_id, n.event) for n in told) == sorted(
        (watcher.pk, "tenant_without_admin") for watcher in watchers
    )
    assert all(n.facts == {"tenant": migrated_tenant.number} for n in told)


def test_lift_restores_the_groups(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right, rights_on

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, someone, membership = member_of("some.one@example.test")
    read = new_document(admin_user, "Synthetic archive regulation")
    edited = new_document(admin_user, "Synthetic approval procedure")
    link_group(read, [Right.VIEW_PENDING], [membership], admin_user)
    link_group(edited, [Right.EDIT, Right.ACCEPT], [membership], admin_user)
    documents = (read, edited)
    with schema_context(migrated_tenant.number):
        before = {d.number: rights_on(someone, d) for d in documents}
    assert all(before.values())
    assert block(admin, membership, migrated_tenant).status_code == 302
    with schema_context(migrated_tenant.number):
        assert all(rights_on(someone, d) == frozenset() for d in documents)
    page = admin.get(USERS).content.decode()
    assert f'action="{lift_url(membership)}"' in row_of(page, "some.one@example.test")
    seen = audit_ids()

    response = admin.post(lift_url(membership))

    assert response.status_code == 302
    assert response["Location"] == USERS
    membership.refresh_from_db()
    assert membership.state == "active"
    lifted = history_of(membership)[-1]
    assert (lifted.field, lifted.before, lifted.after, lifted.by_id) == (
        "state",
        "blocked",
        "active",
        admin_user.pk,
    )
    with schema_context(migrated_tenant.number):
        assert {d.number: rights_on(someone, d) for d in documents} == before
    assert [e.action for e in written_since(seen)].count("membership.block_lifted") == 1


def test_self_block_is_drawn_nowhere_and_not_lifted_here(
    migrated_tenant: Any, member_of: Any
) -> None:
    from identity.models import User

    host = "docs.example.test"
    a_domain(migrated_tenant, host)
    admin, _, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, someone, membership = member_of("self.block@example.test")
    User.objects.filter(pk=someone.pk).update(self_blocked=True)
    someone.refresh_from_db()
    own_client = client_on(host, someone)

    row = row_of(admin.get(USERS).content.decode(), "self.block@example.test")
    assert "active" in row
    assert "blocked" not in row
    assert f'href="{block_url(membership)}"' in row
    assert 'aria-disabled="true"' not in row
    assert own_client.get("/").status_code == 404

    assert block(admin, membership, migrated_tenant).status_code == 302
    membership.refresh_from_db()
    assert membership.state == "blocked"
    assert own_client.get("/").status_code == 404

    assert admin.post(lift_url(membership)).status_code == 302
    membership.refresh_from_db()
    assert membership.state == "active"
    assert own_client.get("/").status_code == 404
    someone.refresh_from_db()
    assert someone.self_blocked is True


def test_blocked_here_active_elsewhere(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    first = migrated_tenant
    second = make_tenant_schema("Second Synthetic Org")
    a_domain(first, "first.example.test")
    a_domain(second, "second.example.test")
    admin, _, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, someone, in_first = member_of("some.one@example.test")
    member_elsewhere(second, someone)

    assert block(admin, in_first, first).status_code == 302

    assert client_on("first.example.test", someone).get("/").status_code == 404
    elsewhere = client_on("second.example.test", someone).get("/")
    assert elsewhere.status_code == 302
    assert elsewhere["Location"] == "/folder/1/"


def test_a_busy_document_refuses_the_block(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from documents.locks import document_lock

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, editor, membership = member_of("an.editor@example.test")
    document, hold = holding(
        migrated_tenant, new_document, link_group, admin_user, editor, membership
    )
    monkeypatch.setattr("editing.holds.LOCK_WAIT_SECONDS", 0.2)
    entered = threading.Event()
    answered = threading.Event()

    def commit_elsewhere() -> None:
        # Another request committing the document holds its writer lock until the block answers.
        try:
            with document_lock(migrated_tenant.number, document.number):
                entered.set()
                answered.wait(timeout=30)
        finally:
            connection.close()

    other = threading.Thread(target=commit_elsewhere)
    other.start()
    try:
        assert entered.wait(timeout=10)
        seen = audit_ids()
        response = block(admin, membership, migrated_tenant)
    finally:
        answered.set()
        other.join(timeout=30)

    assert response.status_code == 200
    assert BUSY in text_of(response)
    membership.refresh_from_db()
    assert membership.state == "active"
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.released_at is None
    assert history_of(membership) == []
    assert written_since(seen) == []


def test_block_and_lift_closed_to_members(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    from identity.models import User

    second = make_tenant_schema("Second Synthetic Org")
    admin, _, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    member, _, _ = member_of("a.member@example.test")
    _, _, target = member_of("some.one@example.test")
    stranger = User.objects.create_user("other.admin@example.test", PASSWORD)
    member_elsewhere(second, stranger, is_tenant_admin=True)
    outsider = Client(headers={"host": "127.0.0.1"})
    outsider.force_login(stranger)
    session = outsider.session
    session["tenant_number"] = second.number
    session.save()
    seen = audit_ids()

    for client in (member, outsider):
        for url in (block_url(target), lift_url(target)):
            assert client.get(url).status_code == 404, url
            posted = client.post(url, {"organisations": [str(migrated_tenant.number)]})
            assert posted.status_code == 404, url

    target.refresh_from_db()
    assert target.state == "active"
    assert history_of(target) == []
    assert written_since(seen) == []
    # The routes exist: the organisation's administrator is shown the confirmation, and the lift
    # route refuses a GET to everyone.
    assert admin.get(block_url(target)).status_code == 200
    assert admin.get(lift_url(target)).status_code == 404


def test_blocked_everywhere_is_active_nowhere(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    """A person blocked in every organisation they hold is not reported active elsewhere."""
    second = make_tenant_schema("Second Synthetic Org")
    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    member_elsewhere(second, admin_user, is_tenant_admin=True)
    _, someone, in_first = member_of("some.one@example.test")
    member_elsewhere(second, someone)
    platform_administrator("platform.1@example.test")

    assert block(admin, in_first, migrated_tenant, second).status_code == 302

    assert not [n for n in platform_notifications() if n.event == "user_partially_blocked"]


def test_a_forged_organisation_is_left_alone(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    from identity.models import Membership

    other = make_tenant_schema("Other Synthetic Org")
    admin, _, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, someone, in_first = member_of("some.one@example.test")
    in_other = member_elsewhere(other, someone)

    assert block(admin, in_first, migrated_tenant, other).status_code == 302

    assert Membership.objects.get(pk=in_first.pk).state == "blocked"
    assert Membership.objects.get(pk=in_other.pk).state == "active"


def test_a_platform_administrator_is_offered_every_organisation(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    other = make_tenant_schema("Other Synthetic Org")
    platform, _, _ = member_of("p.admin@example.test", is_platform_admin=True)
    _, someone, in_first = member_of("some.one@example.test")
    member_elsewhere(other, someone)

    body = text_of(platform.get(block_url(in_first)))

    assert organisation_boxes(body) == {str(migrated_tenant.number): True, str(other.number): False}


@pytest.mark.parametrize("other_self_blocked", [False, True])
def test_the_last_administrator_rule_reads_the_memberships_own_state(
    migrated_tenant: Any, member_of: Any, other_self_blocked: bool
) -> None:
    """A self-block shows through no control: the rule counts memberships by their own state, so
    another person's own block changes nothing an administrator can see or do (DL-0398)."""
    from identity.models import User

    admin, admin_user, mine = member_of("t.admin@example.test", is_tenant_admin=True)
    _, other_admin, _ = member_of("t.other@example.test", is_tenant_admin=True)
    member_of("a.member@example.test")
    if other_self_blocked:
        User.objects.filter(pk=other_admin.pk).update(self_blocked=True)

    page = text_of(admin.get(USERS))
    own_row = row_of(page, "t.admin@example.test")
    answer = block(admin, mine, migrated_tenant)

    assert 'aria-disabled="true"' not in own_row
    assert answer.status_code == 302


def test_a_blocked_administrator_blocks_nobody(migrated_tenant: Any, member_of: Any) -> None:
    """Two administrators blocking each other one after the other: the second, blocked by then,
    is refused (the rows are re-read under the block's own locks)."""
    from identity import blocking
    from identity.models import Membership

    _, first_user, first = member_of("t.first@example.test", is_tenant_admin=True)
    _, second_user, second = member_of("t.second@example.test", is_tenant_admin=True)

    blocking.block_membership(second, by=first_user)
    with pytest.raises(blocking.BlockRefused):
        blocking.block_membership(first, by=second_user)

    assert Membership.objects.get(pk=first.pk).state == "active"


def test_several_organisations_are_one_act(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    """The last administrator of the second organisation is among the chosen: nothing is
    blocked anywhere."""
    from identity.models import Membership

    second = make_tenant_schema("Second Synthetic Org")
    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    member_elsewhere(second, admin_user, is_tenant_admin=False)
    _, someone, in_first = member_of("some.one@example.test")
    member_elsewhere(second, someone, is_tenant_admin=True)
    member_elsewhere(second, platform_administrator("x.member@example.test"))
    from identity.models import User

    User.objects.filter(pk=admin_user.pk).update(is_platform_admin=True)

    answer = block(admin, in_first, migrated_tenant, second)

    assert answer.status_code == 200
    assert LAST_ADMINISTRATOR in text_of(answer)
    assert set(Membership.objects.filter(user=someone).values_list("state", flat=True)) == {
        "active"
    }


def test_a_failed_notification_keeps_the_block(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any, monkeypatch: Any
) -> None:
    from django.db import DatabaseError

    from identity.models import Membership

    other = make_tenant_schema("Other Synthetic Org")
    admin, _, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, someone, in_first = member_of("some.one@example.test")
    member_elsewhere(other, someone)
    platform_administrator("platform.1@example.test")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise DatabaseError("a synthetic failure")

    monkeypatch.setattr("notifications.services.notify_platform", fail)

    assert block(admin, in_first, migrated_tenant).status_code == 302
    assert Membership.objects.get(pk=in_first.pk).state == "blocked"


def test_a_block_ends_the_organisations_open_invitations(
    migrated_tenant: Any, member_of: Any, invited: Any
) -> None:
    from identity.models import Membership

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    member_of("a.member@example.test")
    token = invited(migrated_tenant, "new.person@example.test", by=admin_user)
    membership = Membership.objects.get(user__email="new.person@example.test")

    assert block(admin, membership, migrated_tenant).status_code == 302

    assert Client(headers={"host": "127.0.0.1"}).get(f"/invitation/{token}/").status_code == 404


def test_a_hold_cannot_be_taken_while_a_block_is_written(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """The block holds the membership's row until it commits; a take waits for it and then sees
    the membership blocked (DL-0256: no hold survives a block)."""
    import threading

    from django.db import connection, transaction

    from access.rights import Right
    from editing import holds
    from identity.models import Membership

    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, editor, membership = member_of("the.editor@example.test")
    document = new_document(admin_user, "Synthetic leave procedure")
    link_group(document, [Right.EDIT], [membership], admin_user)
    locked = threading.Event()
    release = threading.Event()

    def blocking_in_progress() -> None:
        try:
            with transaction.atomic():
                row = Membership.objects.select_for_update().get(pk=membership.pk)
                row.change("state", "blocked", by=admin_user)
                locked.set()
                release.wait(timeout=30)
        finally:
            connection.close()

    other = threading.Thread(target=blocking_in_progress)
    other.start()
    assert locked.wait(timeout=30)
    outcome: list[Any] = []

    def take() -> None:
        try:
            with schema_context(migrated_tenant.number):
                outcome.append(holds.take(document, editor))
        except holds.NotEditable as refused:
            outcome.append(refused)
        finally:
            connection.close()

    taker = threading.Thread(target=take)
    taker.start()
    taker.join(timeout=1)
    still_waiting = taker.is_alive()
    release.set()
    other.join(timeout=30)
    taker.join(timeout=30)

    assert still_waiting
    assert len(outcome) == 1 and isinstance(outcome[0], holds.NotEditable)


def test_a_block_waits_for_no_take_and_no_write_naming_the_person(
    migrated_tenant: Any, member_of: Any
) -> None:
    """A take in flight shares the organisation's row, and a write naming the person — an audit
    row — shares theirs: a membership's block locks its own rows alone, so it waits on neither."""
    import threading

    from django.db import connection, transaction

    from identity import blocking
    from identity.models import Membership

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    _, someone, membership = member_of("some.one@example.test")
    holding, release = threading.Event(), threading.Event()

    def share_the_rows() -> None:
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM tenancy_tenant WHERE number = %s FOR SHARE",
                    [migrated_tenant.number],
                )
                cursor.execute("SELECT 1 FROM identity_user WHERE id = %s FOR SHARE", [someone.pk])
                holding.set()
                release.wait(timeout=30)
        finally:
            connection.close()

    other = threading.Thread(target=share_the_rows)
    other.start()
    assert holding.wait(timeout=30)
    done: list[bool] = []

    def block_now() -> None:
        try:
            blocking.block_membership(membership, by=admin_user)
            done.append(True)
        finally:
            connection.close()

    blocker = threading.Thread(target=block_now)
    blocker.start()
    blocker.join(timeout=5)
    finished_while_shared = not blocker.is_alive()
    release.set()
    other.join(timeout=30)
    blocker.join(timeout=30)

    assert finished_while_shared and done == [True]
    assert Membership.objects.get(pk=membership.pk).state == "blocked"


def test_no_invitation_into_a_blocked_organisation(
    migrated_tenant: Any, member_of: Any, sending_address: Any
) -> None:
    from identity.models import Invitation
    from tenancy.models import Tenant

    platform, _, _ = member_of("p.admin@example.test", is_platform_admin=True)
    sending_address(migrated_tenant.number)
    Tenant.objects.filter(pk=migrated_tenant.pk).update(state="blocked")

    answer = platform.post(
        "/administration/tenant/users/invite/", {"email": "new.person@example.test"}
    )

    assert answer.status_code == 200
    assert "The invitation could not be sent." in text_of(answer)
    assert not Invitation.objects.exists()


@pytest.mark.parametrize("lost_by", ["revoked", "self_blocked", "erased"])
def test_a_platform_role_lost_before_the_act_blocks_and_lifts_nothing(
    migrated_tenant: Any, member_of: Any, lost_by: str
) -> None:
    """The actor's platform role is read again inside the act: one revoked, self-blocked or erased
    since the request loaded its user refuses the block and the lift, and nothing is written."""
    from identity import blocking
    from identity.models import Membership, User

    member_of("t.admin@example.test", is_tenant_admin=True)
    _, _, active = member_of("still.active@example.test")
    _, _, blocked = member_of("already.blocked@example.test")
    Membership.objects.filter(pk=blocked.pk).update(state="blocked")
    stale = platform_administrator("p.stale@example.test")
    platform_administrator("p.other@example.test")
    lost = {
        "revoked": {"is_platform_admin": False},
        "self_blocked": {"self_blocked": True},
        "erased": {"is_tombstoned": True},
    }[lost_by]
    User.objects.filter(pk=stale.pk).update(**lost)
    seen = audit_ids()
    before = history_of(active, blocked)

    for act, membership in (
        (blocking.block_membership, active),
        (blocking.lift_membership_block, blocked),
    ):
        with pytest.raises(blocking.BlockRefused) as refused:
            act(membership, by=stale)
        assert refused.value.reason == "not_administrator"

    assert Membership.objects.get(pk=active.pk).state == "active"
    assert Membership.objects.get(pk=blocked.pk).state == "blocked"
    assert history_of(active, blocked) == before
    assert written_since(seen) == []
    assert platform_notifications() == []

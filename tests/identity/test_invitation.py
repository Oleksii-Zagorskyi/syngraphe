"""Inviting a person into an organisation (ST-0003, ST-0054, ASR-17): a new address and one already
registered elsewhere draw the same page, the same email and audit events that name no address;
without a sending address, or for a membership the organisation blocked, nothing is written; a
person's own block is no refusal; inviting again sends again; the act is one transaction, and
joining its groups is told in the application without an email of its own (DL-0399).

People, organisations, groups and texts are synthetic examples; every address ends in
`@example.test`.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
    pytest.mark.usefixtures("in_english"),
]

INVITE = "/administration/tenant/users/invite/"
# The addresses compared are of one length, so the masked bodies keep one Content-Length.
NEW = "new.person@example.test"
KNOWN = "old.person@example.test"
SELF_BLOCKED = "self.block@example.test"
INVITATION_LINK = r"https?://[^/\s]+/invitation/[A-Za-z0-9_-]{43}/"
SENT = "An invitation to {address} is queued for sending."
REFUSED = "The invitation could not be sent."


def a_group(tenant: Any, by: Any, name: str = "Synthetic readers") -> Any:
    from access.models import AccessGroup

    with schema_context(tenant.number):
        return AccessGroup.objects.create(name=name, created_by=by, actor_kind="user")


def invite_by_form(client: Client, email: str, *groups: Any) -> Any:
    return client.post(INVITE, {"email": email, "groups": [str(g.id) for g in groups]})


def audit_ids() -> set[Any]:
    from audit.models import AuditEvent

    return set(AuditEvent.objects.values_list("id", flat=True))


def written_since(seen: set[Any]) -> list[Any]:
    from audit.models import AuditEvent

    return list(AuditEvent.objects.exclude(id__in=seen))


def names_an_address(event: Any) -> bool:
    return "@" in json.dumps(event.after, default=str) or "@" in json.dumps(
        event.before, default=str
    )


def counts(tenant: Any) -> dict[str, int]:
    """Every table the invitation writes, shared and in the organisation's schema."""
    from access.models import AccessChange, GroupMember
    from audit.models import AuditEvent
    from identity.models import Invitation, Membership, User
    from mail.models import EmailOutbox
    from notifications.models import Notification

    found = {
        "users": User.objects.count(),
        "memberships": Membership.objects.count(),
        "invitations": Invitation.objects.count(),
        "audit": AuditEvent.objects.count(),
    }
    with schema_context(None):
        found["shared outbox"] = EmailOutbox.objects.count()
    with schema_context(tenant.number):
        found["group members"] = GroupMember.objects.count()
        found["access changes"] = AccessChange.objects.count()
        found["outbox"] = EmailOutbox.objects.count()
        found["notifications"] = Notification.objects.count()
    return found


def test_new_and_existing_addresses_are_indistinguishable(
    migrated_tenant: Any,
    member_of: Any,
    person: Any,
    sending_address: Any,
    masked: Any,
    masked_text: Any,
    outbox: Any,
) -> None:
    from identity.models import Membership

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    sending_address(migrated_tenant.number)
    group = a_group(migrated_tenant, admin_user)
    person(KNOWN, "Another Synthetic Org")
    seen = audit_ids()

    new = invite_by_form(admin, NEW, group)
    known = invite_by_form(admin, KNOWN, group)

    assert new.status_code == 200
    assert SENT.format(address=NEW) in new.content.decode()
    assert masked(new, NEW) == masked(known, KNOWN)

    joined_new = Membership.objects.get(tenant=migrated_tenant, user__email=NEW)
    joined_known = Membership.objects.get(tenant=migrated_tenant, user__email=KNOWN)
    assert abs((joined_new.granted_at - joined_known.granted_at).total_seconds()) < 1

    rows = outbox(migrated_tenant.number)
    [to_new] = [row for row in rows if row.recipient == NEW]
    [to_known] = [row for row in rows if row.recipient == KNOWN]
    assert len(rows) == 2
    for field in ("sender", "subject", "status", "tenant_id"):
        assert getattr(to_new, field) == getattr(to_known, field), field
    assert masked_text(to_new.body, NEW) == masked_text(to_known.body, KNOWN)
    assert len(re.findall(INVITATION_LINK, to_new.body)) == 1

    events = written_since(seen)
    assert len([e for e in events if e.action == "invitation.sent"]) == 2
    assert [e.action for e in events if names_an_address(e)] == []


def test_refused_without_a_sender(
    migrated_tenant: Any,
    member_of: Any,
    person: Any,
    no_sending_address: Any,
    masked: Any,
) -> None:
    from identity.models import User

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    no_sending_address(migrated_tenant.number)
    group = a_group(migrated_tenant, admin_user)
    person(KNOWN, "Another Synthetic Org")
    before = counts(migrated_tenant)

    new = invite_by_form(admin, NEW, group)
    known = invite_by_form(admin, KNOWN, group)

    for response in (new, known):
        assert response.status_code == 200
        assert REFUSED in response.content.decode()
    assert masked(new, NEW) == masked(known, KNOWN)
    assert counts(migrated_tenant) == before
    assert not User.objects.filter(email=NEW).exists()


def test_self_blocked_as_anyone_blocked_membership_refused_and_resend(
    migrated_tenant: Any,
    member_of: Any,
    person: Any,
    sending_address: Any,
    masked: Any,
    outbox: Any,
) -> None:
    from identity.models import Invitation, Membership, MembershipState

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    sending_address(migrated_tenant.number)
    group = a_group(migrated_tenant, admin_user)

    # (a) A person who blocked their own account is invited as anyone is.
    person(SELF_BLOCKED, "Another Synthetic Org", self_blocked=True)
    seen = audit_ids()
    self_blocked = invite_by_form(admin, SELF_BLOCKED, group)
    new = invite_by_form(admin, NEW, group)

    assert masked(self_blocked, SELF_BLOCKED) == masked(new, NEW)
    joined = Membership.objects.get(tenant=migrated_tenant, user__email=SELF_BLOCKED)
    assert joined.state == MembershipState.ACTIVE
    assert len([r for r in outbox(migrated_tenant.number) if r.recipient == SELF_BLOCKED]) == 1
    assert [e.action for e in written_since(seen) if names_an_address(e)] == []

    # (b) A membership this organisation blocked is refused, and nothing is written.
    _, _, blocked = member_of("blocked.one@example.test")
    blocked.change("state", MembershipState.BLOCKED, by=admin_user)
    blocked.refresh_from_db()
    before = counts(migrated_tenant)

    refused = invite_by_form(admin, "blocked.one@example.test", group)

    assert refused.status_code == 200
    assert REFUSED in refused.content.decode()
    assert counts(migrated_tenant) == before
    assert not Invitation.objects.filter(email="blocked.one@example.test").exists()
    again = Membership.objects.get(pk=blocked.pk)
    assert (again.state, again.granted_at, again.is_tenant_admin, again.updated_at) == (
        blocked.state,
        blocked.granted_at,
        blocked.is_tenant_admin,
        blocked.updated_at,
    )

    # (c) An active member invited again: a second invitation and a second email, one membership.
    _, _, member = member_of("again.here@example.test")
    first = invite_by_form(admin, "again.here@example.test", group)
    second = invite_by_form(admin, "again.here@example.test", group)

    assert first.status_code == second.status_code == 200
    assert Invitation.objects.filter(email="again.here@example.test").count() == 2
    to_member = [
        r for r in outbox(migrated_tenant.number) if r.recipient == "again.here@example.test"
    ]
    assert len(to_member) == 2
    [still] = Membership.objects.filter(
        tenant=migrated_tenant, user__email="again.here@example.test"
    )
    assert still.pk == member.pk and still.granted_at == member.granted_at


@pytest.mark.crash
@pytest.mark.parametrize("stop", ["invitation", "queue"])
def test_invite_is_one_transaction(
    migrated_tenant: Any, member_of: Any, sending_address: Any, monkeypatch: Any, stop: str
) -> None:
    """Stopped after the person, the membership and the group — at the invitation row, or at the
    queue after it — the invitation leaves nothing, its audit events included."""
    from identity import invitations
    from identity.models import User

    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    sending_address(migrated_tenant.number)
    group = a_group(migrated_tenant, admin_user)
    before = counts(migrated_tenant)

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("a synthetic failure")

    target = "identity.models.Invitation.save" if stop == "invitation" else "mail.services.queue"
    monkeypatch.setattr(target, refuse)
    with schema_context(migrated_tenant.number), pytest.raises(RuntimeError):
        invitations.invite(migrated_tenant, NEW, [group], by=admin_user)

    assert not User.objects.filter(email=NEW).exists()
    assert counts(migrated_tenant) == before


def test_invite_refuses_outside_the_organisations_schema(
    migrated_tenant: Any, member_of: Any, sending_address: Any
) -> None:
    from identity import invitations

    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    sending_address(None)
    before = counts(migrated_tenant)

    with pytest.raises(RuntimeError):
        invitations.invite(migrated_tenant, NEW, [], by=admin_user)

    assert counts(migrated_tenant) == before


def test_groups_tell_in_the_application_without_email(
    migrated_tenant: Any, member_of: Any, sending_address: Any, outbox: Any
) -> None:
    from identity.models import User
    from notifications.models import Notification

    admin, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    sending_address(migrated_tenant.number)
    readers = a_group(migrated_tenant, admin_user, "Synthetic readers")
    editors = a_group(migrated_tenant, admin_user, "Synthetic editors")

    response = invite_by_form(admin, NEW, readers, editors)

    assert response.status_code == 200
    invitee = User.objects.get(email=NEW)
    with schema_context(migrated_tenant.number):
        told = Notification.objects.filter(user=invitee, event="access_granted")
        assert told.count() == 2
    [row] = outbox(migrated_tenant.number)
    assert row.recipient == NEW
    assert len(re.findall(INVITATION_LINK, row.body)) == 1

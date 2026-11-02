"""Accepting an invitation (ST-0003, ST-0054): a valid link sets the password, signs the person in
with the inviting organisation chosen and is spent; an expired, unknown or used link answers as a
page that does not exist; the password rule applies and a refused password leaves the link valid.

People, organisations, groups and texts are synthetic examples; every address ends in
`@example.test`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
    pytest.mark.usefixtures("in_english"),
]

PLATFORM = "127.0.0.1"
PASSWORD = "Tr4vel-Plan-Ok"


def link(token: str) -> str:
    return f"/invitation/{token}/"


def choose(password: str, again: str | None = None) -> dict[str, str]:
    return {"password": password, "password_again": password if again is None else again}


def test_accept_sets_password_signs_in_and_spends_the_token(
    migrated_tenant: Any, member_of: Any, invited: Any
) -> None:
    from identity.models import Invitation, User

    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    token = invited(migrated_tenant, "new.person@example.test", by=admin_user)
    client = Client(headers={"host": PLATFORM})

    page = client.get(link(token))
    done = client.post(link(token), choose(PASSWORD))

    assert page.status_code == 200
    body = page.content.decode()
    assert 'name="password"' in body and 'name="password_again"' in body
    assert done.status_code == 302 and done["Location"] == "/"
    invitee = User.objects.get(email="new.person@example.test")
    assert invitee.check_password(PASSWORD)
    assert client.session["_auth_user_id"] == str(invitee.id)
    assert client.session["tenant_number"] == migrated_tenant.number
    assert Invitation.objects.get(email="new.person@example.test").accepted_at is not None
    assert client.get(link(token)).status_code == 404


def test_bad_tokens_answer_as_a_missing_page(
    migrated_tenant: Any, member_of: Any, invited: Any, masked: Any
) -> None:
    from identity.models import Invitation
    from identity.tokens import new_token

    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    expired = invited(migrated_tenant, "late.person@example.test", by=admin_user)
    Invitation.objects.filter(email="late.person@example.test").update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    used = invited(migrated_tenant, "used.person@example.test", by=admin_user)
    Invitation.objects.filter(email="used.person@example.test").update(accepted_at=timezone.now())
    unknown = new_token()
    client = Client(headers={"host": PLATFORM})

    missing = masked(client.get("/no-such-page/"))

    assert missing[0] == 404
    for name, token in (("expired", expired), ("unknown", unknown), ("used", used)):
        assert masked(client.get(link(token))) == missing, name
        assert masked(client.post(link(token), choose(PASSWORD))) == missing, name
    assert "_auth_user_id" not in client.session


def test_password_rule_applies(migrated_tenant: Any, member_of: Any, invited: Any) -> None:
    from identity.models import Invitation, User

    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    email = "first.invitee@example.test"
    token = invited(migrated_tenant, email, by=admin_user)
    client = Client(headers={"host": PLATFORM})

    no_digit = client.post(link(token), choose("Travel-Plan-Okay!"))
    similar = client.post(link(token), choose("First.invitee@example1"))
    differ = client.post(link(token), choose(PASSWORD, "Tr4vel-Plan-Ok2"))

    for name, response in (("no digit", no_digit), ("similar", similar), ("differ", differ)):
        assert response.status_code == 200, name
        assert 'name="password"' in response.content.decode(), name
        assert response.context["form"].errors, name
    assert not User.objects.get(email=email).has_usable_password()
    assert Invitation.objects.get(email=email).accepted_at is None
    assert "_auth_user_id" not in client.session
    assert client.get(link(token)).status_code == 200


def test_a_fresh_invitation_ends_the_earlier_link(
    migrated_tenant: Any, member_of: Any, invited: Any
) -> None:
    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    earlier = invited(migrated_tenant, "new.person@example.test", by=admin_user)
    fresh = invited(migrated_tenant, "new.person@example.test", by=admin_user)
    client = Client(headers={"host": PLATFORM})

    assert client.get(link(earlier)).status_code == 404
    assert client.post(link(earlier), choose(PASSWORD)).status_code == 404
    assert client.get(link(fresh)).status_code == 200


def test_accepting_one_link_spends_every_other(
    migrated_tenant: Any, member_of: Any, invited: Any, make_tenant_schema: Any
) -> None:
    from identity.models import User

    other = make_tenant_schema("Another Synthetic Org")
    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    here = invited(migrated_tenant, "new.person@example.test", by=admin_user)
    there = invited(other, "new.person@example.test", by=admin_user)

    accepted = Client(headers={"host": PLATFORM}).post(link(here), choose(PASSWORD))
    stranger = Client(headers={"host": PLATFORM})

    assert accepted.status_code == 302
    assert stranger.get(link(there)).status_code == 404
    assert stranger.post(link(there), choose("An0ther-Plan-Ok")).status_code == 404
    assert User.objects.get(email="new.person@example.test").check_password(PASSWORD)


def test_the_session_names_the_inviting_organisation(
    migrated_tenant: Any, member_of: Any, invited: Any, make_tenant_schema: Any
) -> None:
    """A person active in another organisation already: sign-in would choose neither, the link
    chooses the organisation it came from."""
    from identity.models import Membership, User

    other = make_tenant_schema("Another Synthetic Org")
    both = User.objects.create_user("both.places@example.test", "test-only-not-a-password")
    Membership.objects.create(tenant=other, user=both, actor_kind="system")
    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    token = invited(migrated_tenant, "both.places@example.test", by=admin_user)
    client = Client(headers={"host": PLATFORM})

    assert client.post(link(token), choose(PASSWORD)).status_code == 302
    assert client.session["tenant_number"] == migrated_tenant.number


@pytest.mark.crash
def test_accepting_is_one_transaction(
    migrated_tenant: Any, member_of: Any, invited: Any, monkeypatch: Any
) -> None:
    from audit import record as audit_record
    from identity import invitations
    from identity.models import Invitation, User

    _, admin_user, _ = member_of("t.admin@example.test", is_tenant_admin=True)
    token = invited(migrated_tenant, "new.person@example.test", by=admin_user)
    original = audit_record.record

    def stop(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("action") == "invitation.accepted":
            raise RuntimeError("a synthetic failure")
        return original(*args, **kwargs)

    monkeypatch.setattr("identity.invitations.record", stop)
    with pytest.raises(RuntimeError):
        invitations.accept(token, PASSWORD)

    assert not User.objects.get(email="new.person@example.test").has_usable_password()
    assert Invitation.objects.get().accepted_at is None
    assert invitations.person_of(token) is not None


def test_the_invitation_is_in_the_default_and_its_page_in_the_persons_language(
    migrated_tenant: Any, member_of: Any, invited: Any
) -> None:
    """An invitation goes in the installation's default, whoever it reaches — an administrator
    reads the outbox (ASR-17); the page its link opens speaks the person's own language
    (DL-0501)."""
    from identity.models import User
    from identity.views.preferences import _keep
    from mail.models import EmailOutbox
    from tenancy.schemas import schema_context

    _, admin, _ = member_of("an.inviter@example.test", is_tenant_admin=True)
    known = User.objects.create_user("known.elsewhere@example.test", "test-only-not-a-password")
    _keep(known, "language", "uk")

    token = invited(migrated_tenant, "known.elsewhere@example.test", by=admin)

    with schema_context(migrated_tenant.number):
        row = EmailOutbox.objects.filter(recipient="known.elsewhere@example.test").latest(
            "created_at"
        )
    assert row.subject.startswith("Invitation to ")
    page = Client(headers={"host": "127.0.0.1"}).get(f"/invitation/{token}/").content.decode()
    assert '<html lang="uk">' in page

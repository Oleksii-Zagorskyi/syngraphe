"""`create_member`: a person and an active membership by an operator's command, the password
generated and printed once (ST-0073, DL-0343)."""

from __future__ import annotations

import string
from io import StringIO
from typing import Any

import pytest
from django.core.management import CommandError, call_command
from django.test import Client

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

SPECIAL = set(string.punctuation)


def tenant(name: str = "Example Org", state: str = "active") -> Any:
    from tenancy.models import Tenant

    return Tenant.objects.create(name=name, state=state, actor_kind="system")


def run(**options: Any) -> str:
    out = StringIO()
    call_command("create_member", stdout=out, **options)
    return out.getvalue()


def password_of(output: str) -> str:
    lines = [line for line in output.splitlines() if line.startswith("password: ")]
    assert len(lines) == 1
    return lines[0].removeprefix("password: ")


def test_creates_user_and_membership() -> None:
    from audit.models import AuditEvent
    from identity.models import Membership, User

    org = tenant()
    output = run(tenant=org.number, email="Reader@Example.test", name="Reader One")
    password = password_of(output)

    user = User.objects.get()
    assert user.email == "reader@example.test" and user.display_name == "Reader One"
    membership = Membership.objects.get(user=user)
    assert membership.tenant == org and membership.state == "active"
    assert not membership.is_tenant_admin
    events = {
        e.action: e
        for e in AuditEvent.objects.filter(action__in=["user.created", "membership.created"])
    }
    assert set(events) == {"user.created", "membership.created"}
    assert all(e.actor_kind == "system" for e in events.values())
    assert all(password not in repr((e.before, e.after)) for e in AuditEvent.objects.all())
    # The address is personal data the audit log could never erase (DL-0108): the person is
    # named by id; a person's creation is the platform's event, not the organisation's.
    assert all("example.test" not in repr((e.before, e.after)) for e in AuditEvent.objects.all())
    assert events["user.created"].after == {"user": str(user.pk)}
    assert events["user.created"].tenant_id is None
    assert events["membership.created"].tenant_id == org.pk


def test_password_passes_and_signs_in(client: Client) -> None:
    from django.contrib.auth.password_validation import validate_password

    from identity.models import User

    org = tenant()
    password = password_of(run(tenant=org.number, email="reader@example.test"))
    user = User.objects.get()
    validate_password(password, user)
    response = client.post("/signin/", {"email": "reader@example.test", "password": password})
    assert response.status_code == 302 and client.session["_auth_user_id"] == str(user.id)


def test_generator_classes() -> None:
    from identity.generated import password

    for _ in range(200):
        drawn = password()
        assert len(drawn) == 20
        assert all(c in string.printable and not c.isspace() for c in drawn)
        assert any(c.isupper() for c in drawn) and any(c.islower() for c in drawn)
        assert any(c.isdigit() for c in drawn) and any(c in SPECIAL for c in drawn)


def test_rerun_changes_nothing() -> None:
    from identity.models import Membership, User

    org = tenant()
    run(tenant=org.number, email="reader@example.test")
    hashed = User.objects.get().password
    output = run(tenant=org.number, email="READER@example.test")
    assert User.objects.count() == 1 and Membership.objects.count() == 1
    assert User.objects.get().password == hashed
    assert "password:" not in output and "already a member" in output


def test_existing_user_gets_membership_only() -> None:
    from identity.models import Membership, User

    first, second = tenant("One"), tenant("Two")
    run(tenant=first.number, email="reader@example.test")
    hashed = User.objects.get().password
    output = run(tenant=second.number, email="reader@example.test")
    assert Membership.objects.filter(tenant=second).count() == 1
    assert User.objects.get().password == hashed
    assert "already registered; password unchanged" in output and "password:" not in output


def test_refusals_write_nothing() -> None:
    from identity.models import Membership, User

    org = tenant()
    with pytest.raises(CommandError, match="no active tenant"):
        run(tenant=9999, email="a@example.test")
    with pytest.raises(CommandError, match="not an address"):
        run(tenant=org.number, email="not-an-address")
    blocked = User.objects.create_user("blocked@example.test", None)
    Membership.objects.create(tenant=org, user=blocked, state="blocked", actor_kind="system")
    with pytest.raises(CommandError, match="blocked"):
        run(tenant=org.number, email="blocked@example.test")
    User.objects.create_user("self@example.test", None, self_blocked=True)
    with pytest.raises(CommandError, match="self-blocked"):
        run(tenant=org.number, email="self@example.test")
    User.objects.create_user("gone@example.test", None, is_tombstoned=True)
    with pytest.raises(CommandError, match="tombstoned"):
        run(tenant=org.number, email="gone@example.test")
    assert User.objects.count() == 3 and Membership.objects.count() == 1
    assert Membership.objects.get().user == blocked


def test_generator_gives_up_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    from django.core.exceptions import ValidationError

    from identity.models import User

    org = tenant()

    def refuse(password: str, user: Any = None) -> None:
        raise ValidationError("refused")

    monkeypatch.setattr("identity.management.commands.create_member.validate_password", refuse)
    with pytest.raises(CommandError, match="password"):
        run(tenant=org.number, email="reader@example.test")
    assert not User.objects.exists()


@pytest.mark.parametrize("state", ["blocked", "migrating"])
def test_inactive_tenant_refused(state: str) -> None:
    from identity.models import Membership, User

    org = tenant(state=state)
    with pytest.raises(CommandError, match="no active tenant"):
        run(tenant=org.number, email="reader@example.test")
    assert not User.objects.exists() and not Membership.objects.exists()

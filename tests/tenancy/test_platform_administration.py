"""Platform administration granted and revoked (ST-0002, ADR-0007, DL-0315): a platform
administrator grants the role to a registered person by address and revokes it per row, each act
audited by ids; the last platform administrator never loses the role — the act is drawn disabled
with its reason, and a forged request is refused.

People are synthetic examples; every address ends in `@example.test`."""

from __future__ import annotations

import json
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

PAGE = "/administration/platform/administrators/"
GRANT = PAGE + "grant/"
LAST = "The last platform administrator keeps the role."


def _revoke(user: Any) -> str:
    return f"{PAGE}{user.pk}/revoke/"


def test_grant_and_revoke(platform_admin: Any, settings: Any) -> None:
    from audit.models import AuditEvent
    from identity.models import User

    settings.LANGUAGE_CODE = "en"
    client, me = platform_admin()
    User.objects.create_user("second.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True)
    person = User.objects.create_user("a.person@example.test", "Tr4vel-Plan-Ok")

    granted = client.post(GRANT, {"email": "A.Person@example.test "})
    after_grant = set(User.objects.filter(is_platform_admin=True).values_list("email", flat=True))
    revoked = client.post(_revoke(person))
    after_revoke = set(User.objects.filter(is_platform_admin=True).values_list("email", flat=True))

    assert granted.status_code == 302 and granted["Location"] == PAGE
    assert revoked.status_code == 302 and revoked["Location"] == PAGE
    assert after_grant == {me.email, "second.admin@example.test", "a.person@example.test"}
    assert after_revoke == {me.email, "second.admin@example.test"}
    events = {
        event.action: event
        for event in AuditEvent.objects.filter(action__startswith="platform.administration_")
    }
    assert set(events) == {"platform.administration_granted", "platform.administration_revoked"}
    for event in events.values():
        assert event.actor_id == me.pk and event.object_id == person.pk
        assert "@" not in json.dumps([event.before, event.after], default=str)


def test_the_last_cannot_lose_the_role(platform_admin: Any, settings: Any) -> None:
    from identity.models import User

    settings.LANGUAGE_CODE = "en"
    client, me = platform_admin()
    # A self-blocked and an erased administrator do not count (DL-0308, DL-0315).
    User.objects.create_user(
        "self.blocked@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True, self_blocked=True
    )
    User.objects.create_user(
        "former.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True, is_tombstoned=True
    )

    page = client.get(PAGE).content.decode()
    forged = client.post(_revoke(me))

    # The person's row in the list, not the shell's own line with their address.
    mine = page.split("<tbody>", 1)[1].split(me.email, 1)[1].split("</tr>", 1)[0]
    assert 'aria-disabled="true"' in mine and LAST in page
    assert f'action="{_revoke(me)}"' not in page
    assert forged.status_code == 404
    me.refresh_from_db()
    assert me.is_platform_admin


def test_grant_needs_a_registered_person(platform_admin: Any, settings: Any) -> None:
    from audit.models import AuditEvent
    from identity.models import User

    settings.LANGUAGE_CODE = "en"
    client, _ = platform_admin()
    User.objects.create_user("self.blocked@example.test", "Tr4vel-Plan-Ok", self_blocked=True)

    unknown = client.post(GRANT, {"email": "nobody.here@example.test"})
    blocked = client.post(GRANT, {"email": "self.blocked@example.test"})

    assert unknown.status_code == blocked.status_code == 200
    assert "No registered person has this address." in unknown.content.decode()
    # A platform page may say why: the account is the person's own to have closed.
    assert "has blocked their own account" in blocked.content.decode()
    assert User.objects.filter(is_platform_admin=True).count() == 1
    assert not AuditEvent.objects.filter(action__startswith="platform.administration_").exists()


def test_closed_to_everyone_else(make_tenant_schema: Any) -> None:
    from django.test import Client

    from identity.models import Membership, User

    tenant = make_tenant_schema("Synthetic organisation")
    admin = User.objects.create_user("t.admin@example.test", "Tr4vel-Plan-Ok")
    Membership.objects.create(tenant=tenant, user=admin, is_tenant_admin=True, actor_kind="system")
    platform = User.objects.create_user(
        "p.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True
    )
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(admin)

    assert client.post(GRANT, {"email": "t.admin@example.test"}).status_code == 404
    assert client.post(_revoke(platform)).status_code == 404
    admin.refresh_from_db()
    assert not admin.is_platform_admin


def test_an_act_whose_actor_lost_the_role_is_refused(platform_admin: Any, settings: Any) -> None:
    """The role is read again inside each act's transaction: one taken back since the request
    began refuses the act, and nothing is written."""
    from audit.models import AuditEvent
    from identity.models import User
    from tenancy import services

    settings.LANGUAGE_CODE = "en"
    _, me = platform_admin()
    other = User.objects.create_user(
        "second.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True
    )
    person = User.objects.create_user("a.person@example.test", "Tr4vel-Plan-Ok")
    User.objects.filter(pk=me.pk).update(is_platform_admin=False)
    audited = AuditEvent.objects.count()

    for act in (
        lambda: services.grant_platform_administration(person, by=me),
        lambda: services.revoke_platform_administration(other, by=me),
    ):
        with pytest.raises(services.Refused) as refused:
            act()
        assert str(refused.value) == "You no longer administer the platform."

    assert not User.objects.get(pk=person.pk).is_platform_admin
    assert User.objects.get(pk=other.pk).is_platform_admin
    assert AuditEvent.objects.count() == audited


def test_a_holder_who_blocked_their_own_account_is_marked(
    platform_admin: Any, settings: Any
) -> None:
    """Such a holder is listed, marked, and not counted among the platform's administrators."""
    from identity.models import User

    settings.LANGUAGE_CODE = "en"
    client, _ = platform_admin()
    User.objects.create_user(
        "away.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True, self_blocked=True
    )

    page = client.get(PAGE).content.decode()

    row = page.split("away.admin@example.test", 1)[1].split("</tr>", 1)[0]
    assert "blocked their own account" in row
    # The one holder who counts is the last, whose *revoke* is drawn disabled.
    assert LAST in page

"""Appointing an organisation's administrator (an organisation left without one is given one —
the data model's prose on blocking, DL-0367): a platform administrator makes an
active member of an active organisation its administrator, with the membership's history row and
the act audited; an address that is not an active member is refused, naming the field.

People and organisations are synthetic examples; every address ends in `@example.test`."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/platform/tenants/"


def test_appoint_an_active_member(migrated_tenant: Any, member_of: Any, settings: Any) -> None:
    from audit.models import AuditEvent
    from identity.models import Membership, MembershipHistory, User

    settings.LANGUAGE_CODE = "en"
    _, member, membership = member_of("m.synthetic@example.test")
    User.objects.create_user("outside@example.test", "Tr4vel-Plan-Ok")
    admin = User.objects.create_user(
        "p.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True
    )
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(admin)
    url = f"{PAGE}{migrated_tenant.number}/appoint/"

    form = client.get(url)
    appointed = client.post(url, {"email": "M.Synthetic@example.test"})
    refused = client.post(url, {"email": "outside@example.test"})

    assert form.status_code == 200
    assert appointed.status_code == 302 and appointed["Location"] == PAGE
    assert Membership.objects.get(pk=membership.pk).is_tenant_admin
    [history] = MembershipHistory.objects.filter(membership=membership, field="is_tenant_admin")
    assert (history.before, history.after, history.by_id) == ("False", "True", admin.pk)
    [event] = AuditEvent.objects.filter(action="membership.administrator_appointed")
    assert event.actor_id == admin.pk and event.object_id == membership.pk
    assert refused.status_code == 200
    assert "No active member of this organisation has this address." in refused.content.decode()
    assert not Membership.objects.filter(user__email="outside@example.test").exists()


def test_appoint_reads_the_membership_again(migrated_tenant: Any, member_of: Any) -> None:
    """A membership blocked between the form's check and the act is not appointed."""
    from identity.models import Membership, MembershipHistory, User
    from tenancy import services

    _, member, membership = member_of("m.synthetic@example.test")
    admin = User.objects.create_user(
        "p.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True
    )
    stale = Membership.objects.get(pk=membership.pk)
    membership.change("state", "blocked", by=admin)

    appointed = services.appoint_administrator(migrated_tenant, stale, by=admin)

    assert appointed is False
    assert not Membership.objects.get(pk=membership.pk).is_tenant_admin
    assert not MembershipHistory.objects.filter(
        membership=membership, field="is_tenant_admin"
    ).exists()

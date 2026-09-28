"""`audit.record()` writes one event with actor, kind, action, object, before and after."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_record_writes_one_event() -> None:
    from audit import record
    from audit.models import AuditEvent
    from identity.models import User
    from tenancy.models import Tenant

    actor = User.objects.create_user("a.person@example.test", "test-only-not-a-password")
    tenant = Tenant.objects.create(name="Example Org", actor_kind="system")

    event = record.record(
        actor=actor, action="tenant.created", obj=tenant, before=None, after={"name": tenant.name}
    )

    assert AuditEvent.objects.count() == 1
    assert event.actor == actor
    assert event.actor_kind == "user"
    assert event.tenant is None
    assert event.object_type == "tenant"
    assert event.object_id == tenant.id
    assert event.before is None
    assert event.after == {"name": tenant.name}


def test_system_event_has_no_actor() -> None:
    from audit import record
    from tenancy.models import Tenant

    tenant = Tenant.objects.create(name="Example Org", actor_kind="system")

    event = record.record(actor=None, action="tenant.migrated", obj=tenant, before=None, after=None)

    assert event.actor is None
    assert event.actor_kind == "system"


def test_event_carries_a_tenant_and_dates_in_its_payload() -> None:
    from audit import record
    from identity.models import User
    from tenancy.models import Tenant

    actor = User.objects.create_user("a.person@example.test", "test-only-not-a-password")
    tenant = Tenant.objects.create(name="Example Org", actor_kind="system")

    event = record.record(
        actor=actor,
        action="membership.granted",
        obj=tenant,
        before=None,
        after={"granted_at": tenant.created_at, "id": tenant.id},
        tenant=tenant,
    )

    event.refresh_from_db()
    assert event.tenant == tenant
    assert event.after["id"] == str(tenant.id)


def test_event_never_carries_a_secret() -> None:
    from audit import record
    from tenancy.models import Tenant

    tenant = Tenant.objects.create(name="Example Org", actor_kind="system")

    with pytest.raises(ValueError):
        record.record(actor=None, action="x", obj=tenant, before=None, after={"password_hash": "h"})


def test_object_without_a_uuid_key_leaves_object_id_empty() -> None:
    from audit import record
    from identity.models import Language

    language = Language.objects.create(code="xx", label="Invented", actor_kind="system")

    event = record.record(
        actor=None, action="language.reseeded", obj=language, before=None, after={"code": "xx"}
    )

    assert event.object_type == "language"
    assert event.object_id is None


def test_trail_is_append_only() -> None:
    from django.db import DatabaseError, transaction

    from audit import record
    from tenancy.models import Tenant

    tenant = Tenant.objects.create(name="Example Org", actor_kind="system")
    event = record.record(actor=None, action="x", obj=tenant, before=None, after=None)

    with pytest.raises(DatabaseError), transaction.atomic():
        event.action = "y"
        event.save()
    with pytest.raises(DatabaseError), transaction.atomic():
        event.delete()

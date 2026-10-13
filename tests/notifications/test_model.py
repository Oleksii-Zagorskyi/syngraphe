"""Where notifications are kept (DL-0367, DL-0382): an organisation's in its schema, beside its
documents; what platform administrators are told in a table of its own in the shared schema."""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def tables_in(schema: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s", [schema])
        return {row[0] for row in cursor.fetchall()}


def test_each_table_in_its_own_schema_and_document_optional(
    migrated_tenant: Any, member_of: Any
) -> None:
    from notifications.models import Category, Event, Notification

    tenant_tables = tables_in(migrated_tenant.schema_name)
    assert "notifications_notification" in tenant_tables
    assert "tenancy_platformnotification" not in tenant_tables
    shared_tables = tables_in("public")
    assert "tenancy_platformnotification" in shared_tables
    assert "notifications_notification" not in shared_tables

    _, user, _ = member_of("a.member@example.test")
    with schema_context(migrated_tenant.number):
        row = Notification.objects.create(
            user=user,
            category=Category.ADMINISTRATIVE,
            event=Event.EMAIL_FAILED,
            facts={"tenant": 3},
        )
        row.refresh_from_db()
    assert row.document_id is None
    assert row.facts == {"tenant": 3}


def test_each_table_refuses_an_event_it_does_not_hold(migrated_tenant: Any, member_of: Any) -> None:
    from django.db import IntegrityError, transaction

    from notifications.models import Category, Event, Notification
    from tenancy.models import PlatformNotification

    _, user, _ = member_of("a.member@example.test")
    with schema_context(migrated_tenant.number):
        # Every value the rebuilt constraint holds; a correction notice needs its notice.
        for event in Event:
            if event != Event.CORRECTION_NOTICE:
                Notification.objects.create(
                    user=user, category=Category.ADMINISTRATIVE, event=event
                )
        with pytest.raises(IntegrityError), transaction.atomic():
            Notification.objects.create(
                user=user, category=Category.ADMINISTRATIVE, event="no_such_event"
            )
    with pytest.raises(IntegrityError), transaction.atomic():
        PlatformNotification.objects.create(user=user, event=Event.ACCESS_GRANTED)

"""The one writer: `notify` writes one row per person and refuses the actor among
them; `notify_platform` writes to the shared schema whatever schema the connection is in.

People and titles are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_one_row_per_user_never_the_actor(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from notifications.models import Category, Event, Notification
    from notifications.services import notify

    _, a, _ = member_of("a.reader@example.test")
    _, b, _ = member_of("b.reader@example.test")
    _, actor, _ = member_of("the.actor@example.test")
    document = make_document(title="Синтетичний документ", created_by=actor)
    with schema_context(migrated_tenant.number):
        rows = notify(
            users=[a, b],
            actor=actor,
            category=Category.DOCUMENT,
            event=Event.VERSION_COMMITTED,
            document=document,
            facts={"version": "0.0-1"},
        )
        assert {row.user_id for row in rows} == {a.pk, b.pk}
        assert Notification.objects.count() == 2
        with pytest.raises(ValueError):
            notify(
                users=[a, actor],
                actor=actor,
                category=Category.DOCUMENT,
                event=Event.VERSION_COMMITTED,
                document=document,
            )
        assert Notification.objects.count() == 2


def test_platform_level_rows_live_in_the_shared_schema(
    migrated_tenant: Any, member_of: Any
) -> None:
    from notifications.models import Event, Notification
    from notifications.services import notify_platform
    from tenancy.models import PlatformNotification

    _, admin, _ = member_of("p.admin@example.test", is_platform_admin=True)
    with schema_context(migrated_tenant.number):
        rows = notify_platform(event=Event.BACKUP_CONDITION, facts={"condition": "backup_behind"})
        assert Notification.objects.count() == 0
    assert [row.user_id for row in rows] == [admin.pk]
    with schema_context(None):
        stored = PlatformNotification.objects.get()
    assert stored.event == Event.BACKUP_CONDITION
    assert stored.facts == {"condition": "backup_behind"}


def test_the_platform_writer_tells_active_platform_administrators_alone(
    migrated_tenant: Any, member_of: Any
) -> None:
    from identity.models import User
    from notifications.models import Event
    from notifications.services import notify_platform

    _, first, _ = member_of("first.p.admin@example.test", is_platform_admin=True)
    _, second, _ = member_of("second.p.admin@example.test", is_platform_admin=True)
    _, member, _ = member_of("a.member@example.test")
    User.objects.create_user("blocked.p.admin@example.test", is_platform_admin=True)
    User.objects.filter(email="blocked.p.admin@example.test").update(self_blocked=True)

    rows = notify_platform(event=Event.BACKUP_CONDITION, facts={})
    assert {row.user_id for row in rows} == {first.pk, second.pk}

    # The actor is left out of the default list, never refused from it.
    rows = notify_platform(event=Event.BACKUP_CONDITION, actor=first, facts={})
    assert {row.user_id for row in rows} == {second.pk}
    with pytest.raises(ValueError):
        notify_platform(event=Event.BACKUP_CONDITION, users=[first, member], facts={})


def test_an_event_keeps_its_own_category(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from notifications.models import Category, Event
    from notifications.services import notify

    _, person, _ = member_of("a.reader@example.test")
    with schema_context(migrated_tenant.number), pytest.raises(ValueError):
        notify(users=[person], category=Category.DOCUMENT, event=Event.ACCESS_GRANTED)

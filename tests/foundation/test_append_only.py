"""The typed history is append-only in the database (ASR-18 as DL-0459 amends it): the access
changes, the memberships' history, the account blocks' history and the organisations' state
history refuse an update or a delete as the audit trail does, while the acts that write them go on
as before — and the test suite's restore still empties a kept tenant schema.

People, groups and organisations are synthetic examples."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.db import DatabaseError, connection, transaction

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

TRIGGERS = {
    "access_accesschange": "access_change_append_only",
    "identity_membershiphistory": "membership_history_append_only",
    "identity_accountblockhistory": "account_block_history_append_only",
    "tenancy_tenantstatehistory": "tenant_state_history_append_only",
}
# The one tenant table among them; the others are the shared schema's.
TENANT_TABLES = {"access_accesschange"}


def _rows(migrated_tenant: Any, member_of: Any) -> dict[str, Any]:
    """One row of each history table, written by the acts that write them."""
    from access.models import AccessChange, AccessGroup
    from access.rights import Right
    from identity.blocking import self_block
    from identity.models import AccountBlockHistory, MembershipHistory
    from tenancy.models import TenantStateHistory

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, person, membership = member_of("a.person@example.test")
    membership.change("state", "blocked", by=admin)
    self_block(person)
    TenantStateHistory.objects.create(
        tenant=migrated_tenant, before="active", after="blocked", by=admin
    )
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")
        group.grant(Right.VIEW_CANONICAL, by=admin)
        change = AccessChange.objects.get()
    return {
        "access_accesschange": change,
        "identity_membershiphistory": MembershipHistory.objects.get(field="state"),
        "identity_accountblockhistory": AccountBlockHistory.objects.get(),
        "tenancy_tenantstatehistory": TenantStateHistory.objects.filter(after="blocked").get(),
    }


def test_history_rows_refuse_change(migrated_tenant: Any, member_of: Any) -> None:
    rows = _rows(migrated_tenant, member_of)

    for table, row in rows.items():
        stored = type(row).objects.filter(pk=row.pk)
        with schema_context(migrated_tenant.number):
            with pytest.raises(DatabaseError, match=f"{table} is append-only"):
                with transaction.atomic():
                    stored.update(at=row.at + timedelta(seconds=1))
            with pytest.raises(DatabaseError, match=f"{table} is append-only"):
                with transaction.atomic():
                    stored.delete()
            kept = stored.get()
        assert kept.at == row.at, table


def test_acts_still_write_history(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    from access.models import AccessChange, AccessGroup, DocumentGroup, GroupMember, GroupRight
    from access.rights import Right

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, membership = member_of("a.reader@example.test")
    document = make_document(created_by=admin)

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")
        group.grant(Right.VIEW_CANONICAL, by=admin)
        group.revoke(Right.VIEW_CANONICAL, by=admin)
        group.add_member(membership, by=admin, email=False)
        group.remove_member(membership, by=admin)
        DocumentGroup.link(document, group, by=admin)
        DocumentGroup.unlink(document, group, by=admin)
        written = list(AccessChange.objects.order_by("at").values_list("kind", "action"))
        current = (
            GroupRight.objects.count(),
            GroupMember.objects.count(),
            DocumentGroup.objects.count(),
        )

    assert written == [
        ("right", "added"),
        ("right", "removed"),
        ("member", "added"),
        ("member", "removed"),
        ("link", "added"),
        ("link", "removed"),
    ]
    assert current == (0, 0, 0)


def test_the_restore_empties_the_history(
    migrated_tenant: Any, member_of: Any, tenant_schema: Any
) -> None:
    from access.models import AccessChange, AccessGroup
    from access.rights import Right

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")
        group.grant(Right.VIEW_CANONICAL, by=admin)
        assert AccessChange.objects.count() == 1

    tenant_schema.restore()

    with schema_context(migrated_tenant.number):
        assert AccessChange.objects.count() == 0


def test_triggers_exist_in_every_schema(migrated_tenant: Any) -> None:
    from tenancy.schemas import schema_name

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT n.nspname, c.relname, t.tgname FROM pg_trigger t"
            " JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE NOT t.tgisinternal AND n.nspname IN ('public', %s)",
            [schema_name(migrated_tenant.number)],
        )
        found = set(cursor.fetchall())

    tenant = schema_name(migrated_tenant.number)
    expected = {
        (tenant if table in TENANT_TABLES else "public", table, trigger)
        for table, trigger in TRIGGERS.items()
    }
    assert expected <= found

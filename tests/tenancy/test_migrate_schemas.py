"""`migrate_schemas`: every schema migrated, shared apps faked, a half-made tenant completed."""

from __future__ import annotations

import time
from typing import Any

import pytest
from django.core.management import call_command
from django.db import connection

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

# A representative tenant app for the measurement: several migrations, several tables, a dependency
# on a shared-only app.
REPRESENTATIVE_TENANT_APP = "django.contrib.auth"


@pytest.fixture
def auth_as_tenant_app(settings: Any) -> None:
    settings.TENANT_APPS = [REPRESENTATIVE_TENANT_APP]
    settings.SHARED_APPS = [a for a in settings.SHARED_APPS if a != REPRESENTATIVE_TENANT_APP]


def tables_in(schema: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s", [schema])
        return {row[0] for row in cursor.fetchall()}


def migrations_recorded_in(schema: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT count(*) FROM "{schema}".django_migrations')
        return int(cursor.fetchone()[0])


def timed(*numbers: int) -> float:
    started = time.perf_counter()
    call_command("migrate_schemas", *[f"--tenant={n}" for n in numbers], verbosity=0)
    return time.perf_counter() - started


def test_ten_schemas_within_budget(
    make_tenant: Any, drop_tenant_schemas: None, auth_as_tenant_app: None, record_property: Any
) -> None:
    tenants = [make_tenant(f"Org {i}") for i in range(33)]
    numbers = [t.number for t in tenants]

    # One schema is measured three times and averaged: a single sample is too noisy a base.
    t1 = sum(timed(n) for n in numbers[:3]) / 3
    t10 = timed(*numbers[3:13])
    t20 = timed(*numbers[13:33])

    print(f"V-12 timings: t1={t1:.2f}s t10={t10:.2f}s t20={t20:.2f}s")
    record_property("v12_timings", {"t1": t1, "t10": t10, "t20": t20})
    assert t10 < 60
    assert t10 <= 1.2 * 10 * t1
    assert t20 <= 1.2 * 2 * t10


def test_tenant_schema_holds_tenant_tables_only(
    make_tenant: Any, drop_tenant_schemas: None, auth_as_tenant_app: None
) -> None:
    tenants = [make_tenant("Org A"), make_tenant("Org B")]

    for tenant in tenants:
        call_command("migrate_schemas", f"--tenant={tenant.number}", verbosity=0)

    from django.db.migrations.loader import MigrationLoader

    every_migration = len(MigrationLoader(None).graph.nodes)
    for tenant in tenants:
        assert tables_in(tenant.schema_name) == {
            "django_migrations",
            "auth_group",
            "auth_group_permissions",
            "auth_permission",
        }
        assert migrations_recorded_in(tenant.schema_name) == every_migration


def test_app_on_both_lists_is_migrated_not_faked(settings: Any) -> None:
    from tenancy.management.commands.migrate_schemas import plan_for_tenant_schema

    settings.SHARED_APPS = [*settings.SHARED_APPS, "django.contrib.auth"]
    settings.TENANT_APPS = ["django.contrib.auth"]

    migrated, faked = plan_for_tenant_schema()

    assert "auth" in migrated
    assert "auth" not in faked
    assert "sessions" in faked


def test_completes_a_half_made_tenant(
    make_tenant: Any, drop_tenant_schemas: None, auth_as_tenant_app: None
) -> None:
    from tenancy.models import TenantState, TenantStateHistory
    from tenancy.schemas import schema_exists

    tenant = make_tenant("Org A", state=TenantState.MIGRATING)
    assert not schema_exists(tenant.number)

    call_command("migrate_schemas", verbosity=0)

    from django.db.migrations.loader import MigrationLoader

    tenant.refresh_from_db()
    assert schema_exists(tenant.number)
    assert "auth_group" in tables_in(tenant.schema_name)
    assert migrations_recorded_in(tenant.schema_name) == len(MigrationLoader(None).graph.nodes)
    assert tenant.state == TenantState.ACTIVE
    steps = list(TenantStateHistory.objects.filter(tenant=tenant))
    assert len(steps) == 1
    assert (steps[0].before, steps[0].after, steps[0].by) == (
        TenantState.MIGRATING,
        TenantState.ACTIVE,
        None,
    )


def test_shared_tables_stay_in_public(
    make_tenant: Any, drop_tenant_schemas: None, auth_as_tenant_app: None
) -> None:
    make_tenant("Org A")

    call_command("migrate_schemas", verbosity=0)

    assert "identity_user" in tables_in("public")
    assert "tenancy_tenant" in tables_in("public")


def test_router_migrates_each_app_in_its_own_schema(auth_as_tenant_app: None) -> None:
    from tenancy.routers import TenantGuardRouter
    from tenancy.schemas import schema_context

    router = TenantGuardRouter()

    with schema_context(None):
        assert router.allow_migrate("default", "auth") is False
        assert router.allow_migrate("default", "identity") is True
    with schema_context(1):
        assert router.allow_migrate("default", "auth") is True
        assert router.allow_migrate("default", "identity") is False


def test_tenant_option_refuses_a_shared_schema_behind(
    make_tenant: Any, drop_tenant_schemas: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from django.core.management.base import CommandError

    tenant = make_tenant("Org A")
    monkeypatch.setattr(
        "tenancy.management.commands.migrate_schemas._plan_is_empty", lambda *a: False
    )

    with pytest.raises(CommandError):
        call_command("migrate_schemas", f"--tenant={tenant.number}", verbosity=0)

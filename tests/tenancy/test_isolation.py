"""ASR-01: one tenant's context cannot reach another's rows, and no tenant means no query."""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection

pytestmark = [
    pytest.mark.invariant,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


@pytest.fixture
def two_tenants_with_a_row(make_tenant: Any, drop_tenant_schemas: None) -> tuple[Any, Any]:
    """Two schemas, a throwaway table in each, one row each — by raw SQL, never a migration."""
    from tenancy.schemas import create_schema

    tenants = (make_tenant("Org A"), make_tenant("Org B"))
    with connection.cursor() as cursor:
        for tenant in tenants:
            create_schema(tenant.number)
            cursor.execute(f'CREATE TABLE "{tenant.schema_name}".probe (owner text)')
            cursor.execute(
                f'INSERT INTO "{tenant.schema_name}".probe (owner) VALUES (%s)', [tenant.name]
            )
    return tenants


def test_schema_isolation_holds(two_tenants_with_a_row: tuple[Any, Any]) -> None:
    from tenancy.schemas import schema_context

    tenant_a, tenant_b = two_tenants_with_a_row

    with schema_context(tenant_a.number), connection.cursor() as cursor:
        cursor.execute("SELECT owner FROM probe")
        owners = [row[0] for row in cursor.fetchall()]

    assert owners == [tenant_a.name]
    assert tenant_b.name not in owners


def test_guard_refuses_tenantless_query(settings: Any) -> None:
    from django.contrib.auth.models import Group

    from tenancy.routers import TenantRequired

    settings.TENANT_APPS = ["django.contrib.auth"]
    settings.SHARED_APPS = [app for app in settings.SHARED_APPS if app != "django.contrib.auth"]

    with pytest.raises(TenantRequired):
        Group.objects.count()


def test_shared_app_passes_the_guard_without_a_tenant() -> None:
    from tenancy.models import PlatformHost

    assert PlatformHost.objects.filter(host="127.0.0.1").exists()

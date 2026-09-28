"""A tenant with its schema migrated, and people signed in on the platform host inside it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client


@pytest.fixture
def migrated_tenant(drop_tenant_schemas: None) -> Any:
    """An active tenant whose schema holds the access tables.

    `drop_tenant_schemas` is requested first so it tears down last: the tenant schema's rows
    reference `identity_membership`, which the flush after the test truncates.
    """
    from tenancy.models import Tenant

    tenant = Tenant.objects.create(name="Example Org", actor_kind="system")
    call_command("migrate_schemas", f"--tenant={tenant.number}", verbosity=0)
    tenant.refresh_from_db()
    return tenant


@pytest.fixture
def member_of(migrated_tenant: Any) -> Callable[..., tuple[Client, Any, Any]]:
    """A client signed in as a member of the migrated tenant, the tenant chosen in the session."""

    def make(email: str, *, is_tenant_admin: bool = False) -> tuple[Client, Any, Any]:
        from identity.models import Membership, User

        user = User.objects.create_user(email, "test-only-not-a-password")
        membership = Membership.objects.create(
            tenant=migrated_tenant, user=user, is_tenant_admin=is_tenant_admin, actor_kind="system"
        )
        client = Client(headers={"host": "127.0.0.1"})
        client.force_login(user)
        session = client.session
        session["tenant_number"] = migrated_tenant.number
        session.save()
        return client, user, membership

    return make

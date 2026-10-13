"""People signed in on the platform host, with a tenant chosen in the session."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.test import Client


@pytest.fixture
def tenant(migrated_tenant: Any) -> Any:
    """An organisation as a request resolves one: active, its schema migrated, since the shell
    counts its person's unread notifications there."""
    return migrated_tenant


@pytest.fixture
def signed_in() -> Callable[..., tuple[Client, Any]]:
    """A client signed in as a person with the given memberships, the tenant in the session."""

    def make(
        email: str,
        *,
        tenant: Any = None,
        is_tenant_admin: bool = False,
        is_platform_admin: bool = False,
    ) -> tuple[Client, Any]:
        from identity.models import Membership, User

        user = User.objects.create_user(
            email, "test-only-not-a-password", is_platform_admin=is_platform_admin
        )
        if tenant is not None:
            Membership.objects.create(
                tenant=tenant, user=user, is_tenant_admin=is_tenant_admin, actor_kind="system"
            )
        client = Client(headers={"host": "127.0.0.1"})
        client.force_login(user)
        if tenant is not None:
            session = client.session
            session["tenant_number"] = tenant.number
            session.save()
        return client, user

    return make

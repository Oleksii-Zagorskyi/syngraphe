"""People with memberships in organisations, for the sign-in tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

PASSWORD = "Tr4vel-Plan-Ok"


@pytest.fixture
def person() -> Callable[..., Any]:
    """A user with an active membership in each named organisation, created as needed."""

    def make(email: str, *organisations: str, **fields: Any) -> Any:
        from identity.models import Membership, User
        from tenancy.models import Tenant

        user = User.objects.create_user(email, PASSWORD, **fields)
        for name in organisations:
            tenant, _ = Tenant.objects.get_or_create(
                name=name, defaults={"state": "active", "actor_kind": "system"}
            )
            Membership.objects.create(tenant=tenant, user=user, actor_kind="system")
        return user

    return make

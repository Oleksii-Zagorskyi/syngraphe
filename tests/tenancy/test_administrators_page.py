"""The platform pages answer only a platform administrator; the administrators page lists them."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

PAGES = (
    "/administration/platform/tenants/",
    "/administration/platform/tenants/new/",
    "/administration/platform/hosts/",
    "/administration/platform/administrators/",
    "/administration/platform/mail/",
)


def test_platform_pages_closed_to_tenant_admins(make_tenant_schema: Any) -> None:
    from identity.models import Membership, User

    # Its schema migrated, as every organisation a request resolves has one.
    tenant = make_tenant_schema("Example Org")
    user = User.objects.create_user("t.admin@example.test", "Tr4vel-Plan-Ok")
    Membership.objects.create(tenant=tenant, user=user, is_tenant_admin=True, actor_kind="system")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(user)
    session = client.session
    session["tenant_number"] = tenant.number
    session.save()

    for page in PAGES:
        assert client.get(page).status_code == 404, page


def test_platform_administrators_listed(platform_admin: Any) -> None:
    from identity.models import User

    client, me = platform_admin()
    other = User.objects.create_user(
        "second.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True
    )
    User.objects.create_user("not.admin@example.test", "Tr4vel-Plan-Ok")

    response = client.get(PAGES[3])

    assert response.status_code == 200
    assert set(response.context["administrators"]) == {me, other}


def test_platform_pages_render(platform_admin: Any) -> None:
    client, _ = platform_admin()

    for page in PAGES:
        assert client.get(page).status_code == 200, page


def test_platform_pages_closed_on_an_organisations_domain(make_tenant_schema: Any) -> None:
    from identity.models import User
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import TenantDomain

    tenant = make_tenant_schema("Example Org")
    TenantDomain.objects.create(
        tenant=tenant, host="docs.example.test", is_default=True, actor_kind="system"
    )
    invalidate_host_cache()
    user = User.objects.create_user(
        "p.admin@example.test", "Tr4vel-Plan-Ok", is_platform_admin=True
    )
    client = Client(headers={"host": "docs.example.test"})
    client.force_login(user)

    for page in PAGES:
        assert client.get(page).status_code == 404, page

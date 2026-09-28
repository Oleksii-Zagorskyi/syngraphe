"""Django's own administration interface: operators only, platform hosts only, audited (DL-0210)."""

from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings
from django.test import Client

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

PASSWORD = "Tr4vel-Plan-Ok"


def admin_path() -> str:
    return f"/{settings.DJANGO_ADMIN_PATH}"


def signed_in(user: Any, host: str = "127.0.0.1") -> Client:
    client = Client(headers={"host": host})
    client.force_login(user)
    return client


def test_admin_confined() -> None:
    from audit.models import AuditEvent
    from identity.models import User
    from tenancy.models import Tenant, TenantDomain

    platform_admin = User.objects.create_user(
        "p.admin@example.test", PASSWORD, is_platform_admin=True
    )
    operator = User.objects.create_superuser("an.operator@example.test", PASSWORD)
    tenant = Tenant.objects.create(name="Example Org", state="active", actor_kind="system")
    TenantDomain.objects.create(tenant=tenant, host="docs.example.test", actor_kind="system")

    not_operator = signed_in(platform_admin).get(admin_path())
    on_a_domain = signed_in(operator, "docs.example.test").get(admin_path())
    anonymous = Client(headers={"host": "127.0.0.1"}).get(admin_path())
    before = AuditEvent.objects.count()
    allowed = signed_in(operator).get(admin_path())

    assert not_operator.status_code == on_a_domain.status_code == anonymous.status_code == 404
    assert allowed.status_code == 200
    assert AuditEvent.objects.count() == before + 1
    assert AuditEvent.objects.filter(action="framework_admin.request", actor=operator).count() == 1


def test_bare_admin_path_answers_like_an_unknown_address() -> None:
    bare = Client(headers={"host": "127.0.0.1"}).get(admin_path().rstrip("/"))

    assert bare.status_code == 404


def test_admin_never_at_the_default_path() -> None:
    assert settings.DJANGO_ADMIN_PATH != "admin/"
    assert Client(headers={"host": "127.0.0.1"}).get("/admin/").status_code == 404

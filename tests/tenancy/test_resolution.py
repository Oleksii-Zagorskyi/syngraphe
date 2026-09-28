"""The tenant step: a domain names its tenant, a platform host takes it from the session."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_tenant_domain_resolves(make_tenant: Any, run_request: Any) -> None:
    tenant = make_tenant("Example Org", domain="docs.example.test")

    response, seen = run_request("docs.example.test")

    assert response.status_code == 200
    assert seen["tenant"] == tenant
    assert seen["search_path"].startswith(tenant.schema_name)


def test_platform_host_uses_session(make_tenant: Any, run_request: Any) -> None:
    make_tenant("Another Org")
    tenant = make_tenant("Example Org")

    response, seen = run_request("127.0.0.1", session_tenant=tenant.number)

    assert response.status_code == 200
    assert seen["tenant"] == tenant
    assert seen["search_path"].startswith(tenant.schema_name)


def test_platform_host_without_tenant(make_tenant: Any, run_request: Any) -> None:
    make_tenant("Example Org")

    response, seen = run_request("127.0.0.1")

    assert response.status_code == 200
    assert seen["tenant"] is None
    assert seen["search_path"] == "public"


def test_migrating_tenant_never_resolved(make_tenant: Any, run_request: Any) -> None:
    from tenancy.models import TenantState

    tenant = make_tenant("Example Org", state=TenantState.MIGRATING, domain="docs.example.test")

    on_domain, _ = run_request("docs.example.test")
    on_platform, seen = run_request("127.0.0.1", session_tenant=tenant.number)

    assert on_domain.status_code == 400
    assert on_platform.status_code == 200
    assert seen["tenant"] is None
    assert seen["search_path"] == "public"


def test_session_tenant_needs_a_signed_in_person(make_tenant: Any, run_request: Any) -> None:
    tenant = make_tenant("Example Org")

    _, seen = run_request("127.0.0.1", session_tenant=tenant.number, signed_in=False)

    assert seen["tenant"] is None
    assert seen["search_path"] == "public"


def test_domain_of_a_vanished_tenant_is_refused(
    make_tenant: Any, run_request: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_tenant("Example Org", domain="docs.example.test")
    monkeypatch.setattr("tenancy.middleware.resolve_tenant", lambda request, entry: None)

    response, _ = run_request("docs.example.test")

    assert response.status_code == 400


def test_search_path_is_public_again_after_the_request(make_tenant: Any, run_request: Any) -> None:
    from django.db import connection

    make_tenant("Example Org", domain="docs.example.test")
    run_request("docs.example.test")

    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        assert cursor.fetchone()[0] == "public"

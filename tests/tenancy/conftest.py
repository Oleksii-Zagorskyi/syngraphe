"""Tenancy fixtures: tenants without schemas, requests through the middleware, schema cleanup."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory


@pytest.fixture
def make_tenant() -> Callable[..., Any]:
    """A tenant row in the given state, with an optional domain; no schema is created."""
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import Tenant, TenantDomain, TenantState

    def make(name: str, *, state: str = TenantState.ACTIVE, domain: str | None = None) -> Any:
        tenant = Tenant.objects.create(name=name, state=state, actor_kind="system")
        if domain is not None:
            TenantDomain.objects.create(
                tenant=tenant, host=domain, is_default=True, actor_kind="system"
            )
            invalidate_host_cache()
        return tenant

    return make


@pytest.fixture
def run_request() -> Callable[..., tuple[HttpResponse, dict[str, Any]]]:
    """Run one request through `TenancyMiddleware` alone and record what the view would see."""
    from tenancy.middleware import TenancyMiddleware

    def run(
        host: str,
        *,
        session_tenant: int | None = None,
        signed_in: bool = True,
        path: str = "/",
        forwarded_host: str | None = None,
        peer: str = "127.0.0.1",
    ) -> tuple[HttpResponse, dict[str, Any]]:
        from django.contrib.auth.models import AnonymousUser

        from identity.models import User

        headers = {"host": host}
        if forwarded_host is not None:
            headers["x-forwarded-host"] = forwarded_host
        request: HttpRequest = RequestFactory().get(path, headers=headers, REMOTE_ADDR=peer)
        SessionMiddleware(lambda r: HttpResponse()).process_request(request)
        if session_tenant is not None:
            request.session["tenant_number"] = session_tenant
        if signed_in:
            request.user = User.objects.create_user(
                f"person-{uuid.uuid4().hex[:8]}@example.test", "test-only-not-a-password"
            )
        else:
            request.user = AnonymousUser()
        seen: dict[str, Any] = {}

        def view(req: HttpRequest) -> HttpResponse:
            seen["tenant"] = req.tenant
            with connection.cursor() as cursor:
                cursor.execute("SHOW search_path")
                seen["search_path"] = cursor.fetchone()[0]
            return HttpResponse("ok")

        response = TenancyMiddleware(view)(request)
        return response, seen

    return run


@pytest.fixture
def drop_tenant_schemas() -> Iterator[None]:
    """Drop every `tenant_N` schema the test created, since a schema outlives a rolled-back row."""
    yield
    with connection.cursor() as cursor:
        cursor.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE 'tenant\\_%'")
        for (name,) in cursor.fetchall():
            cursor.execute(f'DROP SCHEMA "{name}" CASCADE')

"""The one middleware that checks the host and resolves the tenant (ADR-0008, ADR-0017).

Step one refuses any host not in the platform's set or a tenant's domains, before any tenant
is looked up.
Step two resolves the tenant: a domain names it; a platform host takes it from a signed-in
person's session, or none. A `migrating` tenant is never resolved. The connection's `search_path`
follows, and is `public` again when the response has left.
"""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest

from syngraphe.logs import tenant_number_var
from tenancy.models import PlatformHost, Tenant, TenantDomain, TenantState
from tenancy.schemas import current_tenant, set_search_path

if TYPE_CHECKING:
    from identity.models import Membership

HOST_CACHE_SECONDS = 30
EXEMPT_PATHS = ("/health/",)
SESSION_TENANT_KEY = "tenant_number"
# One line for every refusal, so an unknown host and a migrating tenant's domain read the same.
REFUSAL = "Unknown host."


@dataclass(frozen=True)
class HostEntry:
    tenant_number: int | None  # None for a platform host
    tenant_state: str | None


class TenantRequest(HttpRequest):
    """The attributes the middleware gives every request; for annotation only."""

    tenant: Tenant | None
    membership: Membership | None


_cache: tuple[float, dict[str, HostEntry]] | None = None


def known_hosts() -> dict[str, HostEntry]:
    """Every allowed host, lower-cased, loaded from the rows and kept for thirty seconds."""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < HOST_CACHE_SECONDS:
        return _cache[1]
    hosts: dict[str, HostEntry] = {
        host.lower(): HostEntry(None, None)
        for host in PlatformHost.objects.values_list("host", flat=True)
    }
    for host, number, state in TenantDomain.objects.values_list(
        "host", "tenant__number", "tenant__state"
    ):
        hosts[host.lower()] = HostEntry(number, state)
    _cache = (now, hosts)
    return hosts


def invalidate_host_cache() -> None:
    global _cache
    _cache = None


def match_host(host: str, hosts: dict[str, HostEntry]) -> HostEntry | None:
    """A row without a port matches any port; a row with a port matches that port only."""
    host = host.strip().lower()
    if host in hosts:
        return hosts[host]
    if ":" in host and not host.endswith("]"):
        bare = host.rsplit(":", 1)[0]
        if bare in hosts:
            return hosts[bare]
    return None


def _from_trusted_proxy(request: HttpRequest) -> bool:
    try:
        peer = ipaddress.ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return False
    return any(peer in network for network in settings.TRUSTED_PROXIES)


def request_host(request: HttpRequest) -> str:
    """The host the request was made for.

    From a trusted proxy the forwarded host is the last one in the header — the proxy's own,
    whatever a client put before it; the proxy is expected to set the header, not append to it.
    """
    forwarded = str(request.META.get("HTTP_X_FORWARDED_HOST", ""))
    if forwarded and _from_trusted_proxy(request):
        return forwarded.rsplit(",", 1)[-1].strip()
    return str(request.META.get("HTTP_HOST", ""))


def resolve_tenant(request: HttpRequest, entry: HostEntry) -> Tenant | None:
    """The tenant a known host names, or a signed-in person's session's on a platform host.

    Never one that is `migrating`.
    """
    number: int
    if entry.tenant_number is not None:
        number = entry.tenant_number
    else:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        chosen = request.session.get(SESSION_TENANT_KEY)
        if not isinstance(chosen, int):
            return None
        number = chosen
    return Tenant.objects.exclude(state=TenantState.MIGRATING).filter(number=number).first()


def active_membership(request: HttpRequest, tenant: Tenant | None) -> Membership | None:
    """The signed-in person's active membership in the resolved tenant, or `None`.

    `None` also for a tenant that is not active and for a person who blocked their own account:
    each closes every membership it covers.
    """
    from identity.models import Membership, MembershipState

    user = getattr(request, "user", None)
    if tenant is None or tenant.state != TenantState.ACTIVE:
        return None
    if user is None or not user.is_authenticated or user.self_blocked:
        return None
    membership = Membership.objects.filter(
        tenant=tenant, user=user, state=MembershipState.ACTIVE
    ).first()
    if membership is not None:
        membership.user = user
    return membership


class TenancyMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if current_tenant(connection) is not None:
            set_search_path(connection, None)
        if request.path in EXEMPT_PATHS:
            return self.get_response(request)

        entry = match_host(request_host(request), known_hosts())
        if entry is None or entry.tenant_state == TenantState.MIGRATING:
            return HttpResponseBadRequest(REFUSAL, content_type="text/plain")

        tenant = resolve_tenant(request, entry)
        if entry.tenant_number is not None and tenant is None:
            # The domain's tenant is gone or no longer resolvable; a tenant host never falls
            # through to the platform.
            return HttpResponseBadRequest(REFUSAL, content_type="text/plain")
        typed = cast(TenantRequest, request)
        typed.tenant = tenant
        typed.membership = active_membership(request, tenant)
        number = None if tenant is None else tenant.number
        set_search_path(connection, number)
        tenant_number_var.set(number)
        try:
            return self.get_response(request)
        finally:
            set_search_path(connection, None)
            tenant_number_var.set(None)

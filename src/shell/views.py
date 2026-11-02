"""The shell's views: the health endpoint, the root address, the administration frame, and the one
answer for what may not be seen."""

from __future__ import annotations

from typing import Any

import redis
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import Error, connection
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from tenancy.middleware import SESSION_TENANT_KEY
from tenancy.models import Tenant, TenantState

PROBE_TIMEOUT_SECONDS = 2


def _database_answers() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Error:
        return False
    return True


def _redis_answers() -> bool:
    client = redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=PROBE_TIMEOUT_SECONDS,
        socket_timeout=PROBE_TIMEOUT_SECONDS,
    )
    try:
        return bool(client.ping())
    except (redis.RedisError, OSError):
        return False
    finally:
        client.close()


@never_cache
@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """`200` when the database and Redis answer, `503` naming the one that does not; and the
    backup's state, which never changes the status (DL-0295).

    Never a version or a host.
    """
    from documents.backup_watch import health_entry

    checks = {
        "database": "ok" if _database_answers() else "unreachable",
        "redis": "ok" if _redis_answers() else "unreachable",
    }
    status = 200 if all(value == "ok" for value in checks.values()) else 503
    return JsonResponse({**checks, "backup": health_entry()}, status=status)


def not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    """*Nothing to show here*, with status 404 and no title, author or version (ADR-0008).

    The one answer for an address that does not exist and an object the reader may not open;
    every view returns it for what may not be seen, and Django's 404 handler is this function.
    """
    response = render(request, "shell/nothing_to_show.html", status=404)
    # Every refusal carries the same headers, whether or not its view is itself never cached.
    add_never_cache_headers(response)
    return response


def _is_platform_admin(request: HttpRequest) -> bool:
    return bool(getattr(getattr(request, "user", None), "acts_as_platform_admin", False))


def _is_administrator(request: HttpRequest) -> bool:
    membership = getattr(request, "membership", None)
    return _is_platform_admin(request) or bool(membership and membership.is_tenant_admin)


@login_required
def root(request: HttpRequest) -> HttpResponse:
    """`/`: the organisation's documents; with no organisation chosen, the administration for a
    platform administrator and the not-found answer for anyone else."""
    member = getattr(request, "membership", None) is not None or _is_platform_admin(request)
    if getattr(request, "tenant", None) is not None and member:
        return HttpResponseRedirect("/folder/1/")
    if _is_platform_admin(request):
        return HttpResponseRedirect(reverse("administration"))
    person = request.user
    if person.is_authenticated and getattr(request, "tenant", None) is None:
        from identity.models import Membership

        # A person of several organisations, none chosen: asked which (DL-0511), from the list
        # the switcher draws, so nothing else is named.
        if Membership.objects.active().filter(user=person).count() > 1:
            return render(request, "shell/organisations.html")
    return not_found(request)


def frame(request: HttpRequest) -> dict[str, Any]:
    """What the administration frame needs around any section: its panes and the selector."""
    context: dict[str, Any] = {
        "platform_pane": _is_platform_admin(request),
        # On a tenant's own domain the host names the organisation; there is nothing to choose.
        # A request the middleware did not mark is taken for an organisation's own domain, as
        # every other consumer takes it.
        "selector": _is_platform_admin(request)
        and not getattr(request, "tenant_from_domain", True),
    }
    if context["selector"]:
        # A blocked organisation is listed, marked: the selector is a platform administrator's
        # way into it from the platform host; one being set up is never listed (DL-0376).
        context["organisations"] = Tenant.objects.filter(
            state__in=[TenantState.ACTIVE, TenantState.BLOCKED]
        ).order_by("number")
    return context


@login_required
def administration(request: HttpRequest) -> HttpResponse:
    """The first section the person may use (DL-0511): the platform's *Hosts* for a platform
    administrator, the organisation's *Users* for its administrator — each the first link of its
    pane, every section drawing the frame; anyone else gets the not-found answer."""
    if not _is_administrator(request):
        return not_found(request)
    # On an organisation's own domain the platform's sections are not there to use.
    if _is_platform_admin(request) and not getattr(request, "tenant_from_domain", True):
        return HttpResponseRedirect("/administration/platform/hosts/")
    return HttpResponseRedirect("/administration/tenant/users/")


@login_required
def choose_organisation(request: HttpRequest) -> HttpResponse:
    """A platform administrator picks the organisation the frame's *Organisation* pane shows.

    Anything else — another method, another person, a host that already names the organisation,
    an unknown number — gets the not-found answer, never a hint that the selector exists.
    """
    if (
        request.method != "POST"
        or not _is_platform_admin(request)
        or getattr(request, "tenant_from_domain", True)
    ):
        return not_found(request)
    try:
        number = int(request.POST.get("organisation", ""))
    except ValueError:
        return not_found(request)
    if not Tenant.objects.filter(
        number=number, state__in=[TenantState.ACTIVE, TenantState.BLOCKED]
    ).exists():
        return not_found(request)
    request.session[SESSION_TENANT_KEY] = number
    return HttpResponseRedirect(reverse("administration"))

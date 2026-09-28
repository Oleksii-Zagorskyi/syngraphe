"""The shell's views: the health endpoint, the landing page, the administration frame, and the one
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
    """`200` when the database and Redis answer, `503` naming the one that does not.

    Never a version or a host.
    """
    checks = {
        "database": "ok" if _database_answers() else "unreachable",
        "redis": "ok" if _redis_answers() else "unreachable",
    }
    status = 200 if all(value == "ok" for value in checks.values()) else 503
    return JsonResponse(checks, status=status)


def not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    """*Nothing to show here*, with status 404 and no title, author or version (ADR-0008).

    The one answer for an address that does not exist and an object the reader may not open;
    every view returns it for what may not be seen, and Django's 404 handler is this function.
    """
    return render(request, "shell/nothing_to_show.html", status=404)


def _is_platform_admin(request: HttpRequest) -> bool:
    return bool(getattr(getattr(request, "user", None), "is_platform_admin", False))


def _is_administrator(request: HttpRequest) -> bool:
    membership = getattr(request, "membership", None)
    return _is_platform_admin(request) or bool(membership and membership.is_tenant_admin)


@login_required
def landing(request: HttpRequest) -> HttpResponse:
    """The shell with the organisation's name and nothing else."""
    return render(request, "shell/landing.html")


@login_required
def administration(request: HttpRequest) -> HttpResponse:
    """The two-pane frame: *Platform* for platform administrators, *Organisation* for
    administrators of the chosen organisation; anyone else gets the not-found answer."""
    if not _is_administrator(request):
        return not_found(request)
    context: dict[str, Any] = {
        "platform_pane": _is_platform_admin(request),
        # On a tenant's own domain the host names the organisation; there is nothing to choose.
        "selector": _is_platform_admin(request)
        and not getattr(request, "tenant_from_domain", False),
    }
    if context["selector"]:
        context["organisations"] = Tenant.objects.filter(state=TenantState.ACTIVE).order_by(
            "number"
        )
    return render(request, "shell/administration.html", context)


@login_required
def choose_organisation(request: HttpRequest) -> HttpResponse:
    """A platform administrator picks the organisation the frame's *Organisation* pane shows.

    Anything else — another method, another person, a host that already names the organisation,
    an unknown number — gets the not-found answer, never a hint that the selector exists.
    """
    if (
        request.method != "POST"
        or not _is_platform_admin(request)
        or getattr(request, "tenant_from_domain", False)
    ):
        return not_found(request)
    try:
        number = int(request.POST.get("organisation", ""))
    except ValueError:
        return not_found(request)
    if not Tenant.objects.filter(number=number, state=TenantState.ACTIVE).exists():
        return not_found(request)
    request.session[SESSION_TENANT_KEY] = number
    return HttpResponseRedirect(reverse("administration"))

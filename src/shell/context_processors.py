"""What every template knows: the organisation, the person's membership in it, their roles."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest


def shell(request: HttpRequest) -> dict[str, Any]:
    membership = getattr(request, "membership", None)
    is_platform_admin = bool(
        getattr(getattr(request, "user", None), "acts_as_platform_admin", False)
    )
    return {
        "current_tenant": getattr(request, "tenant", None),
        "membership": membership,
        "is_platform_admin": is_platform_admin,
        "display_timezone": settings.DISPLAY_TIMEZONE,
        "is_administrator": is_platform_admin or bool(membership and membership.is_tenant_admin),
    }

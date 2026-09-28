"""The platform's routes; every app's routes are included here."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from django.views.decorators.common import no_append_slash


def _never_append_slash(patterns: list[Any]) -> list[Any]:
    """Mark every view under these patterns so the framework never redirects a bare path to it:
    that redirect would answer an address that otherwise answers as one that does not exist."""
    for pattern in patterns:
        if isinstance(pattern, URLPattern):
            pattern.callback = no_append_slash(pattern.callback)
        elif isinstance(pattern, URLResolver):
            _never_append_slash(pattern.url_patterns)
    return patterns


_admin_patterns, _admin_app, _admin_namespace = admin.site.urls

urlpatterns = [
    path("", include("shell.urls")),
    path("", include("access.urls")),
    path("", include("identity.urls")),
    path("", include("tenancy.urls")),
    # Confined by identity.middleware.FrameworkAdminMiddleware; never at the default path (DL-0210).
    path(
        settings.DJANGO_ADMIN_PATH,
        (_never_append_slash(_admin_patterns), _admin_app, _admin_namespace),
    ),
]

# Every address that does not exist answers as an object that may not be seen does (ADR-0008).
handler404 = "shell.views.not_found"

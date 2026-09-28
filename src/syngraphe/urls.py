"""The platform's routes; every app's routes are included here."""

from django.urls import include, path

urlpatterns = [
    path("", include("shell.urls")),
    path("", include("access.urls")),
]

# Every address that does not exist answers as an object that may not be seen does (ADR-0008).
handler404 = "shell.views.not_found"

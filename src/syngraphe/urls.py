"""The platform's routes; every app's routes are included here."""

from django.urls import path

from shell.views import health

urlpatterns = [
    path("health/", health, name="health"),
]

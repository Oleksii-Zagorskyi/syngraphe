"""Signing a person in: the framework's login and the session's fixed span, in one place."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import login
from django.http import HttpRequest
from django.utils import timezone

if TYPE_CHECKING:
    from identity.models import User


def start_session(request: HttpRequest, user: User) -> None:
    """Sign the person in for `SESSION_COOKIE_AGE` from now, not sliding (DL-0307): a later write
    to the session does not move the expiry. Sign-in and the first run both come through here."""
    login(request, user)
    request.session.set_expiry(timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE))

"""What every template knows: the organisation, the person's membership in it, their roles, how
many of their notifications are unread, which of *In edit* and *In review* are offered, and the
organisations they can switch to."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest

logger = logging.getLogger(__name__)


def _unread(request: HttpRequest, is_platform_admin: bool) -> int | None:
    """One count per schema the person reads: the organisation's, and the shared one for a
    platform administrator (DL-0382); `None` where there is no page to count for."""
    from notifications.services import platform_rows_for, unread_in_organisation

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    in_organisation = getattr(request, "tenant", None) is not None and (
        getattr(request, "membership", None) is not None or is_platform_admin
    )
    if not (in_organisation or is_platform_admin):
        return None
    count = 0
    if in_organisation:
        count += unread_in_organisation(user)
    if is_platform_admin:
        count += platform_rows_for(user).filter(read_at__isnull=True).count()
    return count


class _Views:
    """Whether each of *In edit* and *In review* holds anything — `None` where its link is not
    drawn: no organisation, not a member, or the right on no document; read once a template
    asks, at most once a request, and from the view's own answer on its page (DL-0197). And
    whether *My reservations* is drawn: while the person holds a reservation (DL-0241, DL-0525)."""

    def __init__(self, request: HttpRequest) -> None:
        self.request = request
        self._found: dict[str, bool | None] = {}

    def _read(self, view: str) -> bool | None:
        from access.rights import Right, holds_anywhere
        from documents.views import any_in_edit, any_in_review, is_member

        request = self.request
        user = getattr(request, "user", None)
        if user is None or getattr(request, "tenant", None) is None or not is_member(request):
            return None
        if view == "my_reservations":
            from editing.reservations import holds_one

            return True if holds_one(user) else None
        right, holds = (
            (Right.EDIT, any_in_edit) if view == "in_edit" else (Right.ACCEPT, any_in_review)
        )
        if not holds_anywhere(user, right):
            return None
        answered = getattr(request, "views_found", {})
        if view in answered:
            return bool(answered[view])
        try:
            return holds(user)
        except Exception:  # noqa: BLE001 — the menu must not fail the page it is drawn on
            logger.exception("whether a view holds anything could not be read")
            return False

    def __getitem__(self, view: str) -> bool | None:
        if view not in self._found:
            self._found[view] = self._read(view)
        return self._found[view]


class _Organisations:
    """The organisations a person reaches through an active membership, read once a template asks
    — the organisation's link and its list, drawn for two or more (ST-0007, ADR-0008, DL-0525)."""

    def __init__(self, request: HttpRequest) -> None:
        self.request = request
        self._found: list[Any] | None = None

    def __iter__(self) -> Any:
        return iter(self._read())

    def __len__(self) -> int:
        return len(self._read())

    def _read(self) -> list[Any]:
        if self._found is None:
            from identity.models import Membership

            user = getattr(self.request, "user", None)
            self._found = []
            if user is not None and user.is_authenticated:
                self._found = list(
                    Membership.objects.active()
                    .filter(user=user)
                    .order_by("tenant__name", "tenant__number")
                    .values("tenant__number", "tenant__name")
                )
        return self._found


def shell(request: HttpRequest) -> dict[str, Any]:
    from django.middleware.csrf import get_token

    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        # Every signed-in page sets the token's cookie: the panes' and the folder tree's own
        # requests read it, whether or not the page draws a form.
        get_token(request)
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
        "unread_notifications": _unread(request, is_platform_admin),
        "views": _Views(request),
        "organisations_of_person": _Organisations(request),
    }

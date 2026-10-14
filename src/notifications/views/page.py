"""The notifications page (DL-0204): two tabs, newest first, unread marked; the
administrative tab's filters for the events a person can receive, drawn only where there is a
choice (DL-0236); *mark all as read* on that tab alone."""

from __future__ import annotations

from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from identity.models import User
from mail.services import sender_for_queue
from notifications.events import (
    PLATFORM_ADMINISTRATIVE,
    TENANT_ADMINISTRATIVE,
    describe,
    label,
    tag,
)
from notifications.models import Category, Event, Notification
from notifications.services import mark_read_platform, openable, platform_rows_for
from notifications.views.detail import _in_organisation
from shell.views import not_found

TABS = (Category.DOCUMENT, Category.ADMINISTRATIVE)


def _receivable(request: HttpRequest, in_organisation: bool, platform: bool) -> list[Event]:
    """The administrative events this person can receive, in a fixed order."""
    from access.views import administers

    events: set[Event] = set()
    if in_organisation:
        events.add(Event.ACCESS_GRANTED)
        if administers(request):
            events |= set(TENANT_ADMINISTRATIVE)
    if platform:
        events |= set(PLATFORM_ADMINISTRATIVE)
    return [event for event in Event if event in events]


@never_cache
@login_required
def page(request: HttpRequest) -> HttpResponse:
    """The person's notifications under the tab `?tab=` names."""
    user = cast(User, request.user)
    in_organisation = _in_organisation(request)
    platform = bool(getattr(user, "acts_as_platform_admin", False))
    if request.method != "GET" or not (in_organisation or platform):
        return not_found(request)
    # Without an organisation only the shared rows exist, and they are all administrative.
    tabs = TABS if in_organisation else (Category.ADMINISTRATIVE,)
    tab = request.GET.get("tab", tabs[0])
    if tab not in tabs:
        tab = tabs[0]
    rows: list[Any] = []
    if in_organisation:
        rows += openable(
            user,
            Notification.objects.filter(user_id=user.pk, category=tab).select_related(
                "document", "correction_notice__acceptance"
            ),
        )
    if platform and tab == Category.ADMINISTRATIVE:
        rows += platform_rows_for(user)
    receivable = _receivable(request, in_organisation, platform)
    chosen = request.GET.get("event", "")
    if tab == Category.ADMINISTRATIVE and chosen in receivable:
        rows = [row for row in rows if row.event == chosen]
    rows.sort(key=lambda row: (row.created_at, str(row.pk)), reverse=True)
    membership = getattr(request, "membership", None)
    administrator = platform or bool(membership and membership.is_tenant_admin)
    context = {
        "tab": tab,
        "tabs": tabs,
        "entries": [
            {
                "id": row.pk,
                # Who reserved a document is told to administrators; a former one keeps the
                # entry and the fact, not the name (DL-0226).
                "text": describe(
                    row, named=administrator or row.event != Event.RESERVATION_STARTED
                ),
                "tag": tag(row),
                # A reason a person typed is read here, under the reader's own rights, never in
                # the email the entry's sentence becomes (DL-0369).
                "reason": (row.facts or {}).get("reason", "")
                if row.event == Event.RESERVATION_ENDED_BY_ADMIN
                else "",
                "unread": row.read_at is None,
                "at": row.created_at,
            }
            for row in rows
        ],
        "filters": (
            [{"event": event.value, "label": label(event)} for event in receivable]
            if tab == Category.ADMINISTRATIVE and len(receivable) > 1
            else []
        ),
        "chosen": chosen,
        # With no sender anywhere nothing is emailed, and the administrators are told (DL-0367).
        "no_sender": administrator and sender_for_queue() is None,
    }
    return render(request, "notifications/page.html", context)


@never_cache
@login_required
def read_all(request: HttpRequest) -> HttpResponse:
    """Mark every administrative notification of the person read, in either schema."""
    user = cast(User, request.user)
    in_organisation = _in_organisation(request)
    platform = bool(getattr(user, "acts_as_platform_admin", False))
    if request.method != "POST" or not (in_organisation or platform):
        return not_found(request)
    if in_organisation:
        Notification.objects.filter(
            user_id=user.pk, category=Category.ADMINISTRATIVE, read_at__isnull=True
        ).update(read_at=timezone.now())
    if platform:
        mark_read_platform(user)
    return HttpResponseRedirect(f"/notifications/?tab={Category.ADMINISTRATIVE}")

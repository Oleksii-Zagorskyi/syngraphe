"""A notification opened by the person it was written for: opening it marks it read and leads to
what it concerns. The address is the notification's, so only its person reaches it, and any text
follows their current rights (DL-0113). An organisation's row is looked for first; a platform
administrator's shared row after it."""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from notifications.models import Event, Notification
from notifications.services import mark_read_platform, openable, platform_rows_for
from shell.views import not_found


def _in_organisation(request: HttpRequest) -> bool:
    from documents.views import is_member

    return getattr(request, "tenant", None) is not None and is_member(request)


def _group_page(facts: dict[str, Any]) -> str:
    try:
        group = uuid.UUID(str(facts.get("group", "")))
    except ValueError:
        return reverse("groups")
    return reverse("group_members", args=[group])


def _target(request: HttpRequest, row: Any) -> str:
    """Where an entry leads (DL-0385): its document, or the page its event concerns."""
    from access.views import administers
    from documents.models import ROOT_FOLDER

    event = Event(row.event)
    facts = row.facts or {}
    if event == Event.BACKUP_CONDITION:
        return reverse("health")
    if event == Event.EMAIL_FAILED:
        # The outbox that holds the row (DL-0385): an organisation's while it is the one chosen,
        # else the administration, where it is chosen; the platform's for platform mail.
        if isinstance(row, Notification):
            return reverse("sending_address")
        if facts.get("tenant") is None:
            return reverse("platform_mail")
        chosen = getattr(request, "tenant", None)
        if chosen is not None and chosen.number == facts["tenant"]:
            return reverse("sending_address")
        return reverse("administration")
    if event in (Event.USER_PARTIALLY_BLOCKED, Event.TENANT_WITHOUT_ADMIN):
        # The organisations page, which shows each organisation's state and administrators; on an
        # organisation's domain, which never serves it (DL-0290), the administration.
        if getattr(request, "tenant_from_domain", True):
            return reverse("administration")
        return reverse("tenants")
    if event == Event.ACCESS_GRANTED:
        return _group_page(facts) if administers(request) else reverse("folder", args=[ROOT_FOLDER])
    if row.document is None:
        return reverse("notifications") + "?tab=administrative"
    # The version's own page is the historical page's; until it exists, the document (DL-0334).
    return reverse("document", args=[row.document.number])


@never_cache
@login_required
def detail(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    """The notification `pk`, to its own person alone; opening it marks it read."""
    from review.views.notice import page as correction_notice

    user = request.user
    if request.method != "GET" or user.pk is None:
        return not_found(request)
    if _in_organisation(request):
        row = (
            Notification.objects.filter(pk=pk, user_id=user.pk)
            .select_related("document", "correction_notice")
            .first()
        )
        # An entry the list hides — its document no longer opens for its reader — is missing
        # here too (DL-0386).
        if row is not None and openable(user, [row]):
            if row.read_at is None:
                Notification.objects.filter(pk=row.pk).update(read_at=timezone.now())
            if row.event == Event.CORRECTION_NOTICE:
                return correction_notice(request, row)
            return HttpResponseRedirect(_target(request, row))
    if getattr(user, "acts_as_platform_admin", False):
        shared = platform_rows_for(user).filter(pk=pk).first()
        if shared is not None:
            mark_read_platform(user, [shared.pk])
            return HttpResponseRedirect(_target(request, shared))
    return not_found(request)

"""A notification opened by the person it was written for, while a member of its organisation. Each
event renders through its own view; the address is the notification's, so only its person reaches
it, and any text follows their current rights (DL-0113)."""

from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from notifications.models import Event, Notification
from shell.views import not_found


@never_cache
@login_required
def detail(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    """The notification `pk`, to its own person alone; opening it marks it read."""
    from documents.views import _member
    from review.views.notice import page as correction_notice

    user_id = request.user.pk
    if (
        getattr(request, "tenant", None) is None
        or request.method != "GET"
        or user_id is None
        or not _member(request)
    ):
        return not_found(request)
    notification = (
        Notification.objects.filter(pk=pk, user_id=user_id)
        .select_related("document", "correction_notice")
        .first()
    )
    if notification is None or notification.event != Event.CORRECTION_NOTICE:
        return not_found(request)
    if notification.read_at is None:
        Notification.objects.filter(pk=notification.pk).update(read_at=timezone.now())
    return correction_notice(request, notification)

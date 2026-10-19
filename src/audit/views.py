"""Administration › Platform › Audit log (ST-0050): the newest events matching the filters, for a
platform administrator on a platform host alone (DL-0290). The page reads only the shared tables —
the events, their actors and organisations — and enters no organisation's schema (DL-0393)."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from audit.forms import PLATFORM, AuditFilterForm
from audit.models import AuditEvent
from audit.presenters import row
from shell.views import frame, not_found
from tenancy.views import _platform_admin

# As the outbox's pages bound theirs (DL-0392): the filters reach older events.
AUDIT_SHOWN = 200


def matching(cleaned: dict[str, Any]) -> list[AuditEvent]:
    """The newest `AUDIT_SHOWN` events the filters match, newest first, in one query."""
    events = AuditEvent.objects.select_related("actor", "tenant")
    organisation = cleaned.get("organisation")
    if organisation == PLATFORM:
        events = events.filter(tenant__isnull=True)
    elif organisation:
        events = events.filter(tenant__number=int(organisation))
    if cleaned.get("kind"):
        events = events.filter(actor_kind=cleaned["kind"])
    if cleaned.get("action"):
        events = events.filter(action__startswith=cleaned["action"])
    zone = ZoneInfo(settings.DISPLAY_TIMEZONE)
    if cleaned.get("since"):
        events = events.filter(at__gte=datetime.combine(cleaned["since"], time.min, tzinfo=zone))
    if cleaned.get("until"):
        events = events.filter(at__lte=datetime.combine(cleaned["until"], time.max, tzinfo=zone))
    return list(events.order_by("-at")[:AUDIT_SHOWN])


@never_cache
@login_required
def audit_log(request: HttpRequest) -> HttpResponse:
    """The filters and the events they match; a filter refused, its error and `400`."""
    if request.method != "GET" or not _platform_admin(request):
        return not_found(request)
    form = AuditFilterForm(request.GET)
    context: dict[str, Any] = {**frame(request), "form": form, "shown": AUDIT_SHOWN}
    if not form.is_valid():
        return render(request, "audit/log.html", context, status=400)
    events = matching(form.cleaned_data)
    context.update(rows=[row(e) for e in events], bounded=len(events) >= AUDIT_SHOWN)
    return render(request, "audit/log.html", context)

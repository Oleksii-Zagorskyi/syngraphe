"""Administration › Settings (ST-0053, ST-0030, ST-0062): the organisation's attachment size cap,
inactivity timeout and distinct-approver check, for its administrators and a platform administrator
who has chosen it; anyone else is answered as for a missing page. Each bound is named by the form
and the stored ones held by the database too (DL-0458, DL-0469)."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache

from access.views import administers
from identity.models import User
from shell.views import frame, not_found
from tenancy.models import INACTIVITY_LEAST, INACTIVITY_MOST, MB, Tenant
from tenancy.services import Refused, cap_most_bytes, change_settings

PAGE = "/administration/tenant/settings/"


def most_mb() -> int:
    """The largest cap an organisation may set, in whole MB."""
    return cap_most_bytes() // MB


class SettingsForm(forms.Form):
    attachment_max_mb = forms.IntegerField(label=gettext_lazy("Attachment size cap"))
    hold_inactivity_minutes = forms.IntegerField(label=gettext_lazy("Inactivity timeout"))
    require_distinct_approver = forms.BooleanField(
        label=gettext_lazy("Distinct approver check"),
        required=False,
        help_text=gettext_lazy(
            "When on, nobody who accepted a run since the previous edition may make the next one"
            " canonical."
        ),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        most = most_mb()
        cap = self.fields["attachment_max_mb"]
        cap.help_text = _("From 1 to %(most)s MB.") % {"most": most}
        cap.validators.append(_bounded(1, most, _("From 1 to %(most)s MB.") % {"most": most}))
        timeout = self.fields["hold_inactivity_minutes"]
        between = _("From %(least)s to %(most)s minutes.") % {
            "least": INACTIVITY_LEAST,
            "most": INACTIVITY_MOST,
        }
        timeout.help_text = between
        timeout.validators.append(_bounded(INACTIVITY_LEAST, INACTIVITY_MOST, between))


def _bounded(least: int, most: int, message: str) -> Any:
    def check(value: int) -> None:
        if not least <= value <= most:
            raise forms.ValidationError(message)

    return check


@never_cache
@login_required
def tenant_settings(request: HttpRequest) -> HttpResponse:
    """The page; `POST` saves the three settings and answers `303` to the page, or draws the form
    again with each refused value's bound and `400`, nothing saved."""
    if request.method not in ("GET", "POST") or not administers(request):
        return not_found(request)
    tenant = Tenant.objects.get(pk=request.tenant.pk)  # type: ignore[attr-defined]
    if request.method == "GET":
        return _page(request, SettingsForm(initial=_initial(tenant)))
    form = SettingsForm(request.POST)
    if not form.is_valid():
        return _page(request, form, status=400)
    try:
        change_settings(
            tenant,
            by=cast(User, request.user),
            attachment_max_bytes=form.cleaned_data["attachment_max_mb"] * MB,
            hold_inactivity_minutes=form.cleaned_data["hold_inactivity_minutes"],
            require_distinct_approver=form.cleaned_data["require_distinct_approver"],
        )
    except Refused as refused:
        form.add_error("attachment_max_mb", str(refused))
        return _page(request, form, status=400)
    response = HttpResponse(status=303)
    response["Location"] = PAGE
    return response


def _initial(tenant: Tenant) -> dict[str, Any]:
    return {
        "attachment_max_mb": tenant.attachment_max_bytes // MB,
        "hold_inactivity_minutes": tenant.hold_inactivity_minutes,
        "require_distinct_approver": tenant.require_distinct_approver,
    }


def _page(request: HttpRequest, form: SettingsForm, *, status: int = 200) -> HttpResponse:
    context = {**frame(request), "form": form, "page_url": PAGE}
    return render(request, "tenancy/settings.html", context, status=status)

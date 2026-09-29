"""A person's own preferences, kept per person across sessions (DL-0040, DL-0195): one route per
preference, each a POST that stores one value and returns to the page it was set from."""

from __future__ import annotations

from typing import cast

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme

from identity.models import User, UserPreference
from shell.views import not_found
from syngraphe.provenance import ActorKind

ON_OFF = ("on", "off")


def _back(request: HttpRequest) -> HttpResponseRedirect:
    """Back to the page the form named, when it is a path on this site; else the start."""
    target = request.POST.get("next", "")
    if not target.startswith("/") or not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        target = "/"
    return HttpResponseRedirect(target)


def _keep(user: User, key: str, value: str) -> None:
    UserPreference.objects.update_or_create(
        user=user,
        key=key,
        defaults={"value": value, "updated_by": user},
        create_defaults={
            "value": value,
            "created_by": user,
            "updated_by": user,
            "actor_kind": ActorKind.USER,
        },
    )


@login_required
def show_author(request: HttpRequest) -> HttpResponse:
    """*Show author*: `on` or `off`."""
    value = request.POST.get("show_author", "")
    if request.method != "POST" or value not in ON_OFF:
        return not_found(request)
    _keep(cast(User, request.user), "show_author", value)
    return _back(request)

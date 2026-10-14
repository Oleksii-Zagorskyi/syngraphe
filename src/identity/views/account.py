"""A person's own account: *Block my account…* (ST-0066, DL-0254, DL-0315)."""

from __future__ import annotations

from typing import cast

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from identity import blocking
from identity.models import User
from shell.views import not_found


@never_cache
@login_required
def block_account(request: HttpRequest) -> HttpResponse:
    """The confirmation, and the block: every organisation closes, every hold ends, and only a
    platform administrator can lift it, not from within the platform (DL-0254). The platform's
    last administrator is refused (DL-0315); a person already blocked has nothing to block."""
    person = cast(User, request.user)
    if request.method not in ("GET", "POST") or person.self_blocked:
        return not_found(request)
    last = blocking.is_last_platform_administrator(person)
    if request.method == "GET":
        return _page(request, last=last)
    try:
        blocking.self_block(person)
    except blocking.BlockRefused as refused:
        return _page(
            request,
            last=last or refused.reason == "last_platform_administrator",
            refused=refused.reason,
        )
    logout(request)
    return HttpResponseRedirect(reverse("signin"))


def _page(request: HttpRequest, *, last: bool, refused: str = "") -> HttpResponse:
    return render(request, "identity/block_account.html", {"last": last, "refused": refused})

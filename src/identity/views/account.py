"""A person's own account (DL-0499, DL-0500, DL-0523): its page, with the address, the display
name, the interface's language and, apart, *Block my account…* (ST-0066, DL-0254, DL-0315)."""

from __future__ import annotations

from typing import cast

from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from identity import blocking, names
from identity.language import PREFERENCE, language_of
from identity.models import User
from identity.names import NAME_MAX
from identity.views.preferences import _keep
from shell.views import not_found


@never_cache
@login_required
def account(request: HttpRequest) -> HttpResponse:
    """`/account/`: the person's address, their interface language with *Apply*, and the block.
    *Apply* keeps one of the languages the catalogue serves and returns to the page, which says
    so; any other value is refused with the page drawn again."""
    person = cast(User, request.user)
    if request.method == "GET":
        return _account(request, person, applied=bool(request.GET.get("applied")))
    if request.method != "POST":
        return not_found(request)
    if "display_name" in request.POST:
        return _name(request, person, request.POST["display_name"])
    chosen = request.POST.get("language", "")
    if chosen not in {code for code, _ in settings.LANGUAGES}:
        return _account(request, person, refused=True, status=400)
    _keep(person, PREFERENCE, chosen)
    return HttpResponseRedirect("/account/?applied=1", status=303)


def _name(request: HttpRequest, person: User, asked: str) -> HttpResponse:
    """The person's own display name (DL-0523): required, at most `NAME_MAX` characters once
    stripped, and free in each of their organisations; refused with the page drawn again and the
    field marked."""
    name = names.visible(asked)
    if not names.normal(name):
        problem = _("Write the name your colleagues will see.")
    elif not names.drawable(name):
        problem = _("The name holds a character that cannot be shown.")
    elif len(name) > NAME_MAX:
        problem = _("The name is at most %(count)s characters.") % {"count": NAME_MAX}
    else:
        clash = names.rename(person, name)
        if clash is None:
            return HttpResponseRedirect("/account/?named=1", status=303)
        # The organisation is not named: the refusal tells nobody where, or whose (DL-0537).
        problem = _("Another member already uses this name.")
    return _account(request, person, name_problem=problem, asked_name=asked, status=400)


def _account(
    request: HttpRequest,
    person: User,
    *,
    applied: bool = False,
    refused: bool = False,
    name_problem: str = "",
    asked_name: str | None = None,
    status: int = 200,
) -> HttpResponse:
    return render(
        request,
        "identity/account.html",
        {
            "chosen": language_of(person),
            "languages": settings.LANGUAGES,
            "last": blocking.is_last_platform_administrator(person),
            "applied": applied,
            "refused": refused,
            "named": bool(request.GET.get("named")),
            "name_problem": name_problem,
            "display_name": person.display_name if asked_name is None else asked_name,
            "name_max": NAME_MAX,
        },
        status=status,
    )


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

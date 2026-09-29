"""Signing in and out (ST-0008, DL-0116, T-14).

Every failure — a wrong password, an unknown or malformed address, an attempt made while the
delay runs — is one template, one status and one message. The unknown address costs a password
hash all the same: the framework's backend hashes the password it was given when no user matches.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables

from identity import throttle
from identity.forms import SignInForm
from identity.models import Membership, User
from identity.sessions import start_session
from shell.views import not_found
from tenancy.middleware import SESSION_TENANT_KEY


def _page(request: HttpRequest, form: SignInForm, failed: bool) -> HttpResponse:
    return render(request, "identity/signin.html", {"form": form, "failed": failed})


def _next(request: HttpRequest) -> str:
    target = request.GET.get("next", "")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=settings.SESSION_COOKIE_SECURE
    ):
        return target
    return "/"


def _sole_tenant(user: User) -> int | None:
    """The number of the tenant of the person's one active membership in an active organisation,
    or none."""
    numbers = list(
        Membership.objects.active().filter(user=user).values_list("tenant__number", flat=True)[:2]
    )
    return numbers[0] if len(numbers) == 1 else None


@never_cache
@sensitive_variables()
@sensitive_post_parameters("password")
def signin(request: HttpRequest) -> HttpResponse:
    if request.method not in ("GET", "POST"):
        return not_found(request)
    if request.user.is_authenticated:
        return HttpResponseRedirect(_next(request))
    if request.method == "GET":
        return _page(request, SignInForm(), failed=False)

    form = SignInForm(request.POST)
    email = form.cleaned_data["email"] if form.is_valid() else None
    device = throttle.device(request, email)
    attempt = throttle.keys(
        email, throttle.client_key(request), device.key if device is not None else None
    )
    user = None
    charged = throttle.charge(attempt)
    if charged.allowed and form.is_valid():
        user = authenticate(
            request, username=form.cleaned_data["email"], password=form.cleaned_data["password"]
        )
    else:
        throttle.spend_a_hash(request.POST.get("password", ""))
    if not isinstance(user, User):
        # A fresh form whatever failed, so a refused address and a wrong password render alike.
        return _page(request, SignInForm(initial={"email": request.POST.get("email", "")}), True)

    throttle.succeed(charged)
    start_session(request, user)
    if not getattr(request, "tenant_from_domain", True):
        tenant_number = _sole_tenant(user)
        if tenant_number is not None:
            request.session[SESSION_TENANT_KEY] = tenant_number
    User.objects.filter(pk=user.pk).update(last_login_at=timezone.now())
    response = HttpResponseRedirect(_next(request))
    throttle.issue_device(response, user, device)
    return response


def signout(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return not_found(request)
    logout(request)
    return HttpResponseRedirect(settings.LOGIN_URL)

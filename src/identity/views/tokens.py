"""Accepting an invitation and resetting a password: the request for a reset, and the pages a
single-use link opens (DL-0107, DL-0373).

Served to anyone, signed in or not. The request answers the same page for any address (ASR-17). A
token is looked up by its hash and its expiry together, so an expired token answers as an unknown
one; anything but a valid token — unknown, expired, used, or a method other than GET or POST — is
the uniform not-found answer (ADR-0008).
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables

from identity import invitations, resets, throttle
from identity.forms import ResetRequestForm, SetPasswordForm
from identity.models import Membership, User
from identity.sessions import start_session
from shell.views import not_found
from tenancy.middleware import SESSION_TENANT_KEY


def _signed_in(request: HttpRequest, user: User, tenant_number: int | None) -> HttpResponse:
    """Sign the person in — whoever was signed in on this browser is signed out — and, on the
    platform host, choose the organisation the link was for while they may reach it; with no
    organisation named, the one of their sole active membership, as signing in does."""
    start_session(request, user)
    if not getattr(request, "tenant_from_domain", True):
        reachable = Membership.objects.active().filter(user=user)
        if tenant_number is not None:
            reachable = reachable.filter(tenant__number=tenant_number)
        numbers = list(reachable.values_list("tenant__number", flat=True)[:2])
        if len(numbers) == 1:
            request.session[SESSION_TENANT_KEY] = numbers[0]
    return HttpResponseRedirect("/")


@never_cache
@sensitive_variables()
@sensitive_post_parameters("password", "password_again")
def accept_invitation(request: HttpRequest, token: str) -> HttpResponse:
    if request.method not in ("GET", "POST"):
        return not_found(request)
    user = invitations.person_of(token)
    if user is None:
        return not_found(request)
    if request.method == "GET":
        return _page(request, SetPasswordForm(user=user))
    form = SetPasswordForm(request.POST, user=user)
    if not form.is_valid():
        return _page(request, form)
    accepted = invitations.accept(token, form.cleaned_data["password"])
    if accepted is None:
        return not_found(request)
    person, invitation = accepted
    return _signed_in(request, person, invitation.tenant.number)


@never_cache
@sensitive_variables()
@sensitive_post_parameters("password", "password_again")
def reset_password(request: HttpRequest, token: str) -> HttpResponse:
    if request.method not in ("GET", "POST"):
        return not_found(request)
    user = resets.person_of(token)
    if user is None:
        return not_found(request)
    if request.method == "GET":
        return _page(request, SetPasswordForm(user=user))
    form = SetPasswordForm(request.POST, user=user)
    if not form.is_valid():
        return _page(request, form)
    person = resets.reset(token, form.cleaned_data["password"])
    if person is None:
        return not_found(request)
    return _signed_in(request, person, None)


@never_cache
def reset_request(request: HttpRequest) -> HttpResponse:
    """*Forgot your password?*: one page and one sentence after any address, known or not, throttled
    or not, with a sender or without (ASR-17)."""
    if request.method not in ("GET", "POST"):
        return not_found(request)
    if request.method == "GET":
        return _request_page(request, ResetRequestForm(), asked=False)
    form = ResetRequestForm(request.POST)
    if not form.is_valid():
        return _request_page(request, form, asked=False)
    from_domain = getattr(request, "tenant_from_domain", True)
    resets.request_reset(
        form.cleaned_data["email"],
        throttle.reset_key(throttle.client_key(request)),
        tenant=getattr(request, "tenant", None) if from_domain else None,
    )
    return _request_page(request, ResetRequestForm(), asked=True)


def _page(request: HttpRequest, form: SetPasswordForm) -> HttpResponse:
    return render(request, "identity/set_password.html", {"form": form})


def _request_page(request: HttpRequest, form: ResetRequestForm, *, asked: bool) -> HttpResponse:
    return render(request, "identity/reset_request.html", {"form": form, "asked": asked})

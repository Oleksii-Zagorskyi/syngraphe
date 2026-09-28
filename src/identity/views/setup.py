"""The first-run page: the setup token, then the first platform administrator (DL-0231, T-19).

Between the two steps the session holds the token's hash, never the token. Every refusal —
a wrong, used or expired token, an administrator already present, a tenant's domain, another
method — is the uniform not-found answer (ADR-0008).
"""

from __future__ import annotations

from django.contrib.auth import login
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables

from audit.record import record
from identity.forms import FirstAdministratorForm, SetupTokenForm
from identity.models import SetupToken, User
from identity.tokens import hash_token
from shell.views import not_found

SESSION_KEY = "setup_token_hash"


def _valid(token_hash: str) -> bool:
    return SetupToken.objects.filter(token_hash=token_hash, expires_at__gt=timezone.now()).exists()


def _open() -> bool:
    return (
        not User.objects.filter(is_platform_admin=True).exists()
        and SetupToken.objects.filter(expires_at__gt=timezone.now()).exists()
    )


def _page(
    request: HttpRequest, step: int, form: SetupTokenForm | FirstAdministratorForm
) -> HttpResponse:
    return render(request, "identity/setup.html", {"step": step, "form": form})


@never_cache
@sensitive_variables()
@sensitive_post_parameters("token", "password", "password_again")
def setup(request: HttpRequest) -> HttpResponse:
    if (
        request.method not in ("GET", "POST")
        # A request the middleware did not mark is refused, never taken for a platform host.
        or getattr(request, "tenant_from_domain", True)
        or not _open()
    ):
        return not_found(request)

    held = request.session.get(SESSION_KEY)
    if held is not None and not _valid(held):
        del request.session[SESSION_KEY]
        held = None

    if held is None:
        if request.method == "GET":
            return _page(request, 1, SetupTokenForm())
        token_form = SetupTokenForm(request.POST)
        if not token_form.is_valid():
            return not_found(request)
        token_hash = hash_token(token_form.cleaned_data["token"])
        if not _valid(token_hash):
            return not_found(request)
        # The token raises what the session may do, so the session gets a key of its own.
        request.session.cycle_key()
        request.session[SESSION_KEY] = token_hash
        return HttpResponseRedirect(reverse("setup"))

    if request.method == "GET":
        return _page(request, 2, FirstAdministratorForm())
    form = FirstAdministratorForm(request.POST)
    if not form.is_valid():
        return _page(request, 2, form)
    with transaction.atomic():
        SetupToken.lock_first_run()
        if (
            not SetupToken.objects.filter(token_hash=held, expires_at__gt=timezone.now()).exists()
            or User.objects.filter(is_platform_admin=True).exists()
        ):
            return not_found(request)
        admin = User.objects.create_user(
            form.cleaned_data["email"], form.cleaned_data["password"], is_platform_admin=True
        )
        SetupToken.objects.all().delete()
        record(
            actor=None,
            action="platform.first_administrator_created",
            obj=admin,
            before=None,
            after={"is_platform_admin": True},
        )
    del request.session[SESSION_KEY]
    login(request, admin)
    return HttpResponseRedirect(reverse("administration"))

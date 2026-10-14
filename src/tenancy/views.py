"""Administration › Platform — organisations, hosts and platform administrators (ST-0001,
ADR-0008), every page answering not-found to anyone but a platform administrator — and switching
organisation (ST-0007), which answers a person with an active membership."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from identity.models import Membership, User, member_in_good_standing_q
from shell.views import frame, not_found
from tenancy import services
from tenancy.forms import AppointForm, GrantForm, HostForm, TenantForm
from tenancy.middleware import SESSION_TENANT_KEY
from tenancy.models import PlatformHost, Tenant, TenantDomain, TenantState

# What the interface calls each state; `migrating` is internal (DL-0287).
STATE_LABELS = {
    TenantState.ACTIVE: pgettext_lazy("organisation state", "active"),
    TenantState.BLOCKED: pgettext_lazy("organisation state", "blocked"),
    TenantState.MIGRATING: pgettext_lazy("organisation state", "being set up"),
}


class Tampered(Exception):
    """A form no page of ours produces: an unknown action, row or organisation."""


def _platform_admin(request: HttpRequest) -> bool:
    """A platform administrator on a platform host: the platform's pages are never served on an
    organisation's domain, where a request already belongs to that organisation (DL-0290)."""
    return bool(getattr(request.user, "acts_as_platform_admin", False)) and not getattr(
        request, "tenant_from_domain", True
    )


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _page(request: HttpRequest, template: str, **context: Any) -> HttpResponse:
    return render(request, f"tenancy/{template}", {**frame(request), **context})


@login_required
def tenants(request: HttpRequest) -> HttpResponse:
    if request.method != "GET" or not _platform_admin(request):
        return not_found(request)
    listed = Tenant.objects.annotate(
        administrators=Count(
            "memberships",
            # Counted whatever the organisation's state: an operator deciding whether to lift a
            # block sees who would administer it.
            filter=Q(memberships__is_tenant_admin=True)
            & member_in_good_standing_q("memberships__"),
        )
    ).order_by("number")
    rows = [
        {
            "tenant": tenant,
            "state_label": STATE_LABELS[TenantState(tenant.state)],
            "administrators": tenant.administrators,
        }
        for tenant in listed
    ]
    return _page(request, "tenants.html", rows=rows)


@login_required
def tenant_new(request: HttpRequest) -> HttpResponse:
    if request.method not in ("GET", "POST") or not _platform_admin(request):
        return not_found(request)
    if request.method == "GET":
        return _page(request, "tenant_form.html", form=TenantForm())
    form = TenantForm(request.POST)
    if not form.is_valid():
        return _page(request, "tenant_form.html", form=form)
    services.create_tenant(form.cleaned_data["name"], form.person, by=_actor(request))
    return HttpResponseRedirect(reverse("tenants"))


@login_required
def hosts(request: HttpRequest) -> HttpResponse:
    if request.method not in ("GET", "POST") or not _platform_admin(request):
        return not_found(request)
    refusal = None
    form = HostForm()
    if request.method == "POST":
        try:
            _change_hosts(request)
        except Tampered:
            return not_found(request)
        except services.Refused as refused:
            refusal = str(refused)
            form = HostForm(request.POST)
        else:
            return HttpResponseRedirect(reverse("hosts"))
    platform_hosts = list(PlatformHost.objects.order_by("host"))
    domains = list(TenantDomain.objects.select_related("tenant").order_by("tenant__number", "host"))
    domains_of = Counter(domain.tenant_id for domain in domains)
    # *Remove* is offered exactly where `services.remove_host` allows it: never the platform's
    # last host, never a default among siblings; an organisation's sole domain may go.
    rows = [
        {
            "row": row,
            "belongs_to": None,
            "kind": "platform",
            "removable": not row.is_default and len(platform_hosts) > 1,
        }
        for row in platform_hosts
    ] + [
        {
            "row": row,
            "belongs_to": row.tenant,
            "kind": "domain",
            "removable": not row.is_default or domains_of[row.tenant_id] == 1,
        }
        for row in domains
    ]
    organisations = Tenant.objects.exclude(state=TenantState.MIGRATING).order_by("number")
    return _page(
        request, "hosts.html", rows=rows, form=form, refusal=refusal, organisations=organisations
    )


def _change_hosts(request: HttpRequest) -> None:
    """Add, make default or remove, as the form asks; `Tampered` for a form no page produces."""
    action = request.POST.get("action")
    by = _actor(request)
    if action == "add":
        form = HostForm(request.POST)
        if not form.is_valid():
            raise services.Refused(_("Not a host name."))
        tenant = _organisation(form.cleaned_data["belongs_to"])
        services.add_host(form.cleaned_data["host"], tenant, by=by)
        return
    row = _host_row(request.POST.get("id", ""))
    if action == "default":
        services.make_default(row, by=by)
    elif action == "remove":
        services.remove_host(row, by=by)
    else:
        raise Tampered


def _organisation(belongs_to: str) -> Tenant | None:
    if belongs_to == "platform":
        return None
    try:
        # Nothing but completing it for an organisation being set up (DL-0291).
        return Tenant.objects.exclude(state=TenantState.MIGRATING).get(number=int(belongs_to))
    except (ValueError, Tenant.DoesNotExist):
        raise Tampered from None


def _host_row(identifier: str) -> PlatformHost | TenantDomain:
    try:
        uuid.UUID(identifier)
    except ValueError:
        raise Tampered from None
    found: PlatformHost | TenantDomain | None = (
        PlatformHost.objects.filter(id=identifier).first()
        or TenantDomain.objects.select_related("tenant").filter(id=identifier).first()
    )
    if found is None:
        raise Tampered
    return found


@login_required
def switch(request: HttpRequest) -> HttpResponse:
    """Switch organisation (ST-0007, ADR-0008): on the platform host the session's organisation
    changes; on an organisation's domain, which carries its own session, the browser goes to the
    other's default domain, or the platform's default host when it has none, and signs in there.
    Only an organisation the person reaches through an active membership; anything else is the
    not-found answer. Reads the shared schema alone."""
    # The one place a link to another host is built, from the rows alone, never the request.
    from mail.services import link

    if request.method not in ("GET", "POST"):
        return not_found(request)
    field = "to" if request.method == "GET" else "organisation"
    source = request.GET if request.method == "GET" else request.POST
    try:
        number = int(source.get(field, ""))
    except ValueError:
        return not_found(request)
    membership = (
        Membership.objects.active()
        .filter(user=_actor(request), tenant__number=number)
        .select_related("tenant")
        .first()
    )
    if membership is None:
        return not_found(request)
    on_domain = getattr(request, "tenant_from_domain", True)
    if request.method == "GET":
        # The confirmation a switch from a domain arrives at: opening it writes nothing.
        if on_domain:
            return not_found(request)
        return render(request, "tenancy/switch.html", {"tenant": membership.tenant})
    if on_domain:
        if TenantDomain.objects.filter(tenant=membership.tenant, is_default=True).exists():
            return HttpResponseRedirect(link(membership.tenant, "/"))
        # The platform host carries a session of its own: the choice travels in the address and
        # is made there by the person's own POST.
        return HttpResponseRedirect(link(None, f"{reverse('switch_organisation')}?to={number}"))
    request.session[SESSION_TENANT_KEY] = number
    return HttpResponseRedirect("/")


@login_required
def administrators(request: HttpRequest) -> HttpResponse:
    """The platform's administrators, *grant to* and per row *revoke*; the last one's *revoke*
    drawn disabled with its reason (DL-0315)."""
    if request.method != "GET" or not _platform_admin(request):
        return not_found(request)
    return _administrators_page(request, GrantForm())


def _administrators_page(request: HttpRequest, form: GrantForm) -> HttpResponse:
    listed = User.objects.filter(is_platform_admin=True, is_tombstoned=False).order_by("email")
    holders = list(services.platform_administrators().values_list("pk", flat=True)[:2])
    return _page(
        request,
        "administrators.html",
        administrators=list(listed),
        last=holders[0] if len(holders) == 1 else None,
        form=form,
    )


@login_required
def administration_grant(request: HttpRequest) -> HttpResponse:
    if request.method != "POST" or not _platform_admin(request):
        return not_found(request)
    form = GrantForm(request.POST)
    if not form.is_valid():
        return _administrators_page(request, form)
    try:
        services.grant_platform_administration(form.person, by=_actor(request))
    except services.Refused:
        return not_found(request)
    return HttpResponseRedirect(reverse("administrators"))


@login_required
def administration_revoke(request: HttpRequest, user_id: uuid.UUID) -> HttpResponse:
    if request.method != "POST" or not _platform_admin(request):
        return not_found(request)
    person = User.objects.filter(pk=user_id, is_platform_admin=True).first()
    if person is None:
        return not_found(request)
    try:
        services.revoke_platform_administration(person, by=_actor(request))
    except services.Refused:
        # The control is drawn disabled; a request that reaches here was forged.
        return not_found(request)
    return HttpResponseRedirect(reverse("administrators"))


def _organisation_for_act(request: HttpRequest, number: int, state: str) -> Tenant | None:
    """The organisation an act on the organisations page names, in the state the act needs, to a
    platform administrator; otherwise `None`. An organisation being set up takes no act
    (DL-0291)."""
    if not _platform_admin(request):
        return None
    return Tenant.objects.filter(number=number, state=state).first()


@login_required
def tenant_block(request: HttpRequest, number: int) -> HttpResponse:
    """*Block…*: the confirmation, and the block (ST-0065)."""
    from identity.blocking import BlockRefused

    tenant = _organisation_for_act(request, number, TenantState.ACTIVE)
    if tenant is None or request.method not in ("GET", "POST"):
        return not_found(request)
    if request.method == "GET":
        return _page(request, "block_tenant.html", tenant=tenant)
    try:
        services.block_tenant(tenant, by=_actor(request))
    except services.Refused:
        return not_found(request)
    except BlockRefused:
        return _page(request, "block_tenant.html", tenant=tenant, busy=True)
    return HttpResponseRedirect(reverse("tenants"))


@login_required
def tenant_lift(request: HttpRequest, number: int) -> HttpResponse:
    """*Lift the block* on an organisation (ST-0071)."""
    tenant = _organisation_for_act(request, number, TenantState.BLOCKED)
    if tenant is None or request.method != "POST":
        return not_found(request)
    try:
        services.lift_tenant_block(tenant, by=_actor(request))
    except services.Refused:
        return not_found(request)
    return HttpResponseRedirect(reverse("tenants"))


@login_required
def tenant_appoint(request: HttpRequest, number: int) -> HttpResponse:
    """*Appoint an administrator…*: an active member, chosen by address (a platform page, so
    naming a missing person tells only a platform administrator)."""
    tenant = _organisation_for_act(request, number, TenantState.ACTIVE)
    if tenant is None or request.method not in ("GET", "POST"):
        return not_found(request)
    if request.method == "GET":
        return _page(request, "appoint_form.html", tenant=tenant, form=AppointForm(tenant=tenant))
    form = AppointForm(request.POST, tenant=tenant)
    if not form.is_valid():
        return _page(request, "appoint_form.html", tenant=tenant, form=form)
    try:
        appointed = services.appoint_administrator(tenant, form.membership, by=_actor(request))
    except services.Refused:
        return not_found(request)
    if not appointed:
        form.add_error("email", form.missing)
        return _page(request, "appoint_form.html", tenant=tenant, form=form)
    return HttpResponseRedirect(reverse("tenants"))

"""Administration › groups: the grid of rights, and the members of one group."""

from __future__ import annotations

import uuid
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from access.forms import GroupForm, MemberForm, RightForm
from access.models import AccessGroup
from access.rights import GRID, LABELS, Right, implied
from identity.models import Membership, MembershipState, User
from shell.views import not_found
from syngraphe.provenance import ActorKind
from tenancy.middleware import TenantRequest

GROUPS_URL = "/administration/tenant/groups/"
# A new group starts with these two rights (ADR-0007).
STARTING_RIGHTS = (Right.UPLOAD_ATTACHMENT, Right.REPLACE_ATTACHMENT)


def administers(request: HttpRequest) -> bool:
    """A tenant administrator of the resolved organisation, or a platform administrator."""
    if getattr(request, "tenant", None) is None:
        return False
    membership = getattr(request, "membership", None)
    return bool(getattr(request.user, "is_platform_admin", False)) or bool(
        membership and membership.is_tenant_admin
    )


def _actor(request: HttpRequest) -> User:
    """The signed-in person; every view here sits behind `login_required`."""
    return cast(User, request.user)


def _is_htmx(request: HttpRequest) -> bool:
    return bool(getattr(request, "htmx", False))


def _grid(request: HttpRequest, **extra: Any) -> dict[str, Any]:
    rows = []
    for group in AccessGroup.objects.prefetch_related("granted"):
        held = {Right(row.right) for row in group.granted.all()}
        effective = implied(held)
        cells = []
        for right in GRID:
            if right in held and right in effective:
                state = "held"
            elif right in held:
                # Stored but ineffective: a part right without `edit`.
                state = "inert"
            elif right in effective:
                state = "faint"
            else:
                state = ""
            cells.append(
                {
                    "right": right.value,
                    "label": LABELS[right],
                    "state": state,
                    "held": right in held,
                }
            )
        rows.append({"group": group, "cells": cells})
    return {
        "columns": [{"right": r.value, "label": LABELS[r]} for r in GRID],
        "rows": rows,
        "form": GroupForm(),
        "groups_url": GROUPS_URL,
        **extra,
    }


@login_required
@require_http_methods(["GET", "POST"])
def groups(request: HttpRequest) -> HttpResponse:
    if not administers(request):
        return not_found(request)
    if request.method == "POST":
        form = GroupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                group = AccessGroup.objects.create(
                    name=form.cleaned_data["name"],
                    created_by=_actor(request),
                    actor_kind=ActorKind.USER,
                )
                for right in STARTING_RIGHTS:
                    group.grant(right, by=_actor(request))
            return HttpResponseRedirect(GROUPS_URL)
        return render(request, "access/groups.html", _grid(request, form=form), status=400)
    return render(request, "access/groups.html", _grid(request))


@login_required
@require_http_methods(["POST"])
def group_rights(request: HttpRequest, group_id: uuid.UUID) -> HttpResponse:
    """Grant or revoke one right; answers with the grid, which htmx swaps in place."""
    if not administers(request):
        return not_found(request)
    group = AccessGroup.objects.filter(pk=group_id).first()
    form = RightForm(request.POST)
    if group is None or not form.is_valid():
        return not_found(request)
    right = Right(form.cleaned_data["right"])
    if form.cleaned_data["action"] == "grant":
        group.grant(right, by=_actor(request))
    else:
        group.revoke(right, by=_actor(request))
    return render(request, "access/groups.html", _grid(request))


def _members_context(request: HttpRequest, group: AccessGroup) -> dict[str, Any]:
    tenant = cast(TenantRequest, request).tenant
    members = group.members.select_related("membership__user").order_by("membership__user__email")
    in_group = {m.membership_id for m in members}
    candidates = (
        Membership.objects.filter(tenant=tenant, state=MembershipState.ACTIVE)
        .exclude(pk__in=in_group)
        .select_related("user")
        .order_by("user__email")
    )
    return {"group": group, "members": members, "candidates": candidates, "groups_url": GROUPS_URL}


def _members_response(request: HttpRequest, group: AccessGroup) -> HttpResponse:
    """The members list alone for htmx; inside the whole groups page for a plain request."""
    context = _members_context(request, group)
    if _is_htmx(request):
        return render(request, "access/group_members.html", context)
    return render(request, "access/groups.html", _grid(request, dialog=context))


@login_required
@require_http_methods(["GET", "POST"])
def group_members(request: HttpRequest, group_id: uuid.UUID) -> HttpResponse:
    """The members of one group; a POST adds or removes one and answers with the list."""
    if not administers(request):
        return not_found(request)
    group = AccessGroup.objects.filter(pk=group_id).first()
    if group is None:
        return not_found(request)
    if request.method == "POST":
        form = MemberForm(request.POST)
        if not form.is_valid():
            return not_found(request)
        tenant = cast(TenantRequest, request).tenant
        removing = form.cleaned_data["action"] == "remove"
        candidates = Membership.objects.filter(pk=form.cleaned_data["membership"], tenant=tenant)
        if not removing:
            # Only an active member joins a group; a blocked one may still be taken out.
            candidates = candidates.filter(state=MembershipState.ACTIVE)
        membership = candidates.first()
        if membership is None:
            return not_found(request)
        if removing:
            group.remove_member(membership, by=_actor(request))
        else:
            group.add_member(membership, by=_actor(request))
    return _members_response(request, group)

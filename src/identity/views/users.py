"""Administration › users: the organisation's memberships, *invite by email*, *block…* and *lift
the block* (ST-0003, ST-0054, ST-0004, ST-0072).

The page shows each membership as a tenant administrator may see it — `granted_at` and the
membership's own state, never whether an invitation was accepted nor a person's own block
(DL-0374, DL-0398) — so nothing on it tells a new person from one registered elsewhere (ASR-17).
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from access.models import AccessGroup
from access.views import administers
from identity import blocking, invitations
from identity.forms import InviteForm
from identity.models import Membership, MembershipState, User
from identity.presenters import membership_for_administrator
from shell.views import frame, not_found

USERS_URL = "/administration/tenant/users/"
INVITE_URL = "/administration/tenant/users/invite/"


@never_cache
@login_required
def users(request: HttpRequest) -> HttpResponse:
    """The organisation's memberships, in the order they were granted."""
    if request.method != "GET" or not administers(request):
        return not_found(request)
    tenant = getattr(request, "tenant", None)
    memberships = list(
        Membership.objects.filter(tenant=tenant)
        .select_related("user")
        .order_by("granted_at", "user__email")
    )
    # By the membership's own state, the one the page draws (DL-0398, DL-0409).
    standing = set(
        Membership.objects.filter(state=MembershipState.ACTIVE, tenant=tenant).values_list(
            "pk", "is_tenant_admin"
        )
    )
    administrators = {pk for pk, is_admin in standing if is_admin}
    rows = []
    for membership in memberships:
        row = membership_for_administrator(membership)
        # The organisation's last active administrator, while others remain, cannot be blocked;
        # the control is drawn disabled with its reason (DL-0233).
        row["last_administrator"] = administrators == {membership.pk} and len(standing) > 1
        row["id"] = membership.pk
        rows.append(row)
    return render(
        request,
        "identity/users.html",
        {**frame(request), "rows": rows, "invite_url": INVITE_URL, "users_url": USERS_URL},
    )


@never_cache
@login_required
def block(request: HttpRequest, membership_id: uuid.UUID) -> HttpResponse:
    """*Block…*: the organisations the administrator administers in which the person is an active
    member, the current one checked; blocking each chosen one in one transaction."""
    membership = _membership(request, membership_id)
    if membership is None or request.method not in ("GET", "POST"):
        return not_found(request)
    by = cast(User, request.user)
    offered = blocking.organisations_to_block(membership.user, by)
    if not any(tenant.pk == membership.tenant_id for tenant in offered):
        return not_found(request)
    if request.method == "GET":
        return _confirmation(request, membership, offered, [membership.tenant.number])
    chosen = {str(number) for number in request.POST.getlist("organisations")}
    blocked = [tenant for tenant in offered if str(tenant.number) in chosen]
    if not blocked:
        return _confirmation(request, membership, offered, [])
    try:
        with transaction.atomic():
            administered = []
            for tenant in blocked:
                found = Membership.objects.select_related("user").get(
                    tenant=tenant, user=membership.user
                )
                if found.is_tenant_admin and not found.user.self_blocked:
                    administered.append(tenant)
                blocking.block_membership(found, by=by, tell=False)
            # Told once, after every chosen organisation is blocked: the person is active
            # elsewhere only outside all of them.
            blocking.tell_the_platform(membership.user, blocked, by=by, administered=administered)
    except blocking.BlockRefused as refused:
        if refused.reason == "not_administrator":
            return not_found(request)
        return _confirmation(
            request, membership, offered, [t.number for t in blocked], refused=refused.reason
        )
    return HttpResponseRedirect(USERS_URL)


@never_cache
@login_required
def lift(request: HttpRequest, membership_id: uuid.UUID) -> HttpResponse:
    """*Lift the block* on a membership of this organisation."""
    membership = _membership(request, membership_id)
    if membership is None or request.method != "POST":
        return not_found(request)
    try:
        blocking.lift_membership_block(membership, by=cast(User, request.user))
    except blocking.BlockRefused:
        return not_found(request)
    return HttpResponseRedirect(USERS_URL)


def _membership(request: HttpRequest, membership_id: uuid.UUID) -> Membership | None:
    """A membership of the resolved organisation, to its administrators; otherwise `None`."""
    if not administers(request):
        return None
    return (
        Membership.objects.filter(pk=membership_id, tenant=getattr(request, "tenant", None))
        .select_related("user", "tenant")
        .first()
    )


def _confirmation(
    request: HttpRequest,
    membership: Membership,
    offered: list[Any],
    checked: list[int],
    *,
    refused: str = "",
) -> HttpResponse:
    context: dict[str, Any] = {
        **frame(request),
        "person": membership.user.email,
        "organisations": [
            {"number": tenant.number, "name": tenant.name, "checked": tenant.number in checked}
            for tenant in offered
        ],
        "refused": refused,
        "users_url": USERS_URL,
    }
    return render(request, "identity/block_confirm.html", context)


@never_cache
@login_required
def invite(request: HttpRequest) -> HttpResponse:
    """*Invite by email*: one page, one sentence whatever the address (ASR-17)."""
    if request.method not in ("GET", "POST") or not administers(request):
        return not_found(request)
    groups = list(AccessGroup.objects.order_by("name"))
    if request.method == "GET":
        return _page(request, InviteForm(groups=groups))
    form = InviteForm(request.POST, groups=groups)
    if not form.is_valid():
        return _page(request, form)
    chosen = [group for group in groups if str(group.pk) in form.cleaned_data["groups"]]
    tenant = getattr(request, "tenant", None)
    assert tenant is not None  # `administers` answers only with an organisation resolved
    try:
        invitations.invite(
            tenant,
            form.cleaned_data["email"],
            chosen,
            by=cast(User, request.user),
        )
    except invitations.NameTaken:
        return _page(request, form, name_taken=True)
    except invitations.Refused:
        return _page(request, form, refused=True)
    return _page(request, InviteForm(groups=groups), sent_to=form.cleaned_data["email"])


def _page(
    request: HttpRequest,
    form: InviteForm,
    *,
    refused: bool = False,
    name_taken: bool = False,
    sent_to: str = "",
) -> HttpResponse:
    context: dict[str, Any] = {
        **frame(request),
        "form": form,
        "refused": refused,
        "name_taken": name_taken,
        "sent_to": sent_to,
        "users_url": USERS_URL,
        "invite_url": INVITE_URL,
    }
    return render(request, "identity/invite.html", context)


@never_cache
@login_required
def member(request: HttpRequest, membership_id: uuid.UUID) -> HttpResponse:
    """One member's page (DL-0505, ST-0077): their groups, changed here, and what the groups and
    the documents' links give them per folder — read only, the membership's own state shown,
    never the person's own block (DL-0398)."""
    if request.method != "GET":
        return not_found(request)
    membership = _membership(request, membership_id)
    if membership is None:
        return not_found(request)
    return render(request, "identity/member.html", _member_context(request, membership))


@never_cache
@login_required
def member_groups(request: HttpRequest, membership_id: uuid.UUID) -> HttpResponse:
    """*Add* or *Remove* one group from the member's page, as the groups page's *members…* does:
    a blocked membership may be taken out of a group and joins none (DL-0505). Under htmx the
    answer is the member's whole section, so the rights beside the groups are redrawn with them."""
    from access.forms import GroupChoiceForm

    if request.method != "POST":
        return not_found(request)
    membership = _membership(request, membership_id)
    if membership is None:
        return not_found(request)
    form = GroupChoiceForm(request.POST)
    if not form.is_valid():
        return not_found(request)
    group = AccessGroup.objects.filter(pk=form.cleaned_data["group"]).first()
    if group is None:
        return not_found(request)
    actor = cast(User, request.user)
    if form.cleaned_data["action"] == "remove":
        group.remove_member(membership, by=actor)
    elif membership.state != MembershipState.ACTIVE:
        return not_found(request)
    else:
        group.add_member(membership, by=actor)
    context = _member_context(request, membership)
    if getattr(request, "htmx", False):
        return render(request, "identity/member_detail.html", context)
    return render(request, "identity/member.html", context)


def _member_context(request: HttpRequest, membership: Membership) -> dict[str, Any]:
    """The member's groups, the groups they could join, and — unless they administer the
    organisation, which their page says in one line — a row per document their groups reach,
    under its folder in tree order."""
    from access.models import GroupMember
    from access.rights import GRID, LABELS, member_rights
    from documents.models import Document
    from documents.tree import Tree

    joined = set(
        GroupMember.objects.filter(membership=membership).values_list("group_id", flat=True)
    )
    groups = list(AccessGroup.objects.order_by("name"))
    shown = membership_for_administrator(membership)
    context: dict[str, Any] = {
        **frame(request),
        "membership": membership,
        "shown": shown,
        "member_url": f"{USERS_URL}{membership.pk}/",
        "groups": [g for g in groups if g.pk in joined],
        "candidates": [g for g in groups if g.pk not in joined]
        if membership.state == MembershipState.ACTIVE
        else [],
        "blocked": membership.state != MembershipState.ACTIVE,
        "columns": [{"right": r.value, "label": LABELS[r]} for r in GRID],
    }
    if membership.is_tenant_admin:
        return context
    held = member_rights(membership)
    documents = Document.objects.filter(pk__in=held).select_related("folder").order_by("number")
    by_folder: dict[Any, list[Document]] = {}
    for document in documents:
        by_folder.setdefault(document.folder_id, []).append(document)
    tenant = getattr(request, "tenant", None)
    tree = Tree(tenant.name if tenant is not None else "")
    context["folders"] = [
        {
            "path": tree.path_of(node.folder),
            "rows": [
                {
                    "document": document,
                    "author": document.author_only and document.created_by_id == membership.user_id,
                    "cells": [{"right": r.value, "held": r in held[document.pk]} for r in GRID],
                }
                for document in by_folder[node.folder.pk]
            ],
        }
        for node in tree.flat()
        if node.folder.pk in by_folder
    ]
    return context

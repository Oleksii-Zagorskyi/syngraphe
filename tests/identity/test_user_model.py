"""The user row, the membership a tenant administrator sees, and the membership step."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import IntegrityError, transaction
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_email_is_case_folded_and_unique() -> None:
    from identity.models import User

    user = User.objects.create_user("A.Person@Example.test", "test-only-not-a-password")

    assert user.email == "a.person@example.test"
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("a.person@example.test", "test-only-not-a-password")


def test_membership_view_hides_user_creation_date() -> None:
    from identity.models import Membership, User
    from identity.presenters import membership_for_administrator
    from tenancy.models import Tenant

    user = User.objects.create_user("a.person@example.test", "test-only-not-a-password")
    tenant = Tenant.objects.create(name="Example Org", actor_kind="system")
    membership = Membership.objects.create(tenant=tenant, user=user, actor_kind="system")

    shown = membership_for_administrator(membership)

    assert "granted_at" in shown
    assert shown["granted_at"] == membership.granted_at
    assert "created_at" not in shown
    assert user.created_at not in shown.values()
    assert str(user.created_at) not in str(shown)


def _request_on(host: str, user: Any) -> tuple[HttpRequest, dict[str, Any]]:
    from tenancy.middleware import TenancyMiddleware

    request = RequestFactory().get("/", headers={"host": host})
    SessionMiddleware(lambda r: HttpResponse()).process_request(request)
    request.user = user
    seen: dict[str, Any] = {}

    def view(req: HttpRequest) -> HttpResponse:
        seen["membership"] = req.membership
        return HttpResponse("ok")

    TenancyMiddleware(view)(request)
    return request, seen


def test_membership_step_finds_the_active_membership() -> None:
    from identity.models import Membership, MembershipState, User
    from tenancy.models import Tenant, TenantDomain

    user = User.objects.create_user("a.person@example.test", "test-only-not-a-password")
    tenant = Tenant.objects.create(name="Example Org", state="active", actor_kind="system")
    TenantDomain.objects.create(
        tenant=tenant, host="docs.example.test", is_default=True, actor_kind="system"
    )
    membership = Membership.objects.create(tenant=tenant, user=user, actor_kind="system")

    _, seen = _request_on("docs.example.test", user)
    assert seen["membership"] == membership

    membership.change("state", MembershipState.BLOCKED, by=None)
    _, seen = _request_on("docs.example.test", user)
    assert seen["membership"] is None


def test_membership_step_closes_a_blocked_tenant_and_a_self_blocked_person() -> None:
    from identity.models import Membership, User
    from tenancy.models import Tenant, TenantDomain, TenantState

    user = User.objects.create_user("a.person@example.test", "test-only-not-a-password")
    tenant = Tenant.objects.create(name="Example Org", state="active", actor_kind="system")
    TenantDomain.objects.create(
        tenant=tenant, host="docs.example.test", is_default=True, actor_kind="system"
    )
    Membership.objects.create(tenant=tenant, user=user, actor_kind="system")

    user.self_blocked = True
    user.save()
    _, seen = _request_on("docs.example.test", user)
    assert seen["membership"] is None

    user.self_blocked = False
    user.save()
    tenant.state = TenantState.BLOCKED
    tenant.save()
    _, seen = _request_on("docs.example.test", user)
    assert seen["membership"] is None


def test_membership_changes_only_with_their_history() -> None:
    from identity.models import Membership, MembershipHistory, MembershipState, User
    from tenancy.models import Tenant

    user = User.objects.create_user("a.person@example.test", "test-only-not-a-password")
    admin = User.objects.create_user("an.admin@example.test", "test-only-not-a-password")
    tenant = Tenant.objects.create(name="Example Org", actor_kind="system")
    membership = Membership.objects.create(tenant=tenant, user=user, actor_kind="system")

    membership.state = MembershipState.BLOCKED
    with pytest.raises(RuntimeError):
        membership.save()

    membership.refresh_from_db()
    membership.change("is_tenant_admin", True, by=admin)
    membership.change("state", MembershipState.BLOCKED, by=None)

    rows = list(MembershipHistory.objects.filter(membership=membership))
    assert [(r.field, r.before, r.after, r.by, r.actor_kind) for r in rows] == [
        ("is_tenant_admin", "False", "True", admin, "user"),
        ("state", "active", "blocked", None, "system"),
    ]

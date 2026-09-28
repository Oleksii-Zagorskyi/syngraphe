"""Groups, their rights and members, and the history every change writes (ASR-08, ASR-18)."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_every_change_is_history(migrated_tenant: Any, member_of: Any) -> None:
    from access.models import AccessChange, AccessGroup
    from access.rights import Right
    from tenancy.schemas import schema_context

    _, admin, admin_membership = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, membership = member_of("a.member@example.test")

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Reviewers", created_by=admin, actor_kind="user")
        group.grant(Right.ACCEPT, by=admin)
        group.revoke(Right.ACCEPT, by=admin)
        group.add_member(membership, by=admin)
        rows = list(AccessChange.objects.filter(group=group).order_by("at"))

    assert [(r.kind, r.action, r.right, r.membership_id, r.by_id) for r in rows] == [
        ("right", "added", "accept", None, admin.id),
        ("right", "removed", "accept", None, admin.id),
        ("member", "added", "", membership.id, admin.id),
    ]
    assert all(r.at is not None and r.actor_kind == "user" for r in rows)


def test_rights_and_members_are_rows(migrated_tenant: Any, member_of: Any) -> None:
    from access.models import AccessGroup, GroupMember, GroupRight
    from access.rights import Right
    from tenancy.schemas import schema_context

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, membership = member_of("a.member@example.test")

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Editors", created_by=admin, actor_kind="user")
        group.grant(Right.EDIT, by=admin)
        group.grant(Right.EDIT, by=admin)
        group.add_member(membership, by=admin)
        group.remove_member(membership, by=admin)

        assert list(GroupRight.objects.filter(group=group).values_list("right", flat=True)) == [
            "edit"
        ]
        assert GroupMember.objects.filter(group=group).count() == 0
        assert set(group.rights()) == {Right.EDIT}
        assert Right.VIEW_PENDING in group.implied_rights()


def test_a_member_of_another_organisation_is_refused(migrated_tenant: Any, member_of: Any) -> None:
    from access.models import AccessGroup
    from identity.models import Membership, User
    from tenancy.models import Tenant
    from tenancy.schemas import schema_context

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    other = Tenant.objects.create(name="Other Org", actor_kind="system")
    stranger = User.objects.create_user("a.stranger@example.test", "test-only-not-a-password")
    elsewhere = Membership.objects.create(tenant=other, user=stranger, actor_kind="system")

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Editors", created_by=admin, actor_kind="user")
        with pytest.raises(ValueError):
            group.add_member(elsewhere, by=admin)
        assert group.members.count() == 0


@pytest.mark.django_db(transaction=False, serialized_rollback=False)
def test_guard_refuses_tenantless_query() -> None:
    from access.models import AccessGroup
    from tenancy.routers import TenantRequired

    with pytest.raises(TenantRequired):
        AccessGroup.objects.count()

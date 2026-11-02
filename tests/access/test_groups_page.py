"""Administration › groups: the grid of rights, stored as ticks and implied as faint ticks."""

from __future__ import annotations

import re
from typing import Any

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

GROUPS = "/administration/tenant/groups/"


def test_grid_shows_implied_rights_faint(migrated_tenant: Any, member_of: Any) -> None:
    from access.models import AccessGroup
    from access.rights import Right
    from tenancy.schemas import schema_context

    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Reviewers", created_by=admin, actor_kind="user")
        group.grant(Right.ACCEPT, by=admin)

    response = client.get(GROUPS)
    body = response.content.decode()

    assert response.status_code == 200
    assert "Reviewers" in body
    assert f'data-group="{group.id}" data-right="accept" class="right held"' in body
    assert f'data-group="{group.id}" data-right="edit" class="right faint"' in body
    assert f'data-group="{group.id}" data-right="create_and_edit" class="right"' in body


def test_non_admin_sees_nothing(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("a.member@example.test")

    response = client.get(GROUPS)

    assert response.status_code == 404
    assert 'class="content empty"' in response.content.decode()


def test_administrator_creates_a_group_grants_and_adds(
    migrated_tenant: Any, member_of: Any
) -> None:
    from access.models import AccessChange, AccessGroup
    from tenancy.schemas import schema_context

    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, membership = member_of("a.member@example.test")

    created = client.post(GROUPS, {"name": "Editors"})
    assert created.status_code == 302
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.get(name="Editors")

    granted = client.post(f"{GROUPS}{group.id}/rights/", {"right": "edit", "action": "grant"})
    added = client.post(f"{GROUPS}{group.id}/members/", {"membership": membership.id})
    members = client.get(f"{GROUPS}{group.id}/members/")

    assert granted.status_code == 200
    assert added.status_code == 200
    assert "a.member@example.test" in members.content.decode()
    with schema_context(migrated_tenant.number):
        # Two starting rights on creation, then the grant and the member.
        assert AccessChange.objects.filter(group=group).count() == 4
        assert all(c.by_id == admin.id for c in AccessChange.objects.filter(group=group))
        assert {"upload_attachment", "replace_attachment", "edit"} <= {
            r.right for r in group.granted.all()
        }


def test_a_blocked_member_cannot_be_added(migrated_tenant: Any, member_of: Any) -> None:
    from access.models import AccessGroup
    from identity.models import MembershipState
    from tenancy.schemas import schema_context

    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, _, membership = member_of("a.member@example.test")
    membership.change("state", MembershipState.BLOCKED, by=admin)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Editors", created_by=admin, actor_kind="user")

    response = client.post(f"{GROUPS}{group.id}/members/", {"membership": membership.id})

    assert response.status_code == 404
    with schema_context(migrated_tenant.number):
        assert group.members.count() == 0


def test_a_self_block_shows_through_no_group(migrated_tenant: Any, member_of: Any) -> None:
    """A person's own block is drawn on no organisation's page (DL-0398): their membership is a
    candidate and joins a group as any active member's does; they still reach nothing."""
    from access.models import AccessGroup
    from identity.models import User
    from tenancy.schemas import schema_context

    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, plain, plain_membership = member_of("plain.one@example.test")
    _, blocked, blocked_membership = member_of("blocked.on@example.test")
    User.objects.filter(pk=blocked.pk).update(self_blocked=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Editors", created_by=admin, actor_kind="user")
    members = f"{GROUPS}{group.id}/members/"

    page = client.get(members).content.decode()
    added = [
        client.post(members, {"membership": membership.id}).status_code
        for membership in (plain_membership, blocked_membership)
    ]

    assert f'value="{plain_membership.id}"' in page and f'value="{blocked_membership.id}"' in page
    assert added == [200, 200]
    with schema_context(migrated_tenant.number):
        assert group.members.count() == 2


def test_a_stored_part_right_without_edit_is_inert(migrated_tenant: Any, member_of: Any) -> None:
    from access.models import AccessGroup
    from access.rights import Right
    from tenancy.schemas import schema_context

    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Uploaders", created_by=admin, actor_kind="user")
        group.grant(Right.UPLOAD_ATTACHMENT, by=admin)

    body = client.get(GROUPS).content.decode()

    assert f'data-group="{group.id}" data-right="upload_attachment" class="right inert"' in body


def test_members_page_without_htmx_is_the_whole_page(migrated_tenant: Any, member_of: Any) -> None:
    from access.models import AccessGroup
    from tenancy.schemas import schema_context

    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Editors", created_by=admin, actor_kind="user")

    whole = client.get(f"{GROUPS}{group.id}/members/").content.decode()
    fragment = client.get(f"{GROUPS}{group.id}/members/", headers={"HX-Request": "true"})

    assert "<html" in whole and 'id="members"' in whole
    assert 'action="/administration/tenant/groups/" class="close"' in whole
    assert "<html" not in fragment.content.decode()


def test_platform_administrator_edits_the_chosen_organisation(
    migrated_tenant: Any, member_of: Any
) -> None:
    from django.test import Client

    from identity.models import User

    operator = User.objects.create_user(
        "an.operator@example.test", "test-only-not-a-password", is_platform_admin=True
    )
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(operator)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    assert client.get(GROUPS).status_code == 200


def test_the_members_block_stands_above_the_grid(
    migrated_tenant: Any, member_of: Any, settings: Any
) -> None:
    """A group's members open in a block at the top of the section, in view (DL-0506)."""
    settings.LANGUAGE_CODE = "en"
    from access.models import AccessGroup
    from tenancy.schemas import schema_context

    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Editors", created_by=admin, actor_kind="user")

    body = client.get(GROUPS).content.decode()

    assert body.index('id="dialog"') < body.index('<table class="grid"')
    assert 'hx-swap="innerHTML show:#dialog:top"' in body
    fragment = client.get(f"{GROUPS}{group.id}/members/", headers={"HX-Request": "true"})
    close = re.search(
        r'<form method="get" action="/administration/tenant/groups/"[^>]*>'
        r"\s*<button[^>]*>([^<]+)</button>",
        fragment.content.decode(),
    )
    assert close is not None and close.group(1) == "Close"

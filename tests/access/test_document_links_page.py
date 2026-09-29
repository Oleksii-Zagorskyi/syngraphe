"""Administration › document links: which groups reach which document, for administrators only.

Group names and people are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

URL = "/administration/tenant/document-links/"


def test_page_for_administrators_only(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    admin_client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member_client, creator, _ = member_of("the.creator@example.test")
    creator.display_name = "Авторка Приклад"
    creator.save()
    make_document(title="Синтетичний приклад", created_by=creator, author_only=True)

    as_admin = admin_client.get(URL)
    as_member = member_client.get(URL)

    body = as_admin.content.decode()
    assert as_admin.status_code == 200
    assert "Синтетичний приклад" in body
    assert "Авторка Приклад" in body
    assert 'class="tag author-only"' in body
    assert as_member.status_code == 404


def test_link_and_unlink_through_the_page(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup

    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(title="Синтетичний приклад", created_by=admin)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")

    linked = admin_client.post(
        f"{URL}{document.number}/", {"group": str(group.id), "action": "link"}
    )
    with schema_context(migrated_tenant.number):
        after_link = DocumentGroup.objects.filter(document=document, group=group).count()
    unlinked = admin_client.post(
        f"{URL}{document.number}/", {"group": str(group.id), "action": "unlink"}
    )
    with schema_context(migrated_tenant.number):
        after_unlink = DocumentGroup.objects.filter(document=document, group=group).count()

    assert linked.status_code == 302
    assert unlinked.status_code == 302
    assert (after_link, after_unlink) == (1, 0)


def test_members_cannot_link(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    from access.models import AccessGroup, DocumentGroup

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member_client, _, _ = member_of("a.member@example.test")
    document = make_document(created_by=admin)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")

    response = member_client.post(
        f"{URL}{document.number}/", {"group": str(group.id), "action": "link"}
    )

    assert response.status_code == 404
    with schema_context(migrated_tenant.number):
        assert not DocumentGroup.objects.exists()


def test_the_groups_page_shows_the_platform_pane(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("an.operator@example.test", is_platform_admin=True)

    body = client.get("/administration/tenant/groups/").content.decode()

    assert 'class="pane platform"' in body


def test_other_methods_answer_not_found(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    assert client.post(URL).status_code == 404
    assert client.get(f"{URL}1/").status_code == 404
    assert client.put("/administration/tenant/groups/").status_code == 404

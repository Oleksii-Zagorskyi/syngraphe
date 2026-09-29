"""Linking a group to a document: history for every change, the end of author-only, and no change
while someone holds the document (ADR-0007).

Group names and people are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_first_link_ends_author_only(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import AccessChange, AccessGroup, DocumentGroup
    from access.rights import Right, rights_on

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, creator, creator_membership = member_of("the.creator@example.test")
    document = make_document(created_by=creator, author_only=True)

    with schema_context(migrated_tenant.number):
        readers = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")
        readers.grant(Right.VIEW_CANONICAL, by=admin)
        readers.add_member(creator_membership, by=admin)
        DocumentGroup.link(document, readers, by=admin)
        document.refresh_from_db()
        changes = list(AccessChange.objects.filter(kind="link"))
        rights = rights_on(creator, document)

    assert document.author_only is False
    assert [(c.kind, c.action, c.group_id, c.document_id, c.by_id) for c in changes] == [
        ("link", "added", readers.id, document.id, admin.id)
    ]
    assert rights == {Right.VIEW_CANONICAL}


def test_link_twice_and_unlink(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    from access.models import AccessChange, AccessGroup, DocumentGroup

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(created_by=admin)

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")
        DocumentGroup.link(document, group, by=admin)
        DocumentGroup.link(document, group, by=admin)
        DocumentGroup.unlink(document, group, by=admin)
        DocumentGroup.unlink(document, group, by=admin)
        actions = list(AccessChange.objects.filter(kind="link").values_list("action", flat=True))
        remaining = DocumentGroup.objects.filter(document=document).count()
        document.refresh_from_db()

    assert actions == ["added", "removed"]
    assert remaining == 0
    # Author-only is where a document starts, never where the last unlink returns it.
    assert document.author_only is False


def test_links_frozen_while_held(
    migrated_tenant: Any, member_of: Any, make_document: Any, monkeypatch: Any
) -> None:
    from access.models import AccessChange, AccessGroup, DocumentGroup, DocumentHeld
    from documents import holds

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(created_by=admin)

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")
        DocumentGroup.link(document, group, by=admin)
        before = AccessChange.objects.count()
        monkeypatch.setattr(holds, "is_held", lambda document: True)

        with pytest.raises(DocumentHeld):
            DocumentGroup.unlink(document, group, by=admin)
        other = AccessGroup.objects.create(name="Others", created_by=admin, actor_kind="user")
        with pytest.raises(DocumentHeld):
            DocumentGroup.link(document, other, by=admin)

        assert AccessChange.objects.count() == before
        assert DocumentGroup.objects.filter(document=document).count() == 1


def test_a_document_being_created_cannot_be_linked(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(created_by=admin, state="creating")

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")
        with pytest.raises(ValueError):
            DocumentGroup.link(document, group, by=admin)

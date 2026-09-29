"""What a person may do with one document: the union of their linked groups' rights, the
author's own reach while the document is author-only, and the administrators' reading (ADR-0007,
ADR-0016).

Group names and people are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

VIEWS = {Right.VIEW_CANONICAL, Right.VIEW_ACCEPTED, Right.VIEW_PENDING}
HISTORY = {Right.VIEW_PREVIOUS_CANONICAL, Right.VIEW_ALL_HISTORY}


def _group(name: str, rights: list[Right], members: list[Any], admin: Any) -> Any:
    from access.models import AccessGroup

    group = AccessGroup.objects.create(name=name, created_by=admin, actor_kind="user")
    for right in rights:
        group.grant(right, by=admin)
    for membership in members:
        group.add_member(membership, by=admin)
    return group


def test_union_over_linked_groups_only(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import DocumentGroup
    from access.rights import rights_on

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, user, membership = member_of("a.reviewer@example.test")
    a = make_document(title="A", created_by=admin)
    b = make_document(title="B", created_by=admin)

    with schema_context(migrated_tenant.number):
        reviewers = _group("Reviewers", [Right.ACCEPT], [membership], admin)
        DocumentGroup.link(a, reviewers, by=admin)
        on_a, on_b = rights_on(user, a), rights_on(user, b)

    assert on_a == {Right.ACCEPT, Right.EDIT} | VIEWS
    assert on_b == frozenset()


def test_several_groups_add_up(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    from access.models import DocumentGroup
    from access.rights import rights_on

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, user, membership = member_of("a.member@example.test")
    document = make_document(created_by=admin)

    with schema_context(migrated_tenant.number):
        readers = _group("Readers", [Right.VIEW_CANONICAL], [membership], admin)
        auditors = _group("Auditors", [Right.VIEW_ALL_HISTORY], [membership], admin)
        unlinked = _group("Editors", [Right.EDIT], [membership], admin)
        DocumentGroup.link(document, readers, by=admin)
        DocumentGroup.link(document, auditors, by=admin)
        rights = rights_on(user, document)

    assert unlinked is not None
    assert rights == {Right.VIEW_CANONICAL, Right.VIEW_ALL_HISTORY}


def test_author_only_and_administrators(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.rights import rights_on

    _, creator, _ = member_of("the.creator@example.test")
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, stranger, _ = member_of("a.stranger@example.test")
    _, operator, _ = member_of("an.operator@example.test", is_platform_admin=True)
    document = make_document(created_by=creator, author_only=True)

    with schema_context(migrated_tenant.number):
        results = {
            who: rights_on(person, document)
            for who, person in (
                ("creator", creator),
                ("admin", admin),
                ("stranger", stranger),
                ("operator", operator),
            )
        }

    assert results["creator"] == {Right.EDIT} | VIEWS
    assert results["admin"] == VIEWS | HISTORY
    assert results["operator"] == VIEWS | HISTORY
    assert results["stranger"] == frozenset()


def test_an_administrator_in_a_linked_group_holds_both(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import DocumentGroup
    from access.rights import rights_on

    _, admin, admin_membership = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(created_by=admin)

    with schema_context(migrated_tenant.number):
        reviewers = _group("Reviewers", [Right.ACCEPT], [admin_membership], admin)
        DocumentGroup.link(document, reviewers, by=admin)
        rights = rights_on(admin, document)

    assert rights == {Right.ACCEPT, Right.EDIT} | VIEWS | HISTORY


def test_a_blocked_member_holds_nothing(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import DocumentGroup
    from access.rights import rights_on

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, user, membership = member_of("a.member@example.test")
    document = make_document(created_by=user, author_only=True)

    with schema_context(migrated_tenant.number):
        readers = _group("Readers", [Right.VIEW_CANONICAL], [membership], admin)
        other = make_document(created_by=admin)
        DocumentGroup.link(other, readers, by=admin)
        membership.change("state", "blocked", by=admin)
        rights = (rights_on(user, document), rights_on(user, other))

    assert rights == (frozenset(), frozenset())


def test_a_document_being_created_reaches_nobody(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.rights import rights_on

    _, creator, _ = member_of("the.creator@example.test")
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(created_by=creator, state="creating")

    with schema_context(migrated_tenant.number):
        assert rights_on(creator, document) == frozenset()
        assert rights_on(admin, document) == frozenset()


def test_can_create_reads_the_groups(migrated_tenant: Any, member_of: Any) -> None:
    from access.rights import can_create

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, author, membership = member_of("an.author@example.test")
    _, reader, reader_membership = member_of("a.reader@example.test")

    with schema_context(migrated_tenant.number):
        _group("Authors", [Right.CREATE_AND_EDIT], [membership], admin)
        _group("Readers", [Right.VIEW_CANONICAL], [reader_membership], admin)
        results = (
            can_create(author, migrated_tenant),
            can_create(reader, migrated_tenant),
            can_create(admin, migrated_tenant),
        )

    assert results == (True, False, False)


def test_a_part_right_needs_edit_in_the_same_group(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import DocumentGroup
    from access.rights import rights_on

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, user, membership = member_of("a.member@example.test")
    document = make_document(created_by=admin)

    with schema_context(migrated_tenant.number):
        uploaders = _group("Uploaders", [Right.UPLOAD_ATTACHMENT], [membership], admin)
        editors = _group("Editors", [Right.EDIT], [membership], admin)
        DocumentGroup.link(document, uploaders, by=admin)
        DocumentGroup.link(document, editors, by=admin)
        rights = rights_on(user, document)

    assert Right.EDIT in rights
    assert Right.UPLOAD_ATTACHMENT not in rights


def test_a_blocked_organisation_grants_nothing(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import DocumentGroup
    from access.rights import rights_on

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, user, membership = member_of("a.member@example.test")
    document = make_document(created_by=admin)
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(document, _group("Readers", [Right.EDIT], [membership], admin), by=admin)
    migrated_tenant.state = "blocked"
    migrated_tenant.save()

    with schema_context(migrated_tenant.number):
        assert rights_on(user, document) == frozenset()
        assert rights_on(admin, document) == frozenset()


@pytest.mark.parametrize("flag", ["self_blocked", "is_tombstoned"])
def test_a_blocked_or_former_person_holds_nothing(
    migrated_tenant: Any, member_of: Any, make_document: Any, flag: str
) -> None:
    from access.rights import can_create, rights_on

    _, operator, _ = member_of("an.operator@example.test", is_platform_admin=True)
    _, author, _ = member_of("the.creator@example.test")
    document = make_document(created_by=author, author_only=True)
    for person in (operator, author):
        setattr(person, flag, True)
        person.save()

    with schema_context(migrated_tenant.number):
        assert rights_on(operator, document) == frozenset()
        assert rights_on(author, document) == frozenset()
        assert can_create(author, migrated_tenant) is False


def test_an_archived_document_reaches_administrators_only(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import DocumentGroup
    from access.rights import rights_on

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, author, membership = member_of("the.creator@example.test")
    document = make_document(created_by=author)
    with schema_context(migrated_tenant.number):
        DocumentGroup.link(document, _group("Readers", [Right.EDIT], [membership], admin), by=admin)
        type(document).objects.filter(pk=document.pk).update(state="archived")

        assert rights_on(author, document) == frozenset()
        assert rights_on(admin, document) == VIEWS | HISTORY


def test_a_stale_instance_grants_nothing_the_row_does_not(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup
    from access.rights import rights_on
    from documents.models import Document

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, author, _ = member_of("the.creator@example.test")
    document = make_document(created_by=author, author_only=True)
    with schema_context(migrated_tenant.number):
        stale = Document.objects.get(pk=document.pk)
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")
        DocumentGroup.link(document, group, by=admin)

        assert stale.author_only is True
        assert rights_on(author, stale) == frozenset()


def test_another_tenants_member_holds_nothing(
    migrated_tenant: Any, member_of: Any, make_document: Any, make_tenant_schema: Any
) -> None:
    from access.rights import rights_on
    from identity.models import Membership, User

    _, author, _ = member_of("the.creator@example.test")
    document = make_document(created_by=author, author_only=True)
    other = make_tenant_schema("Other Org")
    outsider = User.objects.create_user("an.outsider@example.test", "test-only-not-a-password")
    Membership.objects.create(
        tenant=other, user=outsider, is_tenant_admin=True, actor_kind="system"
    )

    with schema_context(migrated_tenant.number):
        assert rights_on(outsider, document) == frozenset()
    with schema_context(other.number):
        assert rights_on(author, document) == frozenset()

"""The document list, minimal: the root folder's documents a person may read.

Group names, people and titles are synthetic examples."""

from __future__ import annotations

import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

ROOT = "/folder/1/"


def _rows(body: str) -> list[str]:
    return re.findall(r'<tr class="document"[^>]*data-number="(\d+)"', body)


def _readers(
    migrated_tenant: Any, admin: Any, membership: Any, *documents: Any, right: str = "view_accepted"
) -> None:
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right

    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", created_by=admin, actor_kind="user")
        group.grant(Right(right), by=admin)
        group.add_member(membership, by=admin)
        for document in documents:
            DocumentGroup.link(document, group, by=admin)


def test_list_shows_only_readable(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    client, _, membership = member_of("a.reader@example.test")
    b = make_document(title="Бета", created_by=admin, author_only=False)
    a = make_document(title="Альфа", created_by=admin, author_only=False)
    hidden = make_document(title="Гамма", created_by=admin, author_only=False)
    _readers(migrated_tenant, admin, membership, a, b)

    response = client.get(ROOT)
    body = response.content.decode()

    assert response.status_code == 200
    assert _rows(body) == [str(a.number), str(b.number)]
    assert "Гамма" not in body and f"#{hidden.number}" not in body
    assert body.count('class="part appendices absent"') == 2
    assert "Документ" in body


def test_titles_sort_as_ukrainian_is_read(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    titles = ["Явка", "Ґанок", "Бета", "Інструкція", "Євро", "апельсин"]
    numbers = {
        make_document(title=t, created_by=admin, author_only=False).number: t for t in titles
    }

    body = client.get(ROOT).content.decode()

    assert [numbers[int(n)] for n in _rows(body)] == [
        "апельсин",
        "Бета",
        "Ґанок",
        "Євро",
        "Інструкція",
        "Явка",
    ]


@pytest.mark.parametrize("right", ["view_canonical", "view_all_history"])
def test_no_edition_no_document_for_canonical_or_history_readers(
    migrated_tenant: Any, member_of: Any, make_document: Any, right: str
) -> None:
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    client, _, membership = member_of("a.reader@example.test")
    document = make_document(title="Без редакції", created_by=admin, author_only=False)
    _readers(migrated_tenant, admin, membership, document, right=right)

    assert _rows(client.get(ROOT).content.decode()) == []
    assert client.get(f"/document/{document.number}/").status_code == 404


def test_part_markers_follow_the_version_shown(
    migrated_tenant: Any, operator: Any, commit_parts: Any, reader_in: Any
) -> None:
    """The *Parts* icons describe the version the row's numbers name (DL-0209): an attachment in
    pending work shows to a reader of pending work, and not to a reader of accepted text."""
    from access.rights import Right
    from documents import services
    from documents.models import DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    with schema_context(migrated_tenant.number):
        document = services.create_document(
            operator.user,
            "З додатком",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
    commit_parts(
        document,
        operator.user,
        "Синтетичний текст.\n",
        [("Синтетична схема", "scheme.txt", "Синтетичний файл.\n".encode())],
    )
    pending_client, _ = reader_in(Right.VIEW_PENDING, document)
    accepted_client, _ = reader_in(Right.VIEW_ACCEPTED, document)

    as_pending = pending_client.get(ROOT).content.decode()
    as_accepted = accepted_client.get(ROOT).content.decode()

    assert 'class="part attachments"' in as_pending
    assert 'class="part attachments absent"' in as_accepted
    assert 'class="part appendices absent"' in as_pending


def test_author_only_visibility(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    creator_client, creator, _ = member_of("the.creator@example.test")
    other_client, _, _ = member_of("a.member@example.test")
    admin_client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(title="Чернетка", created_by=creator, author_only=True)

    seen = [
        str(document.number) in _rows(client.get(ROOT).content.decode())
        for client in (creator_client, other_client, admin_client)
    ]

    assert seen == [True, False, True]


def test_documents_being_created_are_not_listed(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    client, creator, _ = member_of("the.creator@example.test")
    make_document(title="Незавершений", created_by=creator, state="creating")

    assert _rows(client.get(ROOT).content.decode()) == []


def test_create_shows_for_its_holders_only(migrated_tenant: Any, member_of: Any) -> None:
    from access.models import AccessGroup
    from access.rights import Right

    author_client, _, membership = member_of("an.author@example.test")
    reader_client, _, _ = member_of("a.reader@example.test")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Authors", actor_kind="system")
        group.grant(Right.CREATE_AND_EDIT, by=None)
        group.add_member(membership, by=None)

    assert 'href="/document/new/"' in author_client.get(ROOT).content.decode()
    assert 'href="/document/new/"' not in reader_client.get(ROOT).content.decode()


def test_the_root_is_named_after_the_organisation(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("a.member@example.test")

    body = client.get(ROOT).content.decode()

    assert migrated_tenant.name in body


def test_other_folders_answer_not_found(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("a.member@example.test")

    assert client.get("/folder/2/").status_code == 404
    assert client.post(ROOT).status_code == 404


def test_the_root_path_opens_the_list(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("a.member@example.test")

    response = client.get("/")

    assert response.status_code == 302
    assert response["Location"] == ROOT


def test_a_non_member_on_the_organisations_domain_finds_nothing(
    migrated_tenant: Any, signed_in_without_tenant: Any
) -> None:
    from tenancy.models import TenantDomain

    TenantDomain.objects.create(
        tenant=migrated_tenant, host="example-org.test", is_default=True, actor_kind="system"
    )
    client = signed_in_without_tenant("an.outsider@example.test")

    assert client.get("/", headers={"host": "example-org.test"}).status_code == 404
    assert client.get(ROOT, headers={"host": "example-org.test"}).status_code == 404


def test_no_organisation_chosen(migrated_tenant: Any, signed_in_without_tenant: Any) -> None:
    operator = signed_in_without_tenant("an.operator@example.test", is_platform_admin=True)
    person = signed_in_without_tenant("a.person@example.test")

    to_administration = operator.get("/")
    nothing = person.get("/")

    assert (to_administration.status_code, to_administration["Location"]) == (
        302,
        "/administration/",
    )
    assert nothing.status_code == 404


def test_all_documents_in_the_navigation(migrated_tenant: Any, member_of: Any) -> None:
    client, _, _ = member_of("a.member@example.test")

    body = client.get(ROOT).content.decode()

    assert '<a href="/folder/1/"' in body

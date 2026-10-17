"""The document list: a folder's documents a person may read, sorted, with the ✎ column.

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
    b = make_document(title="Beta", created_by=admin, author_only=False)
    a = make_document(title="Alpha", created_by=admin, author_only=False)
    hidden = make_document(title="Gamma", created_by=admin, author_only=False)
    _readers(migrated_tenant, admin, membership, a, b)

    response = client.get(ROOT)
    body = response.content.decode()

    assert response.status_code == 200
    assert _rows(body) == [str(a.number), str(b.number)]
    assert "Gamma" not in body and f"#{hidden.number}" not in body
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
    document = make_document(title="Without an edition", created_by=admin, author_only=False)
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
            "With a part",
            "uk",
            DocumentType.objects.get(code="document"),
            Folder.objects.get(number=1),
        )
    commit_parts(
        document,
        operator.user,
        "Synthetic text.\n",
        [("Synthetic scheme", "scheme.txt", b"Synthetic file.\n")],
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
    document = make_document(title="Draft", created_by=creator, author_only=True)

    seen = [
        str(document.number) in _rows(client.get(ROOT).content.decode())
        for client in (creator_client, other_client, admin_client)
    ]

    assert seen == [True, False, True]


def test_documents_being_created_are_not_listed(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    client, creator, _ = member_of("the.creator@example.test")
    make_document(title="Unfinished", created_by=creator, state="creating")

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
    """A folder holding nothing the member reads answers as one that does not exist (DL-0206)."""
    from documents import folders
    from documents.models import Folder

    client, _, _ = member_of("a.member@example.test")
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        empty = folders.create_folder(Folder.objects.get(number=1), "Empty (synthetic)", by=admin)

    assert client.get(f"/folder/{empty.number}/").status_code == 404
    assert client.get("/folder/999/").status_code == 404
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
    # A member holding *edit* or *accept* on no document is offered neither view.
    assert 'data-nav="in-edit"' not in body and 'data-nav="in-review"' not in body


def test_sorting_by_number_or_title_both_ways(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    first = make_document(title="Charlie (synthetic)", created_by=admin, author_only=False)
    second = make_document(title="Alpha (synthetic)", created_by=admin, author_only=False)
    third = make_document(title="Bravo (synthetic)", created_by=admin, author_only=False)

    by_number = _rows(client.get(f"{ROOT}?sort=number&dir=desc").content.decode())
    by_title = client.get(f"{ROOT}?sort=title").content.decode()
    nonsense = _rows(client.get(f"{ROOT}?sort=nonsense&dir=sideways").content.decode())
    title_desc = _rows(client.get(f"{ROOT}?sort=title&dir=desc").content.decode())

    numbers = [str(d.number) for d in (third, second, first)]
    assert by_number == numbers
    assert _rows(by_title) == [str(second.number), str(third.number), str(first.number)]
    assert nonsense == _rows(by_title)
    assert title_desc == list(reversed(_rows(by_title)))
    # The active header names its direction and links to the other.
    assert 'href="?sort=title&amp;dir=desc"' in by_title and "▲" in by_title
    assert 'href="?sort=number&amp;dir=asc"' in by_title


def test_the_pencil_is_for_holders_of_edit(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right

    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    editor, _, editor_membership = member_of("an.editor@example.test")
    reader, _, reader_membership = member_of("a.reader@example.test")
    editable = make_document(title="Synthetic editable", created_by=admin, author_only=False)
    readable = make_document(title="Synthetic readable", created_by=admin, author_only=False)
    with schema_context(migrated_tenant.number):
        editors = AccessGroup.objects.create(name="Editors", created_by=admin, actor_kind="user")
        editors.grant(Right.EDIT, by=admin)
        editors.add_member(editor_membership, by=admin)
        DocumentGroup.link(editable, editors, by=admin)
        viewers = AccessGroup.objects.create(name="Viewers", created_by=admin, actor_kind="user")
        viewers.grant(Right.VIEW_ACCEPTED, by=admin)
        viewers.add_member(editor_membership, by=admin)
        DocumentGroup.link(readable, viewers, by=admin)
    _readers(migrated_tenant, admin, reader_membership, editable, readable)

    as_editor = editor.get(ROOT).content.decode()
    as_reader = reader.get(ROOT).content.decode()

    pencils = re.findall(r'<a class="icon" href="/document/(\d+)/edit/"[^>]*>✎</a>', as_editor)
    assert pencils == [str(editable.number)]
    # Both rows listed to both; the readable row's cell empty, the reader's column not drawn.
    both = sorted([str(editable.number), str(readable.number)])
    assert sorted(_rows(as_editor)) == both and sorted(_rows(as_reader)) == both
    row = as_editor.split(f'data-number="{readable.number}"', 1)[1].split("</tr>", 1)[0]
    assert '<td class="edit"></td>' in row
    assert "✎" not in as_reader

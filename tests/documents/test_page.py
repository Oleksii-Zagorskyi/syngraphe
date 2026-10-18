"""The document page, minimal: its header and the *Info* tab (DL-0208); what may not be seen
answers as what does not exist (ADR-0008).

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


def test_header_and_info(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any
) -> None:
    from datetime import UTC, datetime

    from documents.models import Document
    from identity.models import Language

    settings.DISPLAY_TIMEZONE = "Europe/Kyiv"
    client, creator, _ = member_of("the.creator@example.test")
    creator.display_name = "Synthetic Author"
    creator.save()
    Language.objects.update_or_create(
        code="uk", defaults={"label": "Українська", "actor_kind": "system"}
    )
    document = make_document(title="Synthetic example", created_by=creator)
    with schema_context(migrated_tenant.number):
        # Late in the evening in UTC is the next day in Kyiv.
        Document.objects.filter(pk=document.pk).update(
            created_at=datetime(2026, 9, 28, 22, 30, tzinfo=UTC)
        )

    # The View tab, at the document's own address, is `tests/rendering/test_view.py`'s: this
    # document has no repository to render.
    info = client.get(f"/document/{document.number}/info/")

    body = info.content.decode()
    assert info.status_code == 200
    assert f'<a href="/folder/1/">{migrated_tenant.name}</a> /' in body
    assert f"#{document.number}" in body
    assert "Synthetic example" in body
    assert "<dd>Українська</dd>" in body
    assert "<dd>Документ</dd>" in body
    assert f"<dd>{migrated_tenant.name}</dd>" in body
    assert "29 вересня 2026" in body and "Synthetic Author" in body
    # Only administrators are told a document is author-only.
    assert "author-only" not in body
    # No version shown, so nothing to say of a title page; no stylesheet applied.
    assert '<dd class="title-page-shown">—</dd>' in body
    assert '<dd class="style">Типовий вигляд платформи</dd>' in body


def test_administrators_see_author_only(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _, creator, _ = member_of("the.creator@example.test")
    document = make_document(created_by=creator, author_only=True)

    body = client.get(f"/document/{document.number}/info/").content.decode()

    assert "author-only" in body


def test_unreadable_and_missing_identical(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    client, _, _ = member_of("a.stranger@example.test")
    _, creator, _ = member_of("the.creator@example.test")
    hidden = make_document(title="Synthetic concealed", created_by=creator, author_only=True)
    being_created = make_document(title="Unfinished", created_by=creator, state="creating")

    responses = [
        client.get(path)
        for path in (
            f"/document/{hidden.number}/",
            f"/document/{hidden.number}/info/",
            f"/document/{being_created.number}/",
            "/document/9999/",
        )
    ]

    assert {r.status_code for r in responses} == {404}
    # The sign-out form's token is masked afresh in every response.
    token = re.compile(rb'name="csrfmiddlewaretoken" value="[^"]+"')
    assert len({token.sub(b"", r.content) for r in responses}) == 1
    assert "Synthetic concealed" not in responses[0].content.decode()


def test_another_organisations_document_is_missing(
    migrated_tenant: Any, member_of: Any, make_document: Any, make_tenant_schema: Any
) -> None:
    from identity.models import Membership

    client, user, _ = member_of("the.creator@example.test")
    document = make_document(title="Synthetic example", created_by=user)
    other = make_tenant_schema("Other Org")
    Membership.objects.create(tenant=other, user=user, actor_kind="system")
    session = client.session
    session["tenant_number"] = other.number
    session.save()

    assert client.get(f"/document/{document.number}/").status_code == 404


def test_a_reader_never_sees_the_creators_address(
    migrated_tenant: Any, member_of: Any, make_document: Any, settings: Any
) -> None:
    """The *Info* tab names a creator without a name *anonymous editor* to every reader,
    administrators included (DL-0434)."""
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right

    settings.LANGUAGE_CODE = "en"
    _, creator, _ = member_of("the.creator@example.test")
    reader, _, membership = member_of("a.reader@example.test")
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(created_by=creator, author_only=False)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", actor_kind="system")
        group.grant(Right.VIEW_ACCEPTED, by=None)
        group.add_member(membership, by=None)
        DocumentGroup.link(document, group, by=admin_user)

    as_reader = reader.get(f"/document/{document.number}/info/").content.decode()
    as_admin = admin.get(f"/document/{document.number}/info/").content.decode()

    assert "the.creator@example.test" not in as_reader
    assert "the.creator@example.test" not in as_admin
    assert "by anonymous editor" in as_reader and "by anonymous editor" in as_admin
    assert "Readers" in as_admin and "Readers" not in as_reader


def test_the_breadcrumb_and_info_name_the_folders_path(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """The breadcrumb links each folder of the path below the root; *Info* names the path, the
    organisation's name for a document in the root."""
    from documents import folders
    from documents.models import Folder

    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        a = folders.create_folder(Folder.objects.get(number=1), "A (synthetic example)", by=admin)
        b = folders.create_folder(a, "B (synthetic example)", by=admin)
    deep = make_document(title="Synthetic deep", folder=b)
    rooted = make_document(title="Synthetic rooted")

    deep_info = client.get(f"/document/{deep.number}/info/").content.decode()
    root_info = client.get(f"/document/{rooted.number}/info/").content.decode()

    crumb = deep_info.split('<nav class="breadcrumb">', 1)[1].split("</nav>", 1)[0]
    assert crumb == (
        f'<a href="/folder/{a.number}/">A (synthetic example)</a> / '
        f'<a href="/folder/{b.number}/">B (synthetic example)</a> /'
    )
    assert migrated_tenant.name not in crumb
    assert "<dd>A (synthetic example) / B (synthetic example)</dd>" in deep_info
    assert f'<nav class="breadcrumb"><a href="/folder/1/">{migrated_tenant.name}</a> /</nav>' in (
        root_info
    )
    assert f"<dd>{migrated_tenant.name}</dd>" in root_info


def test_every_tab_draws_the_folders_path(
    migrated_tenant: Any, member_of: Any, repo_root: Any
) -> None:
    """The breadcrumb is the page's header, so *History* and *Pending edits* draw the same path
    as *View* and *Info*."""
    from documents import folders, services
    from documents.models import DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        a = folders.create_folder(Folder.objects.get(number=1), "A (synthetic example)", by=admin)
        document = services.create_document(
            admin, "Synthetic tabbed", "uk", DocumentType.objects.get(code="document"), a
        )
    crumb = (
        f'<nav class="breadcrumb"><a href="/folder/{a.number}/">A (synthetic example)</a> /</nav>'
    )

    for tab in ("", "info/", "history/", "pending/"):
        body = client.get(f"/document/{document.number}/{tab}").content.decode()
        assert crumb in body, tab

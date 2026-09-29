"""The hold and the draft (ADR-0006): opening the edit tab takes the hold through the editor's POST,
another holder of *edit* sees *held* and nothing more, and links cannot change while it is open.

Group names, people and titles are synthetic examples."""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.db import connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

HELD = "This document is held"


def open_rows(tenant: Any, document: Any) -> tuple[int, int]:
    from editing.models import Draft, Hold

    with schema_context(tenant.number):
        return (
            Hold.objects.filter(document=document, released_at__isnull=True).count(),
            Draft.objects.filter(hold__document=document).count(),
        )


def test_opening_the_tab_takes_the_hold(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    from documents import bundle, gitstore
    from editing import holds
    from editing.models import Draft, Hold

    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)

    page = client.get(f"/document/{document.number}/edit/")
    assert page.status_code == 200
    assert 'id="editor"' in page.content.decode()
    assert open_rows(migrated_tenant, document) == (0, 0)

    taken = client.post(f"/document/{document.number}/edit/take/")
    assert taken.status_code == 200
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document, released_at__isnull=True)
        draft = Draft.objects.get(hold=hold)
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        assert head is not None
        stored = gitstore.read(repo, "document.md", head).decode()
    assert hold.user == author
    assert draft.base_commit == head
    assert draft.content["document.md"] == bundle.parse(stored)[1]
    assert holds.join(draft.content["frontmatter"], draft.content["document.md"]) == stored
    assert draft.content["frontmatter"]["title"] == document.title
    tabs = re.search(r'<nav class="tabs">.*?</nav>', page.content.decode(), re.S)
    assert tabs is not None
    assert tabs.group(0) == (
        f'<nav class="tabs"><a href="/document/{document.number}/">View</a>'
        f'<a href="/document/{document.number}/edit/" aria-current="page">'
        f'Edit</a><a href="/document/{document.number}/pending/">Pending edits</a>'
        f'<a href="/document/{document.number}/info/">Info</a></nav>'
    )
    info = client.get(f"/document/{document.number}/info/").content.decode()
    assert f'<a href="/document/{document.number}/info/" aria-current="page">Info</a>' in info


def test_held_tab_for_others(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    from access.rights import Right

    settings.LANGUAGE_CODE = "en"
    holder, author, own = member_of("the.holder@example.test")
    other, _, membership = member_of("another.editor@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [own, membership], author)
    assert holder.post(f"/document/{document.number}/edit/take/").status_code == 200

    page = other.get(f"/document/{document.number}/edit/")
    body = page.content.decode()
    assert page.status_code == 200
    assert HELD in body
    assert 'id="editor"' not in body
    assert "the.holder" not in body
    assert other.post(f"/document/{document.number}/edit/take/").status_code == 409
    assert open_rows(migrated_tenant, document) == (1, 1)


def test_links_locked_while_held(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup, DocumentHeld

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Читачі", created_by=author, actor_kind="user")
        with pytest.raises(DocumentHeld):
            DocumentGroup.link(document, group, by=author)


def test_edit_tab_needs_edit(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right

    _, author, _ = member_of("the.author@example.test")
    reader, _, membership = member_of("a.reader@example.test")
    document = new_document(author)
    link_group(document, [Right.VIEW_PENDING], [membership], author)

    assert reader.get(f"/document/{document.number}/edit/").status_code == 404
    assert reader.post(f"/document/{document.number}/edit/take/").status_code == 404
    info = reader.get(f"/document/{document.number}/info/").content.decode()
    assert f"/document/{document.number}/edit/" not in info
    assert open_rows(migrated_tenant, document) == (0, 0)


def test_reopening_is_idempotent(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    for _ in range(2):
        assert client.get(f"/document/{document.number}/edit/").status_code == 200
        assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    assert open_rows(migrated_tenant, document) == (1, 1)


def test_take_needs_the_csrf_token(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    _, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    strict = Client(enforce_csrf_checks=True, headers={"host": "127.0.0.1"})
    strict.force_login(author)
    session = strict.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    assert strict.post(f"/document/{document.number}/edit/take/").status_code == 403
    assert open_rows(migrated_tenant, document) == (0, 0)


def test_the_right_is_decided_under_the_locks(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A group unlinked while the taker waits for the document's lock is seen under it: no hold."""
    from access.models import DocumentGroup
    from access.rights import Right
    from editing import holds

    _, author, own = member_of("the.author@example.test")
    taker, _, membership = member_of("an.editor@example.test")
    document = new_document(author)
    group = link_group(document, [Right.EDIT], [own, membership], author)
    other = link_group(document, [Right.EDIT], [own], author)
    real_lock = holds.document_lock

    def unlink_first(*args: Any, **kwargs: Any) -> Any:
        with schema_context(migrated_tenant.number):
            DocumentGroup.unlink(document, group, by=author)
        return real_lock(*args, **kwargs)

    monkeypatch.setattr(holds, "document_lock", unlink_first)
    assert taker.post(f"/document/{document.number}/edit/take/").status_code == 404
    assert open_rows(migrated_tenant, document) == (0, 0)
    assert other is not None


def test_missing_and_forbidden_cost_the_same(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    _, author, _ = member_of("the.author@example.test")
    stranger, _, _ = member_of("a.stranger@example.test")
    document = new_document(author)
    stranger.get(f"/document/{document.number}/edit/")  # the host and the session, loaded once
    for suffix in ("edit/", "edit/take/"):
        counts = []
        for number in (document.number, 999999):
            with CaptureQueriesContext(connection) as queries:
                if suffix == "edit/":
                    response = stranger.get(f"/document/{number}/{suffix}")
                else:
                    response = stranger.post(f"/document/{number}/{suffix}")
            assert response.status_code == 404
            counts.append(len(queries))
        assert counts[0] == counts[1], suffix


def test_release_is_idempotent_and_names_no_releaser_for_a_finish(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from audit.models import AuditEvent
    from documents import holds as document_holds
    from documents.locks import document_lock
    from editing import holds
    from editing.models import Hold, ReleaseKind

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        hold = Hold.objects.get(document=document)
        with document_lock(migrated_tenant.number, document.number), transaction.atomic():
            assert holds.release(hold, ReleaseKind.FINISHED, actor=author) is True
            assert holds.release(hold, ReleaseKind.FINISHED, actor=author) is False
        hold.refresh_from_db()
        assert hold.released_by is None
        assert not document_holds.is_held(document)
    assert AuditEvent.objects.filter(action="document.hold_released").count() == 1


@pytest.mark.parametrize(
    ("site", "at_once"),
    [
        ("same-origin", True),
        ("none", True),
        ("cross-site", False),
        ("same-site", False),
        (None, False),
    ],
)
def test_the_tab_takes_the_hold_at_once_only_from_the_application(
    migrated_tenant: Any, member_of: Any, new_document: Any, site: str | None, at_once: bool
) -> None:
    """Opened from another site, or with no word from the browser, the tab waits for *Start
    editing*; from the application or typed in, it takes the hold as it mounts (DL-0325)."""
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    headers = {"Sec-Fetch-Site": site} if site else {}

    body = client.get(f"/document/{document.number}/edit/", headers=headers).content.decode()

    assert f'data-take-on-mount="{"true" if at_once else "false"}"' in body
    assert open_rows(migrated_tenant, document) == (0, 0)


def test_the_holder_reopening_from_elsewhere_is_not_asked(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    headers = {"Sec-Fetch-Site": "cross-site"}
    body = client.get(f"/document/{document.number}/edit/", headers=headers).content.decode()
    assert 'data-take-on-mount="true"' in body

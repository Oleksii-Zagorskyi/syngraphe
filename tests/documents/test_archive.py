"""Archive and restore (ST-0015, ST-0016, DL-0084, DL-0449, DL-0450): an administrator's acts,
audited with the document as object; an archived document leaves every list, answers as a missing
one to everyone but administrators, and comes back exactly as it was.

What administrators open and every act refused on an archived document are
`test_archive_gate.py`'s. Titles, groups, folders and people are synthetic examples."""

from __future__ import annotations

import html
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

_spec = importlib.util.spec_from_file_location(
    "archive_review_fixtures", Path(__file__).resolve().parents[1] / "review" / "conftest.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _review
_spec.loader.exec_module(_review)
new_document = _review.new_document
link_group = _review.link_group
commit_version = _review.commit_version

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "# Conditions\n\nThe first synthetic sentence.\n"
ROWS = re.compile(r'<tr class="document"[^>]*data-number="(\d+)"')


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"


def _events(action: str) -> list[Any]:
    from audit.models import AuditEvent

    return list(AuditEvent.objects.filter(action=action).order_by("at"))


def _archive(migrated_tenant: Any, document: Any, by: Any) -> bool:
    from documents import archive

    with schema_context(migrated_tenant.number):
        return archive.archive(document, by)


def _restore(migrated_tenant: Any, document: Any, by: Any) -> bool:
    from documents import archive

    with schema_context(migrated_tenant.number):
        return archive.restore(document, by)


def _state(migrated_tenant: Any, document: Any) -> str:
    from documents.models import Document

    with schema_context(migrated_tenant.number):
        return str(Document.objects.get(pk=document.pk).state)


def test_archive_and_restore_are_audited(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = new_document(admin, "Synthetic regulation")

    archived = _archive(migrated_tenant, document, admin)
    again = _archive(migrated_tenant, document, admin)
    state_archived = _state(migrated_tenant, document)
    restored = _restore(migrated_tenant, document, admin)
    restored_again = _restore(migrated_tenant, document, admin)

    assert (archived, again, restored, restored_again) == (True, False, True, False)
    assert state_archived == "archived" and _state(migrated_tenant, document) == "active"
    for action in ("document.archived", "document.restored"):
        (event,) = _events(action)
        assert event.object_type == "document" and event.object_id == document.pk
        assert event.after == {"number": document.number}
        assert event.actor_id == admin.pk


def test_an_archived_document_leaves_every_list(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    from access.rights import Right
    from documents import folders
    from documents.models import Document, Folder

    member, _, membership = member_of("a.member@example.test")
    _, admin, admin_membership = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        only = folders.create_folder(Folder.objects.get(number=1), "Only (synthetic)", by=admin)
    document = new_document(admin, "Synthetic travel rules")
    with schema_context(migrated_tenant.number):
        Document.objects.filter(pk=document.pk).update(folder=only)
    link_group(document, [Right.ACCEPT], [membership, admin_membership], admin)
    commit_version(document, admin, BODY, "edit")
    assert ROWS.findall(member.get(f"/folder/{only.number}/").content.decode())
    assert ROWS.findall(member.get("/in-review/").content.decode())

    _archive(migrated_tenant, document, admin)

    assert member.get(f"/folder/{only.number}/").status_code == 404
    assert "Only (synthetic)" not in member.get("/folder/1/").content.decode()
    assert member.get("/in-review/").status_code == 404
    answer = member.get(f"/document/{document.number}/")
    assert answer.status_code == 404 and "Nothing to show here" in answer.content.decode()
    assert not ROWS.findall(member.get("/search/?q=travel").content.decode())


def test_restored_exactly_as_it_was(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """A frozen document with a pending run, its links changed while archived: the freeze and the
    run as before; the links as they then stand decide who reads it."""
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right
    from editions import services as editions
    from editions.models import open_freeze

    old_reader, _, old_membership = member_of("an.old.reader@example.test")
    new_reader, _, new_membership = member_of("a.new.reader@example.test")
    _, admin, admin_membership = member_of("an.admin@example.test", is_tenant_admin=True)
    document = new_document(admin, "Synthetic frozen rules")
    old_group = link_group(document, [Right.VIEW_PENDING], [old_membership], admin)
    link_group(document, [Right.FREEZE, Right.ACCEPT], [admin_membership], admin)
    commit_version(document, admin, BODY, "edit")
    with schema_context(migrated_tenant.number):
        editions.freeze(document, admin, "Synthetic reason")
    pending_before = old_reader.get(f"/document/{document.number}/pending/").content.decode()

    _archive(migrated_tenant, document, admin)
    with schema_context(migrated_tenant.number):
        DocumentGroup.objects.filter(document=document, group=old_group).delete()
        group = AccessGroup.objects.create(name="New readers", created_by=admin, actor_kind="user")
        group.grant(Right.VIEW_PENDING, by=admin)
        group.add_member(new_membership, by=admin)
        DocumentGroup.link(document, group, by=admin)
    _restore(migrated_tenant, document, admin)

    with schema_context(migrated_tenant.number):
        assert open_freeze(document) is not None
    assert old_reader.get(f"/document/{document.number}/").status_code == 404
    pending_after = new_reader.get(f"/document/{document.number}/pending/")
    assert pending_after.status_code == 200
    assert re.findall(r"<ins\b", pending_after.content.decode()) == re.findall(
        r"<ins\b", pending_before
    )


def test_the_archive_page_lists_and_restores(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    from zoneinfo import ZoneInfo

    from django.utils import formats, translation

    from audit.models import AuditEvent

    settings.LANGUAGE_CODE = "en"
    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    first = new_document(admin, "Synthetic first archived")
    second = new_document(admin, "Synthetic second archived")
    # Archived one after the other: the second is the newer.
    _archive(migrated_tenant, first, admin)
    _archive(migrated_tenant, second, admin)

    page = admin_client.get("/administration/tenant/archive/").content.decode()
    restored = admin_client.post(f"/document/{first.number}/restore/")

    rows = re.findall(r'<tr data-number="(\d+)"', page)
    assert rows == [str(second.number), str(first.number)]
    assert f'action="/document/{first.number}/restore/"' in page
    assert f'href="/document/{first.number}/export/"' in page
    # Each row's date is its newest `document.archived` event's, in the display timezone.
    for document in (first, second):
        at = AuditEvent.objects.filter(action="document.archived", object_id=document.pk)
        when = at.latest("at").at.astimezone(ZoneInfo(settings.DISPLAY_TIMEZONE))
        with translation.override("en"):
            shown = formats.date_format(when, "j E Y")
        row = re.search(rf'<tr data-number="{document.number}">(.*?)</tr>', page, re.S)
        assert row is not None and f"<td>{shown}</td>" in row.group(1)
    assert restored.status_code == 302 and _state(migrated_tenant, first) == "active"
    empty = admin_client.get("/administration/tenant/archive/").content.decode()
    assert re.findall(r'<tr data-number="(\d+)"', empty) == [str(second.number)]


def test_the_archive_page_says_when_nothing_is_archived(
    migrated_tenant: Any, member_of: Any
) -> None:
    admin_client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    assert (
        "No document is archived."
        in admin_client.get("/administration/tenant/archive/").content.decode()
    )


def test_only_administrators_archive(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right

    member, _, membership = member_of("a.member@example.test")
    _, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = new_document(admin, "Synthetic regulation")
    link_group(document, list(Right), [membership], admin)

    answers = [
        member.post(f"/document/{document.number}/archive/"),
        member.post(f"/document/{document.number}/restore/"),
        member.get("/administration/tenant/archive/"),
    ]

    assert [a.status_code for a in answers] == [404, 404, 404]
    assert _state(migrated_tenant, document) == "active"
    assert _events("document.archived") == []


def test_archiving_from_the_page_and_back(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = new_document(admin, "Synthetic regulation")

    page = admin_client.get(f"/document/{document.number}/").content.decode()
    archived = admin_client.post(f"/document/{document.number}/archive/", follow=True)
    restored = admin_client.post(f"/document/{document.number}/restore/", follow=True)

    assert f'action="/document/{document.number}/archive/"' in page
    assert archived.status_code == 200 and "Archived." in archived.content.decode()
    assert f'action="/document/{document.number}/restore/"' in archived.content.decode()
    assert restored.status_code == 200 and "Restored." in restored.content.decode()
    assert _state(migrated_tenant, document) == "active"


def test_busy_and_incomplete_refusals(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from documents import archive
    from documents.locks import LockTimeout
    from review.services import RecordIncomplete

    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = new_document(admin, "Synthetic regulation")

    def busy(*args: Any, **kwargs: Any) -> Any:
        raise LockTimeout

    def incomplete(*args: Any, **kwargs: Any) -> Any:
        raise RecordIncomplete("synthetic")

    monkeypatch.setattr(archive, "archive", busy)
    first = admin_client.post(f"/document/{document.number}/archive/", follow=True)
    monkeypatch.setattr(archive, "archive", incomplete)
    second = admin_client.post(f"/document/{document.number}/archive/", follow=True)

    assert "The document is busy. Try again in a moment." in html.unescape(first.content.decode())
    assert "The document's record is incomplete" in html.unescape(second.content.decode())
    assert _state(migrated_tenant, document) == "active"


def test_the_type_of_an_archived_document_is_not_changed(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from documents import types
    from documents.models import Document

    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = new_document(admin, "Synthetic regulation")
    with schema_context(migrated_tenant.number):
        policy = types.add_type("policy (synthetic example)", by=admin)
    _archive(migrated_tenant, document, admin)

    info = admin_client.get(f"/document/{document.number}/info/").content.decode()
    posted = admin_client.post(
        f"/document/{document.number}/info/type/", {"document_type": policy.code}
    )

    form = info.split(f'action="/document/{document.number}/info/type/"', 1)[1].split("</form>", 1)[
        0
    ]
    assert "disabled" in form and "archived — restore it first" in info
    assert posted.status_code in (400, 404)
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=document.pk).document_type.code == "document"


def test_an_archived_documents_tabs_draw_no_act(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """Group rights do not reach an archived document (DL-0084): its tabs draw *Restore* and the
    disabled type choice, no *Edit* tab and no other act's form."""
    from access.rights import Right

    client, admin, membership = member_of("an.admin@example.test", is_tenant_admin=True)
    document = new_document(admin, "Synthetic regulation")
    link_group(document, list(Right), [membership], admin)
    commit_version(document, admin, BODY, "edit")
    _archive(migrated_tenant, document, admin)

    for tab in ("", "info/", "history/", "pending/"):
        body = client.get(f"/document/{document.number}/{tab}").content.decode()
        forms = set(re.findall(r'action="(/document/\d+/[^"]+)"', body))
        assert forms <= {
            f"/document/{document.number}/restore/",
            f"/document/{document.number}/info/type/",
        }, tab
        assert f'href="/document/{document.number}/edit/"' not in body, tab


cast = _review.cast


def test_a_held_writer_lock_refuses_the_archive(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another writer holds the document's lock: the archive waits its bound, then answers busy,
    nothing written."""
    import threading

    from django.db import connection

    from documents.locks import document_lock

    admin_client, admin, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = new_document(admin, "Synthetic regulation")
    monkeypatch.setattr("editing.holds.LOCK_WAIT_SECONDS", 0.2)
    entered, answered = threading.Event(), threading.Event()

    def hold_the_lock() -> None:
        try:
            with document_lock(migrated_tenant.number, document.number):
                entered.set()
                answered.wait(timeout=30)
        finally:
            connection.close()

    other = threading.Thread(target=hold_the_lock)
    other.start()
    try:
        assert entered.wait(timeout=10)
        answer = admin_client.post(f"/document/{document.number}/archive/", follow=True)
    finally:
        answered.set()
        other.join(timeout=30)

    assert "The document is busy. Try again in a moment." in html.unescape(answer.content.decode())
    assert _state(migrated_tenant, document) == "active"
    assert _events("document.archived") == []


def test_an_incomplete_record_refuses_the_archive(
    migrated_tenant: Any, member_of: Any, cast: Any, commit_version: Any
) -> None:
    """A second return section over a returned run, which the record cannot derive: settling the
    head refuses, and the archive with it, nothing written."""
    from django.utils import timezone

    from documents import bundle, gitstore
    from documents.identity import identity_for
    from documents.locks import document_lock
    from review import services

    admin_client, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    last = commit_version(document, people["a"], BODY, "edit")
    number = migrated_tenant.number
    with schema_context(number):
        services.return_run(document, people["r"], "Synthetic reason to return")
        repo = gitstore.open_repository(number, document.number)
        with document_lock(number, document.number):
            head = gitstore.head(repo)
            assert head is not None
            now = timezone.now().replace(microsecond=0)
            entry = bundle.PassportEntry(
                kind="return",
                number=None,
                at=now,
                by=str(people["r"].pk),
                version=last.commit_sha,
                reason="Synthetic reason to return",
            )
            passport = gitstore.read(repo, "passport.md", head).decode()
            gitstore.commit(
                repo,
                {"passport.md": bundle.append_passport(passport, entry).encode()},
                identity_for(people["r"], at=now),
                "Returned without accepting",
                gitstore.Kind.RETURN,
            )

    answer = admin_client.post(f"/document/{document.number}/archive/", follow=True)

    assert "The document's record is incomplete" in html.unescape(answer.content.decode())
    assert _state(migrated_tenant, document) == "active"
    assert _events("document.archived") == []

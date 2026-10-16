"""Folders (ST-0012, DL-0453): numbers from the organisation's sequence, names unique among
siblings in any case, an empty folder deleted, documents moved — the administrator's acts on
Administration › folders.

Folder names, people and titles are synthetic examples."""

from __future__ import annotations

import html
import threading
import uuid
from typing import Any

import pytest
from django.db import connection

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/tenant/folders/"


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    # The refusals' wording is read in English; the catalogue test reads the pages in `uk`.
    settings.LANGUAGE_CODE = "en"


def _events(action: str) -> list[Any]:
    from audit.models import AuditEvent

    return list(AuditEvent.objects.filter(action=action).order_by("at"))


def _folder(migrated_tenant: Any, **filters: Any) -> Any:
    from documents.models import Folder

    with schema_context(migrated_tenant.number):
        return Folder.objects.select_related("parent").filter(**filters).first()


def _make_folder(migrated_tenant: Any, by: Any, name: str, parent: int = 1) -> Any:
    from documents import folders
    from documents.models import Folder

    with schema_context(migrated_tenant.number):
        return folders.create_folder(Folder.objects.get(number=parent), name, by=by)


def test_numbers_come_from_the_sequence(migrated_tenant: Any, member_of: Any) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    first = admin.post(f"{PAGE}new/", {"parent": 1, "name": "Policies (synthetic example)"})
    second = admin.post(f"{PAGE}new/", {"parent": 2, "name": "Finance (synthetic example)"})
    refused = admin.post(f"{PAGE}new/", {"parent": 1, "name": "policies (synthetic example)"})
    third = admin.post(f"{PAGE}new/", {"parent": 1, "name": "Travel (synthetic example)"})

    assert [first.status_code, second.status_code, third.status_code] == [302, 302, 302]
    assert refused.status_code == 400
    assert first["Location"] == f"{PAGE}?folder=2"
    assert _folder(migrated_tenant, number=2).parent.number == 1
    assert _folder(migrated_tenant, number=3).parent.number == 2
    assert _folder(migrated_tenant, name="Travel (synthetic example)").number >= 4
    # A deleted folder's number is never given again.
    assert admin.post(f"{PAGE}3/delete/").status_code == 302
    again = admin.post(f"{PAGE}new/", {"parent": 2, "name": "Finance (synthetic example)"})
    assert again.status_code == 302
    given = [e.after["number"] for e in _events("folder.created")]
    assert given[-1] > max(given[:-1])
    created = _events("folder.created")[:3]
    assert [e.after for e in created[:2]] == [
        {"number": 2, "parent": 1},
        {"number": 3, "parent": 2},
    ]
    assert len(created) == 3
    assert all(e.object_type == "folder" for e in created)


def test_names_are_unique_among_siblings_ignoring_case(
    migrated_tenant: Any, member_of: Any
) -> None:
    from documents import folders
    from documents.models import Folder

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _make_folder(migrated_tenant, admin_user, "Policies (synthetic example)")
    other = _make_folder(migrated_tenant, admin_user, "Archive room (synthetic example)")

    taken = admin.post(f"{PAGE}new/", {"parent": 1, "name": "POLICIES (synthetic example)"})
    elsewhere = admin.post(
        f"{PAGE}new/", {"parent": other.number, "name": "Policies (synthetic example)"}
    )
    renamed = admin.post(f"{PAGE}{other.number}/rename/", {"name": "policies (Synthetic Example)"})

    assert taken.status_code == 400 and "already" in taken.content.decode()
    assert elsewhere.status_code == 302
    assert renamed.status_code == 400
    with schema_context(migrated_tenant.number):
        assert Folder.objects.filter(name__iexact="Policies (synthetic example)").count() == 2
        for name in ("", "   ", "x" * 201, "two\nlines"):
            with pytest.raises(folders.FolderRefused) as refused:
                folders.create_folder(Folder.objects.get(number=1), name, by=admin_user)
            assert refused.value.reason == "name_invalid"
        with pytest.raises(folders.FolderRefused) as refused:
            folders.create_folder(
                Folder.objects.get(number=1), "pOLICIES (synthetic example)", by=admin_user
            )
        assert refused.value.reason == "name_taken"
    # A rename to its own name in another case is the folder's own: allowed.
    assert (
        admin.post(
            f"{PAGE}{other.number}/rename/", {"name": "ARCHIVE ROOM (synthetic example)"}
        ).status_code
        == 302
    )
    (event,) = _events("folder.renamed")
    assert event.after == {"number": other.number}


def test_only_an_empty_folder_is_deleted(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from documents.models import Folder

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    holding = _make_folder(migrated_tenant, admin_user, "Holding (synthetic example)")
    parent = _make_folder(migrated_tenant, admin_user, "Parent (synthetic example)")
    _make_folder(migrated_tenant, admin_user, "Child (synthetic example)", parent=parent.number)
    keeping = _make_folder(migrated_tenant, admin_user, "Keeping (synthetic example)")
    empty = _make_folder(migrated_tenant, admin_user, "Empty (synthetic example)")
    make_document(title="Synthetic rule", folder=holding)
    make_document(title="Synthetic old rule", folder=keeping, state="archived")

    page = html.unescape(admin.get(f"{PAGE}?folder={keeping.number}").content.decode())
    answers = [admin.post(f"{PAGE}{f.number}/delete/") for f in (holding, parent, keeping)]
    deleted = admin.post(f"{PAGE}{empty.number}/delete/")

    assert [a.status_code for a in answers] == [400, 400, 400]
    refused = [html.unescape(a.content.decode()) for a in answers]
    assert "Only an empty folder can be deleted." in refused[0]
    assert "Holding (synthetic example) holds 1 document." in refused[0]
    assert "Parent (synthetic example) holds 1 folder." in refused[1]
    assert "0 " not in refused[0].split("holds", 1)[1].split(".", 1)[0]
    assert "Keeping (synthetic example) holds 1 document." in page
    acts = page.split('class="folder-acts"', 1)[1].split("</div>", 1)[0]
    assert "disabled" in acts and f"{PAGE}{keeping.number}/delete/" not in acts
    assert "Synthetic old rule" in page
    assert deleted.status_code == 302
    with schema_context(migrated_tenant.number):
        assert not Folder.objects.filter(pk=empty.pk).exists()
        assert Folder.objects.filter(pk__in=[holding.pk, parent.pk, keeping.pk]).count() == 3
    (event,) = _events("folder.deleted")
    assert event.after == {"number": empty.number, "parent": 1}


def test_moving_changes_the_folder_alone(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right
    from documents.models import Document

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    source = _make_folder(migrated_tenant, admin_user, "Source (synthetic example)")
    target = _make_folder(migrated_tenant, admin_user, "Target (synthetic example)")
    first = make_document(title="Synthetic one", folder=source, author_only=False)
    second = make_document(title="Synthetic two", folder=source)
    archived = make_document(title="Synthetic three", folder=source, state="archived")
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", actor_kind="system")
        group.grant(Right.VIEW_ACCEPTED, by=None)
        DocumentGroup.link(first, group, by=admin_user)
        before = {
            d.pk: (d.number, d.title, d.author_only, d.state, d.document_type_id, d.updated_at)
            for d in Document.objects.all()
        }

    form = admin.get(f"{PAGE}{source.number}/move/").content.decode()
    moved = admin.post(
        f"{PAGE}{source.number}/move/",
        {"document": [first.number, second.number], "to": target.number},
    )
    refused = admin.post(
        f"{PAGE}{source.number}/move/", {"document": [archived.number], "to": target.number}
    )

    assert f'name="document" value="{archived.number}"' not in form
    assert f'name="document" value="{first.number}"' in form
    assert moved.status_code == 302
    assert refused.status_code == 400
    with schema_context(migrated_tenant.number):
        rows = {d.pk: d for d in Document.objects.select_related("folder")}
        assert rows[first.pk].folder.number == rows[second.pk].folder.number == target.number
        assert rows[archived.pk].folder.number == source.number
        for pk, (number, title, author_only, state, kind, _updated) in before.items():
            row = rows[pk]
            assert (row.number, row.title, row.author_only, row.state, row.document_type_id) == (
                number,
                title,
                author_only,
                state,
                kind,
            )
        assert DocumentGroup.objects.filter(document_id=first.pk, group=group).exists()
    events = _events("document.moved")
    assert sorted(e.after["number"] for e in events) == sorted([first.number, second.number])
    assert all(e.after["from"] == source.number and e.after["to"] == target.number for e in events)

    with schema_context(migrated_tenant.number):
        from documents import folders

        mixed = [Document.objects.get(pk=archived.pk), Document.objects.get(pk=first.pk)]
        with pytest.raises(folders.FolderRefused) as batch:
            folders.move_documents(mixed, to=source, by=admin_user)
        assert batch.value.reason == "archived"
        assert Document.objects.get(pk=first.pk).folder_id == target.pk
        with pytest.raises(folders.FolderRefused) as same:
            folders.move_documents([Document.objects.get(pk=first.pk)], to=target, by=admin_user)
        assert same.value.reason == "same_folder"


def test_a_delete_and_a_move_into_it_serialise(
    migrated_tenant: Any,
    member_of: Any,
    make_document: Any,
    monkeypatch: pytest.MonkeyPatch,
    waiting_on_a_lock: Any,
) -> None:
    """The move holds the target's row when the delete reads it: the delete waits, then finds the
    document the move landed, and refuses."""
    from documents import folders
    from documents.models import Document, Folder

    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    target = _make_folder(migrated_tenant, admin_user, "Target (synthetic example)")
    document = make_document(title="Synthetic moved rule")
    locked = threading.Event()
    go = threading.Event()
    lock_target = folders._lock_target
    outcome: dict[str, Any] = {}

    def holding_the_target(folder: Any) -> Any:
        found = lock_target(folder)
        locked.set()
        go.wait(timeout=30)
        return found

    monkeypatch.setattr(folders, "_lock_target", holding_the_target)

    def move() -> None:
        try:
            with schema_context(migrated_tenant.number):
                outcome["moved"] = folders.move_documents(
                    [Document.objects.get(pk=document.pk)], to=target, by=admin_user
                )
        finally:
            connection.close()

    def delete() -> None:
        try:
            with schema_context(migrated_tenant.number):
                folders.delete_folder(Folder.objects.get(pk=target.pk), by=admin_user)
                outcome["deleted"] = True
        except folders.FolderRefused as refused:
            outcome["refused"] = refused.reason
        finally:
            connection.close()

    mover = threading.Thread(target=move)
    mover.start()
    assert locked.wait(timeout=10)
    deleter = threading.Thread(target=delete)
    deleter.start()
    # The delete has reached the target's row and waits on it; the move goes on only then.
    waited = waiting_on_a_lock()
    go.set()
    mover.join(timeout=30)
    deleter.join(timeout=30)

    assert waited
    assert outcome == {"moved": 1, "refused": "not_empty"}
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=document.pk).folder_id == target.pk
        assert Folder.objects.filter(pk=target.pk).exists()


def test_the_root_is_neither_renamed_nor_deleted(migrated_tenant: Any, member_of: Any) -> None:
    from documents import folders
    from documents.models import Folder

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    page = admin.get(PAGE).content.decode()
    renamed = admin.post(f"{PAGE}1/rename/", {"name": "Root (synthetic example)"})
    deleted = admin.post(f"{PAGE}1/delete/")

    assert f'action="{PAGE}1/rename/"' not in page
    assert f'action="{PAGE}1/delete/"' not in page
    assert [renamed.status_code, deleted.status_code] == [400, 400]
    with schema_context(migrated_tenant.number):
        root = Folder.objects.get(number=1)
        for act, args in ((folders.rename_folder, ("Root",)), (folders.delete_folder, ())):
            with pytest.raises(folders.FolderRefused) as refused:
                act(root, *args, by=admin_user)
            assert refused.value.reason == "root"
        assert root.name == ""


def test_the_page_is_an_administrators(migrated_tenant: Any, member_of: Any) -> None:
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member, _, _ = member_of("a.member@example.test")
    folder = _make_folder(migrated_tenant, admin_user, "Policies (synthetic example)")

    answers = [
        member.get(PAGE),
        member.get(f"{PAGE}?folder={folder.number}"),
        member.post(f"{PAGE}new/", {"parent": 1, "name": "Other (synthetic example)"}),
        member.post(f"{PAGE}{folder.number}/rename/", {"name": "Other (synthetic example)"}),
        member.post(f"{PAGE}{folder.number}/delete/"),
        member.get(f"{PAGE}{folder.number}/move/"),
        member.post(f"{PAGE}{folder.number}/move/", {"document": [1], "to": 1}),
    ]

    assert [a.status_code for a in answers] == [404] * len(answers)
    assert all("Nothing to show here" in a.content.decode() for a in answers)
    assert _folder(migrated_tenant, number=folder.number).name == "Policies (synthetic example)"
    assert admin.get(f"{PAGE}?folder=999").status_code == 404


def test_a_folder_deleted_before_a_creation_lands_is_refused_in_the_form(
    migrated_tenant: Any, member_of: Any
) -> None:
    """A creation into a folder deleted since the form offered it writes nothing and says why."""
    from documents import services
    from documents.models import Document, DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    doomed = _make_folder(migrated_tenant, admin_user, "Doomed (synthetic example)")
    with schema_context(migrated_tenant.number):
        Folder.objects.filter(pk=doomed.pk).delete()
        with pytest.raises(services.ChoiceGone) as gone:
            services.create_document(
                admin_user,
                "Synthetic plan",
                "uk",
                DocumentType.objects.get(code="document"),
                doomed,
            )
        assert gone.value.field == "folder"
        assert not Document.objects.exists()


def test_a_blocked_administrators_waiting_folder_act_is_refused(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Authority is read again under each act's locks."""
    from audit.models import AuditEvent
    from documents import folders
    from documents.models import Document, Folder
    from identity.models import Membership, MembershipState

    _, sender, membership = member_of("an.admin@example.test", is_tenant_admin=True)
    source = _make_folder(migrated_tenant, sender, "Source (synthetic example)")
    target = _make_folder(migrated_tenant, sender, "Target (synthetic example)")
    document = make_document(folder=source)
    before = AuditEvent.objects.count()
    Membership.objects.filter(pk=membership.pk).update(state=MembershipState.BLOCKED)

    with schema_context(migrated_tenant.number):
        root = Folder.objects.get(number=1)
        acts = (
            (folders.create_folder, (root, "New (synthetic example)")),
            (folders.rename_folder, (source, "Renamed (synthetic example)")),
            (folders.delete_folder, (target,)),
            (folders.move_documents, ([Document.objects.get(pk=document.pk)], target)),
        )
        for act, args in acts:
            with pytest.raises(folders.FolderRefused) as refused:
                act(*args, by=sender)
            assert refused.value.reason == "not_allowed", act
        assert Folder.objects.count() == 3
        assert Document.objects.get(pk=document.pk).folder_id == source.pk
    assert AuditEvent.objects.count() == before


def test_a_stranger_finds_no_folder_and_a_crafted_move_moves_nothing(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from django.test import Client

    from documents.models import Document
    from identity.models import Membership, User
    from tenancy.models import Tenant

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member, _, _ = member_of("a.member@example.test")
    source = _make_folder(migrated_tenant, admin_user, "Source (synthetic example)")
    other = _make_folder(migrated_tenant, admin_user, "Other (synthetic example)")
    target = _make_folder(migrated_tenant, admin_user, "Target (synthetic example)")
    elsewhere_doc = make_document(title="Synthetic elsewhere", folder=other)
    creating = make_document(title="Synthetic unfinished", folder=source, state="creating")
    elsewhere = Tenant.objects.create(name="Other Org (synthetic example)", actor_kind="system")
    stranger = User.objects.create_user("an.admin@elsewhere.test", "test-only-not-a-password")
    Membership.objects.create(
        tenant=elsewhere, user=stranger, is_tenant_admin=True, actor_kind="system"
    )
    outsider = Client(headers={"host": "127.0.0.1"})
    outsider.force_login(stranger)
    session = outsider.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    seen = [
        member.get(f"{PAGE}?folder={source.number}"),
        member.get(f"{PAGE}?folder=999"),
        outsider.get(PAGE),
        outsider.get(f"{PAGE}?folder={source.number}"),
        admin.get(f"{PAGE}?folder=0"),
    ]
    crafted = [
        admin.post(
            f"{PAGE}{source.number}/move/",
            {"document": [elsewhere_doc.number], "to": target.number},
        ),
        admin.post(
            f"{PAGE}{source.number}/move/", {"document": [creating.number], "to": target.number}
        ),
    ]

    assert [a.status_code for a in seen] == [404] * len(seen)
    assert all("Nothing to show here" in a.content.decode() for a in seen)
    assert [a.status_code for a in crafted] == [400, 400]
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=elsewhere_doc.pk).folder_id == other.pk
        assert Document.objects.get(pk=creating.pk).folder_id == source.pk


def test_a_move_refuses_what_left_its_folder_meanwhile(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """The service reads each document again under its lock: one moved elsewhere since the page
    listed it, or not active, refuses the batch whole."""
    from documents import folders
    from documents.models import Document

    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    source = _make_folder(migrated_tenant, admin_user, "Source (synthetic example)")
    other = _make_folder(migrated_tenant, admin_user, "Other (synthetic example)")
    target = _make_folder(migrated_tenant, admin_user, "Target (synthetic example)")
    stays = make_document(title="Synthetic stays", folder=source)
    left = make_document(title="Synthetic left", folder=source)
    unfinished = make_document(title="Synthetic unfinished", folder=source, state="creating")
    with schema_context(migrated_tenant.number):
        listed = [Document.objects.get(pk=stays.pk), Document.objects.get(pk=left.pk)]
        Document.objects.filter(pk=left.pk).update(folder=other)
        with pytest.raises(folders.FolderRefused) as refused:
            folders.move_documents(listed, to=target, by=admin_user, source=source)
        assert refused.value.reason == "not_in_folder"
        with pytest.raises(folders.FolderRefused) as refused:
            folders.move_documents(
                [Document.objects.get(pk=unfinished.pk)], to=target, by=admin_user
            )
        assert refused.value.reason == "not_in_folder"
        assert Document.objects.get(pk=stays.pk).folder_id == source.pk


def test_a_folder_deleted_before_a_creation_lands_is_refused_through_the_form(
    migrated_tenant: Any, member_of: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from access.models import AccessGroup
    from access.rights import Right
    from documents import services, views
    from documents.models import Document, DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    creator, _, membership = member_of("a.creator@example.test")
    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Creators", actor_kind="system")
        group.grant(Right.CREATE_AND_EDIT, by=None)
        group.add_member(membership, by=None)
        root = Folder.objects.get(number=1)
        kind = DocumentType.objects.get(code="document")
    create = services.create_document

    def folder_gone(user: Any, title: Any, language: Any, document_type: Any, folder: Any) -> Any:
        # The form offers only folders that exist; the one it chose goes before the row lands.
        doomed = Folder(pk=uuid.uuid4(), number=999, name="gone")
        return create(user, title, language, document_type, doomed)

    monkeypatch.setattr(views, "create_document", folder_gone)
    answer = creator.post(
        "/document/new/",
        {
            "title": "Synthetic plan",
            "language": "uk",
            "document_type": str(kind.pk),
            "folder": str(root.pk),
        },
    )

    assert answer.status_code == 400
    body = answer.content.decode()
    assert "This folder no longer exists" in body and "Synthetic plan" in body
    with schema_context(migrated_tenant.number):
        assert not Document.objects.exists()


def test_two_siblings_named_alike_at_once_are_one_folder(
    migrated_tenant: Any, member_of: Any, monkeypatch: pytest.MonkeyPatch, waiting_on_a_lock: Any
) -> None:
    """Two creations of one name under one parent: the second waits on the parent's row, then
    finds the name taken."""
    from documents import folders
    from documents.models import Folder

    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    locked = threading.Event()
    go = threading.Event()
    lock = folders._locked
    outcome: list[str] = []
    first_call = threading.local()

    def holding_the_parent(folder: Any) -> Any:
        found = lock(folder)
        if getattr(first_call, "pause", False):
            locked.set()
            go.wait(timeout=30)
        return found

    monkeypatch.setattr(folders, "_locked", holding_the_parent)

    def create(pause: bool) -> None:
        first_call.pause = pause
        try:
            with schema_context(migrated_tenant.number):
                folders.create_folder(
                    Folder.objects.get(number=1), "Twin (synthetic example)", by=admin_user
                )
                outcome.append("created")
        except folders.FolderRefused as refused:
            outcome.append(refused.reason)
        finally:
            connection.close()

    first = threading.Thread(target=create, args=(True,))
    first.start()
    assert locked.wait(timeout=10)
    second = threading.Thread(target=create, args=(False,))
    second.start()
    waited = waiting_on_a_lock()
    go.set()
    first.join(timeout=30)
    second.join(timeout=30)

    assert waited
    assert outcome == ["created", "name_taken"]
    with schema_context(migrated_tenant.number):
        assert Folder.objects.filter(name="Twin (synthetic example)").count() == 1


def test_a_move_into_a_folder_being_deleted_waits_and_finds_it_gone(
    migrated_tenant: Any,
    member_of: Any,
    make_document: Any,
    monkeypatch: pytest.MonkeyPatch,
    waiting_on_a_lock: Any,
) -> None:
    """The delete holds the folder first: the move waits on its row, then finds it gone."""
    from documents import folders
    from documents.models import Document, Folder

    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    target = _make_folder(migrated_tenant, admin_user, "Target (synthetic example)")
    document = make_document(title="Synthetic rule")
    locked = threading.Event()
    go = threading.Event()
    lock_folder = folders._lock_folder
    outcome: dict[str, Any] = {}

    def holding_the_folder(folder: Any) -> Any:
        found = lock_folder(folder)
        locked.set()
        go.wait(timeout=30)
        return found

    monkeypatch.setattr(folders, "_lock_folder", holding_the_folder)

    def delete() -> None:
        try:
            with schema_context(migrated_tenant.number):
                folders.delete_folder(Folder.objects.get(pk=target.pk), by=admin_user)
                outcome["deleted"] = True
        finally:
            connection.close()

    def move() -> None:
        try:
            with schema_context(migrated_tenant.number):
                folders.move_documents(
                    [Document.objects.get(pk=document.pk)], to=target, by=admin_user
                )
                outcome["moved"] = True
        except folders.FolderRefused as refused:
            outcome["refused"] = refused.reason
        finally:
            connection.close()

    deleter = threading.Thread(target=delete)
    deleter.start()
    assert locked.wait(timeout=10)
    mover = threading.Thread(target=move)
    mover.start()
    waited = waiting_on_a_lock()
    go.set()
    deleter.join(timeout=30)
    mover.join(timeout=30)

    assert waited
    assert outcome == {"deleted": True, "refused": "gone"}
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=document.pk).folder.number == 1


def test_the_tree_is_alphabetical_as_ukrainian_is_read(
    migrated_tenant: Any, member_of: Any
) -> None:
    """The folders page lists siblings in `uk-x-icu` order, each under its parent (the language
    of the names is the subject)."""
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    for name in ("Ґрафіки", "Бюджет", "Аудит"):
        _make_folder(migrated_tenant, admin_user, name)
    budget = _folder(migrated_tenant, name="Бюджет")
    _make_folder(migrated_tenant, admin_user, "Внутрішній", parent=budget.number)

    page = admin.get(PAGE).content.decode()
    tree = page.split('class="folder-admin"', 1)[1].split("</ul>", 1)[0]
    positions = [tree.index(name) for name in ("Аудит", "Бюджет", "Внутрішній", "Ґрафіки")]

    assert positions == sorted(positions)


def test_a_move_waiting_on_its_documents_reads_authority_after_them(
    migrated_tenant: Any, member_of: Any, make_document: Any, waiting_on_a_lock: Any
) -> None:
    """Another act holds the document's row while the move waits for it; the mover is blocked
    meanwhile: the move, once it holds the row, refuses and writes nothing."""
    from django.db import transaction

    from audit.models import AuditEvent
    from documents import folders
    from documents.models import Document
    from identity.models import Membership, MembershipState

    _, mover, membership = member_of("an.admin@example.test", is_tenant_admin=True)
    target = _make_folder(migrated_tenant, mover, "Target (synthetic example)")
    document = make_document(title="Synthetic rule")
    held = threading.Event()
    release = threading.Event()
    outcome: dict[str, Any] = {}

    def hold_the_row() -> None:
        try:
            with schema_context(migrated_tenant.number), transaction.atomic():
                list(Document.objects.select_for_update().filter(pk=document.pk))
                held.set()
                release.wait(timeout=30)
        finally:
            connection.close()

    def move() -> None:
        try:
            with schema_context(migrated_tenant.number):
                folders.move_documents([Document.objects.get(pk=document.pk)], target, mover)
                outcome["moved"] = True
        except folders.FolderRefused as refused:
            outcome["refused"] = refused.reason
        finally:
            connection.close()

    holder = threading.Thread(target=hold_the_row)
    holder.start()
    assert held.wait(timeout=10)
    mover_thread = threading.Thread(target=move)
    mover_thread.start()
    waited = waiting_on_a_lock()
    Membership.objects.filter(pk=membership.pk).update(state=MembershipState.BLOCKED)
    before = AuditEvent.objects.filter(action="document.moved").count()
    release.set()
    holder.join(timeout=30)
    mover_thread.join(timeout=30)

    assert waited
    assert outcome == {"refused": "not_allowed"}
    assert AuditEvent.objects.filter(action="document.moved").count() == before
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=document.pk).folder.number == 1


def test_a_creation_waiting_on_its_folder_holds_no_type(
    migrated_tenant: Any,
    member_of: Any,
    make_document: Any,
    monkeypatch: pytest.MonkeyPatch,
    waiting_on_a_lock: Any,
) -> None:
    """One lock order — folder, then document, then type: a creation waiting for a folder a move
    holds has not yet taken its type, so a type change of the moved document goes through, and
    the three never close a cycle."""
    from documents import folders, services, types
    from documents.models import Document, DocumentType, Folder
    from identity.models import Language

    Language.objects.get_or_create(code="uk", defaults={"label": "uk", "actor_kind": "system"})
    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    child = _make_folder(migrated_tenant, admin_user, "Child (synthetic example)")
    document = make_document(title="Synthetic rule", folder=child)
    with schema_context(migrated_tenant.number):
        policy = types.add_type("policy (synthetic example)", by=admin_user)
    locked = threading.Event()
    go = threading.Event()
    lock_target = folders._lock_target
    outcome: dict[str, Any] = {}

    def holding_the_target(folder: Any) -> Any:
        found = lock_target(folder)
        locked.set()
        go.wait(timeout=30)
        return found

    monkeypatch.setattr(folders, "_lock_target", holding_the_target)

    def run(name: str, act: Any) -> None:
        try:
            with schema_context(migrated_tenant.number):
                act()
                outcome[name] = "done"
        except Exception as error:  # noqa: BLE001 — the outcome is the assertion
            outcome[name] = type(error).__name__
        finally:
            connection.close()

    def move() -> None:
        folders.move_documents(
            [Document.objects.get(pk=document.pk)], Folder.objects.get(number=1), admin_user
        )

    def create() -> None:
        services.create_document(
            admin_user,
            "Synthetic plan",
            "uk",
            DocumentType.objects.get(pk=policy.pk),
            Folder.objects.get(number=1),
        )

    def change() -> None:
        types.change_type(Document.objects.get(pk=document.pk), policy, by=admin_user)

    mover = threading.Thread(target=run, args=("move", move))
    mover.start()
    assert locked.wait(timeout=10)
    creator = threading.Thread(target=run, args=("create", create))
    creator.start()
    waited = waiting_on_a_lock()
    changer = threading.Thread(target=run, args=("change", change))
    changer.start()
    changer.join(timeout=10)
    changed_while_held = outcome.get("change")
    go.set()
    mover.join(timeout=30)
    creator.join(timeout=60)

    assert waited
    assert changed_while_held == "done"
    assert outcome == {"change": "done", "move": "done", "create": "done"}


def test_a_deep_chain_of_folders_is_drawn(migrated_tenant: Any, member_of: Any) -> None:
    """Folders nest without limit: a chain deeper than the interpreter's recursion is listed."""
    import sys

    from documents.models import Folder, next_folder_number
    from documents.tree import Tree

    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    depth = sys.getrecursionlimit() + 50
    with schema_context(migrated_tenant.number):
        parent = Folder.objects.get(number=1)
        chain = []
        for level in range(depth):
            folder = Folder(
                pk=uuid.uuid4(),
                number=next_folder_number(),
                parent=parent,
                name=f"Level {level} (synthetic example)",
                actor_kind="system",
            )
            chain.append(folder)
            parent = folder
        Folder.objects.bulk_create(chain)
        tree = Tree("Example Org")
        flat = tree.flat()
        deepest = chain[-1]
        key = tree.path_key(deepest)

    assert len(flat) == depth + 1
    assert flat[-1].depth == depth
    assert len(key) == depth
    assert admin.get(f"{PAGE}?folder={deepest.number}").status_code == 200


def test_a_number_too_long_is_a_missing_folder(migrated_tenant: Any, member_of: Any) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    huge = "7" * 4301

    answers = [
        admin.get(f"{PAGE}?folder={huge}"),
        admin.post(f"{PAGE}new/", {"parent": huge, "name": "Policies (synthetic example)"}),
        admin.post(f"{PAGE}1/move/", {"document": ["1"], "to": huge}),
    ]

    assert [a.status_code for a in answers] == [404, 404, 404]


def test_a_refused_move_keeps_its_destination(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    _make_folder(migrated_tenant, admin_user, "Alpha (synthetic example)")
    second = _make_folder(migrated_tenant, admin_user, "Beta (synthetic example)")
    make_document(title="Synthetic rule")

    refused = admin.post(f"{PAGE}1/move/", {"to": second.number}).content.decode()

    assert f'<option value="{second.number}" selected>' in refused


def test_a_move_with_nowhere_to_go_says_so(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    make_document(title="Synthetic rule")

    page = admin.get(f"{PAGE}1/move/").content.decode()

    assert "Create another folder to move documents into." in page
    assert 'type="submit" disabled' in page

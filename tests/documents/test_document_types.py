"""The organisation's own document types (DL-0235, DL-0310): Administration › document types —
add, rename, retire, delete only an unused one — and a document's type changed on its *Info* tab.

Types, groups, people and titles are synthetic examples."""

from __future__ import annotations

import html
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/tenant/document-types/"


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    # The refusals' wording is read in English; the catalogue test reads the pages in `uk`.
    settings.LANGUAGE_CODE = "en"


def _events(migrated_tenant: Any, action: str) -> list[Any]:
    from audit.models import AuditEvent

    return list(AuditEvent.objects.filter(action=action).order_by("at"))


def _type(migrated_tenant: Any, **filters: Any) -> Any:
    from documents.models import DocumentType

    with schema_context(migrated_tenant.number):
        return DocumentType.objects.filter(**filters).first()


def _creator(migrated_tenant: Any, member_of: Any, email: str) -> tuple[Any, Any]:
    """A member holding *create and edit*, who reaches the create dialog."""
    from access.models import AccessGroup
    from access.rights import Right

    client, user, membership = member_of(email)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Creators", actor_kind="system")
        group.grant(Right.CREATE_AND_EDIT, by=None)
        group.add_member(membership, by=None)
    return client, user


def test_add_rename_retire(migrated_tenant: Any, member_of: Any) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    creator, _ = _creator(migrated_tenant, member_of, "a.creator@example.test")

    added = admin.post(PAGE, {"act": "add", "label": "policy (synthetic example)"})
    kind = _type(migrated_tenant, label="policy (synthetic example)")
    renamed = admin.post(PAGE, {"act": "rename", "code": kind.code, "label": "Policy"})
    retired = admin.post(PAGE, {"act": "retire", "code": kind.code})

    assert [added.status_code, renamed.status_code, retired.status_code] == [302, 302, 302]
    kind = _type(migrated_tenant, code=kind.code)
    assert kind.label == "Policy" and kind.retired_at is not None
    assert kind.code.startswith("type-") and len(kind.code) == len("type-") + 12
    for action in ("document_type.added", "document_type.renamed", "document_type.retired"):
        (event,) = _events(migrated_tenant, action)
        assert event.after == {"code": kind.code}
        assert event.object_type == "documenttype" and event.object_id == kind.pk
    page = admin.get(PAGE).content.decode()
    row = page.split(f'data-code="{kind.code}"', 1)[1].split("</tr>", 1)[0]
    assert "Policy" in row and 'class="tag retired"' in row
    dialog = creator.get("/document/new/").content.decode()
    assert "Документ" in dialog and "Policy" not in dialog


def test_only_an_unused_type_is_deleted(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from documents import types
    from documents.models import Document, DocumentType

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document()
    with schema_context(migrated_tenant.number):
        used = types.add_type("controls (synthetic example)", by=admin_user)
        unused = types.add_type("procedure (synthetic example)", by=admin_user)
        Document.objects.filter(pk=document.pk).update(document_type=used)

    page = admin.get(PAGE).content.decode()
    refused = admin.post(PAGE, {"act": "delete", "code": used.code})
    deleted = admin.post(PAGE, {"act": "delete", "code": unused.code})

    assert f'name="code" value="{unused.code}"' in page
    used_row = page.split(f'data-code="{used.code}"', 1)[1].split("</tr>", 1)[0]
    assert 'value="delete"' not in used_row
    assert refused.status_code == 400
    assert "This type is in use: it can be retired, not deleted." in refused.content.decode()
    assert deleted.status_code == 302
    with schema_context(migrated_tenant.number):
        assert DocumentType.objects.filter(pk=used.pk).exists()
        assert not DocumentType.objects.filter(pk=unused.pk).exists()
    (event,) = _events(migrated_tenant, "document_type.deleted")
    assert event.after == {"code": unused.code}


def test_labels_follow_their_rule(migrated_tenant: Any, member_of: Any) -> None:
    from documents import types
    from documents.models import DocumentType

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        types.add_type("Policy", by=admin_user)
        before = DocumentType.objects.count()

    taken = admin.post(PAGE, {"act": "add", "label": "policy"})
    long = admin.post(PAGE, {"act": "add", "label": "x" * 101})
    two_lines = admin.post(PAGE, {"act": "add", "label": "first line\nsecond line"})
    blank = admin.post(PAGE, {"act": "add", "label": "   "})

    assert [r.status_code for r in (taken, long, two_lines, blank)] == [400] * 4
    assert "Another type already has this label" in taken.content.decode()
    with schema_context(migrated_tenant.number):
        assert DocumentType.objects.count() == before
        with pytest.raises(types.TypeRefused) as refused:
            types.add_type("POLICY", by=admin_user)
        assert refused.value.reason == "label_taken"
        with pytest.raises(types.TypeRefused) as refused:
            types.add_type("x" * 101, by=admin_user)
        assert refused.value.reason == "label_invalid"
    assert len(_events(migrated_tenant, "document_type.added")) == 1


def test_the_page_is_an_administrators(migrated_tenant: Any, member_of: Any) -> None:
    from django.test import Client

    from identity.models import Membership, User
    from tenancy.models import Tenant

    member, _, _ = member_of("a.member@example.test")
    elsewhere = Tenant.objects.create(name="Other Org (synthetic example)", actor_kind="system")
    stranger = User.objects.create_user("an.admin@elsewhere.test", "test-only-not-a-password")
    Membership.objects.create(
        tenant=elsewhere, user=stranger, is_tenant_admin=True, actor_kind="system"
    )
    other = Client(headers={"host": "127.0.0.1"})
    other.force_login(stranger)
    session = other.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    code = _type(migrated_tenant, code="document").code

    for client in (member, other):
        answers = [
            client.get(PAGE),
            client.post(PAGE, {"act": "add", "label": "Policy"}),
            client.post(PAGE, {"act": "rename", "code": code, "label": "Policy"}),
            client.post(PAGE, {"act": "retire", "code": code}),
            client.post(PAGE, {"act": "delete", "code": code}),
        ]
        assert [a.status_code for a in answers] == [404] * 5
        assert all("Nothing to show here" in a.content.decode() for a in answers)
    assert _type(migrated_tenant, code="document").label == "Документ"


def test_an_administrator_changes_a_documents_type(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from documents import types
    from documents.models import Document

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    active = make_document(title="Synthetic regulation")
    archived = make_document(title="Synthetic archived regulation")
    with schema_context(migrated_tenant.number):
        policy = types.add_type("policy (synthetic example)", by=admin_user)
        retired = types.add_type("old (synthetic example)", by=admin_user)
        types.retire_type(retired, by=admin_user)
        Document.objects.filter(pk=archived.pk).update(state="archived")

    info = admin.get(f"/document/{active.number}/info/").content.decode()
    changed = admin.post(f"/document/{active.number}/info/type/", {"document_type": policy.code})

    assert f'action="/document/{active.number}/info/type/"' in info
    assert f'value="{retired.code}"' not in info
    assert changed.status_code == 302
    assert changed["Location"] == f"/document/{active.number}/info/"
    with schema_context(migrated_tenant.number):
        active = Document.objects.select_related("document_type").get(pk=active.pk)
        assert active.document_type.code == policy.code
        with pytest.raises(types.TypeRefused) as refused:
            types.change_type(active, retired, by=admin_user)
        assert refused.value.reason == "retired"
        with pytest.raises(types.TypeRefused) as refused:
            types.change_type(active, policy, by=admin_user)
        assert refused.value.reason == "unchanged"
        archived = Document.objects.get(pk=archived.pk)
        with pytest.raises(types.TypeRefused) as refused:
            types.change_type(archived, policy, by=admin_user)
        assert refused.value.reason == "archived"
    (event,) = _events(migrated_tenant, "document.type_changed")
    assert event.after == {"number": active.number, "from": "document", "to": policy.code}
    assert event.object_type == "document" and event.object_id == active.pk


def test_a_reader_reads_the_type(migrated_tenant: Any, member_of: Any, make_document: Any) -> None:
    from access.models import AccessGroup, DocumentGroup
    from access.rights import Right
    from documents import types
    from documents.models import Document

    reader, _, membership = member_of("a.reader@example.test")
    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document(author_only=False)
    with schema_context(migrated_tenant.number):
        group = AccessGroup.objects.create(name="Readers", actor_kind="system")
        group.grant(Right.VIEW_PENDING, by=None)
        group.add_member(membership, by=None)
        DocumentGroup.link(document, group, by=admin_user)
        policy = types.add_type("policy (synthetic example)", by=admin_user)

    info = reader.get(f"/document/{document.number}/info/").content.decode()
    posted = reader.post(f"/document/{document.number}/info/type/", {"document_type": policy.code})

    assert "<dd>Документ</dd>" in info
    assert "/info/type/" not in info
    assert posted.status_code == 404
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=document.pk).document_type.code == "document"


def test_the_last_type_stays(migrated_tenant: Any, member_of: Any) -> None:
    from documents import types
    from documents.models import DocumentType

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        only = DocumentType.objects.get(code="document")
        old = types.add_type("old (synthetic example)", by=admin_user)
        types.retire_type(old, by=admin_user)

    page = admin.get(PAGE).content.decode()
    retire = admin.post(PAGE, {"act": "retire", "code": only.code})
    delete = admin.post(PAGE, {"act": "delete", "code": only.code})

    row = page.split(f'data-code="{only.code}"', 1)[1].split("</tr>", 1)[0]
    assert row.count("disabled") == 2
    assert "the organisation's last type not retired" in html.unescape(row)
    assert [retire.status_code, delete.status_code] == [400, 400]
    with schema_context(migrated_tenant.number):
        only.refresh_from_db()
        assert only.retired_at is None
        for act in (types.retire_type, types.delete_type):
            with pytest.raises(types.TypeRefused) as refused:
                act(only, by=admin_user)
            assert refused.value.reason == "last_type"


def test_a_type_gone_meanwhile_is_refused_not_a_server_error(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """An act that resolved a type another administrator deleted before its lock was taken is
    refused `gone`; the views answer it as a missing type."""
    from documents import types
    from documents.models import DocumentType

    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document()
    with schema_context(migrated_tenant.number):
        stale = types.add_type("policy (synthetic example)", by=admin_user)
        DocumentType.objects.filter(pk=stale.pk).delete()
        for act, args in (
            (types.rename_type, (stale, "Policy")),
            (types.retire_type, (stale,)),
            (types.delete_type, (stale,)),
            (types.change_type, (document, stale)),
        ):
            with pytest.raises(types.TypeRefused) as refused:
                act(*args, by=admin_user)
            assert refused.value.reason == "gone", act


def test_a_change_waits_for_a_retire_of_its_target(
    migrated_tenant: Any,
    member_of: Any,
    make_document: Any,
    monkeypatch: pytest.MonkeyPatch,
    waiting_on_a_lock: Any,
) -> None:
    """A retire holding the types' rows when a change reads its target: the change waits, then
    finds the target retired and refuses it."""
    import threading

    from django.db import connection

    from documents import types
    from documents.models import Document

    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document()
    with schema_context(migrated_tenant.number):
        target = types.add_type("policy (synthetic example)", by=admin_user)
    locked = threading.Event()
    go = threading.Event()
    lock_all = types._lock_all
    outcome: dict[str, Any] = {}

    def holding_every_type() -> None:
        lock_all()
        locked.set()
        go.wait(timeout=30)

    monkeypatch.setattr(types, "_lock_all", holding_every_type)

    def retire() -> None:
        try:
            with schema_context(migrated_tenant.number):
                types.retire_type(target, by=admin_user)
                outcome["retired"] = True
        finally:
            connection.close()

    def change() -> None:
        try:
            with schema_context(migrated_tenant.number):
                types.change_type(Document.objects.get(pk=document.pk), target, by=admin_user)
                outcome["changed"] = True
        except types.TypeRefused as refused:
            outcome["refused"] = refused.reason
        finally:
            connection.close()

    retiring = threading.Thread(target=retire)
    retiring.start()
    assert locked.wait(timeout=10)
    changing = threading.Thread(target=change)
    changing.start()
    # The change has reached the target's row and waits on it; released only then.
    waited = waiting_on_a_lock()
    go.set()
    retiring.join(timeout=30)
    changing.join(timeout=30)

    assert waited
    assert outcome == {"retired": True, "refused": "retired"}
    with schema_context(migrated_tenant.number):
        assert Document.objects.get(pk=document.pk).document_type.code == "document"


def test_every_refusal_of_a_rename_and_a_retire(migrated_tenant: Any, member_of: Any) -> None:
    from documents import types

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        policy = types.add_type("Policy", by=admin_user)
        controls = types.add_type("Controls", by=admin_user)
        types.retire_type(controls, by=admin_user)

    taken = admin.post(PAGE, {"act": "rename", "code": controls.code, "label": "POLICY"})
    invalid = admin.post(PAGE, {"act": "rename", "code": policy.code, "label": "a\nb"})
    again = admin.post(PAGE, {"act": "retire", "code": controls.code})

    assert [taken.status_code, invalid.status_code, again.status_code] == [400, 400, 400]
    assert "Another type already has this label" in taken.content.decode()
    assert "This type is retired." in again.content.decode()
    with schema_context(migrated_tenant.number):
        for label, reason in (("POLICY", "label_taken"), ("x" * 101, "label_invalid")):
            with pytest.raises(types.TypeRefused) as refused:
                types.rename_type(controls, label, by=admin_user)
            assert refused.value.reason == reason
        with pytest.raises(types.TypeRefused) as refused:
            types.retire_type(controls, by=admin_user)
        assert refused.value.reason == "retired"
        assert types.DocumentType.objects.get(pk=controls.pk).label == "Controls"


def test_the_type_change_route_refuses_strangers_and_archived_documents(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    from django.test import Client

    from documents import types
    from documents.models import Document
    from identity.models import Membership, User
    from tenancy.models import Tenant

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    active = make_document(title="Synthetic regulation")
    archived = make_document(title="Synthetic archived regulation", state="archived")
    with schema_context(migrated_tenant.number):
        policy = types.add_type("policy (synthetic example)", by=admin_user)
    elsewhere = Tenant.objects.create(name="Other Org (synthetic example)", actor_kind="system")
    stranger = User.objects.create_user("an.admin@elsewhere.test", "test-only-not-a-password")
    Membership.objects.create(
        tenant=elsewhere, user=stranger, is_tenant_admin=True, actor_kind="system"
    )
    other = Client(headers={"host": "127.0.0.1"})
    other.force_login(stranger)
    session = other.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    answers = [
        other.post(f"/document/{active.number}/info/type/", {"document_type": policy.code}),
        admin.post(f"/document/{archived.number}/info/type/", {"document_type": policy.code}),
    ]

    # A stranger finds nothing; an administrator reads the archived document (DL-0450), and the
    # change is refused with its reason.
    assert answers[0].status_code == 404 and "Nothing to show here" in answers[0].content.decode()
    assert answers[1].status_code == 400
    assert "This document is archived — restore it first." in answers[1].content.decode()
    with schema_context(migrated_tenant.number):
        assert set(Document.objects.values_list("document_type__code", flat=True)) == {"document"}


def test_a_retired_current_type_stays_the_current_choice(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """The choice never shows another type as current: a document keeps a type retired after it
    was given, and only that retired type is listed, marked."""
    from documents import types
    from documents.models import Document

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document()
    with schema_context(migrated_tenant.number):
        current = types.add_type("current (synthetic example)", by=admin_user)
        other = types.add_type("other (synthetic example)", by=admin_user)
        Document.objects.filter(pk=document.pk).update(document_type=current)
        types.retire_type(current, by=admin_user)
        types.retire_type(other, by=admin_user)

    info = admin.get(f"/document/{document.number}/info/").content.decode()

    assert f'<option value="{current.code}" selected>' in info
    assert "current (synthetic example) — retired" in info
    assert f'value="{other.code}"' not in info


def test_a_blocked_administrators_waiting_act_is_refused(
    migrated_tenant: Any, member_of: Any, make_document: Any
) -> None:
    """Authority is read again under the act's locks: an administrator blocked while their act
    waited — the state the act meets once the lock is theirs — changes nothing."""
    from documents import types
    from documents.models import Document, DocumentType
    from identity.models import Membership, MembershipState

    _, sender, membership = member_of("an.admin@example.test", is_tenant_admin=True)
    document = make_document()
    with schema_context(migrated_tenant.number):
        target = types.add_type("policy (synthetic example)", by=sender)
        spare = types.add_type("spare (synthetic example)", by=sender)
    Membership.objects.filter(pk=membership.pk).update(state=MembershipState.BLOCKED)

    with schema_context(migrated_tenant.number):
        acts = (
            (types.change_type, (Document.objects.get(pk=document.pk), target)),
            (types.add_type, ("another (synthetic example)",)),
            (types.rename_type, (target, "Policy")),
            (types.retire_type, (spare,)),
            (types.delete_type, (spare,)),
        )
        for act, args in acts:
            with pytest.raises(types.TypeRefused) as refused:
                act(*args, by=sender)
            assert refused.value.reason == "not_allowed", act
        assert Document.objects.get(pk=document.pk).document_type.code == "document"
        assert DocumentType.objects.filter(pk=spare.pk, retired_at__isnull=True).exists()


def test_a_type_deleted_before_a_creation_lands_is_refused_in_the_form(
    migrated_tenant: Any, member_of: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A creator's chosen type deleted between the form's check and the row: the dialog again,
    `400`, with the reason and what they typed; no row, no server error."""
    from documents import services, types, views
    from documents.models import Document, DocumentType, Folder

    creator, _ = _creator(migrated_tenant, member_of, "a.creator@example.test")
    _, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    from identity.models import Language

    Language.objects.get_or_create(code="en", defaults={"label": "English", "actor_kind": "system"})
    with schema_context(migrated_tenant.number):
        doomed = types.add_type("doomed (synthetic example)", by=admin_user)
        folder = Folder.objects.get(number=1)
    create = services.create_document

    def deleted_first(*args: Any, **kwargs: Any) -> Any:
        DocumentType.objects.filter(pk=doomed.pk).delete()
        return create(*args, **kwargs)

    monkeypatch.setattr(views, "create_document", deleted_first)

    answer = creator.post(
        "/document/new/",
        {
            "title": "Synthetic plan",
            "language": "en",
            "document_type": str(doomed.pk),
            "folder": str(folder.pk),
        },
    )

    assert answer.status_code == 400
    body = answer.content.decode()
    assert "This type is no longer offered" in body and "Synthetic plan" in body
    with schema_context(migrated_tenant.number):
        assert not Document.objects.exists()
        with pytest.raises(services.ChoiceGone) as gone:
            services.create_document(
                admin_user, "Synthetic plan", "en", doomed, Folder.objects.get(number=1)
            )
        assert gone.value.field == "document_type"
        assert not Document.objects.exists()


def test_a_refused_label_is_kept_in_its_field(migrated_tenant: Any, member_of: Any) -> None:
    from documents import types

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        policy = types.add_type("Policy", by=admin_user)
        controls = types.add_type("Controls", by=admin_user)

    added = admin.post(PAGE, {"act": "add", "label": "POLICY"}).content.decode()
    renamed = admin.post(
        PAGE, {"act": "rename", "code": controls.code, "label": "policy"}
    ).content.decode()

    assert 'id="new-type" name="label" maxlength="100" required placeholder' in added
    assert 'value="POLICY"' in added
    row = renamed.split(f'data-code="{controls.code}"', 1)[1].split("</tr>", 1)[0]
    assert 'value="policy"' in row
    other = renamed.split(f'data-code="{policy.code}"', 1)[1].split("</tr>", 1)[0]
    assert 'value="Policy"' in other


def test_the_seeded_type_is_never_deleted(migrated_tenant: Any, member_of: Any) -> None:
    """The seeded `document` type is what loading and the reconciler's recovery give a document:
    it may be renamed and retired, never deleted (DL-10-002)."""
    from documents import types
    from documents.models import DocumentType

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        types.add_type("policy (synthetic example)", by=admin_user)
        seed = DocumentType.objects.get(code="document")
        types.rename_type(seed, "General (synthetic example)", by=admin_user)
        types.retire_type(seed, by=admin_user)

    page = admin.get(PAGE).content.decode()
    deleted = admin.post(PAGE, {"act": "delete", "code": "document"})

    row = page.split('data-code="document"', 1)[1].split("</tr>", 1)[0]
    assert 'value="delete"' not in row
    assert deleted.status_code == 400
    assert "kept for documents the platform loads or recovers" in deleted.content.decode()
    with schema_context(migrated_tenant.number):
        with pytest.raises(types.TypeRefused) as refused:
            types.delete_type(DocumentType.objects.get(code="document"), by=admin_user)
        assert refused.value.reason == "seeded"
        assert DocumentType.objects.filter(code="document").exists()

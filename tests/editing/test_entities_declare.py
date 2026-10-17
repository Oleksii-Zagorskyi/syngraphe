"""Declaring a role, an action or a term in the holder's draft (DL-0073): written to the
draft's `entities.yaml` under the writer lock, its key the kind and the next free number, the same
label of a kind answering the key it already has, audited; a kind or a label outside the rules
refused with nothing written; for the holder alone. People are synthetic examples; labels are
invented."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from access.rights import Right
from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_declare_in_the_draft(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from audit.models import AuditEvent
    from documents import entities
    from documents.locks import document_lock
    from editing.models import Draft
    from editing.views import capture

    client, author, membership = member_of("the.author@example.test")
    other, _, other_membership = member_of("the.other@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [membership, other_membership], author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    address = f"/document/{document.number}/edit/entities/"

    def declared() -> list[Any]:
        with schema_context(migrated_tenant.number):
            text = Draft.objects.get(hold__document=document).content["entities.yaml"]
        return entities.parse(text)

    first = client.post(address, {"kind": "role", "label": "the approver"})
    again = client.post(address, {"kind": "role", "label": "  the approver "})
    # Case is not a second entity: the label keeps the form it was first declared in.
    capitals = client.post(address, {"kind": "role", "label": "The Approver"})
    action = client.post(address, {"kind": "action", "label": "approves"})

    assert first.status_code == again.status_code == action.status_code == 200
    assert first.json()["key"] == again.json()["key"] == capitals.json()["key"] == "role-1"
    assert action.json()["key"] == "action-1"
    assert action.json()["entities"] == [
        {"kind": "role", "key": "role-1", "label": "the approver"},
        {"kind": "action", "key": "action-1", "label": "approves"},
    ]
    assert [(e.kind, e.key, e.label) for e in declared()] == [
        ("role", "role-1", "the approver"),
        ("action", "action-1", "approves"),
    ]
    events = AuditEvent.objects.filter(action="entity.declared").order_by("at")
    assert [e.after for e in events] == [
        {"number": document.number, "kind": "role", "key": "role-1"},
        {"number": document.number, "kind": "action", "key": "action-1"},
    ]

    before = declared()
    for refused in (
        {"kind": "role", "label": "a" * 201},
        {"kind": "role", "label": "   "},
        {"kind": "document", "label": "a plan"},
    ):
        response = client.post(address, refused)
        assert response.status_code == 400, refused
        assert response.json()["refused"], refused
    assert declared() == before
    assert other.post(address, {"kind": "role", "label": "a clerk"}).status_code == 404

    monkeypatch.setattr(capture, "CAPTURE_LOCK_SECONDS", 0.2)
    held, done = threading.Event(), threading.Event()

    def commit() -> None:
        with document_lock(migrated_tenant.number, document.number):
            held.set()
            done.wait(10)

    committing = threading.Thread(target=commit)
    committing.start()
    held.wait(10)
    try:
        busy = client.post(address, {"kind": "term", "label": "ten days"})
    finally:
        done.set()
        committing.join()
    assert busy.status_code == 503 and busy.json() == {"busy": True}
    assert declared() == before


def holding_with(migrated_tenant: Any, member_of: Any, new_document: Any, body: str) -> Any:
    """The author's client holding a new document whose draft's body is `body`; the document."""
    from editing.models import Draft

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "document.md": body}
        draft.save()
    return client, document


def test_a_declared_key_never_takes_a_spans(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """A span the draft marks without declaring keeps its key and its words (DL-0440): a new
    declaration takes the next key no text and no file holds — the editor's own uncaptured ones
    included — and a label a span already reads as answers that span's key, writing nothing."""
    from audit.models import AuditEvent
    from documents import entities
    from editing.models import Draft

    client, document = holding_with(
        migrated_tenant,
        member_of,
        new_document,
        "[The clerk]{.role #role-1} files it.\n\n[The approver]{.role #approver} signs it.\n",
    )
    address = f"/document/{document.number}/edit/entities/"

    fresh = client.post(address, {"kind": "role", "label": "the treasurer", "taken": "role-2"})
    known = client.post(address, {"kind": "role", "label": "The approver"})

    assert fresh.json()["key"] == "role-3"
    assert known.json()["key"] == "approver"
    with schema_context(migrated_tenant.number):
        text = Draft.objects.get(hold__document=document).content["entities.yaml"]
    assert [(e.key, e.label) for e in entities.parse(text)] == [("role-3", "the treasurer")]
    assert AuditEvent.objects.filter(action="entity.declared").count() == 1


def test_declaring_refuses_what_it_must(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    """Every gate and rule of the route: a GET, a member without *edit*, a hold already released,
    a label that only looks empty or turns the text around it, a file at the size the platform
    accepts; and a label holding markup, which is kept as written and read back the same."""
    from documents import entities
    from editing.models import Draft, Hold, ReleaseKind

    settings.LANGUAGE_CODE = "en"
    client, author, own = member_of("the.author@example.test")
    reader, _, membership = member_of("the.reader@example.test")
    document = new_document(author)
    # Linked before the hold: a held document takes no new group.
    link_group(document, [Right.EDIT], [own], author)
    link_group(document, [Right.VIEW_ACCEPTED], [membership], author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    address = f"/document/{document.number}/edit/entities/"

    assert client.get(address).status_code == 404
    assert reader.post(address, {"kind": "role", "label": "a clerk"}).status_code == 404
    for label in ("‮evil", "​", "a⁦b"):
        assert client.post(address, {"kind": "role", "label": label}).status_code == 400, label

    markup = '<b>head</b>: - "office" # {.role}'
    written = client.post(address, {"kind": "role", "label": markup}).json()
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        assert entities.parse(draft.content["entities.yaml"])[-1].label == markup
        stamp = draft.updated_at
        draft.content = {
            **draft.content,
            "entities.yaml": full_file(draft.content["entities.yaml"]),
        }
        draft.save()
    assert written["key"] == "role-1"
    refused = client.post(address, {"kind": "role", "label": "one more"})
    assert refused.status_code == 400
    assert "as many roles, actions and terms" in refused.json()["refused"]
    with schema_context(migrated_tenant.number):
        assert Draft.objects.get(hold__document=document).updated_at > stamp
        Hold.objects.filter(document=document).update(
            released_at=timezone_now(), release_kind=ReleaseKind.DISCARDED
        )
    assert client.post(address, {"kind": "role", "label": "late"}).status_code == 404


def test_declaring_after_the_hold_ended_says_so(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The editor that declares after its hold ended is told how it ended, as a capture is: when
    the release came before the request, and when it came while the request waited for the lock;
    nothing is written either way."""
    from documents import entities
    from documents.locks import document_lock
    from editing.models import Draft, Hold, ReleaseKind
    from editing.views import capture

    client, document = holding_with(migrated_tenant, member_of, new_document, "Text.\n")
    editor = client.post(f"/document/{document.number}/edit/load/").json()["editor"]
    address = f"/document/{document.number}/edit/entities/"

    def release() -> None:
        with schema_context(migrated_tenant.number):
            Hold.objects.filter(document=document).update(
                released_at=timezone_now(), release_kind=ReleaseKind.INACTIVITY
            )

    monkeypatch.setattr(capture, "CAPTURE_LOCK_SECONDS", 5)
    held, waited = threading.Event(), threading.Event()

    def releasing_under_the_lock() -> None:
        with document_lock(migrated_tenant.number, document.number):
            held.set()
            waited.wait(0.5)
            release()

    releasing = threading.Thread(target=releasing_under_the_lock)
    releasing.start()
    held.wait(10)
    try:
        late = client.post(address, {"kind": "role", "label": "late", "editor": editor})
    finally:
        waited.set()
        releasing.join()
    after = client.post(address, {"kind": "role", "label": "later", "editor": editor})

    assert late.status_code == after.status_code == 409
    assert late.json() == after.json() == {"closed": True, "released": "inactivity"}
    with schema_context(migrated_tenant.number):
        content = Draft.objects.get(hold__document=document).content
    assert entities.parse(content["entities.yaml"]) == []


def test_two_declarations_at_once_take_two_keys(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Declarations of one kind made at the same moment wait for each other under the writer
    lock: each takes a key of its own, and the draft keeps both."""
    from documents import entities
    from editing.models import Draft

    client, document = holding_with(migrated_tenant, member_of, new_document, "Text.\n")
    address = f"/document/{document.number}/edit/entities/"
    keys: list[str] = []
    start = threading.Barrier(2)

    def declare(label: str) -> None:
        start.wait(10)
        keys.append(client.post(address, {"kind": "role", "label": label}).json()["key"])

    both = [threading.Thread(target=declare, args=(label,)) for label in ("the clerk", "the head")]
    for thread in both:
        thread.start()
    for thread in both:
        thread.join()

    assert sorted(keys) == ["role-1", "role-2"]
    with schema_context(migrated_tenant.number):
        text = Draft.objects.get(hold__document=document).content["entities.yaml"]
    assert sorted(e.key for e in entities.parse(text)) == ["role-1", "role-2"]


def test_a_spans_label_is_read_as_the_commit_writes_it(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """A span's words are offered, and matched, in the form the commit writes them — typeset as
    the body is — so a label typed in that form is the span's own entity, not a second key."""
    from editing.normalizer.typography import typeset

    raw = 'the "Agent" -- in charge'
    client, document = holding_with(
        migrated_tenant, member_of, new_document, f"[{raw}]{{.role #agent}} decides.\n"
    )
    written = typeset(raw, document.language_id)
    assert written != raw
    address = f"/document/{document.number}/edit/entities/"

    loaded = client.post(f"/document/{document.number}/edit/load/").json()
    known = client.post(address, {"kind": "role", "label": written})

    assert loaded["entities"] == [{"kind": "role", "key": "agent", "label": written}]
    assert known.json() == {"key": "agent", "entities": loaded["entities"]}


def full_file(text: str) -> str:
    """`text` with terms declared until one more would pass the size the platform accepts."""
    from documents import entities

    pieces = [text]
    size = len(text.encode("utf-8"))
    number = 1
    while True:
        piece = entities.dump([entities.Declared("term", f"term-{number}", "x")])
        if size + len(piece.encode("utf-8")) > entities.MAX_BYTES:
            return "".join(pieces)
        pieces.append(piece)
        size += len(piece.encode("utf-8"))
        number += 1


def timezone_now() -> Any:
    from django.utils import timezone

    return timezone.now()

"""`load` opens an editor on the whole draft or on one section of it, for its holder alone, with
the validator's verdict and the draft's declarations."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_load_records_an_open_editor_and_returns_the_verdict(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from editing.models import Draft, OpenEditor

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    loaded = client.post(f"/document/{document.number}/edit/load/").json()
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        editor = OpenEditor.objects.get(pk=loaded["editor"])
        body = draft.content["document.md"]
        assert editor.draft == draft and editor.closed_at is None and editor.range == "whole"
        draft.content = {**draft.content, "document.md": "A paragraph.\n\n<b>no</b>\n"}
        draft.save()
    assert loaded["body"] == body
    assert loaded["verdict"] == {"state": "ok"}
    assert loaded["base_hash"] == hashlib.sha256(body.encode()).hexdigest()
    refused = client.post(f"/document/{document.number}/edit/load/").json()
    assert refused["verdict"] == {"state": "refused", "refusals": [{"code": "html", "line": 3}]}


def test_load_is_the_holders_alone(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right

    holder, author, own = member_of("the.author@example.test")
    other, _, membership = member_of("another.editor@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [own, membership], author)
    holder.post(f"/document/{document.number}/edit/take/")
    assert other.post(f"/document/{document.number}/edit/load/").status_code == 404
    assert holder.get(f"/document/{document.number}/edit/load/").status_code == 404


@pytest.mark.parametrize(
    "route",
    [
        "load",
        "capture",
        "heartbeat",
        "close",
        "finish",
        "send",
        "reserve",
        "cancel-reservation",
        "end-reservation",
        "take-back",
        "discard-draft",
        "force-release",
        "discard",
        "changes",
    ],
)
def test_every_editing_post_needs_the_csrf_token(
    migrated_tenant: Any, member_of: Any, new_document: Any, route: str
) -> None:
    """The test client skips CSRF; a strict one proves no editing route is exempt from it."""
    from django.test import Client

    from editing.models import Draft, OpenEditor

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    strict = Client(enforce_csrf_checks=True, headers={"host": "127.0.0.1"})
    strict.force_login(author)
    session = strict.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    with schema_context(migrated_tenant.number):
        before = Draft.objects.get(hold__document=document).content

    response = strict.post(
        f"/document/{document.number}/edit/{route}/",
        data='{"body": "A reworded paragraph.\\n"}',
        content_type="application/json",
    )

    assert response.status_code == 403
    with schema_context(migrated_tenant.number):
        assert Draft.objects.get(hold__document=document).content == before
        assert not OpenEditor.objects.exists()


def test_load_waits_for_a_commit_then_answers_busy(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No editor opens on a draft a commit is consuming: `load` waits on the writer lock, then
    answers `503`, as the capture route does."""
    import threading

    from documents.locks import document_lock
    from editing.models import OpenEditor
    from editing.views import draft

    monkeypatch.setattr(draft, "LOAD_LOCK_SECONDS", 0.2)
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    held, done = threading.Event(), threading.Event()

    def commit() -> None:
        with document_lock(migrated_tenant.number, document.number):
            held.set()
            done.wait(10)

    committing = threading.Thread(target=commit)
    committing.start()
    held.wait(10)
    try:
        response = client.post(f"/document/{document.number}/edit/load/")
    finally:
        done.set()
        committing.join()

    assert response.status_code == 503 and response.json() == {"busy": True}
    with schema_context(migrated_tenant.number):
        assert not OpenEditor.objects.exists()


def test_another_tenants_editing_is_not_found(
    migrated_tenant: Any, member_of: Any, new_document: Any, make_tenant_schema: Any
) -> None:
    """A member of another organisation, naming this one's document and editor, meets the same
    not-found on every editing route — the schema it reads holds none of them."""
    from django.test import Client

    from identity.models import Membership, User

    holder, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    holder.post(f"/document/{document.number}/edit/take/")
    loaded = holder.post(f"/document/{document.number}/edit/load/").json()
    elsewhere = make_tenant_schema("Another organisation (synthetic example)")
    outsider = User.objects.create_user("an.outsider@example.test", "test-only-not-a-password")
    Membership.objects.create(tenant=elsewhere, user=outsider, actor_kind="system")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(outsider)
    session = client.session
    session["tenant_number"] = elsewhere.number
    session.save()
    base = f"/document/{document.number}"
    payload = {"editor": loaded["editor"], "base_hash": loaded["base_hash"], "body": "Foreign.\n"}

    for path in (f"{base}/edit/", f"{base}/edit/finish/", f"{base}/my-edits/"):
        assert client.get(path).status_code == 404, path
    for route in ("take", "load", "capture", "heartbeat", "close", "send"):
        response = client.post(
            f"{base}/edit/{route}/", data=json.dumps(payload), content_type="application/json"
        )
        assert response.status_code == 404, route
    with schema_context(migrated_tenant.number):
        from editing.models import Draft, OpenEditor

        assert "Foreign" not in Draft.objects.get(hold__document=document).content["document.md"]
        assert OpenEditor.objects.get(pk=loaded["editor"]).closed_at is None


def test_only_the_whole_document_is_opened(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Editing opens the whole document's editor and nothing else (DL-0517): a range other than
    `whole` is no range. Each of the holder's tabs opens its own editor, as before; past the most
    open at once the oldest are closed, and capture settles which text is stale (ADR-0006)."""
    import json

    from editing.models import OpenEditor

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")

    def load(range_: str) -> Any:
        return client.post(
            f"/document/{document.number}/edit/load/",
            data=json.dumps({"range": range_}),
            content_type="application/json",
        )

    assert load("section:0").status_code == 404
    assert load("section:" + "1" * 5000).status_code == 404
    assert load("whole").status_code == 200
    for _ in range(6):
        assert load("whole").status_code == 200
    with schema_context(migrated_tenant.number):
        still = OpenEditor.objects.filter(closed_at__isnull=True)
        assert still.count() == 5
        assert set(still.values_list("range", flat=True)) == {"whole"}


def test_load_returns_the_drafts_entities(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The picker offers the draft's own declarations, as `load` answers them (DL-0073)."""
    from editing.models import Draft

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {
            **draft.content,
            "entities.yaml": '- kind: "role"\n  key: "role-1"\n  label: "the approver"\n',
        }
        draft.save()

    loaded = client.post(f"/document/{document.number}/edit/load/").json()

    assert loaded["entities"] == [{"kind": "role", "key": "role-1", "label": "the approver"}]


def test_load_offers_what_the_commit_will_declare(
    migrated_tenant: Any, member_of: Any, new_document: Any, caplog: Any
) -> None:
    """`load` answers what declaring answers: the draft's declarations and each span it marks
    with a key they lack, labelled with its words (DL-0440); none for a file that does not read,
    which is logged."""
    from editing.models import Draft

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {
            **draft.content,
            "document.md": "[The clerk]{.role #clerk} files it.\n",
            "entities.yaml": '- kind: "role"\n  key: "role-1"\n  label: "the approver"\n',
        }
        draft.save()
    address = f"/document/{document.number}/edit/load/"

    assert client.post(address).json()["entities"] == [
        {"kind": "role", "key": "role-1", "label": "the approver"},
        {"kind": "role", "key": "clerk", "label": "The clerk"},
    ]

    with schema_context(migrated_tenant.number):
        draft.content = {**draft.content, "entities.yaml": "- {"}
        draft.save()
    assert client.post(address).json()["entities"] == []
    assert "entities.yaml does not read" in caplog.text

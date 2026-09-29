"""`load` opens an editor on the whole draft, for its holder alone, with the validator's verdict."""

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
        draft.content = {**draft.content, "document.md": "Абзац.\n\n<b>ні</b>\n"}
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


@pytest.mark.parametrize("route", ["load", "capture", "heartbeat", "close", "finish", "send"])
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
        data='{"body": "Змінений абзац.\\n"}',
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
    elsewhere = make_tenant_schema("Інша організація (синтетичний приклад)")
    outsider = User.objects.create_user("an.outsider@example.test", "test-only-not-a-password")
    Membership.objects.create(tenant=elsewhere, user=outsider, actor_kind="system")
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(outsider)
    session = client.session
    session["tenant_number"] = elsewhere.number
    session.save()
    base = f"/document/{document.number}"
    payload = {"editor": loaded["editor"], "base_hash": loaded["base_hash"], "body": "Чуже.\n"}

    for path in (f"{base}/edit/", f"{base}/edit/finish/", f"{base}/my-edits/"):
        assert client.get(path).status_code == 404, path
    for route in ("take", "load", "capture", "heartbeat", "close", "send"):
        response = client.post(
            f"{base}/edit/{route}/", data=json.dumps(payload), content_type="application/json"
        )
        assert response.status_code == 404, route
    with schema_context(migrated_tenant.number):
        from editing.models import Draft, OpenEditor

        assert "Чуже" not in Draft.objects.get(hold__document=document).content["document.md"]
        assert OpenEditor.objects.get(pk=loaded["editor"]).closed_at is None

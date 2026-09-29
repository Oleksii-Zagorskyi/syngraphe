"""`load` opens an editor on the whole draft, for its holder alone, with the validator's verdict."""

from __future__ import annotations

import hashlib
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

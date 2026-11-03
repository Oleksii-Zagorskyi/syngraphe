"""Capture without Save, on the server (ASR-22, DL-0167): a capture is taken only while the draft's
range still hashes to what the editor last saw; a heartbeat keeps an editor open and counts the
others; a silent editor is closed. People and titles are synthetic examples."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def post(client: Any, document: Any, route: str, **body: Any) -> Any:
    return client.post(
        f"/document/{document.number}/edit/{route}/",
        data=json.dumps(body),
        content_type="application/json",
    )


def send(client: Any, document: Any, loaded: dict[str, Any], body: str) -> Any:
    """A capture of `body` by the editor `loaded` opened, with the hash it saw."""
    editor, base = loaded["editor"], loaded["base_hash"]
    return post(client, document, "capture", editor=editor, base_hash=base, body=body)


def opened(member_of: Any, new_document: Any) -> tuple[Any, Any, dict[str, Any]]:
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    loaded = client.post(f"/document/{document.number}/edit/load/").json()
    return client, document, loaded


def test_capture_accepted_with_current_hash(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from editing.models import Draft, Hold

    client, document, loaded = opened(member_of, new_document)
    text = loaded["body"] + "\nA new sentence.\n"
    response = post(
        client,
        document,
        "capture",
        editor=loaded["editor"],
        base_hash=loaded["base_hash"],
        body=text,
    )
    assert response.status_code == 200
    assert response.json()["base_hash"] == hashlib.sha256(text.encode()).hexdigest()
    with schema_context(migrated_tenant.number):
        assert Draft.objects.get(hold__document=document).content["document.md"] == text
        hold = Hold.objects.get(document=document)
        assert hold.last_activity_at > hold.acquired_at


def test_stale_capture_refused(migrated_tenant: Any, member_of: Any, new_document: Any) -> None:
    from editing.models import Draft

    client, document, first = opened(member_of, new_document)
    second = client.post(f"/document/{document.number}/edit/load/").json()
    changed = first["body"] + "\nThe first tab.\n"
    accepted = post(
        client,
        document,
        "capture",
        editor=first["editor"],
        base_hash=first["base_hash"],
        body=changed,
    )
    assert accepted.status_code == 200
    stale = post(
        client,
        document,
        "capture",
        editor=second["editor"],
        base_hash=second["base_hash"],
        body=first["body"] + "\nThe second tab.\n",
    )
    assert stale.status_code == 409
    with schema_context(migrated_tenant.number):
        assert Draft.objects.get(hold__document=document).content["document.md"] == changed


def test_silent_editor_closed(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Silent past three minutes is closed; silent two is not; an organisation whose schema fails
    leaves the others' sweep to run."""
    from django.db import DatabaseError
    from django.utils import timezone

    from editing import tasks
    from editing.models import OpenEditor

    client, document, silent = opened(member_of, new_document)
    recent = client.post(f"/document/{document.number}/edit/load/").json()
    with schema_context(migrated_tenant.number):
        OpenEditor.objects.filter(pk=silent["editor"]).update(
            last_seen_at=timezone.now() - timedelta(minutes=4)
        )
        OpenEditor.objects.filter(pk=recent["editor"]).update(
            last_seen_at=timezone.now() - timedelta(minutes=2)
        )
    broken = 999

    class Tenants:
        def values_list(self, *_: Any, **__: Any) -> list[int]:
            return [broken, migrated_tenant.number]

    real = tasks.schema_context

    def failing(number: int) -> Any:
        if number == broken:
            raise DatabaseError("no such schema")
        return real(number)

    monkeypatch.setattr("tenancy.models.visited_by_background_work", Tenants)
    monkeypatch.setattr(tasks, "schema_context", failing)

    assert tasks.close_silent_editors() == 1
    with schema_context(migrated_tenant.number):
        assert OpenEditor.objects.get(pk=silent["editor"]).closed_at is not None
        assert OpenEditor.objects.get(pk=recent["editor"]).closed_at is None


def test_a_repeated_capture_is_accepted(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The same text again, from the base the editor last sent — its first answer lost — is
    accepted, not refused as stale."""
    client, document, loaded = opened(member_of, new_document)
    text = loaded["body"] + "\nA new sentence.\n"
    assert send(client, document, loaded, text).status_code == 200
    again = send(client, document, loaded, text)
    assert again.status_code == 200
    assert again.json()["base_hash"] == hashlib.sha256(text.encode()).hexdigest()


def test_a_capture_after_the_hold_ended_is_closed(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Released between the editor's check and its write: `409` *closed*, the kept draft
    untouched."""
    from django.db import transaction

    from documents.models import Document
    from editing import holds
    from editing.models import Draft, Hold, ReleaseKind

    client, document, loaded = opened(member_of, new_document)
    with schema_context(migrated_tenant.number), transaction.atomic():
        Document.objects.select_for_update().get(pk=document.pk)
        holds.release(Hold.objects.get(document=document), ReleaseKind.FORCED, reason="Synthetic")
    # The holder's editor learns how its hold ended, so it can offer the kept draft back.
    late = send(client, document, loaded, "Late text.\n")
    assert late.status_code == 409
    assert late.json() == {"closed": True, "released": "forced"}
    with schema_context(migrated_tenant.number):
        assert "Late" not in Draft.objects.get(hold__document=document).content["document.md"]


def test_a_capture_waits_for_a_commit_then_answers_busy(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The writer lock a commit holds keeps a capture out of the draft being consumed."""
    import threading

    from documents.locks import document_lock
    from editing.models import Draft
    from editing.views import capture

    monkeypatch.setattr(capture, "CAPTURE_LOCK_SECONDS", 0.2)
    client, document, loaded = opened(member_of, new_document)
    held, done = threading.Event(), threading.Event()

    def commit() -> None:
        with document_lock(migrated_tenant.number, document.number):
            held.set()
            done.wait(10)

    committing = threading.Thread(target=commit)
    committing.start()
    held.wait(10)
    try:
        response = send(client, document, loaded, "Typed while committing.\n")
    finally:
        done.set()
        committing.join()

    assert response.status_code == 503 and response.json() == {"busy": True}
    with schema_context(migrated_tenant.number):
        assert "committing" not in Draft.objects.get(hold__document=document).content["document.md"]


@pytest.mark.parametrize("body", ["Text\x00with a null.", "Text \ud800 without a pair."])
def test_a_capture_the_database_cannot_hold_is_refused(
    migrated_tenant: Any, member_of: Any, new_document: Any, body: str
) -> None:
    client, document, loaded = opened(member_of, new_document)
    payload = json.dumps(
        {"editor": loaded["editor"], "base_hash": loaded["base_hash"], "body": body}
    )
    response = client.post(
        f"/document/{document.number}/edit/capture/", data=payload, content_type="application/json"
    )
    assert response.status_code == 400


def test_a_deeply_nested_body_is_no_error(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    client, document, _ = opened(member_of, new_document)
    response = client.post(
        f"/document/{document.number}/edit/capture/",
        data="[" * 100_000 + "]" * 100_000,
        content_type="application/json",
    )
    assert response.status_code == 404


def test_heartbeat_counts_the_other_editors_and_close_closes(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    client, document, first = opened(member_of, new_document)
    assert post(client, document, "heartbeat", editor=first["editor"]).json() == {
        "others": 0,
        "prompt": False,
    }
    second = client.post(f"/document/{document.number}/edit/load/").json()
    assert post(client, document, "heartbeat", editor=first["editor"]).json() == {
        "others": 1,
        "prompt": False,
    }
    assert post(client, document, "close", editor=second["editor"]).status_code == 200
    assert post(client, document, "heartbeat", editor=first["editor"]).json() == {
        "others": 0,
        "prompt": False,
    }
    assert post(client, document, "heartbeat", editor=second["editor"]).status_code == 409


def test_capture_is_the_holders_alone(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right

    holder, author, own = member_of("the.author@example.test")
    other, _, membership = member_of("another.editor@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [own, membership], author)
    holder.post(f"/document/{document.number}/edit/take/")
    loaded = holder.post(f"/document/{document.number}/edit/load/").json()
    for route in ("capture", "heartbeat", "close"):
        response = post(
            other, document, route, editor=loaded["editor"], base_hash=loaded["base_hash"], body="x"
        )
        assert response.status_code == 404, route
    assert (
        post(holder, document, "capture", editor="not-a-uuid", base_hash="", body="").status_code
        == 404
    )


def test_a_capture_over_the_size_is_refused(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from editing.markdown import load_spec

    client, document, loaded = opened(member_of, new_document)
    body = "а" * (load_spec().max_bytes // 2 + 1)
    response = post(
        client,
        document,
        "capture",
        editor=loaded["editor"],
        base_hash=loaded["base_hash"],
        body=body,
    )
    assert response.status_code == 413


def test_a_stale_capture_from_a_closing_page_closes_its_editor(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Refused as stale, the closing page's capture still closes its editor, so the holder's
    other tab can finish without waiting for the silent-editor sweep."""
    from editing.models import OpenEditor

    client, document, first = opened(member_of, new_document)
    second = client.post(f"/document/{document.number}/edit/load/").json()
    assert send(client, document, second, "The second tab.\n").status_code == 200

    stale = post(
        client,
        document,
        "capture",
        editor=first["editor"],
        base_hash=first["base_hash"],
        body="The first tab.\n",
        close=True,
    )

    assert stale.status_code == 409 and stale.json() == {"stale": True}
    with schema_context(migrated_tenant.number):
        assert OpenEditor.objects.get(pk=first["editor"]).closed_at is not None


SECTIONS = (
    "An introductory sentence.\n\n"
    "# First section\n\nLead sentence of the first section.\n\n"
    "# Second section\n\nLead sentence of the second section.\n\n"
    "# Third section\n\nLead sentence of the third section.\n"
)


def sectioned(migrated_tenant: Any, member_of: Any, new_document: Any) -> tuple[Any, Any]:
    """A held document whose draft has three sections after a preamble."""
    from editing.models import Draft

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "document.md": SECTIONS}
        draft.save()
    return client, document


def whole(client: Any, document: Any) -> dict[str, Any]:
    """A tab's whole editor on the draft."""
    response = post(client, document, "load", range="whole")
    assert response.status_code == 200, response.content
    loaded: dict[str, Any] = response.json()
    return loaded


def draft_body(tenant: Any, document: Any) -> str:
    from editing.models import Draft

    with schema_context(tenant.number):
        body: str = Draft.objects.get(hold__document=document).content["document.md"]
    return body


def test_a_second_tabs_capture_is_stale(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Two tabs, each with the whole editor: the second to capture finds the text changed under
    it, and its text is not written (ADR-0006)."""
    client, document = sectioned(migrated_tenant, member_of, new_document)
    first, second = whole(client, document), whole(client, document)
    assert send(client, document, first, first["body"] + "\nAddition one.\n").status_code == 200
    late = send(client, document, second, second["body"] + "\nAddition two.\n")
    assert late.status_code == 409 and late.json() == {"stale": True}
    body = draft_body(migrated_tenant, document)
    assert "Addition one." in body and "Addition two." not in body


def test_changes_shows_the_stopped_text_to_its_holder_alone(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The stopped editor's view: its text as changes against the draft now; refused for another
    person, a text no draft can hold, or one over the size allowed."""
    from editing.markdown import load_spec

    client, document = sectioned(migrated_tenant, member_of, new_document)
    editor = whole(client, document)
    answer = post(
        client, document, "changes", editor=editor["editor"], body=editor["body"] + "New.\n"
    )
    assert answer.status_code == 200 and "New." in answer.json()["html"]
    other, _, _ = member_of("another.member@example.test")
    assert post(other, document, "changes", editor=editor["editor"], body="x").status_code == 404
    assert (
        post(client, document, "changes", editor=editor["editor"], body="\ud800").status_code == 400
    )
    too_big = "x" * (load_spec().max_bytes + 1)
    assert (
        post(client, document, "changes", editor=editor["editor"], body=too_big).status_code == 413
    )


def test_the_answer_says_whether_the_draft_has_edits(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The capture's answer carries `edited`: true when this capture wrote text into the draft,
    false when it brought nothing new — the editor's own flag, on which *My edits* is offered;
    whether the draft differs from the head is the page's and the release's to read."""
    client, document, loaded = opened(member_of, new_document)
    same = send(client, document, loaded, loaded["body"])
    changed = send(client, document, loaded, loaded["body"] + "\nA new sentence.\n")
    loaded["base_hash"] = changed.json()["base_hash"]
    back = send(client, document, loaded, loaded["body"])

    assert same.status_code == changed.status_code == back.status_code == 200
    again = send(
        client, document, {**loaded, "base_hash": back.json()["base_hash"]}, loaded["body"]
    )
    assert [r.json()["edited"] for r in (same, changed, back, again)] == [False, True, True, False]

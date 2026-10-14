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
    text = loaded["body"] + "\nНове речення.\n"
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
    changed = first["body"] + "\nПерша вкладка.\n"
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
        body=first["body"] + "\nДруга вкладка.\n",
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
    text = loaded["body"] + "\nНове речення.\n"
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
        holds.release(Hold.objects.get(document=document), ReleaseKind.FORCED, reason="тест")
    # The holder's editor learns how its hold ended, so it can offer the kept draft back.
    late = send(client, document, loaded, "Пізній текст.\n")
    assert late.status_code == 409
    assert late.json() == {"closed": True, "released": "forced"}
    with schema_context(migrated_tenant.number):
        assert "Пізній" not in Draft.objects.get(hold__document=document).content["document.md"]


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
        response = send(client, document, loaded, "Під час фіксації.\n")
    finally:
        done.set()
        committing.join()

    assert response.status_code == 503 and response.json() == {"busy": True}
    with schema_context(migrated_tenant.number):
        assert "фіксації" not in Draft.objects.get(hold__document=document).content["document.md"]


@pytest.mark.parametrize("body", ["Текст\x00з нулем.", "Текст \ud800 без пари."])
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
    assert send(client, document, second, "Друга вкладка.\n").status_code == 200

    stale = post(
        client,
        document,
        "capture",
        editor=first["editor"],
        base_hash=first["base_hash"],
        body="Перша вкладка.\n",
        close=True,
    )

    assert stale.status_code == 409 and stale.json() == {"stale": True}
    with schema_context(migrated_tenant.number):
        assert OpenEditor.objects.get(pk=first["editor"]).closed_at is not None


SECTIONS = (
    "Вступне речення.\n\n"
    "# Перший розділ\n\nПерше речення першого розділу.\n\n"
    "# Другий розділ\n\nПерше речення другого розділу.\n\n"
    "# Третій розділ\n\nПерше речення третього розділу.\n"
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


def section(client: Any, document: Any, ordinal: int) -> dict[str, Any]:
    response = post(client, document, "load", range=f"section:{ordinal}")
    assert response.status_code == 200, response.content
    loaded: dict[str, Any] = response.json()
    return loaded


def draft_body(tenant: Any, document: Any) -> str:
    from editing.models import Draft

    with schema_context(tenant.number):
        body: str = Draft.objects.get(hold__document=document).content["document.md"]
    return body


def test_disjoint_ranges_both_capture(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Editors over two sections never conflict (DL-0167): each capture lands in its own range."""
    client, document = sectioned(migrated_tenant, member_of, new_document)
    first, second = section(client, document, 0), section(client, document, 1)
    assert first["body"].startswith("# Перший розділ")
    assert second["body"].startswith("# Другий розділ")
    one = first["body"].replace("Перше речення першого", "Змінене речення першого")
    two = second["body"].replace("Перше речення другого", "Змінене речення другого")
    answered = [send(client, document, first, one), send(client, document, second, two)]
    assert [a.status_code for a in answered] == [200, 200]
    body = draft_body(migrated_tenant, document)
    assert "Змінене речення першого" in body and "Змінене речення другого" in body
    assert body.startswith("Вступне речення.\n\n# Перший розділ")
    assert "Перше речення третього розділу." in body
    with schema_context(migrated_tenant.number):
        from editing.models import OpenEditor

        assert (
            OpenEditor.objects.get(pk=first["editor"]).base_hash == answered[0].json()["base_hash"]
        )
        assert (
            OpenEditor.objects.get(pk=second["editor"]).base_hash == answered[1].json()["base_hash"]
        )


def test_same_range_second_is_stale(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Two editors on one section: the second to capture finds its range changed (DL-0167)."""
    client, document = sectioned(migrated_tenant, member_of, new_document)
    first, second = section(client, document, 1), section(client, document, 1)
    assert send(client, document, first, first["body"] + "\nПерше доповнення.\n").status_code == 200
    late = send(client, document, second, second["body"] + "\nДруге доповнення.\n")
    assert late.status_code == 409 and late.json() == {"stale": True}
    body = draft_body(migrated_tenant, document)
    assert "Перше доповнення." in body and "Друге доповнення." not in body


def test_a_later_section_captures_after_an_earlier_one_grew(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """An editor names its section by the heading's ordinal; when an earlier section grows by ten
    sentences and gains a heading, the later editor is renumbered in the same write and still lands
    in its own section."""
    from editing.models import OpenEditor

    client, document = sectioned(migrated_tenant, member_of, new_document)
    first, third = section(client, document, 0), section(client, document, 2)
    grown = first["body"] + "".join(f"\nДодаткове речення {n}.\n" for n in range(10))
    answered = send(client, document, first, grown)
    assert answered.status_code == 200
    first = {**first, "base_hash": answered.json()["base_hash"]}
    with_heading = grown + "\n# Новий розділ\n\nРечення нового розділу.\n"
    assert send(client, document, first, with_heading).status_code == 200
    with schema_context(migrated_tenant.number):
        assert OpenEditor.objects.get(pk=third["editor"]).range == "section:3"
    changed = third["body"].replace("Перше речення третього", "Змінене речення третього")
    assert send(client, document, third, changed).status_code == 200
    body = draft_body(migrated_tenant, document)
    assert "Додаткове речення 9." in body and "# Новий розділ" in body
    assert "Змінене речення третього розділу." in body
    assert body.index("# Новий розділ") < body.index("# Другий розділ")
    assert body.rstrip().endswith("Змінене речення третього розділу.")


ADJACENT = "# Перший розділ\n\nПерше речення.\n\n# Другий розділ\n\nДруге речення.\n"


def test_a_section_keeps_the_blank_line_before_the_next(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The editor sends its text with one final newline; the blank line that parted the section
    from the next heading stays."""
    client, document = sectioned(migrated_tenant, member_of, new_document)
    from editing.models import Draft

    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "document.md": ADJACENT}
        draft.save()
    first = section(client, document, 0)
    sent = "# Перший розділ\n\nЗмінене речення.\n"
    assert send(client, document, first, sent).status_code == 200
    assert draft_body(migrated_tenant, document) == ADJACENT.replace(
        "Перше речення.", "Змінене речення."
    )


def test_a_typed_heading_keeps_the_editor_whole(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """A heading typed into a section editor does not split it (DL-0167): its span counts the new
    heading, and its next capture lands over both."""
    from editing.models import OpenEditor

    client, document = sectioned(migrated_tenant, member_of, new_document)
    editor = section(client, document, 1)
    grown = editor["body"] + "\n# Вставлений розділ\n\nРечення.\n\n"
    answered = send(client, document, editor, grown)
    assert answered.status_code == 200
    with schema_context(migrated_tenant.number):
        assert OpenEditor.objects.get(pk=editor["editor"]).range == "section:1:2"
    editor = {**editor, "base_hash": answered.json()["base_hash"]}
    again = grown.replace("Вставлений", "Перейменований")
    assert send(client, document, editor, again).status_code == 200
    body = draft_body(migrated_tenant, document)
    assert "# Перейменований розділ" in body and "# Вставлений розділ" not in body
    assert body.index("# Перейменований розділ") < body.index("# Третій розділ")


def test_an_editor_that_removes_its_own_heading_is_closed(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Its text is captured, and the editor closed in the same write: it no longer names a
    section, and must not name the next one."""
    from editing.models import OpenEditor

    client, document = sectioned(migrated_tenant, member_of, new_document)
    second, third = section(client, document, 1), section(client, document, 2)
    headless = second["body"].replace("# Другий розділ\n\n", "")
    answered = send(client, document, second, headless)
    assert answered.status_code == 200 and answered.json().get("closed") is True
    assert "Перше речення другого розділу." in draft_body(migrated_tenant, document)
    with schema_context(migrated_tenant.number):
        assert OpenEditor.objects.get(pk=second["editor"]).closed_at is not None
        assert OpenEditor.objects.get(pk=third["editor"]).range == "section:1"
    changed = third["body"].replace("Перше речення третього", "Змінене речення третього")
    assert send(client, document, third, changed).status_code == 200


def test_changes_shows_the_stopped_text_to_its_holder_alone(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The stopped editor's view: its text as changes against its range now; refused for another
    person, a text no draft can hold, or one over the size allowed."""
    from editing.markdown import load_spec

    client, document = sectioned(migrated_tenant, member_of, new_document)
    editor = section(client, document, 0)
    answer = post(
        client, document, "changes", editor=editor["editor"], body=editor["body"] + "Нове.\n"
    )
    assert answer.status_code == 200 and "Нове." in answer.json()["html"]
    other, _, _ = member_of("another.member@example.test")
    assert post(other, document, "changes", editor=editor["editor"], body="x").status_code == 404
    assert (
        post(client, document, "changes", editor=editor["editor"], body="\ud800").status_code == 400
    )
    too_big = "а" * (load_spec().max_bytes + 1)
    assert (
        post(client, document, "changes", editor=editor["editor"], body=too_big).status_code == 413
    )


def test_changes_shows_the_text_alone_once_its_heading_went(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """An editor the server closed because its capture removed its own heading still names an
    ordinal, now another section's: with `alone`, its later text is shown as typed and compared
    with nothing."""
    client, document = sectioned(migrated_tenant, member_of, new_document)
    second = section(client, document, 1)
    headless = second["body"].replace("# Другий розділ\n\n", "")
    assert send(client, document, second, headless).json().get("closed") is True
    later = headless + "Набране потім.\n"
    shown = post(client, document, "changes", editor=second["editor"], body=later, alone=True)
    assert shown.status_code == 200
    html = shown.json()["html"]
    assert "Набране потім." in html and "<ins" not in html and "Третій розділ" not in html
    # The sentence says what is shown: the text as typed, not changes.
    assert "як зміни" not in html and "так, як ви його набрали" in html


def test_section_captures_keep_the_draft_within_its_size(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Each section's text is within the size allowed, and so must be the draft its capture
    leaves: one that would grow the draft past it is refused as too large, the draft as it was."""
    from editing.markdown import load_spec

    client, document = sectioned(migrated_tenant, member_of, new_document)
    first, second = section(client, document, 0), section(client, document, 1)
    filler = "слово " * (load_spec().max_bytes * 6 // 10 // len("слово ".encode()))
    assert send(client, document, first, first["body"] + filler + "\n").status_code == 200
    before = draft_body(migrated_tenant, document)
    refused = send(client, document, second, second["body"] + filler + "\n")
    assert refused.status_code == 413 and refused.json() == {"too_large": True}
    assert draft_body(migrated_tenant, document) == before
    assert len(before.encode()) <= load_spec().max_bytes


def test_a_heading_level_changed_tells_the_page(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """A subsection raised to a section changes the spans though not their number: the page is told
    its sections changed."""
    from editing.models import Draft

    client, document = sectioned(migrated_tenant, member_of, new_document)
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        body = "# А\n\nРечення.\n\n## Б\n\nРечення.\n\n# В\n\nРечення.\n"
        draft.content = {**draft.content, "document.md": body}
        draft.save()
    editor = section(client, document, 1)
    answered = send(client, document, editor, editor["body"].replace("## Б", "# Б"))
    assert answered.status_code == 200 and answered.json().get("sections_changed") is True

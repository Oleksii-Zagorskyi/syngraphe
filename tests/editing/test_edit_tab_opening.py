"""Opening an edit tab normalises the draft at most once (ASR-21, DL-0484), and not at all after a
capture (DL-23-001): the page asks whether the draft holds edits and reads the declarations *Mark*
offers from one normalisation, or from the answers the draft stores with a key over their inputs,
and hands them to the editor, whose `load` then reads none. Counts, not a clock: the normalizer is
most of what an opening costs, whatever the machine.

Invented text."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = (
    "# Scope\n\n[The clerk]{.role #clerk} files the request. The approver signs it.\n\n"
    "# Records\n\nThe record is kept for a year.\n"
)
ENTITIES = '- kind: "role"\n  key: "role-1"\n  label: "the approver"\n'
# The draft's own declaration, then the span's key it lacks, labelled with its words (DL-0440).
DECLARATIONS = [
    {"kind": "role", "key": "role-1", "label": "the approver"},
    {"kind": "role", "key": "clerk", "label": "The clerk"},
]
DECLARED = re.compile(r'<script id="editor-declared" type="application/json">(.*?)</script>', re.S)


def counting(monkeypatch: Any) -> Callable[[], int]:
    """The normalizer's runs from here on, as a function returning their count."""
    from editing import services

    calls = []
    original = services.normalize

    def counted(*args: Any, **kwargs: Any) -> bytes:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(services, "normalize", counted)
    return lambda: len(calls)


def edited_draft(tenant: Any, document: Any) -> Any:
    """The holder's draft of `document`, its body and declarations changed from the head's."""
    from editing.models import Draft

    with schema_context(tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "document.md": BODY, "entities.yaml": ENTITIES}
        draft.save()
        return draft


def one_check(tenant: Any, document: Any, runs: Callable[[], int]) -> int:
    """What one ask of whether the draft holds edits costs the normalizer."""
    from editing import holds, services

    with schema_context(tenant.number):
        before = runs()
        hold = holds.open_hold(document)
        assert hold is not None and services.has_edits(hold)
        return runs() - before


def declared_on(page: Any) -> Any:
    found = DECLARED.search(page.content.decode("utf-8"))
    assert found is not None, "the page hands the editor no declarations"
    return json.loads(found.group(1))


def load(client: Any, path: str, **asked: Any) -> Any:
    response = client.post(
        path, json.dumps({"range": "whole", **asked}), content_type="application/json"
    )
    assert response.status_code == 200, response.content
    return response.json()


def test_opening_the_edit_tab_normalises_the_draft_once(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: Any
) -> None:
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    edited_draft(migrated_tenant, document)
    runs = counting(monkeypatch)
    once = one_check(migrated_tenant, document, runs)
    assert once >= 1

    before = runs()
    page = client.get(f"/document/{document.number}/edit/", HTTP_SEC_FETCH_SITE="same-origin")
    assert page.status_code == 200
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    # As the editor asks once the page has handed it the declarations.
    load(client, f"/document/{document.number}/edit/load/", entities=False)

    assert runs() - before == once


def test_the_edit_tab_validates_the_draft_once(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: Any
) -> None:
    """The check of edits, the declarations, the outline and the draft's view each ask whether the
    whitelist accepts the draft; the page parses it for that once."""
    from editing.markdown import validator

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    edited_draft(migrated_tenant, document)
    parsed = []
    original = validator._refusals

    def counted(text: str, spec: Any) -> Any:
        parsed.append(text)
        return original(text, spec)

    monkeypatch.setattr(validator, "_refusals", counted)

    page = client.get(f"/document/{document.number}/edit/", HTTP_SEC_FETCH_SITE="same-origin")

    assert page.status_code == 200
    assert parsed.count(BODY) == 1


def test_the_page_hands_the_editor_what_load_would_declare(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The declarations on the page are the ones `load` answers when asked for them (DL-0073,
    DL-0440); asked for none, `load` reads none."""
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    edited_draft(migrated_tenant, document)
    address = f"/document/{document.number}/edit/load/"

    page = client.get(f"/document/{document.number}/edit/", HTTP_SEC_FETCH_SITE="same-origin")

    assert declared_on(page) == load(client, address)["entities"] == DECLARATIONS
    assert "entities" not in load(client, address, entities=False)


def test_a_tab_drawn_before_the_hold_leaves_the_declarations_to_load(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Drawn for a take still to come there is no draft yet to read: the page hands nothing, and
    the editor asks `load` for the draft the take made."""
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)

    page = client.get(f"/document/{document.number}/edit/", HTTP_SEC_FETCH_SITE="same-origin")

    assert page.status_code == 200
    assert DECLARED.search(page.content.decode("utf-8")) is None
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    assert load(client, f"/document/{document.number}/edit/load/")["entities"] == []


def test_opening_an_appendix_normalises_the_draft_once(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    monkeypatch: Any,
) -> None:
    """The appendix's tab asks whether the draft holds edits once, and its editor's `load` reads
    the declarations from the page, as the document's own tab does."""
    from access.rights import Right

    _, author, _ = member_of("the.author@example.test")
    client, _, own = member_of("the.holder@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [own], author)
    listed = [{"number": 1, "title": "Request form (example)"}]
    commit_version(
        document,
        author,
        "# One\n\nThe first sentence.\n",
        files={"appendices/1.md": b"# Request form\n\nThe form sentence.\n"},
        appendices=listed,
    )
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    edited_draft(migrated_tenant, document)
    runs = counting(monkeypatch)
    once = one_check(migrated_tenant, document, runs)

    before = runs()
    page = client.get(
        f"/document/{document.number}/appendix/1/edit/", HTTP_SEC_FETCH_SITE="same-origin"
    )
    assert page.status_code == 200
    address = f"/document/{document.number}/appendix/1/edit/load/"
    load(client, address, entities=False)

    assert runs() - before == once
    assert declared_on(page) == load(client, address)["entities"] == DECLARATIONS


@pytest.mark.parametrize("tab", ["edit/", "appendix/1/edit/"])
def test_declarations_that_cannot_be_read_leave_the_tab_drawn(
    tab: str,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    monkeypatch: Any,
) -> None:
    """Reading the declarations failing costs the page nothing it drew before: the tab is drawn,
    the draft counted as edited as `has_edits` counts what it cannot compare, and the editor left
    to ask `load`, which answers as it always did."""
    from access.rights import Right
    from editing import services

    _, author, _ = member_of("the.author@example.test")
    client, _, own = member_of("the.holder@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [own], author)
    commit_version(
        document,
        author,
        "# One\n\nThe first sentence.\n",
        files={"appendices/1.md": b"# Request form\n\nThe form sentence.\n"},
        appendices=[{"number": 1, "title": "Request form (example)"}],
    )
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    edited_draft(migrated_tenant, document)

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("a draft whose declarations do not read")

    monkeypatch.setattr(services, "draft_declarations", broken)

    page = client.get(f"/document/{document.number}/{tab}", HTTP_SEC_FETCH_SITE="same-origin")

    assert page.status_code == 200
    drawn = page.content.decode("utf-8")
    assert DECLARED.search(drawn) is None
    assert 'data-edited="true"' in drawn


def worked(queued: list[Any]) -> None:
    """The jobs a capture queued, run as the worker runs them."""
    from editing.tasks import refresh_opening

    for tenant, hold, written in queued:
        refresh_opening(tenant, str(hold), written.isoformat())
    queued.clear()


def captured(client: Any, document: Any, text: str, queued: list[Any]) -> None:
    """`text` written into the holder's draft as their editor writes it — opened, then captured —
    and the worker's refresh it queued run."""
    address = f"/document/{document.number}/edit/"
    opened = load(client, f"{address}load/")
    payload = {"editor": opened["editor"], "base_hash": opened["base_hash"], "body": text}
    answer = client.post(f"{address}capture/", json.dumps(payload), content_type="application/json")
    assert answer.status_code == 200, answer.content
    worked(queued)


def held_document(
    tenant: Any, member_of: Any, new_document: Any, *, declaring: bool = True
) -> tuple[Any, Any]:
    """`(client, document)`: a new document held by its author, its draft declaring `ENTITIES`
    unless told otherwise."""
    from editing.models import Draft

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    if declaring:
        with schema_context(tenant.number):
            draft = Draft.objects.get(hold__document=document)
            draft.content = {**draft.content, "entities.yaml": ENTITIES}
            draft.save()
    return client, document


def opened(client: Any, document: Any) -> str:
    page = client.get(f"/document/{document.number}/edit/", HTTP_SEC_FETCH_SITE="same-origin")
    assert page.status_code == 200
    return str(page.content.decode("utf-8"))


def test_after_a_capture_the_tab_opens_without_the_normalizer(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: Any, queued_openings: Any
) -> None:
    """After a capture and the worker's job it queues, the tab reads the stored answers, and they
    are the answers the draft itself gives."""
    client, document = held_document(migrated_tenant, member_of, new_document)
    captured(client, document, BODY, queued_openings)
    runs = counting(monkeypatch)

    drawn = opened(client, document)

    assert runs() == 0
    assert json.loads(DECLARED.search(drawn).group(1)) == DECLARATIONS  # type: ignore[union-attr]
    assert 'data-edited="true"' in drawn


def test_text_typed_and_taken_back_is_no_edit(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_openings: Any
) -> None:
    """The stored answer is the comparison's, not a flag of writing: a draft captured back to the
    head's text holds no edits, and the tab says so (DL-0510)."""
    from editing import holds
    from editing.models import Draft

    client, document = held_document(migrated_tenant, member_of, new_document, declaring=False)
    with schema_context(migrated_tenant.number):
        hold = holds.open_hold(document)
        assert hold is not None
        original = hold.draft.content["document.md"]
    captured(client, document, BODY, queued_openings)
    with schema_context(migrated_tenant.number):
        assert Draft.objects.get(hold__document=document).opening["edited"] is True
    captured(client, document, original, queued_openings)

    with schema_context(migrated_tenant.number):
        assert Draft.objects.get(hold__document=document).opening["edited"] is False
    assert 'data-edited="false"' in opened(client, document)


def test_an_answer_whose_inputs_changed_is_read_again(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: Any, queued_openings: Any
) -> None:
    """A draft written behind the stored answers' back — by a path that does not refresh them — is
    read again on its next opening, and the new answers kept for the one after."""
    from editing.models import Draft

    client, document = held_document(migrated_tenant, member_of, new_document)
    captured(client, document, BODY, queued_openings)
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "entities.yaml": ""}
        draft.save()
    runs = counting(monkeypatch)

    first = opened(client, document)
    after_first = runs()
    opened(client, document)

    assert after_first == 1 and runs() == 1
    assert json.loads(DECLARED.search(first).group(1)) == [  # type: ignore[union-attr]
        {"kind": "role", "key": "clerk", "label": "The clerk"}
    ]


def test_the_key_covers_every_input(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """Each input the answers are read from changes the key: the draft's content, its base, the
    head, a staged file and the sentence lists."""
    from django.utils import timezone

    from editing import holds, services
    from editing.models import DraftFile, DraftFileKind, DraftFileOperation
    from editing.normalizer import Lists

    _, document = held_document(migrated_tenant, member_of, new_document)
    with schema_context(migrated_tenant.number):
        hold = holds.open_hold(document)
        assert hold is not None
        draft = hold.draft
        lists = Lists("uk", ("р.",), ("ст.",))
        head = draft.base_commit
        key = services._opening_key(draft, head, lists)
        assert services._opening_key(draft, head, lists) == key
        changed = {
            services._opening_key(draft, "0" * 40, lists),
            services._opening_key(draft, head, Lists("uk", ("р.", "т."), ("ст.",))),
            services._opening_key(draft, head, Lists("uk", ("р.",), ())),
        }
        draft.content = {**draft.content, "document.md": "Another sentence.\n"}
        changed.add(services._opening_key(draft, head, lists))
        draft.refresh_from_db()
        draft.base_commit = "f" * 40
        changed.add(services._opening_key(draft, head, lists))
        draft.refresh_from_db()
        DraftFile.objects.create(
            draft=draft,
            kind=DraftFileKind.ATTACHMENT,
            path="attachments/form.pdf",
            operation=DraftFileOperation.REMOVE,
            at=timezone.now(),
        )
        changed.add(services._opening_key(draft, head, lists))

    assert key not in changed and len(changed) == 6


def test_an_answer_read_through_a_failure_is_not_kept(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: Any
) -> None:
    """A comparison that fails for a reason outside the draft counts the draft as edited, as
    `has_edits` does, and leaves nothing stored that a later opening would trust."""
    from editing import services
    from editing.models import Draft

    client, document = held_document(migrated_tenant, member_of, new_document)

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("a repository that cannot be read")

    monkeypatch.setattr(services, "staged_changes", broken)

    assert 'data-edited="true"' in opened(client, document)
    with schema_context(migrated_tenant.number):
        assert Draft.objects.get(hold__document=document).opening is None


def test_a_capture_queues_the_answers_outside_its_lock(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: Any
) -> None:
    """A capture that writes text asks the worker for the tab's answers — the tenant, the hold and
    the write's time — once its writer lock is released; one that writes nothing asks nothing."""
    from documents import locks
    from editing import holds, tasks
    from editing.models import Draft

    client, document = held_document(migrated_tenant, member_of, new_document)
    asked: list[tuple[Any, ...]] = []

    def watched(*job: Any) -> None:
        asked.append((*job, set(locks._held.__dict__.get("keys", set()))))

    monkeypatch.setattr(tasks, "queue_opening", watched)
    address = f"/document/{document.number}/edit/"
    opened = load(client, f"{address}load/")
    payload = {"editor": opened["editor"], "base_hash": opened["base_hash"], "body": BODY}
    for _ in range(2):
        sent = client.post(
            f"{address}capture/", json.dumps(payload), content_type="application/json"
        )
        assert sent.status_code == 200

    with schema_context(migrated_tenant.number):
        hold = holds.open_hold(document)
        assert hold is not None
        written = Draft.objects.get(hold=hold).updated_at
    assert asked == [(migrated_tenant.number, hold.pk, written, set())]


def test_the_worker_refreshes_in_the_tenant_schema(
    migrated_tenant: Any, member_of: Any, new_document: Any, queued_openings: Any
) -> None:
    """The worker's job reads the answers in the tenant's own schema, outside any request, and the
    tab then opens on them."""
    from editing.models import Draft

    client, document = held_document(migrated_tenant, member_of, new_document)
    address = f"/document/{document.number}/edit/"
    opened = load(client, f"{address}load/")
    payload = {"editor": opened["editor"], "base_hash": opened["base_hash"], "body": BODY}
    client.post(f"{address}capture/", json.dumps(payload), content_type="application/json")
    assert len(queued_openings) == 1

    worked(queued_openings)

    with schema_context(migrated_tenant.number):
        stored = Draft.objects.get(hold__document=document).opening
    assert stored is not None and stored["edited"] is True
    assert stored["declared"] == DECLARATIONS


def test_a_refresh_overtaken_by_a_newer_write_reads_nothing(
    migrated_tenant: Any, member_of: Any, new_document: Any, monkeypatch: Any
) -> None:
    """A refresh whose write a newer one has followed is left to that write's own refresh: typing
    in bursts costs one pass per answer anyone could open, not one per capture."""
    from editing import holds, services

    _, document = held_document(migrated_tenant, member_of, new_document)
    with schema_context(migrated_tenant.number):
        hold = holds.open_hold(document)
        assert hold is not None
        draft = hold.draft
        older = draft.updated_at
        draft.content = {**draft.content, "document.md": BODY}
        draft.save()
        runs = counting(monkeypatch)

        services.refresh_opening(hold.pk, older)

        draft.refresh_from_db()
        assert runs() == 0 and draft.opening is None


def test_an_answer_read_before_a_newer_write_is_not_kept(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """An answer is kept only on the draft as it was read: one read before a newer write never
    replaces what that write's own refresh keeps."""
    from editing import holds, services
    from editing.models import Draft

    _, document = held_document(migrated_tenant, member_of, new_document)
    with schema_context(migrated_tenant.number):
        hold = holds.open_hold(document)
        assert hold is not None
        read = hold.draft
        newer = Draft.objects.get(pk=read.pk)
        newer.content = {**newer.content, "document.md": BODY}
        newer.save()

        services.opening(hold)

        assert Draft.objects.get(pk=read.pk).opening is None


def test_a_refresh_after_the_hold_ended_is_quiet(
    migrated_tenant: Any, member_of: Any, new_document: Any, caplog: Any
) -> None:
    """A draft finished or discarded between a capture's answer and its refresh is an ordinary
    race: the refresh reads nothing and logs nothing."""
    from editing import holds, services
    from editing.models import Draft

    client, document = held_document(migrated_tenant, member_of, new_document)
    with schema_context(migrated_tenant.number):
        hold = holds.open_hold(document)
        assert hold is not None
        written = hold.draft.updated_at
        Draft.objects.filter(hold=hold).delete()

        services.refresh_opening(hold.pk, written)

    assert "not refreshed" not in caplog.text

"""Opening an edit tab normalises the draft once (ASR-21, DL-0484): the page asks whether the draft
holds edits and reads the declarations *Mark* offers from the one normalisation, and hands them to
the editor, whose `load` then reads none. A count, not a clock: the normalizer is most of what an
opening costs, and a second pass over the draft doubles it whatever the machine.

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

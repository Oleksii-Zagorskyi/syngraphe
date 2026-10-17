"""The parts panel in Chromium (DL-0442): shown once the hold is taken on mount, and a part
operation posted only once the open editor has captured and closed, so the typed text is in the
draft the tab draws again. Invented text; the people are synthetic examples."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"


@pytest.fixture(autouse=True)
def settled(page: Any) -> Iterator[None]:
    """Each page left quiet before the server and the database go: what the tab still sends —
    its take on mount, a capture, a heartbeat — answered, every editor finished, the page closed."""
    yield
    for open_page in list(page.context.pages):
        if open_page.is_closed():
            continue
        try:
            open_page.wait_for_load_state("networkidle")
            open_page.evaluate(
                """async () => {
                  const editor = document.getElementById('editor')?.editor;
                  if (editor && editor.capture) await editor.capture.finish().catch(() => null);
                }"""
            )
        finally:
            open_page.close()


def opened(
    browser_server: str,
    page: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
) -> Any:
    """A new document's edit tab opened in the browser by an editor who may create appendices;
    the hold taken by the tab as it mounts."""
    from access.rights import Right

    _, author, _ = member_of("the.author@example.test")
    client, _, own = member_of("the.editor@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT, Right.CREATE_APPENDIX], [own], author)
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/edit/")
    return document


def test_the_panel_appears_once_the_hold_is_taken(
    browser_server: str,
    page: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
) -> None:
    from editing.models import Hold

    document = opened(browser_server, page, member_of, new_document, link_group)
    page.wait_for_selector("[data-parts-panel]:not([hidden])")
    with schema_context(migrated_tenant.number):
        assert Hold.objects.filter(document=document, released_at__isnull=True).exists()


def test_a_part_operation_keeps_the_typed_text(
    browser_server: str,
    page: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    settings: Any,
) -> None:
    from editing.models import Draft, OpenEditor

    settings.LANGUAGE_CODE = "en"
    document = opened(browser_server, page, member_of, new_document, link_group)
    page.click("button[data-command=edit-whole]")
    page.wait_for_function(f"() => {EDITOR} !== undefined")
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    page.keyboard.type(" A sentence typed before the part.", delay=10)
    page.fill("[data-parts-panel] .part-add input[name=title]", "Holiday calendar (example)")
    page.click("[data-parts-panel] .appendices .part-add button[type=submit]")
    page.wait_for_selector("[data-parts-panel] [data-appendix='1']")

    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
        assert "A sentence typed before the part." in draft.content["document.md"]
        assert draft.content["frontmatter"]["appendices"] == [
            {"number": 1, "title": "Holiday calendar (example)"}
        ]
        assert not OpenEditor.objects.filter(draft=draft, closed_at__isnull=True).exists()


def test_the_panel_collapses_to_its_edge(
    browser_server: str,
    page: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
) -> None:
    opened(browser_server, page, member_of, new_document, link_group)
    page.wait_for_selector("[data-parts-panel]:not([hidden])")
    page.click("[data-parts-panel] [data-pane-toggle=parts-panel]")
    width = page.evaluate("document.getElementById('parts-panel').getBoundingClientRect().width")
    assert width <= 40

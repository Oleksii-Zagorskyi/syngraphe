"""The whole-document editor in Chromium: what it loads it writes back unchanged, its toolbar
writes the stored spelling, and its clause numbers follow the text (ADR-0010, DL-0065).
Invented text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"


def test_load_serialise_round_trip(editing: Any, markdown: Any, conformance_body: str) -> None:
    editing(conformance_body)
    assert markdown() == conformance_body


CONTROLS = [
    ("strong", "**слово**\n"),
    ("em", "*слово*\n"),
    ("underline", "[слово]{.underline}\n"),
    ("heading2", "## слово\n"),
    ("heading4", "#### слово\n"),
    ("bullet_list", "- слово\n"),
    ("ordered_list", "1. слово\n"),
    ("quote", "> слово\n"),
    ("note", "> [!note]\n> слово\n"),
    ("warning", "> [!warning]\n> слово\n"),
    ("example", "> [!example]\n> слово\n"),
]


def test_toolbar_constructs_serialise_canonically(editing: Any, markdown: Any, page: Any) -> None:
    editing("слово\n")
    for command, expected in CONTROLS:
        page.evaluate(f"{EDITOR}.replace('слово\\n')")
        page.evaluate(f"{EDITOR}.select(1, 6)")
        page.click(f"button[data-command={command}]")
        assert markdown() == expected, command

    page.evaluate(f"{EDITOR}.replace('слово\\n')")
    page.evaluate(f"{EDITOR}.select(1, 6)")
    page.click("button[data-command=link]")
    page.fill("input[data-field=link]", "https://example.org/poriadok")
    page.press("input[data-field=link]", "Enter")
    assert markdown() == "[слово](https://example.org/poriadok)\n"

    page.evaluate(f"{EDITOR}.replace('слово\\n')")
    page.evaluate(f"{EDITOR}.select(1, 6)")
    page.click("button[data-command=link]")
    page.fill("input[data-field=link]", "javascript:alert(1)")
    page.press("input[data-field=link]", "Enter")
    assert markdown() == "слово\n"

    page.evaluate(f"{EDITOR}.replace('слово\\n')")
    page.evaluate(f"{EDITOR}.select(6)")
    page.click("button[data-command=table]")
    page.click("button[data-command=add_row]")
    assert markdown().startswith("слово\n\n|  |  |\n| --- | --- |\n|  |  |\n")

    page.evaluate(f"{EDITOR}.replace('слово\\n')")
    page.evaluate(f"{EDITOR}.select(1, 6)")
    page.click("button[data-command=strong]")
    page.click("button[data-command=undo]")
    assert markdown() == "слово\n"
    page.click("button[data-command=redo]")
    assert markdown() == "**слово**\n"


def test_the_toolbar_offers_only_whitelisted_controls(editing: Any, page: Any) -> None:
    editing("слово\n")
    commands = page.eval_on_selector_all(
        ".editor-controls button[data-command]", "buttons => buttons.map(b => b.dataset.command)"
    )
    assert commands == [
        "paragraph", "heading1", "heading2", "heading3", "heading4", "bullet_list",
        "ordered_list", "strong", "em", "underline", "quote", "note", "warning", "example",
        "table", "add_row", "undo", "redo", "link", "source", "finish",
    ]  # fmt: skip


def test_gutter_numbers_follow_edits(editing: Any, page: Any) -> None:
    editing("# Перший\n\nАбзац один.\n\nАбзац два.\n\n# Другий\n\nАбзац три.\n")
    clauses = "() => [...document.querySelectorAll('.clause')].map(c => c.textContent)"
    # Headings carry their number in the gutter too, as the reading view shows them.
    assert page.evaluate(clauses) == ["1", "1-1", "1-2", "2", "2-1"]
    end_of_first = page.evaluate(
        f"(() => {{ let at = 0; {EDITOR}.view.state.doc.descendants((n, p) => "
        "{ if (!at && n.type.name === 'paragraph') at = p + n.nodeSize - 1; }); return at; })()"
    )
    page.evaluate(f"{EDITOR}.select({end_of_first})")
    page.focus(".ProseMirror")
    page.keyboard.press("Enter")
    page.keyboard.type("Новий абзац.")
    assert page.evaluate(clauses) == ["1", "1-1", "1-2", "1-3", "2", "2-1"]
    assert page.eval_on_selector(".clause", "c => c.isContentEditable") is False


def test_a_tab_from_elsewhere_waits_for_start_editing(
    browser_server: str, page: Any, migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    """The tab reached from another site shows *Start editing* and takes nothing until pressed
    (DL-0325)."""
    import re

    from editing.models import Hold
    from tenancy.schemas import schema_context

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])

    def as_from_elsewhere(route: Any) -> None:
        response = route.fetch()
        body = response.text().replace('data-take-on-mount="true"', 'data-take-on-mount="false"')
        route.fulfill(response=response, body=body)

    page.route(re.compile(rf".*/document/{document.number}/edit/$"), as_from_elsewhere)
    page.goto(f"{browser_server}/document/{document.number}/edit/")
    page.wait_for_selector("button[data-command=start]")
    with schema_context(migrated_tenant.number):
        assert not Hold.objects.filter(document=document).exists()
    page.click("button[data-command=start]")
    page.wait_for_function("() => document.getElementById('editor').editor !== undefined")
    with schema_context(migrated_tenant.number):
        assert Hold.objects.filter(document=document, released_at__isnull=True).count() == 1
    # Nothing of the page's may reach the server while the test's rows are removed: the editor
    # captures and closes itself first, so the closing page has nothing left to send.
    page.evaluate("document.getElementById('editor').editor.capture.finish()")
    page.unroute_all(behavior="wait")
    page.close()

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
    ("strong", "**word**\n"),
    ("em", "*word*\n"),
    ("underline", "[word]{.underline}\n"),
    ("heading2", "## word\n"),
    ("heading4", "#### word\n"),
    ("bullet_list", "- word\n"),
    ("ordered_list", "1. word\n"),
    ("quote", "> word\n"),
    ("note", "> [!note]\n> word\n"),
    ("warning", "> [!warning]\n> word\n"),
    ("example", "> [!example]\n> word\n"),
]


def test_toolbar_constructs_serialise_canonically(editing: Any, markdown: Any, page: Any) -> None:
    editing("word\n")
    for command, expected in CONTROLS:
        page.evaluate(f"{EDITOR}.replace('word\\n')")
        page.evaluate(f"{EDITOR}.select(1, 6)")
        page.click(f"button[data-command={command}]")
        assert markdown() == expected, command

    page.evaluate(f"{EDITOR}.replace('word\\n')")
    page.evaluate(f"{EDITOR}.select(1, 6)")
    page.click("button[data-command=link]")
    page.fill("input[data-field=link]", "https://example.org/procedure")
    page.press("input[data-field=link]", "Enter")
    assert markdown() == "[word](https://example.org/procedure)\n"

    page.evaluate(f"{EDITOR}.replace('word\\n')")
    page.evaluate(f"{EDITOR}.select(1, 6)")
    page.click("button[data-command=link]")
    page.fill("input[data-field=link]", "javascript:alert(1)")
    page.press("input[data-field=link]", "Enter")
    assert markdown() == "word\n"

    page.evaluate(f"{EDITOR}.replace('word\\n')")
    page.evaluate(f"{EDITOR}.select(6)")
    page.click("button[data-command=table]")
    page.click("button[data-command=add_row]")
    assert markdown().startswith("word\n\n|  |  |\n| --- | --- |\n|  |  |\n")

    page.evaluate(f"{EDITOR}.replace('word\\n')")
    page.evaluate(f"{EDITOR}.select(1, 6)")
    page.click("button[data-command=strong]")
    page.click("button[data-command=undo]")
    assert markdown() == "word\n"
    page.click("button[data-command=redo]")
    assert markdown() == "**word**\n"


def test_the_toolbar_offers_only_whitelisted_controls(editing: Any, page: Any) -> None:
    editing("word\n")
    commands = page.eval_on_selector_all(
        ".editor-controls button[data-command]", "buttons => buttons.map(b => b.dataset.command)"
    )
    assert commands == [
        "paragraph", "heading1", "heading2", "heading3", "heading4", "bullet_list",
        "ordered_list", "strong", "em", "underline", "quote", "note", "warning", "example",
        "table", "add_row", "undo", "redo", "image", "link", "mark", "mention", "source", "finish",
    ]  # fmt: skip


def test_gutter_numbers_follow_edits(editing: Any, page: Any) -> None:
    editing("# First\n\nParagraph one.\n\nParagraph two.\n\n# Second\n\nParagraph three.\n")
    clauses = "() => [...document.querySelectorAll('.clause')].map(c => c.textContent)"
    # Headings carry their number too, set in the heading, as the reading view shows them.
    assert page.evaluate(clauses) == ["1", "1-1", "1-2", "2", "2-1"]
    end_of_first = page.evaluate(
        f"(() => {{ let at = 0; {EDITOR}.view.state.doc.descendants((n, p) => "
        "{ if (!at && n.type.name === 'paragraph') at = p + n.nodeSize - 1; }); return at; })()"
    )
    page.evaluate(f"{EDITOR}.select({end_of_first})")
    page.focus(".ProseMirror")
    page.keyboard.press("Enter")
    page.keyboard.type("A new paragraph.")
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
    assert not page.is_visible("[data-parts-panel]")
    page.click("button[data-command=start]")
    # The take gives the holder their parts panel at once, before the page is drawn again.
    page.wait_for_selector("[data-parts-panel]", state="visible")
    page.wait_for_function("() => document.getElementById('editor').editor !== undefined")
    with schema_context(migrated_tenant.number):
        assert Hold.objects.filter(document=document, released_at__isnull=True).count() == 1
    # Nothing of the page's may reach the server while the test's rows are removed: the editor
    # captures and closes itself first, so the closing page has nothing left to send.
    page.evaluate("document.getElementById('editor').editor.capture.finish()")
    page.unroute_all(behavior="wait")
    page.close()


def test_the_toolbar_shows_icons_named_by_their_words(editing: Any, page: Any) -> None:
    """Each formatting control is an icon (DL-0365): its word is its tooltip and its accessible
    name, never text on the button."""
    editing("word\n")
    buttons = page.eval_on_selector_all(
        ".toolbar button",
        "els => els.map(e => ({command: e.dataset.command, text: [...e.childNodes]"
        ".filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim(),"
        " name: e.getAttribute('aria-label'), title: e.title, svg: !!e.querySelector('svg')}))",
    )
    assert len(buttons) >= 19
    for button in buttons:
        assert button["svg"], button
        assert button["text"] == "", button
        assert button["name"] and button["title"] == button["name"], button


def test_a_headings_number_stands_on_the_headings_line(editing: Any, page: Any) -> None:
    """The number opens the heading's own line, as in the reading view (DL-0363)."""
    editing("# General provisions\n\nThe first sentence.\n")
    number, title = page.evaluate(
        "() => { const h = document.querySelector('.editor-surface h1');"
        " const c = h.querySelector('.clause').getBoundingClientRect();"
        " const r = document.createRange(); r.selectNodeContents(h.lastChild);"
        " const t = r.getBoundingClientRect(); return [c.top, t.top]; }"
    )
    assert abs(number - title) < 4


def test_the_editor_opens_on_arrival(editing: Any, page: Any) -> None:
    """The whole document's editor is open when the page is, with no control to press and no
    section editor anywhere (DL-0517)."""
    editing("# A heading\n\nA synthetic sentence.\n")

    assert page.evaluate(f"() => {EDITOR}.view.editable") is True
    assert page.locator("button[data-command=edit-whole]").count() == 0
    assert page.locator(".section-edit, .section-editor").count() == 0


def test_my_edits_is_a_switch(editing: Any, page: Any, settings: Any) -> None:
    """*My edits* stands in the editor's row, disabled with its reason until the first edit;
    checked, it shows the draft's changes in place of the editor, and unchecked, the editor again
    (DL-0518)."""
    settings.LANGUAGE_CODE = "en"
    # The draft as the head has it: nothing edited yet.
    editing()
    switch = page.locator("#editor input[data-command=my-edits]")

    assert switch.is_disabled()
    assert page.locator("#editor label.my-edits").get_attribute("title") == "After the first edit."
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    with page.expect_response(lambda r: "/edit/capture/" in r.url):
        page.keyboard.type(" A second sentence.", delay=10)
    page.wait_for_function(
        "() => !document.querySelector('#editor input[data-command=my-edits]').disabled"
    )
    switch.check()
    page.wait_for_selector("#editor .my-edits-shown:not([hidden]) ins")
    assert not page.is_visible(".ProseMirror")
    switch.uncheck()
    assert page.is_visible(".ProseMirror")


def test_my_edits_when_signed_out(editing: Any, page: Any, settings: Any) -> None:
    """A session that ended: *My edits* never draws the sign-in page in the editor's place; it
    says so and stays unchecked."""
    settings.LANGUAGE_CODE = "en"
    editing("A synthetic sentence that is an edit.\n")
    page.context.clear_cookies()
    page.check("#editor input[data-command=my-edits]")
    page.wait_for_function(
        "() => !document.querySelector('#editor input[data-command=my-edits]').checked"
    )

    assert page.is_visible(".ProseMirror")
    assert page.locator("#editor .my-edits-shown form").count() == 0


def test_finish_pressed_while_the_editor_opens(
    browser_server: str,
    page: Any,
    member_of: Any,
    new_document: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """*Finish editing* pressed before the load answers waits for the editor, closes it, then
    finishes — never leaving an editor open that the finish would wait on."""
    import time

    from editing.views import draft

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    opened = draft._open

    def slow(*args: Any, **kwargs: Any) -> Any:
        # The editor's row written, the answer late: the window a click can fall into.
        found = opened(*args, **kwargs)
        time.sleep(1.5)
        return found

    monkeypatch.setattr(draft, "_open", slow)
    page.goto(f"{browser_server}/document/{document.number}/edit/", wait_until="load")
    page.click("nav.path a[data-command=finish]")
    page.wait_for_url(f"**/document/{document.number}/edit/finish/")

    assert "Finishing waits" not in (page.text_content("body") or "")

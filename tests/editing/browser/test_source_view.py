"""The source view (DL-0171, DL-0181): the draft as Markdown, a paragraph to a line; a paste the
whitelist refuses stopped with its lines named and a conversion previewed; other spellings read
back in their stored form; a refused draft opened here, nothing discarded. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"

PASTE = """(text) => {
  const data = new DataTransfer();
  data.setData("text/plain", text);
  const field = document.querySelector("textarea[data-field=source]");
  field.focus();
  const init = { clipboardData: data, bubbles: true, cancelable: true };
  field.dispatchEvent(new ClipboardEvent("paste", init));
}"""


def test_switch_is_lossless(editing: Any, markdown: Any, page: Any, conformance_body: str) -> None:
    editing(conformance_body)
    page.click("button[data-command=source]")
    shown = page.input_value("textarea[data-field=source]")
    paragraphs = [block for block in shown.rstrip("\n").split("\n\n") if block[0].isalpha()]
    assert paragraphs and all("\n" not in block for block in paragraphs)
    page.click("button[data-command=source]")
    assert markdown() == conformance_body


def test_paste_refused_with_lines_and_conversion(
    editing: Any, markdown: Any, page: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    editing("The start.\n")
    page.click("button[data-command=source]")
    pasted = "An introduction to the section.\n\n```\nsome code\n```\n\n##### Too deep\n"
    page.evaluate(PASTE, pasted)
    status = page.text_content(".editor-status") or ""
    assert "line 3: a code block" in status
    assert "line 7: a heading below depth four" in status
    assert page.input_value("textarea[data-field=source]") == "The start.\n"
    preview = page.text_content(".source-offer pre") or ""
    assert preview == "An introduction to the section.\n\nsome code\n\n#### Too deep\n"
    page.click("button[data-command=paste-converted]")
    assert "#### Too deep" in page.input_value("textarea[data-field=source]")


def test_other_spellings_accepted(editing: Any, markdown: Any, page: Any) -> None:
    editing("The start.\n")
    page.click("button[data-command=source]")
    page.fill("textarea[data-field=source]", "_italic_\n\n* item\n\nHeading\n=======\n")
    page.click("button[data-command=source]")
    assert markdown() == "*italic*\n\n- item\n\n# Heading\n"


def test_a_construct_typed_in_the_field_is_refused_on_the_switch(
    editing: Any, markdown: Any, page: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    editing("The start.\n")
    page.click("button[data-command=source]")
    page.fill("textarea[data-field=source]", "The start.\n\n---\n")
    page.click("button[data-command=source]")
    assert "line 3: a horizontal rule" in (page.text_content(".editor-status") or "")
    assert page.is_visible("textarea[data-field=source]")
    assert markdown() == "The start.\n\n---\n"


def test_refused_draft_opens_in_source_view(
    editing: Any, markdown: Any, page: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    refused = "A paragraph.\n\n<b>bold</b>\n"
    editing(refused)
    assert page.is_visible("textarea[data-field=source]")
    assert page.input_value("textarea[data-field=source]") == refused
    assert "line 3: HTML" in (page.text_content(".editor-status") or "")
    assert markdown() == refused


def test_a_mention_without_a_number_converts_to_its_words(
    editing: Any, markdown: Any, page: Any, settings: Any
) -> None:
    """A mention names a document by its number (DL-0436): one without a number is refused by name
    and converts to its words; one with a number is taken as written."""
    settings.LANGUAGE_CODE = "en"
    editing("The start.\n")
    page.click("button[data-command=source]")
    page.evaluate(PASTE, "See [the payment procedure]{.document #twelve}.\n")
    status = page.text_content(".editor-status") or ""
    assert "line 1: a mention without a document number" in status
    preview = page.text_content(".source-offer pre") or ""
    assert preview == "See the payment procedure.\n"
    page.fill("textarea[data-field=source]", "See [the payment procedure]{.document #12}.\n")
    page.click("button[data-command=source]")
    assert markdown() == "See [the payment procedure]{.document #12}.\n"


def test_lines_joined_are_named(editing: Any, page: Any, settings: Any) -> None:
    """A paragraph typed over several lines is one paragraph, joined on the switch; the notice
    line says which lines, as the person types (DL-0441)."""
    settings.LANGUAGE_CODE = "en"
    editing("The start.\n")
    page.click("button[data-command=source]")
    page.fill(
        "textarea[data-field=source]",
        "The start.\n\n> [!note]\n> A note.\n\nA paragraph\nover three\nlines.\n",
    )
    page.wait_for_timeout(800)
    status = page.text_content(".editor-status") or ""
    # A callout's marker line is its own: only the paragraph typed over lines is named.
    assert "Lines 6–8 are one paragraph and will be joined" in status
    assert "joined too" not in status

    # Switched before the pause ends, the notice never comes after it.
    page.fill("textarea[data-field=source]", "The start.\n\nOne\ntwo.\n")
    page.click("button[data-command=source]")
    page.wait_for_timeout(800)
    assert "will be joined" not in (page.text_content(".editor-status") or "")


def test_paste_strips_its_headings_own_numbers(editing: Any, page: Any) -> None:
    """A pasted heading's own number goes where it equals the heading's place in the text; the
    lines the paste did not bring are left, whatever they hold (DL-0441)."""
    editing("The start.\n")
    page.click("button[data-command=source]")
    page.fill("textarea[data-field=source]", "# 1 Old\n\nText.\n\n")
    page.evaluate(
        "() => { const f = document.querySelector('textarea[data-field=source]');"
        " f.setSelectionRange(f.value.length, f.value.length); }"
    )
    page.evaluate(PASTE, "# 2 Scope\n")
    assert page.input_value("textarea[data-field=source]") == "# 1 Old\n\nText.\n\n# Scope\n"

    # Words pasted at the end of a line typed earlier leave that line's number as it was; a
    # heading the same paste brings whole loses its own.
    page.fill("textarea[data-field=source]", "# 1 Old")
    page.evaluate(
        "() => { const f = document.querySelector('textarea[data-field=source]');"
        " f.setSelectionRange(f.value.length, f.value.length); }"
    )
    page.evaluate(PASTE, " title\n\n# 2 Scope")
    assert page.input_value("textarea[data-field=source]") == "# 1 Old title\n\n# Scope"

    # A paste ending in a line break brings no part of the line it lands before: that heading
    # keeps what was typed, though the paste moves it to the place its number names.
    page.fill("textarea[data-field=source]", "# 2 Scope\n\nText.\n")
    page.evaluate(
        "() => document.querySelector('textarea[data-field=source]').setSelectionRange(0, 0)"
    )
    page.evaluate(PASTE, "# 1 Purpose\n\n")
    assert page.input_value("textarea[data-field=source]") == "# Purpose\n\n# 2 Scope\n\nText.\n"


def test_the_caret_ends_after_a_stripped_paste(editing: Any, page: Any) -> None:
    """Where a pasted heading loses its number, the caret ends where the paste ends, as it does
    after any paste, not at the end of the line it ends on."""
    editing("The start.\n")
    page.click("button[data-command=source]")
    page.fill("textarea[data-field=source]", "# 1 Old\n\nTail")
    page.evaluate(
        "() => { const f = document.querySelector('textarea[data-field=source]');"
        " f.setSelectionRange(f.value.length - 4, f.value.length - 4); }"
    )
    page.evaluate(PASTE, "# 2 Scope\nmore ")
    field = "textarea[data-field=source]"
    assert page.input_value(field) == "# 1 Old\n\n# Scope\nmore Tail"
    caret = page.evaluate(f"document.querySelector('{field}').selectionStart")
    assert caret == len("# 1 Old\n\n# Scope\nmore ")


def test_a_long_numbered_bullet_list_opens_in_the_editor(
    editing: Any, markdown: Any, page: Any
) -> None:
    """The rule that reads `- 1.` holds at the size the platform accepts: the editor opens the
    draft the server accepted."""
    editing("- 1. a\n" * 30000)
    assert markdown().startswith("1. a\n2. a\n")

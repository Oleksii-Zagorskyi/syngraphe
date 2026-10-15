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

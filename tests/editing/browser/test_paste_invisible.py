"""A paste into the formatted view leaves out the invisible format characters it carries, the two
joiners kept; a reordering mark is refused, named (DL-0486, DL-0487). A real `paste` event on the
editor. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"
START = "Text before the paste.\n"
SOFT_HYPHEN, ZERO_WIDTH_SPACE, NON_JOINER = "­", "​", "‌"

PASTE = """([html, text]) => {
  const data = new DataTransfer();
  if (html) data.setData("text/html", html);
  if (text) data.setData("text/plain", text);
  const editor = document.getElementById("editor").editor;
  editor.view.focus();
  const init = { clipboardData: data, bubbles: true, cancelable: true };
  editor.view.dom.dispatchEvent(new ClipboardEvent("paste", init));
}"""


def paste(page: Any, html: str | None = None, text: str | None = None) -> str:
    page.evaluate("() => { document.querySelector('.editor-status').textContent = ''; }")
    page.evaluate(PASTE, [html, text])
    page.wait_for_timeout(50)
    return str(page.text_content(".editor-status") or "")


def test_a_soft_hyphen_pasted_and_gone(editing: Any, markdown: Any, page: Any) -> None:
    editing(START)
    page.evaluate(f"{EDITOR}.select(1)")
    paste(page, text=f"plain{ZERO_WIDTH_SPACE}text{SOFT_HYPHEN} and a{NON_JOINER}joiner ")
    paste(page, html=f"<p>Hy{SOFT_HYPHEN}phen<b>at{ZERO_WIDTH_SPACE}ed</b>words</p>")

    expected = f"plaintext and a{NON_JOINER}joiner Hyphen**ated**wordsText before the paste.\n"
    assert markdown() == expected


def test_a_pasted_reordering_mark_refused(
    editing: Any, markdown: Any, page: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "en"
    editing(START)
    page.evaluate(f"{EDITOR}.select(1)")

    status = paste(page, text="a ‮clause")

    assert "a mark that reorders text" in status
    assert markdown() == START

"""A paste into the formatted view (DL-0171): HTML carrying a construct outside the whitelist is
refused whole with the construct named, plain text is literal text, and an image that is only a
web address is left out with a notice. The paste is a real `paste` event on the editor. Invented
text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"
START = "Text before the paste.\n"

PASTE = """([html, text]) => {
  const data = new DataTransfer();
  if (html) data.setData("text/html", html);
  if (text) data.setData("text/plain", text);
  const editor = document.getElementById("editor").editor;
  editor.view.focus();
  const init = { clipboardData: data, bubbles: true, cancelable: true };
  const event = new ClipboardEvent("paste", init);
  editor.view.dom.dispatchEvent(event);
}"""


def paste(page: Any, html: str | None = None, text: str | None = None) -> str:
    page.evaluate("() => { document.querySelector('.editor-status').textContent = ''; }")
    page.evaluate(PASTE, [html, text])
    page.wait_for_timeout(50)
    return str(page.text_content(".editor-status") or "")


REFUSED = [
    ("<table><tr><td><table><tr><td>x</td></tr></table></td></tr></table>", "a table inside"),
    ("<table><tr><td colspan='2'>x</td></tr></table>", "a table cell spanning several"),
    ("<h5>Heading</h5>", "a heading below depth four"),
    ("<p>before</p><script>alert(1)</script>", "HTML"),
    ("<p>before</p><hr><p>after</p>", "a horizontal rule"),
    ("<pre>code</pre>", "a code block"),
]


def test_rich_refusals(editing: Any, markdown: Any, page: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"
    editing(START)
    page.evaluate(f"{EDITOR}.select(1)")
    for html, construct in REFUSED:
        status = paste(page, html=html, text="x")
        assert construct in status, html
        assert markdown() == START, html
    assert page.get_attribute(".editor-status a", "href") == "/help/markdown/"


def test_plain_text_is_literal(editing: Any, markdown: Any, page: Any) -> None:
    editing(START)
    page.evaluate(f"{EDITOR}.select(1)")
    paste(page, text="`code` and **not bold**")
    assert markdown() == "\\`code\\` and \\*\\*not bold\\*\\*Text before the paste.\n"


def test_images_left_out_with_notice(editing: Any, markdown: Any, page: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"
    editing(START)
    page.evaluate(f"{EDITOR}.select(1)")
    html = "<p>Words <img src='https://example.org/a.png'> further</p>"
    status = paste(page, html=html, text="Words further")
    assert "only a web address was not pasted; copy the image itself and paste it" in status
    assert "images/" not in markdown() and "example.org" not in markdown()
    assert "Words" in markdown()

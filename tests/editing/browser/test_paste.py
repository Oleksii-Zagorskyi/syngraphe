"""A paste into the formatted view (DL-0171): HTML carrying a construct outside the whitelist is
refused whole with the construct named, plain text is literal text, and images are left out with a
notice. The paste is a real `paste` event on the editor. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"
START = "Текст до вставки.\n"

PASTE = """([html, text, image]) => {
  const data = new DataTransfer();
  if (html) data.setData("text/html", html);
  if (text) data.setData("text/plain", text);
  const png = new Uint8Array([137, 80, 78, 71]);
  if (image) data.items.add(new File([png], "x.png", { type: "image/png" }));
  const editor = document.getElementById("editor").editor;
  editor.view.focus();
  const init = { clipboardData: data, bubbles: true, cancelable: true };
  const event = new ClipboardEvent("paste", init);
  editor.view.dom.dispatchEvent(event);
}"""


def paste(page: Any, html: str | None = None, text: str | None = None, image: bool = False) -> str:
    page.evaluate("() => { document.querySelector('.editor-status').textContent = ''; }")
    page.evaluate(PASTE, [html, text, image])
    page.wait_for_timeout(50)
    return str(page.text_content(".editor-status") or "")


REFUSED = [
    ("<table><tr><td><table><tr><td>x</td></tr></table></td></tr></table>", "a table inside"),
    ("<table><tr><td colspan='2'>x</td></tr></table>", "a merged table cell"),
    ("<h5>Заголовок</h5>", "a heading below depth four"),
    ("<p>до</p><script>alert(1)</script>", "HTML"),
    ("<p>до</p><hr><p>після</p>", "a horizontal rule"),
    ("<pre>код</pre>", "a code block"),
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
    paste(page, text="`код` і **не жирне**")
    assert markdown() == "\\`код\\` і \\*\\*не жирне\\*\\*Текст до вставки.\n"


def test_images_left_out_with_notice(editing: Any, markdown: Any, page: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"
    editing(START)
    page.evaluate(f"{EDITOR}.select(1)")
    html = "<p>Слова <img src='https://example.org/a.png'> далі</p>"
    status = paste(page, html=html, text="Слова далі")
    assert "Images were left out" in status
    assert "images/" not in markdown() and "example.org" not in markdown()
    assert "Слова" in markdown()
    status = paste(page, image=True)
    assert "Images were left out" in status

"""The editor's *Mention* control (DL-0436): a document's number typed into the toolbar, as a
link's address is, wraps the selection in a mention of it; anything but a number is refused on
the notice line and changes nothing. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"


def test_the_mention_control(editing: Any, markdown: Any, page: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"
    editing("See the payment rules.\n")
    page.evaluate(f"{EDITOR}.select(5, 22)")
    page.click("button[data-command=mention]")
    page.fill("input[data-field=mention]", "12")
    page.press("input[data-field=mention]", "Enter")
    assert markdown() == "See [the payment rules]{.document #12}.\n"
    page.click("button[data-command=source]")
    shown = page.input_value("textarea[data-field=source]")
    assert shown == "See [the payment rules]{.document #12}.\n"
    page.click("button[data-command=source]")

    page.evaluate(f"{EDITOR}.replace('See the payment rules.\\n')")
    page.evaluate(f"{EDITOR}.select(5, 22)")
    page.click("button[data-command=mention]")
    page.fill("input[data-field=mention]", "abc")
    page.press("input[data-field=mention]", "Enter")
    assert "A mention needs a document number." in (page.text_content(".editor-status") or "")
    assert markdown() == "See the payment rules.\n"


def test_a_mention_needs_words_and_marks_text_alone(
    editing: Any, markdown: Any, page: Any, settings: Any
) -> None:
    """With nothing selected the control says so; over a selection holding an image it marks the
    words and leaves the image, which may carry no mark."""
    settings.LANGUAGE_CODE = "en"
    image = "images/" + "a" * 64 + ".png"
    editing(f"See the rules.\n\n![A plan]({image})\n")
    page.evaluate(f"{EDITOR}.select(5)")
    page.click("button[data-command=mention]")
    page.fill("input[data-field=mention]", "12")
    page.press("input[data-field=mention]", "Enter")
    assert "Select the words to mention first." in (page.text_content(".editor-status") or "")
    assert markdown() == f"See the rules.\n\n![A plan]({image})\n"

    end = page.evaluate(f"{EDITOR}.view.state.doc.content.size")
    page.evaluate(f"{EDITOR}.select(1, {end})")
    page.click("button[data-command=mention]")
    page.fill("input[data-field=mention]", "12")
    page.press("input[data-field=mention]", "Enter")
    assert markdown() == f"[See the rules.]{{.document #12}}\n\n![A plan]({image})\n"


PASTE = """(html) => {
  const data = new DataTransfer();
  data.setData("text/html", html);
  const editor = document.getElementById("editor").editor;
  editor.view.focus();
  const init = { clipboardData: data, bubbles: true, cancelable: true };
  editor.view.dom.dispatchEvent(new ClipboardEvent("paste", init));
}"""


def test_a_mention_copied_from_the_view_pastes_as_a_mention(
    editing: Any, markdown: Any, page: Any
) -> None:
    """The reading view draws a followed mention as a link; pasted back, it is the mention again,
    never an ordinary link every reader could follow."""
    editing("Start.\n")
    page.evaluate(f"{EDITOR}.select(7)")
    page.evaluate(PASTE, '<p>See <a class="mention" href="/document/12/">the rules</a>.</p>')
    page.wait_for_timeout(50)
    assert "[the rules]{.document #12}" in markdown()
    assert "](/document/12/)" not in markdown()


def test_a_mention_copied_with_its_resolved_address_pastes_as_a_mention(
    editing: Any, markdown: Any, page: Any
) -> None:
    """A browser copying from the reading view resolves the address against the page; the same
    origin's address is still the mention, another host's stays an ordinary link."""
    editing("Start.\n")
    origin = page.evaluate("location.origin")
    page.evaluate(f"{EDITOR}.select(7)")
    page.evaluate(
        PASTE,
        f'<p>See <a class="mention" href="{origin}/document/12/">the rules</a>, '
        '<a class="mention" href="https://elsewhere.example/document/13/">those</a>.</p>',
    )
    page.wait_for_timeout(50)
    assert "[the rules]{.document #12}" in markdown()
    assert "[those](https://elsewhere.example/document/13/)" in markdown()


def test_only_a_mention_of_a_document_pastes_as_one(editing: Any, markdown: Any, page: Any) -> None:
    """A copied mention whose address names no document of this platform is no mention: a number
    out of the specification's form, a scheme the editor refuses; and a plain link to a document
    stays the link it was."""
    editing("Start.\n")
    page.evaluate(f"{EDITOR}.select(7)")
    page.evaluate(
        PASTE,
        '<p><a class="mention" href="/document/012/">padded</a>, '
        '<a class="mention" href="javascript:alert(1)">scripted</a>, '
        '<a href="/document/12/">plain</a>.</p>',
    )
    page.wait_for_timeout(50)
    text = markdown()
    assert "{.document" not in text
    assert "javascript:" not in text
    assert "padded" in text and "scripted" in text and "plain" in text

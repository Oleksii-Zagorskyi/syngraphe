"""Sentence boundaries survive the editor as invisible nodes (V-03): an edit inside a sentence
changes its line alone; Backspace at a sentence's start removes the boundary; Enter makes two
paragraphs and leaves every other boundary. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"
STORED = (
    "The first sentence of the paragraph.\n"
    "The second sentence of the paragraph.\n"
    "The third sentence of the paragraph.\n"
)


def position_of(page: Any, text: str) -> int:
    """The document position of the start of `text`."""
    return int(
        page.evaluate(
            f"(text) => {{ let found = -1; {EDITOR}.view.state.doc.descendants((n, p) => "
            "{ if (found < 0 && n.isText && n.text.includes(text)) "
            "found = p + n.text.indexOf(text); }); return found; }",
            text,
        )
    )


def test_boundary_behaviour(editing: Any, markdown: Any, page: Any) -> None:
    editing(STORED)
    at = position_of(page, "second")
    # Focused first: focusing an editor that lacks it may put the cursor at the start, over a
    # selection set before.
    page.focus(".ProseMirror")
    page.evaluate(f"{EDITOR}.select({at}, {at + len('second')})")
    page.keyboard.type("other")
    assert markdown() == STORED.replace("second", "other")

    page.evaluate(f"{EDITOR}.replace({STORED!r})")
    at = position_of(page, "The third")
    page.focus(".ProseMirror")
    page.evaluate(f"{EDITOR}.select({at})")
    page.keyboard.press("Backspace")
    assert markdown() == (
        "The first sentence of the paragraph.\n"
        "The second sentence of the paragraph.The third sentence of the paragraph.\n"
    )

    page.evaluate(f"{EDITOR}.replace({STORED!r})")
    at = position_of(page, "The second")
    page.focus(".ProseMirror")
    page.evaluate(f"{EDITOR}.select({at + len('The second')})")
    page.keyboard.press("Enter")
    # The spaces at the new paragraphs' edges are the normalizer's to drop at commit.
    assert [line.strip() for line in markdown().split("\n")] == [
        "The first sentence of the paragraph.",
        "The second",
        "",
        "sentence of the paragraph.",
        "The third sentence of the paragraph.",
        "",
    ]

"""How numbers stand beside a document's text (DL-0363) and what a page carries (DL-0362): a
heading's number is part of the heading; clause numbers stand in the gutter in a light grey; no
page header. One look for the reading view, the PDF and the editor."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

SRC = Path(__file__).resolve().parents[2] / "src"
DOCUMENT_CSS = (SRC / "rendering/static/rendering/document.css").read_text("utf-8")
EDITOR_CSS = (SRC / "editing/js/editor.css").read_text("utf-8")
HEADINGS = ("h1", "h2", "h3", "h4")


def rules(css: str, selector: str) -> str:
    """Every declaration of rules whose selector list names `selector`, joined."""
    found = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if selector in [s.strip() for s in selectors.split(",")]:
            found.append(body)
    return ";".join(found)


@pytest.mark.parametrize("level", HEADINGS)
def test_a_headings_number_is_part_of_the_heading(level: str) -> None:
    declared = rules(DOCUMENT_CSS, f".document-text {level} .num")
    assert "position: static" in declared
    assert "color: inherit" in declared
    assert "font-size: inherit" in declared
    assert "font-weight: inherit" in declared
    # One space after the number, the renderer's — no margin beside it; copied with the title.
    assert "margin-right: 0" in declared
    assert "user-select: text" in declared


@pytest.mark.parametrize("level", HEADINGS)
def test_the_editor_sets_a_headings_number_in_the_heading(level: str) -> None:
    declared = rules(EDITOR_CSS, f".editor-surface {level} .clause")
    assert "position: static" in declared
    assert "color: inherit" in declared
    assert "font-size: inherit" in declared
    assert "font-weight" not in declared  # the heading's own weight, inherited


def test_clause_numbers_are_light_grey_and_kept_from_the_text() -> None:
    declared = rules(DOCUMENT_CSS, ".document-text .num")
    assert "color: #c2c2c2" in declared
    assert "width: calc(var(--doc-gutter) - 22px)" in declared
    assert "--doc-gutter: 68px" in rules(DOCUMENT_CSS, ".document-text")
    editor = rules(EDITOR_CSS, ".editor-surface .clause")
    assert "color: #c2c2c2" in editor
    # The editor's gutter as the reading view's: 68 px, the number 22 px short of the text.
    assert "width: 46px" in editor
    assert "padding: 1rem 0 1rem 68px" in rules(EDITOR_CSS, ".editor-surface .ProseMirror")


def test_a_pdf_page_has_no_header_and_a_narrow_left_margin() -> None:
    from rendering.export import furniture

    css = furniture.pdf_css()
    assert "@top-center" not in css
    assert "@bottom-center { content: counter(page)" in css
    assert "margin: 18mm 18mm 20mm 10mm" in css
    # The words naming a formatting change are the screen's; a page shows its colour alone.
    assert ".format-changed::after { content: none; }" in css

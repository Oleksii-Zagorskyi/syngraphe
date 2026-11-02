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
    # On the heading's own line, whatever another stylesheet makes of the class.
    assert "display: inline" in declared


def test_clause_numbers_are_light_grey_and_kept_from_the_text() -> None:
    declared = rules(DOCUMENT_CSS, ".document-text .num")
    assert "color: #c2c2c2" in declared
    assert "width: calc(var(--doc-gutter) - 22px)" in declared
    assert "--doc-gutter: 68px" in rules(DOCUMENT_CSS, ".document-text")
    editor = rules(EDITOR_CSS, ".editor-surface .clause")
    assert "color: #c2c2c2" in editor
    # The editor's gutter as the reading view's: 68 px, the number 22 px short of the text.
    assert "width: 46px" in editor
    # The right padding keeps the editor's text off its border (DL-0503).
    assert "padding: 1rem 24px 1rem 68px" in rules(EDITOR_CSS, ".editor-surface .ProseMirror")


def at_rule_blocks(css: str) -> list[tuple[str, str]]:
    """Every top-level `@… { … }` block as its prelude and its inside, by brace depth."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    blocks, at = [], 0
    while (match := re.compile(r"@[^{};]*\{").search(css, at)) is not None:
        depth, start = 1, match.end()
        for end in range(start, len(css)):
            depth += {"{": 1, "}": -1}.get(css[end], 0)
            if depth == 0:
                break
        blocks.append((match.group(0)[:-1].strip(), css[start:end]))
        at = end + 1
    return blocks


def outside_at_rules(css: str) -> str:
    """The sheet with every top-level `@… { … }` block taken out."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for prelude, inside in at_rule_blocks(css):
        css = css.replace(f"{prelude} {{{inside}}}", "", 1).replace(f"{prelude}{{{inside}}}", "", 1)
    return css


def screen_blocks(css: str) -> str:
    """The inside of every `@media screen …` block, joined."""
    return "\n".join(i for p, i in at_rule_blocks(css) if re.match(r"@media\s+screen\b", p))


def test_the_sheet_readers_see_rules_inside_and_outside_a_block() -> None:
    # The known negative and positive for the reader below: a rule nested in a block is never
    # read as a flat one, whichever its place in the block.
    sheet = "@media print { .document-text { background: #eee } } .a { color: red }"
    assert "background" not in rules(outside_at_rules(sheet), ".document-text")
    assert [p for p, i in at_rule_blocks(sheet) if "background" in i] == ["@media print"]
    later = (
        "@media screen and (min-width: 1px) { .x { color: red } "
        ".document-text { background: #fff } }"
    )
    assert "background" in rules(screen_blocks(later), ".document-text")
    assert "background" not in rules(outside_at_rules(later), ".document-text")


def test_the_text_box_and_the_editor_have_their_backgrounds_on_screen_only() -> None:
    # The document's sheet is also the PDF's (`rendering.stylesheet.export_stylesheets`); exports
    # stay on white paper, so the text's box is drawn on screen alone (DL-0503).
    on_screen = rules(screen_blocks(DOCUMENT_CSS), ".document-text")
    assert "background: #ffffff" in on_screen
    assert "border: 1px solid #d4d4d4" in on_screen
    everywhere = rules(outside_at_rules(DOCUMENT_CSS), ".document-text")
    assert "background" not in everywhere
    assert "border" not in everywhere
    for prelude, inside in at_rule_blocks(DOCUMENT_CSS):
        if not re.match(r"@media\s+screen\b", prelude):
            assert "background" not in rules(inside, ".document-text"), prelude
    # The clause numbers stand against the box's left edge: no left padding beyond the gutter.
    assert "padding-left: var(--doc-gutter)" in everywhere
    assert "padding-left" not in on_screen
    assert "background: #fffdf3" in rules(EDITOR_CSS, ".editor-surface")


def test_a_pdf_page_has_no_header_and_a_narrow_left_margin() -> None:
    from rendering.export import furniture

    css = furniture.pdf_css()
    assert "@top-center" not in css
    assert "@bottom-center { content: counter(page)" in css
    assert "margin: 18mm 18mm 20mm 10mm" in css
    # The words naming a formatting change are the screen's; a page shows its colour alone.
    assert ".format-changed::after { content: none; }" in css


def test_the_shell_gives_the_editors_numbers_no_layout_of_its_own() -> None:
    shell = (SRC / "shell/static/shell.css").read_text("utf-8")
    assert not re.search(r"(^|[^\w-])\.clause\s*\{", shell, re.M)
    # No template wears `class="editor"`; the rule it had is gone.
    assert not re.search(r"(^|[^\w-])\.editor\s*\{", shell, re.M)

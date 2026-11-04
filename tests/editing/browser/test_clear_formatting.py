"""*Clear formatting* in Chromium (DL-0531): over the selection, or the cursor's textblock
when nothing is selected, it removes bold, italic, underline and links, lifts blocks out of lists,
quotes and note blocks, turns headings into paragraphs, keeps entity marks and mentions, leaves a
table a table, and one *undo* restores the whole. Invented text; the roles are synthetic
examples."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

CLEAR = "button[data-command=clear_formatting]"

MIXED = (
    "# **A bold heading**\n\n"
    "- The first item.\n"
    "- The second item.\n\n"
    "> A quoted sentence.\n\n"
    "> [!note]\n"
    "> A noted sentence.\n"
)
MIXED_CLEARED = (
    "A bold heading\n\n"
    "The first item.\n\n"
    "The second item.\n\n"
    "A quoted sentence.\n\n"
    "A noted sentence.\n"
)


def clear(page: Any) -> None:
    """*Clear formatting* pressed: every editor draws the control, so its absence fails here."""
    assert page.locator(CLEAR).count() == 1, "no clear_formatting control in the toolbar"
    page.click(CLEAR)


def select_all(page: Any) -> None:
    """The whole text selected as a person would: the cursor in the editor, then the chord."""
    page.locator(".ProseMirror p, .ProseMirror li, .ProseMirror h1").first.click()
    page.keyboard.press("ControlOrMeta+a")


def test_a_mixed_selection(editing: Any, markdown: Any, page: Any) -> None:
    editing(MIXED)
    assert markdown() == MIXED
    select_all(page)
    clear(page)

    cleared = markdown()
    assert cleared == MIXED_CLEARED
    for spelling in ("#", "- ", "> ", "[!", "**"):
        assert spelling not in cleared, spelling


def test_the_cursors_line(editing: Any, markdown: Any, page: Any) -> None:
    body = "A plain sentence.\n\n- **The first item.**\n- The second item.\n"
    editing(body)
    assert markdown() == body
    # The cursor in the bold item, nothing selected.
    page.locator(".ProseMirror li strong").first.click()
    clear(page)

    assert markdown() == "A plain sentence.\n\nThe first item.\n\n- The second item.\n"


def test_entities_are_kept(editing: Any, markdown: Any, page: Any) -> None:
    body = (
        "The **approver** [signs]{.role #role-1} the [payment rules]{.document #12} "
        "and [files]{.action} them.\n"
    )
    editing(body)
    assert markdown() == body
    select_all(page)
    clear(page)

    assert markdown() == (
        "The approver [signs]{.role #role-1} the [payment rules]{.document #12} "
        "and [files]{.action} them.\n"
    )


def test_a_table_stays(editing: Any, markdown: Any, page: Any) -> None:
    body = "| Role | Action |\n| --- | --- |\n| **author** | prepares |\n"
    editing(body)
    assert markdown() == body
    # The bold cell's word selected by a double click: in a table cell *End* does not move the
    # cursor, and *Shift+Home* would select back to the table's start.
    page.locator(".ProseMirror td strong").first.dblclick()
    clear(page)

    assert markdown() == "| Role | Action |\n| --- | --- |\n| author | prepares |\n"


def test_one_undo_restores_it(editing: Any, markdown: Any, page: Any) -> None:
    editing(MIXED)
    select_all(page)
    clear(page)
    assert markdown() == MIXED_CLEARED
    page.click("button[data-command=undo]")

    assert markdown() == MIXED


def test_a_nested_list_is_lifted_whole(editing: Any, markdown: Any, page: Any) -> None:
    """A list item holding a nested list, and a quote after it, all selected: plain paragraphs."""
    body = "- Outer item.\n  - Inner item.\n- Second item.\n\n> A quoted sentence.\n"
    editing(body)
    assert markdown() == body
    select_all(page)
    clear(page)

    assert markdown() == ("Outer item.\n\nInner item.\n\nSecond item.\n\nA quoted sentence.\n"), (
        markdown()
    )

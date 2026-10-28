"""The editor's *Mark* picker (DL-0073): the kind, the draft's own declarations of that kind,
and *Declare a new one*; picking or declaring wraps the selection in the entity's span, its key the
declaration's. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"
BODY = "The approver signs.\n\nThe clerk files.\n\nThe approver keeps.\n"


def mark(page: Any, start: int, end: int) -> None:
    page.evaluate(f"{EDITOR}.select({start}, {end})")
    page.click("button[data-command=mark]")
    page.select_option("select[data-field=mark-kind]", "role")


def declare(page: Any, label: str, key: str) -> None:
    """Declared on the server, then the selection wrapped: wait for the key in the text."""
    page.fill("input[data-field=mark-label]", label)
    page.click("button[data-field=mark-declare]")
    page.wait_for_function(f"() => {EDITOR}.markdown().includes('#{key}')")


def test_mark_picks_or_declares(editing: Any, markdown: Any, page: Any) -> None:
    editing(BODY)

    mark(page, 1, 13)
    declare(page, "the approver", "role-1")
    mark(page, 40, 52)
    page.click("button[data-entity=role-1]")
    mark(page, 22, 31)
    declare(page, "the clerk", "role-2")

    expected = (
        "[The approver]{.role #role-1} signs.\n\n"
        "[The clerk]{.role #role-2} files.\n\n"
        "[The approver]{.role #role-1} keeps.\n"
    )
    assert markdown() == expected
    page.click("button[data-command=source]")
    assert page.input_value("textarea[data-field=source]") == expected


def test_marking_replaces_an_entity_and_needs_text(
    editing: Any, markdown: Any, page: Any, settings: Any
) -> None:
    """Words already marked take the new entity, as one span; a selection holding no text — an
    image alone — marks nothing and declares nothing, and says so."""
    settings.LANGUAGE_CODE = "en"
    image = "images/" + "a" * 64 + ".png"
    editing(f"The approver signs.\n\n![A plan]({image})\n")
    mark(page, 1, 13)
    declare(page, "the approver", "role-1")
    mark(page, 1, 13)
    declare(page, "the signatory", "role-2")
    assert markdown() == f"[The approver]{{.role #role-2}} signs.\n\n![A plan]({image})\n"

    mark(page, 22, 23)
    page.fill("input[data-field=mark-label]", "the plan")
    page.click("button[data-field=mark-declare]")
    assert "Select the words to mark first." in (page.text_content(".editor-status") or "")
    page.wait_for_timeout(200)
    assert "role-3" not in markdown()

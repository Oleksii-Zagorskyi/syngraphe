"""*Undo* and *redo* in Chromium (ST-0021): typing undone and redone returns the editor's text,
and the stored text's line boundaries once captured, to exactly what they were. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"
START = "Перше речення.\nДруге речення.\n"


def stored(tenant: Any, document: Any) -> str:
    from editing.models import Draft

    with schema_context(tenant.number):
        body: str = Draft.objects.get(hold__document=document).content["document.md"]
    return body


def test_undo_redo_returns_text_and_boundaries(
    editing: Any, page: Any, migrated_tenant: Any
) -> None:
    document = editing(START)
    first_text = page.evaluate(f"{EDITOR}.markdown()")
    first_stored = stored(migrated_tenant, document)
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    page.keyboard.type(" Третє речення.", delay=10)
    assert page.evaluate(f"{EDITOR}.capture.flush()") == "captured"
    typed_text = page.evaluate(f"{EDITOR}.markdown()")
    typed_stored = stored(migrated_tenant, document)
    assert typed_stored == typed_text != first_text
    # Undone: the editor and, once captured, the stored text are back to before the typing.
    page.click("button[data-command=undo]")
    assert page.evaluate(f"{EDITOR}.markdown()") == first_text
    assert page.evaluate(f"{EDITOR}.capture.flush()") == "captured"
    assert stored(migrated_tenant, document).splitlines() == first_stored.splitlines()
    # Redone: back to the typed state, line for line.
    page.click("button[data-command=redo]")
    assert page.evaluate(f"{EDITOR}.markdown()") == typed_text
    assert page.evaluate(f"{EDITOR}.capture.flush()") == "captured"
    assert stored(migrated_tenant, document).splitlines() == typed_stored.splitlines()

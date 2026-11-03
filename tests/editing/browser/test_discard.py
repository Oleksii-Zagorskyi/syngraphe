"""*Discard my edits* from the finishing screen in Chromium (ST-0022, DL-0237): confirmed in its
box, the draft is thrown away and the document page opens, nobody holding it. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"


def test_discard_from_the_finishing_screen(
    editing: Any, page: Any, migrated_tenant: Any, settings: Any
) -> None:
    from editing.models import Draft, Hold

    settings.LANGUAGE_CODE = "en"
    document = editing("The first sentence.\n")
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    page.keyboard.type(" The second sentence.", delay=10)
    page.click("nav.path a[data-command=finish]")
    page.wait_for_url(f"**/document/{document.number}/edit/finish/")
    page.click("nav.path button[data-command=discard]")
    page.click("button[data-command=discard-confirmed]")
    page.wait_for_url(f"**/document/{document.number}/")
    assert "Your edits were discarded." in (page.text_content(".notice") or "")
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(document=document).release_kind == "discarded"
        assert not Draft.objects.exists()


def test_discard_from_the_edit_tab_closes_the_editor_first(
    editing: Any, page: Any, migrated_tenant: Any
) -> None:
    """The edit tab's discard closes the open editor before it asks, so it is never refused for
    the page's own editor."""
    from editing.models import Draft, Hold

    document = editing("The first sentence.\n")
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    page.keyboard.type(" A sentence not yet captured.", delay=10)
    page.click("nav.path button[data-command=discard]")
    page.click("button[data-command=discard-confirmed]")
    page.wait_for_url(f"**/document/{document.number}/")
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(document=document).release_kind == "discarded"
        assert not Draft.objects.exists()


def test_the_window_opens_and_the_editor_closes_first(
    editing: Any, page: Any, migrated_tenant: Any
) -> None:
    """*Discard my edits…* opens its window and *Back to editing* closes it, nothing posted; then
    *Discard my edits* posts once the editor has captured and closed (DL-0513)."""
    import re

    from editing.models import Draft, Hold

    document = editing("The first sentence.\n")
    posted: list[str] = []
    page.on("request", lambda r: posted.append(r.url) if r.method == "POST" else None)
    page.click("nav.path button[data-command=discard]")
    page.wait_for_selector("dialog#discard[open]")
    page.click("dialog#discard [data-close]")
    page.wait_for_function("() => !document.getElementById('discard').open")
    assert not [url for url in posted if re.search(r"/edit/discard/$", url)]

    page.click("nav.path button[data-command=discard]")
    page.click("dialog#discard button[data-command=discard-confirmed]")
    page.wait_for_url(f"**/document/{document.number}/")
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(document=document).release_kind == "discarded"
        assert not Draft.objects.exists()

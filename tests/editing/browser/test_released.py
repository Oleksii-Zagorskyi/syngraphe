"""A hold released while its tab is open, in Chromium (ADR-0006, DL-0225): an open editor says its
editing was ended and leads back to the tab; a tab with no editor open is drawn again on its next
*Edit*, showing the kept draft. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"


def force(tenant: Any, document: Any) -> None:
    """The hold forced free as an administrator's act would leave it."""
    from django.db import transaction

    from documents.locks import document_lock
    from editing import holds
    from editing.models import Hold, ReleaseKind

    with schema_context(tenant.number):
        with document_lock(tenant.number, document.number), transaction.atomic():
            holds.release(
                Hold.objects.get(document=document, released_at__isnull=True), ReleaseKind.FORCED
            )


def test_an_open_editor_is_told_its_editing_was_ended(
    editing: Any, page: Any, migrated_tenant: Any, monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    from editing.views import capture

    settings.LANGUAGE_CODE = "en"
    monkeypatch.setattr(capture, "HEARTBEAT_SECONDS", 1)
    document = editing("The first sentence.\n")
    force(migrated_tenant, document)
    page.wait_for_function(
        f"() => {EDITOR}.capture.indicator.dataset.state === 'released'", timeout=10000
    )
    notice = page.text_content(".capture-indicator") or ""
    assert "your editing of the document was ended" in notice
    assert page.locator(f".capture-indicator a[href='/document/{document.number}/edit/']").count()
    assert page.evaluate(f"{EDITOR}.view.editable") is False


def test_a_tab_with_no_editor_is_drawn_again_on_edit(
    browser_server: str,
    page: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/edit/")
    page.wait_for_function("() => document.getElementById('editor').offered !== undefined")
    force(migrated_tenant, document)
    with page.expect_navigation():
        page.click("button[data-command=edit-whole]")
    page.wait_for_selector(".band.end")
    assert "Take the document back" in (page.text_content("body") or "")
    page.wait_for_load_state("networkidle")

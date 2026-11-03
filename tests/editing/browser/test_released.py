"""A hold released while its tab is open, in Chromium (ADR-0006, DL-0225): an open editor says its
editing was ended and leads back to the tab; a hold released before the editor opens draws the page
again, showing the kept draft. Invented text."""

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


def test_a_hold_released_before_the_editor_opens_draws_the_kept_draft(
    browser_server: str,
    page: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    settings: Any,
) -> None:
    """The hold forced free between the take and the editor's load, the draft holding an edit:
    the load finds no hold, and the page drawn again offers the kept draft."""
    import re

    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])

    def released_first(route: Any) -> None:
        with schema_context(migrated_tenant.number):
            draft = Draft.objects.get(hold__document=document, hold__released_at__isnull=True)
            body = draft.content["document.md"] + "\nA synthetic sentence.\n"
            draft.content = {**draft.content, "document.md": body}
            draft.save()
        force(migrated_tenant, document)
        route.continue_()

    page.route(re.compile(rf".*/document/{document.number}/edit/load/$"), released_first)
    page.goto(f"{browser_server}/document/{document.number}/edit/")
    page.wait_for_selector(".band.end")
    assert "Take the document back" in (page.text_content("body") or "")
    page.wait_for_load_state("networkidle")

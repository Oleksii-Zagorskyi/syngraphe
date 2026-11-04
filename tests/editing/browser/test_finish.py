"""Finishing from the editor in Chromium: *Finish editing* captures the last text and closes the
editor, the screen shows the number the version will carry, *send for review* commits it and frees
the document (DL-0222, DL-0322). Invented text."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"


def test_finish_end_to_end(
    editing: Any, page: Any, migrated_tenant: Any, settings: Any, queued_authorship: list[Any]
) -> None:
    from documents.models import Version
    from editing.models import Hold

    settings.LANGUAGE_CODE = "en"
    document = editing("The first sentence.\n")
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    page.keyboard.type(" The second sentence.", delay=10)
    page.click("#editor button[data-command=finish]")
    page.wait_for_url(f"**/document/{document.number}/edit/finish/")
    assert "the version waits as 0.0-1" in (page.text_content(".finish") or "")
    page.click("button[data-command=send]")
    page.wait_for_url(f"**/document/{document.number}/")
    assert "Sent for review — the version waits as 0.0-1." in (page.text_content(".notice") or "")
    with schema_context(migrated_tenant.number):
        versions = Version.objects.filter(document=document, kind="edit")
        assert versions.count() == 1
        assert Hold.objects.get(document=document).release_kind == "finished"
    assert len(queued_authorship) == 1


def test_a_summary_typed_on_three_lines(
    editing: Any, page: Any, migrated_tenant: Any, settings: Any, queued_authorship: list[Any]
) -> None:
    """A summary typed in Chromium over three lines and sent: the commit's subject is its first
    line, its body the other two; the version keeps the whole (DL-0532)."""
    from documents import gitstore
    from documents.models import Version

    settings.LANGUAGE_CODE = "en"
    document = editing("The first sentence.\n")
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    page.keyboard.type(" The second sentence.", delay=10)
    page.click("#editor button[data-command=finish]")
    page.wait_for_url(f"**/document/{document.number}/edit/finish/")
    page.fill("#summary", "")
    page.focus("#summary")
    page.keyboard.type("A sentence added", delay=5)
    page.keyboard.press("Enter")
    page.keyboard.type("It completes the opening paragraph.", delay=5)
    page.keyboard.press("Enter")
    page.keyboard.type("Nothing else changed.", delay=5)
    page.click("button[data-command=send]")
    page.wait_for_url(f"**/document/{document.number}/")

    with schema_context(migrated_tenant.number):
        version = Version.objects.get(document=document, kind="edit")
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        message = gitstore.commit_at(repo, version.commit_sha).message
    expected = "A sentence added\n\nIt completes the opening paragraph.\nNothing else changed."
    assert message.startswith(expected + "\n\n"), message
    assert version.summary == expected

"""An appendix edited in Chromium (DL-0443, DL-0517): its page opens the appendix's whole editor on
arrival, and *finish editing* on the draft's point goes to the document's finishing screen, whose
version holds the appendix's change. Invented text; the people are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"


def test_edit_an_appendix_and_finish(
    browser_server: str,
    page: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
) -> None:
    from documents import gitstore

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(
        document,
        author,
        "# Purpose\n\nThe body's sentence.\n",
        files={"appendices/2.md": b"# Approval matrix\n\nThe appendix sentence.\n"},
        appendices=[{"number": 2, "title": "Approval matrix (example)"}],
    )
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/appendix/2/edit/")
    page.wait_for_function(f"() => {EDITOR} !== undefined")
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.evaluate(f"{EDITOR}.view.focus()")
    page.keyboard.type(" A sentence typed in the appendix.", delay=10)
    # The draft point's *Finish editing* captures and closes the editor first.
    page.click("nav.path a[data-command=finish]")
    page.wait_for_url(f"**/document/{document.number}/edit/finish/")
    page.fill("textarea[name=summary], input[name=summary]", "An appendix sentence")
    page.click("button[name=choice][value=send]")
    page.wait_for_url(f"**/document/{document.number}/")

    with schema_context(migrated_tenant.number):
        repo = gitstore.open_repository(migrated_tenant.number, document.number)
        head = gitstore.head(repo)
        assert head is not None
        text = gitstore.read(repo, "appendices/2.md", head).decode()
    assert "A sentence typed in the appendix." in text
    assert "The body's sentence." in gitstore.read(repo, "document.md", head).decode()

"""A signed-in Chromium page on a document's edit tab, the editor mounted over a draft the test
chooses. Titles and people are synthetic examples."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

CONFORMANCE = Path(__file__).resolve().parents[2] / "fixtures" / "render" / "conformance.md"


@pytest.fixture
def conformance_body() -> str:
    return CONFORMANCE.read_text(encoding="utf-8")


@pytest.fixture
def editing(
    browser_server: str, page: Any, migrated_tenant: Any, member_of: Any, new_document: Any
) -> Callable[[str | None], Any]:
    """Open the edit tab of a new document as its author, the draft's body set to `body` when
    given; returns the document once the editor is mounted."""

    def open_tab(body: str | None = None) -> Any:
        from editing.models import Draft

        client, author, _ = member_of("the.author@example.test")
        document = new_document(author)
        if body is not None:
            assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
            with schema_context(migrated_tenant.number):
                draft = Draft.objects.get(hold__document=document)
                draft.content = {**draft.content, "document.md": body}
                draft.save()
        session = client.cookies["sessionid"].value
        page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
        page.goto(f"{browser_server}/document/{document.number}/edit/")
        page.wait_for_function("() => document.getElementById('editor').editor !== undefined")
        return document

    return open_tab


@pytest.fixture
def markdown(page: Any) -> Callable[[], str]:
    """The editor's text in its stored form, as it stands."""
    return lambda: str(page.evaluate("document.getElementById('editor').editor.markdown()"))

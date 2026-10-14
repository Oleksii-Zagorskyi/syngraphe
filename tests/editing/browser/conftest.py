"""A signed-in Chromium page on a document's edit tab, the editor mounted over a draft the test
chooses. Titles and people are synthetic examples."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

CONFORMANCE = Path(__file__).resolve().parents[2] / "fixtures" / "render" / "conformance.md"


@pytest.fixture
def conformance_body() -> str:
    return CONFORMANCE.read_text(encoding="utf-8")


# The editor captured and closed on every page, awaited, so that no request of a page's is still
# in flight — a heartbeat, the close a closing page sends — while the test's rows are flushed.
FINISH_EDITORS = """async () => {
  const editor = document.getElementById('editor')?.editor;
  if (editor && editor.capture) await editor.capture.finish().catch(() => null);
}"""


@pytest.fixture
def editing(
    browser_server: str, page: Any, migrated_tenant: Any, member_of: Any, new_document: Any
) -> Iterator[Callable[[str | None], Any]]:
    """Open the edit tab of a new document as its author, the draft's body set to `body` when
    given; returns the document once the whole editor is opened by its control. On teardown,
    before the page and the server go, every page's editor is finished and the page closed."""

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
        # The tab opens on the draft as text; the whole editor is opened by its control.
        page.click("button[data-command=edit-whole]")
        page.wait_for_function("() => document.getElementById('editor').editor !== undefined")
        return document

    yield open_tab
    for open_page in list(page.context.pages):
        if open_page.is_closed():
            continue
        try:
            open_page.unroute_all(behavior="ignoreErrors")
            open_page.evaluate(FINISH_EDITORS)
        finally:
            open_page.close()


@pytest.fixture
def markdown(page: Any) -> Callable[[], str]:
    """The editor's text in its stored form, as it stands."""
    return lambda: str(page.evaluate("document.getElementById('editor').editor.markdown()"))

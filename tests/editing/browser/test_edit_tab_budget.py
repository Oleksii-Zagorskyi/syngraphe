"""Opening the edit tab to an editable text on the forty-page corpus (ASR-21): from the address to
the tab offering its editors, then from *edit whole document* to the editor ready. One case per
run, so a run's own time is its call's, which `--durations=0` prints; the document and its draft
are made in the setup, outside it. Run in the budgets' step, alone, never beside the workers.

The corpus is invented."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [pytest.mark.browser, pytest.mark.budget]

CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "corpus" / "document-ukr.md"
RUNS = 20


@pytest.fixture
def held_tab(
    browser_server: str, page: Any, migrated_tenant: Any, member_of: Any, new_document: Any
) -> Iterator[str]:
    """The edit tab's address over a draft of the forty-page corpus, held by its author, the
    browser signed in; the page not yet opened. Every open editor is finished on teardown."""
    from editing.models import Draft

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    assert client.post(f"/document/{document.number}/edit/take/").status_code == 200
    # The corpus file carries its own frontmatter, which a draft's body never holds.
    body = CORPUS.read_text(encoding="utf-8").partition("\n---\n")[2].removeprefix("\n")
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        draft.content = {**draft.content, "document.md": body}
        draft.save()
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    yield f"{browser_server}/document/{document.number}/edit/"
    if not page.is_closed():
        page.evaluate(
            """async () => {
              const e = document.getElementById('editor');
              if (e?.editor?.capture) await e.editor.capture.finish().catch(() => null);
            }"""
        )


@pytest.mark.parametrize("run", range(RUNS))
def test_opening_the_edit_tab_at_forty_pages(held_tab: str, page: Any, run: int) -> None:
    page.goto(held_tab)
    page.wait_for_function("() => document.getElementById('editor').offered !== undefined")
    offered = page.evaluate("performance.now()")
    page.click("button[data-command=edit-whole]")
    page.wait_for_function("() => document.getElementById('editor').editor")
    ready = page.evaluate("performance.now()")
    # Both read from the navigation's start, the page's own clock.
    print(f"run {run}: offered {offered:.0f} ms, editor ready {ready:.0f} ms")
    assert page.locator(".ProseMirror").count() == 1

"""Opening the edit tab to an editable text on the forty-page corpus (ASR-21, DL-0484): from the
address to the whole document's editor ready, at the 95th percentile of twenty openings, at most
2 s. Each opening is a document of its own, held by its author, its text written through the
product's own capture as a person's is, with the worker's refresh it queues (DL-23-002); read on
the page's own clock from the navigation's start. Run in the budgets' step, alone, never beside
the workers.

The corpus is invented."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.browser, pytest.mark.budget]

CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "corpus" / "document-ukr.md"
RUNS = 20
BUDGET_MS = 2_000


@pytest.fixture
def held_tab(
    browser_server: str,
    page: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    queued_openings: list[Any],
) -> Iterator[Callable[[], str]]:
    """`held()`: the edit tab's address over a new draft of the forty-page corpus, held by its
    author, the browser signed in as them; the page not yet opened. Every open editor is finished
    on teardown."""
    from editing.tasks import refresh_opening

    # The corpus file carries its own frontmatter, which a draft's body never holds.
    body = CORPUS.read_text(encoding="utf-8").partition("\n---\n")[2].removeprefix("\n")
    client, author, _ = member_of("the.author@example.test")
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])

    def held() -> str:
        document = new_document(author)
        address = f"/document/{document.number}/edit/"
        assert client.post(f"{address}take/").status_code == 200
        # Written as the person's editor writes it: an editor opened on the draft, the corpus
        # captured, that editor closed in the same write.
        opened = client.post(f"{address}load/").json()
        captured = client.post(
            f"{address}capture/",
            json.dumps(
                {
                    "editor": opened["editor"],
                    "base_hash": opened["base_hash"],
                    "body": body,
                    "close": True,
                }
            ),
            content_type="application/json",
        )
        assert captured.status_code == 200, captured.content
        # The worker's refresh that capture queued, run as the worker runs it.
        for tenant, hold, written in queued_openings:
            refresh_opening(tenant, str(hold), written.isoformat())
        queued_openings.clear()
        return f"{browser_server}{address}"

    yield held
    if not page.is_closed():
        page.evaluate(
            """async () => {
              const e = document.getElementById('editor');
              if (e?.editor?.capture) await e.editor.capture.finish().catch(() => null);
            }"""
        )


def test_opening_the_edit_tab_at_forty_pages(
    held_tab: Callable[[], str], page: Any, capsys: Any
) -> None:
    times = []
    for _ in range(RUNS):
        address = held_tab()
        # Each opening from a blank page, the previous editor closed before the clock starts.
        page.goto("about:blank")
        page.goto(address)
        page.wait_for_function("() => document.getElementById('editor').editor")
        # From the navigation's start: what the person waits from the address to typing.
        times.append(page.evaluate("performance.now()"))
        assert page.locator(".ProseMirror").count() == 1
    times.sort()
    p95 = times[math.ceil(len(times) * 0.95) - 1]
    # Shown on a green run too, so the margin is watched before it is spent.
    with capsys.disabled():
        print(f"\nthe edit tab, forty pages: p95 {p95:.0f} ms over {RUNS} openings")
    assert p95 <= BUDGET_MS, [round(t) for t in times]

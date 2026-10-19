"""A signed-in Chromium page on a document's edit tab, the editor mounted over a draft the test
chooses. Titles and people are synthetic examples."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from django.core.signals import request_finished, request_started

from tenancy.schemas import schema_context

CONFORMANCE = Path(__file__).resolve().parents[2] / "fixtures" / "render" / "conformance.md"


@pytest.fixture
def conformance_body() -> str:
    return CONFORMANCE.read_text(encoding="utf-8")


# Every editor of a page — the whole document's and each section's — captured and closed, awaited,
# so that the page sends nothing more: no heartbeat, no close as it goes.
FINISH_EDITORS = """async () => {
  for (const element of document.querySelectorAll('#editor, .section-editor')) {
    const editor = element.editor;
    if (editor && editor.capture) await editor.capture.finish().catch(() => null);
  }
}"""
# The longest the live server may take to answer what the pages asked before they closed.
SETTLE_SECONDS = 30


class _InFlight:
    """The requests the live server is answering, counted by the framework's own signals: a
    request still running while the test's rows are flushed holds locks the flush waits for.

    Only the live server's handler threads count. The test client answers on the test's own
    thread and sends `request_finished` only once a streamed body is read, so one of its
    downloads left unread would never balance."""

    def __init__(self) -> None:
        self.count = 0
        self.changed = threading.Condition()
        self.counted = threading.local()

    def started(self, **_: Any) -> None:
        if threading.current_thread() is threading.main_thread():
            return
        self.counted.open = True
        with self.changed:
            self.count += 1

    def finished(self, **_: Any) -> None:
        if not getattr(self.counted, "open", False):
            return
        self.counted.open = False
        with self.changed:
            self.count -= 1
            self.changed.notify_all()

    def reset(self) -> None:
        """No page is open before the test begins, so nothing of the live server's is running."""
        with self.changed:
            self.count = 0

    def settle(self) -> None:
        with self.changed:
            if not self.changed.wait_for(lambda: self.count <= 0, timeout=SETTLE_SECONDS):
                pytest.fail(f"the live server still answers {self.count} request(s)")


IN_FLIGHT = _InFlight()
request_started.connect(IN_FLIGHT.started, dispatch_uid="browser-tests-in-flight")
request_finished.connect(IN_FLIGHT.finished, dispatch_uid="browser-tests-in-flight")


@pytest.fixture(autouse=True)
def settled_pages(page: Any, browser_server: str) -> Iterator[None]:
    """After the test, before its rows are flushed: every page's editors finished, every page
    closed, and every request the pages made answered. A test that opens the edit tab on its own
    is settled as one that went through `editing`. It takes the live server so that it is set up
    after the server's database and torn down before the flush."""
    IN_FLIGHT.reset()
    yield
    try:
        for open_page in list(page.context.pages):
            if open_page.is_closed():
                continue
            try:
                open_page.unroute_all(behavior="ignoreErrors")
                open_page.evaluate(FINISH_EDITORS)
            finally:
                open_page.close()
    finally:
        IN_FLIGHT.settle()


@pytest.fixture
def editing(
    browser_server: str, page: Any, migrated_tenant: Any, member_of: Any, new_document: Any
) -> Iterator[Callable[[str | None], Any]]:
    """Open the edit tab of a new document as its author, the draft's body set to `body` when
    given; returns the document once the whole editor is opened by its control; `settled_pages`
    finishes it before the page and the server go."""

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


@pytest.fixture
def markdown(page: Any) -> Callable[[], str]:
    """The editor's text in its stored form, as it stands."""
    return lambda: str(page.evaluate("document.getElementById('editor').editor.markdown()"))

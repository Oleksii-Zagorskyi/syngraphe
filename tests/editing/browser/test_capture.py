"""Capture without Save in Chromium (ASR-22, DL-0320): typing survives a closed page; captures
follow pauses, never keystrokes; there is no Save control; a failed capture is said, the text
kept. Invented text."""

from __future__ import annotations

import re
from typing import Any

import pytest

pytestmark = pytest.mark.browser

EDITOR = "document.getElementById('editor').editor"
START = "Перше речення.\n"


def type_at_end(page: Any, text: str) -> None:
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    page.keyboard.type(text, delay=20)


def test_typing_survives_a_closed_page(
    editing: Any, page: Any, browser_server: str, migrated_tenant: Any
) -> None:
    """Closed within the pause, before any capture: what the closing page sends is the text and
    the close together, so the reopened tab has the text and no other editor holds finishing."""
    editing(START)
    type_at_end(page, " Друге речення.")
    url = page.url
    page.close()
    reopened = page.context.new_page()
    reopened.goto(url)
    reopened.click("button[data-command=edit-whole]")
    reopened.wait_for_function("() => document.getElementById('editor').editor !== undefined")
    assert "Друге речення." in reopened.evaluate(f"{EDITOR}.markdown()")
    reopened.wait_for_function(f"() => {EDITOR}.others === 0", timeout=5000)


def test_capture_on_pause_not_per_keystroke(editing: Any, page: Any) -> None:
    """Ten seconds of typing with no pause send nothing; the pause after it sends one capture,
    and the indicator goes from capturing to captured."""
    editing(START)
    captures: list[str] = []
    page.on(
        "request", lambda r: captures.append(r.url) if r.url.endswith("/edit/capture/") else None
    )
    page.evaluate(
        """() => {
          window.states = [];
          const indicator = document.querySelector('.capture-indicator');
          new MutationObserver(() => window.states.push(indicator.dataset.state))
            .observe(indicator, { attributes: true, attributeFilter: ['data-state'] });
        }"""
    )
    page.evaluate(f"{EDITOR}.select({EDITOR}.view.state.doc.content.size - 1)")
    page.focus(".ProseMirror")
    words = " Кожне слово цього речення набране без паузи довше за мить" * 3
    page.keyboard.type(words[:100], delay=100)
    assert captures == []
    page.wait_for_selector(".capture-indicator[data-state=captured]", timeout=5000)
    assert len(captures) == 1
    states = page.evaluate("() => window.states")
    assert "capturing" in states and states[-1] == "captured"


def test_a_large_text_is_captured_as_the_tab_hides(editing: Any, page: Any) -> None:
    """Over a `keepalive` request's limit, the flush on hiding is sent as a plain request."""
    editing(START)
    big = "".join(f"Речення номер {n} великого тексту.\n" for n in range(4000))
    page.evaluate(f"(text) => {EDITOR}.replace(text)", big)
    outcome = page.evaluate(f"() => {EDITOR}.capture.flush(true)")
    assert outcome == "captured"


def test_finish_waits_while_text_is_not_captured(
    editing: Any, page: Any, settings: Any, migrated_tenant: Any
) -> None:
    """*Finish editing* with the capture failing: the editor stays, the text with it, and the
    indicator says so; once the route answers, finishing goes on."""
    settings.LANGUAGE_CODE = "en"
    document = editing(START)
    page.route(re.compile(r".*/edit/capture/$"), lambda r: r.fulfill(status=500, body=""))
    type_at_end(page, " Друге речення.")
    page.click("button[data-command=finish]")
    page.wait_for_selector(".capture-indicator[data-state=failed]", timeout=5000)
    assert page.url.endswith(f"/document/{document.number}/edit/")
    assert "Друге речення." in page.evaluate(f"{EDITOR}.markdown()")
    page.wait_for_function(
        "() => !document.querySelector('button[data-command=finish]').disabled", timeout=5000
    )
    page.unroute(re.compile(r".*/edit/capture/$"))
    page.click("button[data-command=finish]")
    page.wait_for_url(f"**/document/{document.number}/edit/finish/")
    assert "Друге речення." in (page.text_content(".finish") or "")


def test_no_save_control(editing: Any, page: Any) -> None:
    editing(START)
    labels = page.eval_on_selector_all(
        "button, input[type=submit], [role=button]",
        # An icon's name is its accessible name, not its text.
        "els => els.map(e => (e.getAttribute('aria-label') || '') + ' ' + e.textContent)",
    )
    assert not any(re.search(r"(?i)save|зберегти", label or "") for label in labels)


def test_failed_capture_is_said_and_kept(editing: Any, page: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"
    editing(START)
    failing = {"on": True}

    def route(request_route: Any) -> None:
        if failing["on"]:
            request_route.fulfill(status=500, body="")
        else:
            request_route.continue_()

    page.route(re.compile(r".*/edit/capture/$"), route)
    type_at_end(page, " Друге речення.")
    page.wait_for_selector(".capture-indicator[data-state=failed]", timeout=5000)
    assert "Not captured" in (page.text_content(".capture-indicator") or "")
    assert "Друге речення." in page.evaluate(f"{EDITOR}.markdown()")
    failing["on"] = False
    page.wait_for_selector(".capture-indicator[data-state=captured]", timeout=10000)

    page.unroute(re.compile(r".*/edit/capture/$"))
    page.route(
        re.compile(r".*/edit/capture/$"),
        lambda r: r.fulfill(status=302, headers={"Location": "/signin/"}),
    )
    type_at_end(page, " Третє.")
    page.wait_for_selector(".capture-indicator[data-state=signed_out]", timeout=5000)
    assert "Signed out" in (page.text_content(".capture-indicator") or "")


def test_an_editor_closed_while_silent_reopens_itself(
    editing: Any, page: Any, migrated_tenant: Any
) -> None:
    """Closed by the sweep — a laptop asleep past three minutes — with the draft unchanged: the
    next capture opens a new editor and is taken, not refused as stale."""
    from django.utils import timezone

    from editing.models import OpenEditor
    from tenancy.schemas import schema_context

    editing(START)
    with schema_context(migrated_tenant.number):
        OpenEditor.objects.update(closed_at=timezone.now())
    type_at_end(page, " Після сну.")
    page.wait_for_selector(".capture-indicator[data-state=captured]", timeout=5000)
    with schema_context(migrated_tenant.number):
        assert OpenEditor.objects.filter(closed_at__isnull=True).count() == 1
    assert "Після сну." in page.evaluate(f"{EDITOR}.markdown()")

"""The pages run under the content policy (DL-0493): Chromium opens the editor, the reading view,
the list, search, administration, the framework's administration, help and the not-found page with
a listener for `securitypolicyviolation`; every document response carries the policy and nothing is
refused. A control proves the listener sees a violation when one is provoked.

The live server serves `/static/…` ahead of every middleware, so only document responses are
collected. Text is invented English; people are synthetic examples at `@example.test`."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from django.conf import settings as django_settings
from django.test import Client

pytestmark = pytest.mark.browser

# The decided string, written out here and compared with what the server sent (DL-0493).
POLICY = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "style-src-attr 'unsafe-inline'; "
    "img-src 'self'; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "object-src 'none'"
)
# A password the validators accept, as `tests/identity/test_framework_admin.py` sets one.
PASSWORD = "Tr4vel-Plan-Ok"
LISTENER = """
window.addEventListener("securitypolicyviolation", e => recordViolation({
  directive: e.violatedDirective, effective: e.effectiveDirective, blocked: e.blockedURI,
  source: e.sourceFile, line: e.lineNumber, sample: e.sample, document: e.documentURI
}));
"""


Policed = tuple[Any, list[dict[str, Any]], list[tuple[str, Any]], list[str]]


@pytest.fixture
def policed(page: Any) -> Iterator[Policed]:
    """The page with its listeners installed before any navigation: every violation the browser
    fires, every document response's URL and policy header, every console line naming the
    policy."""
    violations: list[dict[str, Any]] = []
    documents: list[tuple[str, Any]] = []
    console: list[str] = []

    page.expose_function("recordViolation", lambda violation: violations.append(dict(violation)))
    page.add_init_script(LISTENER)

    def on_response(response: Any) -> None:
        if response.request.resource_type == "document":
            documents.append((response.url, response.header_value("content-security-policy")))

    def on_console(message: Any) -> None:
        if "Content Security Policy" in message.text:
            console.append(message.text)

    page.on("response", on_response)
    page.on("console", on_console)
    yield page, violations, documents, console


def _assert_headers(documents: list[tuple[str, Any]]) -> None:
    assert documents, "no document response was collected"
    for url, header in documents:
        assert header == POLICY, (url, header)


def _assert_nothing_refused(violations: list[dict[str, Any]], console: list[str]) -> None:
    assert violations == [], "\n".join(repr(v) for v in violations)
    assert console == [], "\n".join(console)


def _sign_in(page: Any, browser_server: str, client: Client) -> None:
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])


def _operator() -> Client:
    from identity.models import User

    client = Client(headers={"host": "localhost"})
    client.force_login(User.objects.create_superuser("an.operator@example.test", PASSWORD))
    return client


def test_the_editor_runs_under_the_policy(
    browser_server: str, policed: Any, editing: Any, conformance_body: str
) -> None:
    page, violations, documents, console = policed

    editing(conformance_body)
    page.wait_for_selector("#editor td[style]")
    applied = page.evaluate(
        """() => {
          const cell = document.querySelector('#editor td[style]');
          return {set: cell.style.textAlign, computed: getComputedStyle(cell).textAlign};
        }"""
    )
    with page.expect_response(lambda r: "/edit/capture/" in r.url) as captured:
        page.focus(".ProseMirror")
        page.keyboard.type("a")

    _assert_headers(documents)
    assert applied["set"] in ("left", "center", "right"), applied
    assert applied["computed"] == applied["set"], applied
    assert captured.value.ok, captured.value.status
    _assert_nothing_refused(violations, console)


def test_the_reading_view_runs_under_the_policy(
    browser_server: str, policed: Any, member_of: Any, new_document: Any
) -> None:
    page, violations, documents, console = policed
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    _sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/document/{document.number}/", wait_until="load")
    page.click("[data-panel-switch=generated]")
    assert page.is_visible("[data-panel-pane=generated]")
    outline_width = page.evaluate(
        "() => getComputedStyle(document.querySelector('.panes'))"
        ".getPropertyValue('--outline-width')"
    )

    _assert_headers(documents)
    assert outline_width.strip() != ""
    _assert_nothing_refused(violations, console)


def test_the_pages_run_under_the_policy(
    browser_server: str, policed: Any, member_of: Any, new_document: Any
) -> None:
    page, violations, documents, console = policed
    client, administrator, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    new_document(administrator, "Synthetic approval procedure")
    _sign_in(page, browser_server, client)
    as_administrator = [
        "/folder/1/",
        "/search/?q=Synthetic",
        # The landing opens this, its first section (DL-0511).
        "/administration/tenant/users/",
        "/administration/tenant/folders/",
        "/help/",
        "/help/markdown/",
        "/no-such-page/",
    ]

    # Each page's own status, so a page answering the not-found page in its place is not taken for
    # the page it stands in for.
    answers = {
        path: page.goto(f"{browser_server}{path}", wait_until="load").status
        for path in as_administrator
    }
    _sign_in(page, browser_server, _operator())
    operator_index = page.goto(
        f"{browser_server}/{django_settings.DJANGO_ADMIN_PATH}", wait_until="load"
    )

    expected = {path: 404 if path == "/no-such-page/" else 200 for path in as_administrator}
    assert answers == expected
    assert operator_index.status == 200
    assert len(documents) == len(as_administrator) + 1, [url for url, _ in documents]
    _assert_headers(documents)
    _assert_nothing_refused(violations, console)


def test_the_listener_sees_a_violation(browser_server: str, policed: Any, member_of: Any) -> None:
    """The control: a sheet inserted by script is refused under `style-src 'self'`, and the
    listener records it — without this, a silent listener cannot be told from an absent one."""
    page, violations, documents, console = policed
    client, _, _ = member_of("a.member@example.test")
    _sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/folder/1/", wait_until="load")
    _assert_headers(documents)
    seen_before = len(violations)
    page.evaluate(
        """() => {
          const sheet = document.createElement('style');
          sheet.textContent = 'body { outline: 1px solid red; }';
          document.head.appendChild(sheet);
        }"""
    )
    for _ in range(50):
        if len(violations) > seen_before:
            break
        page.wait_for_timeout(100)

    provoked = violations[seen_before:]
    assert len(provoked) == 1, "\n".join(repr(v) for v in violations)
    assert provoked[0]["effective"] == "style-src-elem", provoked[0]

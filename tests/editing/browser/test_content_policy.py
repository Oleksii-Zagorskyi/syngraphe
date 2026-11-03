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
    assert page.is_visible("[data-section=generated] .section-body")
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


FIRST_RUN = "# General provisions\n\nA request for approval is made in writing.\n"
SECOND_RUN = FIRST_RUN + "\nA copy of the decision goes to the applicant that day.\n"
REVIEWERS_EDIT = SECOND_RUN + "\nThe register of requests is kept by the officer in charge.\n"


def _drafted(tenant: int, document: Any, user: Any, body: str) -> None:
    """`user` holds `document`, their draft's body set to `body`."""
    from editing import holds
    from editing.models import Draft
    from tenancy.schemas import schema_context

    with schema_context(tenant):
        hold = holds.take(document, user)
        draft = Draft.objects.get(hold=hold)
        draft.content = {**draft.content, "document.md": body}
        draft.save()


def _sent(client: Client, number: int) -> None:
    sent = client.post(
        f"/document/{number}/edit/send/", {"summary": "Synthetic edit", "choice": "send"}
    )
    assert sent.status_code == 302, sent.status_code


def _a_document_along_its_path(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> Any:
    """A synthetic document with every page to open: a first run with an appendix, accepted and
    made canonical; a second run pending; the reviewer holding it with a draft of one edit. The
    author holds *edit*, *create appendix* and *reserve for editing*; the reviewer *accept*,
    *freeze* and *make canonical*; the administrator is a tenant administrator."""
    from types import SimpleNamespace

    from access.rights import Right
    from editions import services as editions
    from review import services as review
    from tenancy.schemas import schema_context

    tenant = migrated_tenant.number
    author_client, author, author_membership = member_of("the.author@example.test")
    reviewer_client, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    administrator_client, _, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    document = new_document(author)
    link_group(
        document,
        [Right.EDIT, Right.CREATE_APPENDIX, Right.RESERVE_FOR_EDITING],
        [author_membership],
        author,
    )
    link_group(
        document,
        [Right.ACCEPT, Right.FREEZE, Right.MAKE_CANONICAL],
        [reviewer_membership],
        author,
    )
    number = document.number
    _drafted(tenant, document, author, FIRST_RUN)
    added = author_client.post(
        f"/document/{number}/edit/parts/appendix/", {"title": "Synthetic form of request"}
    )
    assert added.status_code == 303, added.status_code
    _sent(author_client, number)
    with schema_context(tenant):
        review.accept(document, reviewer)
        edition = editions.make_canonical(document, reviewer)
    _drafted(tenant, document, author, SECOND_RUN)
    _sent(author_client, number)
    _drafted(tenant, document, reviewer, REVIEWERS_EDIT)
    return SimpleNamespace(
        document=document,
        canonical=edition.number,
        author=author_client,
        reviewer=reviewer_client,
        administrator=administrator_client,
        author_user=author,
    )


# Pages that read no version: the frame's heading names none (DL-0518).
NO_VERSION = ("info/", "history/", "edit/end-reservation/")


def test_the_document_pages_run_under_the_policy(
    browser_server: str,
    policed: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
) -> None:
    """Every page of a document, opened by the readers who reach it, in the three states the
    pages need: the reviewer holding a draft while a run is pending; the run accepted; the
    author's reservation, which the administrator ends."""
    from editing import holds
    from editing.models import Hold
    from tenancy.schemas import schema_context

    page, violations, documents, console = policed
    built = _a_document_along_its_path(migrated_tenant, member_of, new_document, link_group)
    n, canonical = built.document.number, built.canonical
    head = f"{canonical}-1"
    holding = [
        "",
        "info/",
        "history/",
        "pending/",
        "pending/accept/",
        "pending/return/",
        "edit/",
        "edit/finish/",
        "my-edits/",
        f"version/{canonical}/",
        f"compare/?from={canonical}&to={head}",
        "export/",
        f"version/{canonical}/export/",
        "appendix/1/",
        f"version/{canonical}/appendix/1/",
        "appendix/1/edit/",
    ]
    answers: dict[str, int] = {}
    shapes: dict[str, tuple[bool, bool]] = {}

    def opened(path: str) -> None:
        response = page.goto(f"{browser_server}/document/{n}/{path}", wait_until="load")
        answers[path] = response.status
        shapes[path] = (
            page.locator("nav.path").count() > 0,
            page.locator("h1 .version-number").count() > 0,
        )

    _sign_in(page, browser_server, built.reviewer)
    for path in holding:
        opened(path)
    # The export page's heading follows the view chosen, without a request (DL-0519).
    page.goto(f"{browser_server}/document/{n}/export/", wait_until="networkidle")
    requested = len(documents)
    views = page.locator('input[type=radio][name="view"]')
    assert views.count() >= 2
    views.nth(1).check()
    followed = (
        page.locator("h1 .version-number").inner_text(),
        views.nth(1).get_attribute("data-number"),
    )
    page.wait_for_timeout(300)
    stayed = [url for url, _ in documents[requested:]]
    answers["(the export's views)"] = 200

    # The reviewer's draft thrown away, the run accepted: an acceptance since the edition, so
    # making canonical opens its confirmation. The editor left first, so its reload never takes
    # the document again after the discard.
    page.goto("about:blank")
    discarded = built.reviewer.post(f"/document/{n}/edit/discard/")
    assert discarded.status_code == 302, discarded.status_code
    confirmation = built.reviewer.get(f"/document/{n}/pending/accept/")
    confirmed = confirmation.content.decode().split('name="confirmed" value="')[1][:40]
    accepted = built.reviewer.post(f"/document/{n}/pending/accept/", {"confirmed": confirmed})
    assert accepted.status_code == 302, accepted.status_code
    # The approval's window opens over the page from its act and closes on *Cancel* (DL-0513).
    answers["(the approval's window)"] = page.goto(
        f"{browser_server}/document/{n}/", wait_until="load"
    ).status
    page.click("[data-window=approve]")
    page.wait_for_selector("dialog#approve[open]")
    page.click("dialog#approve [data-close]")
    page.wait_for_function("() => !document.getElementById('approve').open")
    opened("make-canonical/")

    # The author holds it again and reserves it; the administrator ends the reservation.
    with schema_context(migrated_tenant.number):
        holds.take(built.document, built.author_user)
    reserved = built.author.post(f"/document/{n}/edit/reserve/")
    assert reserved.status_code == 302, reserved.status_code
    with schema_context(migrated_tenant.number):
        assert Hold.objects.get(document=built.document, released_at__isnull=True).reserved_at
    _sign_in(page, browser_server, built.administrator)
    opened("edit/end-reservation/")

    assert answers == dict.fromkeys(answers, 200), answers
    assert len(documents) == len(answers), [url for url, _ in documents]
    _assert_headers(documents)
    _assert_nothing_refused(violations, console)
    assert {p for p, (path, _) in shapes.items() if not path} == set()
    assert followed[0] == followed[1], followed
    assert stayed == [], stayed
    assert {p for p, (_, version) in shapes.items() if p in NO_VERSION and version} == set()


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

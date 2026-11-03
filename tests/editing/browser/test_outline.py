"""The outline on every page that draws a document's text (DL-0527): each heading in it scrolls the
text to that heading — a version's page, the review page, the editor and both comparisons. Invented
English text; the people and the department are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

WINDOW = {"width": 1400, "height": 700}

# Twelve sections, long enough that the last is far below the window when the page opens; one
# sentence per line, as the stored form has it.
BODY = "".join(
    f"## Section {n} of the synthetic rules\n\n"
    + "".join(
        f"Sentence {k} of section {n} says what a member of the department does.\n"
        for k in range(1, 9)
    )
    + "\n"
    for n in range(1, 13)
)
# The same rules with one heading removed and one sentence changed, so a comparison draws a
# removed heading before the one an entry names.
CHANGED = BODY.replace("## Section 3 of the synthetic rules\n\n", "", 1).replace(
    "Sentence 8 of section 12 says", "Sentence 8 of section 12 now says", 1
)

# The heading titled `title` in the text and the one before it, relative to the window.
PLACED = """([selector, title]) => {
  const all = [...document.querySelectorAll(selector)].filter(
    (h) => h.textContent.includes(title) && !h.querySelector('del'));
  const heading = all[0];
  if (!heading) return null;
  const headings = [...document.querySelectorAll(selector)];
  const before = headings[headings.indexOf(heading) - 1];
  return {top: heading.getBoundingClientRect().top,
          before: before ? before.getBoundingClientRect().top : null,
          height: window.innerHeight};
}"""
TITLE = "Section 7 of the synthetic rules"


def _sign_in(page: Any, browser_server: str, client: Any) -> None:
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])


def _the_heading_scrolls(page: Any, text_headings: str) -> None:
    """Section 7's heading starts below the window; its outline entry clicked, that heading — not
    a neighbour — stands at the window's top, the heading before it scrolled past."""
    entry = page.locator("#outline-pane a", has_text=TITLE)
    assert entry.count() == 1, entry.count()
    before = page.evaluate(PLACED, [text_headings, TITLE])
    assert before is not None, f"no {text_headings} titled {TITLE!r} on the page"
    assert before["top"] > before["height"], before
    entry.click()
    page.wait_for_function(
        f"""() => {{
          const placed = ({PLACED})([{text_headings!r}, {TITLE!r}]);
          return Math.abs(placed.top) < 2 && placed.before < 0;
        }}""",
        timeout=5000,
    )


def _numbers(user: Any, document: Any, tenant: Any) -> list[str]:
    from review.history import reachable

    with schema_context(tenant.number):
        return [number for number, _version in reachable(user, document)]


def test_the_reading_view(
    browser_server: str, page: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """A version's page: each entry links the heading's own id, so it works without script, and
    the click scrolls to it."""
    page.set_viewport_size(WINDOW)
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(document, author, BODY, "edit")
    _sign_in(page, browser_server, client)
    page.goto(f"{browser_server}/document/{document.number}/", wait_until="load")

    href = page.locator("#outline-pane a", has_text=TITLE).get_attribute("href")
    assert href and href.startswith("#h-"), href
    assert page.locator(f".document-text [id='{href[1:]}']").count() == 1
    _the_heading_scrolls(page, ".document-text h2")


def test_the_review_page(
    browser_server: str,
    page: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    """The review page: an entry scrolls the run's marked text to its heading."""
    from access.rights import Right

    page.set_viewport_size(WINDOW)
    reviewer_client, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    _, author, author_membership = member_of("the.author@example.test")
    document = new_document(reviewer)
    link_group(document, [Right.ACCEPT], [reviewer_membership], reviewer)
    link_group(document, [Right.EDIT], [author_membership], reviewer)
    commit_version(document, author, BODY, "edit")
    _sign_in(page, browser_server, reviewer_client)
    page.goto(f"{browser_server}/document/{document.number}/pending/", wait_until="load")

    _the_heading_scrolls(page, ".changes h2")


def test_the_editor(browser_server: str, page: Any, editing: Any) -> None:
    """The draft's page, opened as the editing fixture opens it: an entry scrolls the editor to
    its heading."""
    page.set_viewport_size(WINDOW)
    editing(BODY)

    _the_heading_scrolls(page, ".ProseMirror h2")


@pytest.mark.parametrize("which", ["versions", "documents"])
def test_the_comparisons(
    which: str,
    browser_server: str,
    page: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    migrated_tenant: Any,
) -> None:
    """A comparison of two versions, and of two documents: the outline of the newer text is drawn
    beside it, and an entry scrolls the text to its heading."""
    page.set_viewport_size(WINDOW)
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(document, author, BODY, "edit")
    if which == "versions":
        commit_version(document, author, CHANGED, "edit")
        numbers = _numbers(author, document, migrated_tenant)
        url = f"/document/{document.number}/compare/?from={numbers[-2]}&to={numbers[-1]}"
    else:
        second = new_document(author)
        commit_version(second, author, CHANGED, "edit")
        url = f"/document/{document.number}/compare/?with={second.number}"
    _sign_in(page, browser_server, client)
    page.goto(f"{browser_server}{url}", wait_until="load")

    assert page.locator(".panes #outline-pane").count() == 1
    _the_heading_scrolls(page, ".changes h2")

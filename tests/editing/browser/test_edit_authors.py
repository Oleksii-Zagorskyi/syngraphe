"""Edit authors in the right margin (DL-0504), under the content policy (DL-0493): on a historical
page with *Show edit authors* ticked, a changed paragraph names its author beside the text, in the
margin the text box leaves for it, without moving its clause number; unticking the box saves the
preference through the platform's own script and the page returns without names. Comparing two
versions runs under the policy with its steps (DL-0508).

The people are synthetic examples at `@example.test`; the text is invented."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

# The policy's fixture and its assertions, loaded by path: a test module is not importable by
# name under `--import-mode=importlib`.
_spec = importlib.util.spec_from_file_location(
    "content_policy_fixtures_authors", Path(__file__).resolve().parent / "test_content_policy.py"
)
assert _spec is not None and _spec.loader is not None
_policy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _policy
_spec.loader.exec_module(_policy)

policed = _policy.policed

NAME = "Synthetic Editor A"
FIRST = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n\n"
    "A request is considered within ten days.\n"
)
SECOND = FIRST.replace("within ten days", "within five working days")

# Where a pseudo-element stands is not measurable from script, so the name's box is computed from
# its float's own width and margin against the paragraph it floats in.
GEOMETRY = """() => {
  const named = document.querySelector('.document-text [data-author]');
  const text = document.querySelector('.document-text');
  const panel = document.querySelector('.panes .panel');
  const num = named.querySelector('.num');
  const before = getComputedStyle(named, '::before');
  const p = named.getBoundingClientRect();
  const right = p.right - parseFloat(before.marginRight);
  const box = text.getBoundingClientRect();
  return {
    content: before.content,
    author: named.getAttribute('data-author'),
    float: before.float,
    name: {left: right - parseFloat(before.width), right: right},
    text: {left: box.left, right: box.right},
    panel: panel ? panel.getBoundingClientRect().left : null,
    viewport: window.innerWidth,
    num: num ? num.getBoundingClientRect().left : null,
    named: document.querySelectorAll('.document-text [data-author]').length,
  };
}"""


def _history(
    migrated_tenant: Any, member_of: Any, new_document: Any, commit_version: Any
) -> tuple[Any, Any]:
    """A document whose second version changes its second paragraph, its edit authors worked out,
    and its author with *Show edit authors* on."""
    from documents import gitstore
    from editing import authorship
    from identity.models import User

    client, author, _ = member_of("the.author@example.test")
    User.objects.filter(pk=author.pk).update(display_name=NAME)
    document = new_document(author)
    commit_version(document, author, FIRST, "edit")
    second = commit_version(document, author, SECOND, "edit")
    with schema_context(migrated_tenant.number):
        authorship.compute(
            document,
            second.commit_sha,
            repository_path=gitstore.repository_path(migrated_tenant.number, document.number),
        )
    assert client.post("/preferences/show-author/", {"show_author": "on"}).status_code == 302
    return client, document


def test_the_name_stands_in_the_margin(
    browser_server: str,
    policed: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    page, violations, documents, console = policed
    client, document = _history(migrated_tenant, member_of, new_document, commit_version)
    _policy._sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/document/{document.number}/version/0.0-2/", wait_until="load")
    drawn = page.evaluate(GEOMETRY)

    assert drawn["named"] == 1, drawn
    assert drawn["author"] == NAME and drawn["content"] == f'"{NAME}"', drawn
    assert drawn["float"] == "right", drawn
    # Right of the text's box, inside the viewport, short of the panel beside the text.
    assert drawn["name"]["left"] > drawn["text"]["right"], drawn
    assert drawn["name"]["right"] <= drawn["viewport"], drawn
    assert drawn["panel"] is None or drawn["name"]["right"] <= drawn["panel"], drawn
    # The clause number keeps the gutter: at the box's left edge, inside its 1 px border.
    assert drawn["num"] is not None and abs(drawn["num"] - drawn["text"]["left"] - 1) < 1, drawn
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)


# The checkbox's box against the text's box and the names' column beside it.
TITLE = """() => {
  const form = document.querySelector('form.show-author').getBoundingClientRect();
  const text = document.querySelector('.document-text').getBoundingClientRect();
  const panel = document.querySelector('.panes .panel');
  return {
    form: {left: form.left, right: form.right, bottom: form.bottom},
    text: {right: text.right, top: text.top},
    panel: panel ? panel.getBoundingClientRect().left : null,
    viewport: window.innerWidth,
  };
}"""


def test_the_checkbox_heads_the_names_column(
    browser_server: str,
    policed: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    """On the historical page the checkbox is the names' column's title: right of the text's box,
    above its first line, and it stays there when the window narrows."""
    page, violations, documents, console = policed
    client, document = _history(migrated_tenant, member_of, new_document, commit_version)
    _policy._sign_in(page, browser_server, client)
    page.goto(f"{browser_server}/document/{document.number}/version/0.0-2/", wait_until="load")

    for width in (1400, 1100):
        page.set_viewport_size({"width": width, "height": 900})
        drawn = page.evaluate(TITLE)
        assert drawn["form"]["left"] >= drawn["text"]["right"], (width, drawn)
        assert drawn["form"]["right"] <= drawn["viewport"], (width, drawn)
        assert drawn["panel"] is None or drawn["form"]["right"] <= drawn["panel"], (width, drawn)
        assert drawn["form"]["bottom"] <= drawn["text"]["top"] + 1, (width, drawn)
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)


def test_the_checkbox_saves_and_redraws(
    browser_server: str,
    policed: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    page, violations, documents, console = policed
    client, document = _history(migrated_tenant, member_of, new_document, commit_version)
    _policy._sign_in(page, browser_server, client)
    page.goto(f"{browser_server}/document/{document.number}/version/0.0-2/", wait_until="load")
    with_names = page.evaluate(GEOMETRY)

    with page.expect_response(lambda r: r.url.endswith("/preferences/show-author/")) as saved:
        page.uncheck("form.show-author input[type=checkbox]")
    page.wait_for_load_state("load")
    page.wait_for_function("() => !document.querySelector('form.show-author input').checked")

    assert saved.value.status == 302
    assert page.locator(".document-text .by").count() == 0
    # Without the names the number stands where it stood with them.
    num = page.evaluate(
        """() => [...document.querySelectorAll('.document-text p')]
          .find(p => p.textContent.includes('five working days'))
          .querySelector('.num').getBoundingClientRect().left"""
    )
    assert with_names["num"] is not None and abs(num - with_names["num"]) < 1
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)


def test_the_pending_tabs_checkbox_runs_under_the_policy(
    browser_server: str,
    policed: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    """The pending tab's checkbox heads the names' column and saves through the platform's own
    script: unticked, the tab returns without names, and nothing is refused."""
    page, violations, documents, console = policed
    client, document = _history(migrated_tenant, member_of, new_document, commit_version)
    _policy._sign_in(page, browser_server, client)
    url = f"{browser_server}/document/{document.number}/pending/"

    answer = page.goto(url, wait_until="load")
    assert answer.status == 200, answer.status
    assert page.is_checked("form.show-author input[type=checkbox]")
    with page.expect_response(lambda r: r.url.endswith("/preferences/show-author/")) as saved:
        page.uncheck("form.show-author input[type=checkbox]")
    page.wait_for_load_state("load")
    page.wait_for_function("() => !document.querySelector('form.show-author input').checked")

    assert saved.value.status == 302
    assert page.url == url
    assert page.locator(".pending.show-authors").count() == 0
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)


def test_compare_runs_under_the_policy(
    browser_server: str,
    policed: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
    settings: Any,
) -> None:
    settings.LANGUAGE_CODE = "en"
    page, violations, documents, console = policed
    client, document = _history(migrated_tenant, member_of, new_document, commit_version)
    _policy._sign_in(page, browser_server, client)

    answer = page.goto(
        f"{browser_server}/document/{document.number}/compare/?from=0.0-1&to=0.0-2",
        wait_until="load",
    )

    assert answer.status == 200
    assert page.get_attribute("a.step.previous", "aria-label") == "previous"
    assert page.locator("button.step.next[disabled]").count() == 1
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)


def test_named_items_of_one_list_stand_in_the_margin(
    browser_server: str,
    policed: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    """Two changed items of one list are two blocks, each named in the margin; only a paragraph
    whose sentences have several authors names them at their sentences' ends."""
    from documents import gitstore
    from editing import authorship
    from identity.models import User

    page, violations, documents, console = policed
    client, author, _ = member_of("the.author@example.test")
    User.objects.filter(pk=author.pk).update(display_name=NAME)
    document = new_document(author)
    listed = FIRST + "\n- The first synthetic item.\n- The second synthetic item.\n"
    commit_version(document, author, FIRST, "edit")
    second = commit_version(document, author, listed, "edit")
    with schema_context(migrated_tenant.number):
        authorship.compute(
            document,
            second.commit_sha,
            repository_path=gitstore.repository_path(migrated_tenant.number, document.number),
        )
    assert client.post("/preferences/show-author/", {"show_author": "on"}).status_code == 302
    _policy._sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/document/{document.number}/version/0.0-2/", wait_until="load")
    drawn = page.evaluate(
        """() => [...document.querySelectorAll('.document-text li[data-author]')].map(li => ({
          before: getComputedStyle(li, '::before').content,
          after: getComputedStyle(li, '::after').content,
        }))"""
    )

    assert drawn == [{"before": f'"{NAME}"', "after": "none"}] * 2, drawn
    _policy._assert_nothing_refused(violations, console)

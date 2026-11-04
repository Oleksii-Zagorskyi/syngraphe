"""The document's frame drawn in Chromium: the acts' reasons wrap inside the frame, the heading's
icons stay on the title's line, every window dims the page behind it, and a dangerous button reads
apart from its cancel. Titles and people are synthetic examples."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

LONG_TITLE = (
    "A synthetic procedure for approving requests made in writing by any member of a department, "
    "and for answering them within ten working days"
)


def _sign_in(page: Any, browser_server: str, client: Any) -> None:
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])


@pytest.fixture
def held(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> Any:
    from access.rights import Right
    from review import services as review
    from tenancy.schemas import schema_context

    editor_client, editor, editor_membership = member_of("the.editor@example.test")
    approver_client, approver, approver_membership = member_of("the.approver@example.test")
    document = new_document(editor, LONG_TITLE)
    link_group(document, [Right.EDIT], [editor_membership], editor)
    link_group(
        document,
        [Right.ACCEPT, Right.FREEZE, Right.MAKE_CANONICAL],
        [approver_membership],
        editor,
    )
    commit_version(document, editor, "# Scope\n\nA synthetic sentence.\n", "edit")
    with schema_context(migrated_tenant.number):
        review.accept(document, approver)
    assert editor_client.post(f"/document/{document.number}/edit/take/").status_code == 200
    return document, approver_client


INSIDE = """() => {
  const frame = document.querySelector('nav.path').getBoundingClientRect();
  const parts = [...document.querySelectorAll('nav.path .phase-acts > .act, nav.path .elbow')]
    .filter((e) => !e.hidden && e.getClientRects().length);
  return {
    count: parts.length,
    outside: parts.map((e) => e.getBoundingClientRect())
      .filter((r) => r.left < frame.left - 1 || r.right > frame.right + 1)
      .map((r) => [r.left, r.right, frame.left, frame.right]),
  };
}"""


def test_reasons_wrap_inside_the_frame(browser_server: str, page: Any, held: Any) -> None:
    document, approver = held
    page.set_viewport_size({"width": 1100, "height": 900})
    _sign_in(page, browser_server, approver)
    page.goto(f"{browser_server}/document/{document.number}/", wait_until="load")
    page.wait_for_function("() => document.querySelector('nav.path .acts-row.placed') !== null")

    drawn = page.evaluate(INSIDE)
    reasons = page.locator("nav.path .phase-acts .reason").count()

    assert reasons >= 2, reasons
    assert drawn["count"] >= 3 and drawn["outside"] == [], drawn


def test_the_walks_notes_drawn(browser_server: str, page: Any, held: Any) -> None:
    document, approver = held
    page.set_viewport_size({"width": 1100, "height": 900})
    _sign_in(page, browser_server, approver)
    page.goto(f"{browser_server}/document/{document.number}/", wait_until="load")

    line = page.evaluate(
        """() => {
          const h1 = document.querySelector('.title-row h1').getBoundingClientRect();
          const icons = document.querySelector('.title-row .head-icons').getBoundingClientRect();
          return {h1top: h1.top, h1right: h1.right, top: icons.top, left: icons.left};
        }"""
    )
    assert line["top"] < line["h1top"] + 24 and line["left"] >= line["h1right"] - 1, line
    colours = page.evaluate(
        """() => {
          const plain = document.createElement('button');
          plain.className = 'btn';
          const danger = document.createElement('button');
          danger.className = 'btn danger';
          document.body.append(plain, danger);
          const out = [getComputedStyle(plain).backgroundColor,
                       getComputedStyle(danger).backgroundColor];
          const dialog = document.createElement('dialog');
          document.body.append(dialog);
          dialog.showModal();
          out.push(getComputedStyle(dialog, '::backdrop').backgroundColor);
          dialog.close();
          return out;
        }"""
    )
    assert colours[0] != colours[1], colours
    assert colours[2] not in ("rgba(0, 0, 0, 0)", "transparent", ""), colours


ELBOW = """() => {
  const row = document.querySelector('nav.path .acts-row.placed .phase-acts');
  const acts = row.getBoundingClientRect();
  const elbow = document.querySelector('nav.path .elbow').getBoundingClientRect();
  return {touches: Math.abs(elbow.right - acts.right) <= 2 || Math.abs(elbow.left - acts.left) <= 2,
          acts: [acts.left, acts.right], elbow: [elbow.left, elbow.right]};
}"""


def test_the_elbow_meets_the_acts_after_a_resize(browser_server: str, page: Any, held: Any) -> None:
    document, approver = held
    page.set_viewport_size({"width": 1400, "height": 900})
    _sign_in(page, browser_server, approver)
    page.goto(f"{browser_server}/document/{document.number}/", wait_until="load")
    page.wait_for_function("() => document.querySelector('nav.path .acts-row.placed') !== null")

    for width in (900, 1250, 760):
        page.set_viewport_size({"width": width, "height": 900})
        page.wait_for_function(f"() => window.innerWidth === {width}")
        page.evaluate(
            "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
        )
        drawn = page.evaluate(ELBOW)
        assert drawn["touches"], (width, drawn)
        assert page.evaluate(INSIDE)["outside"] == [], width

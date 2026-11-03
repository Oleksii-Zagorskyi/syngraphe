"""The side panes (DL-0526): a collapsed pane is a strip of at most 40 px that gives the text its
width back; the person's collapse is kept across reloads and the pages of a kind, each pane apart;
a window too narrow for the text beside the open panes draws them collapsed on load, opens one
over the text on its toggle, and forgets that collapse once the window is wide again — on a
version's page, the review page and the draft's page alike.

Boxes are measured, never classes. The text is invented English; people are synthetic examples
at `@example.test`."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

WIDE = {"width": 1400, "height": 900}
NARROW = {"width": 900, "height": 900}

# The numbers the panes keep: a collapsed pane's widest, the text's narrowest at a narrow window, an
# open pane's narrowest over the text, the tolerance of a restored width, and the default widths.
STRIP = 40
TEXT = 560
OPEN = 160
NEAR = 2
DEFAULTS = {"outline-pane": 250, "panel": 280}

# Three headings, so the outline has entries; one sentence per line, as the stored form has it.
BODY = (
    "# General provisions\n\n"
    "A request for approval is made in writing.\n"
    "A request is considered within ten days.\n\n"
    "## Who may request\n\n"
    "Any member of a synthetic department may request an approval.\n\n"
    "## How a request is answered\n\n"
    "The answer names the person who decided it.\n"
    "A refused request may be made again after a month.\n"
)

# A page's panes at a glance: each box by its id, the text's box, and the toggle's standing.
BOXES = """(ids) => {
  const box = (e) => {
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width};
  };
  const out = {centre: box(document.querySelector('.panes > .centre')), panes: {}};
  for (const id of ids) {
    const pane = document.getElementById(id);
    const toggle = document.querySelector(`[data-pane-toggle="${id}"]`);
    let hit = null;
    if (toggle) {
      const t = toggle.getBoundingClientRect();
      const under = document.elementFromPoint((t.left + t.right) / 2, (t.top + t.bottom) / 2);
      hit = !!under && (under === toggle || toggle.contains(under) || under.contains(toggle));
    }
    out.panes[id] = {box: box(pane), toggle: box(toggle), hit: hit};
  }
  return out;
}"""


def _sign_in(page: Any, browser_server: str, client: Any) -> None:
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])


def _boxes(page: Any, *ids: str) -> dict[str, Any]:
    drawn = page.evaluate(BOXES, list(ids))
    assert drawn["centre"] is not None, "no `.panes > .centre` on the page"
    for pane_id in ids:
        assert drawn["panes"][pane_id]["box"] is not None, f"no `#{pane_id}` on the page"
    return drawn


def _toggle(page: Any, pane_id: str) -> None:
    """Click the pane's toggle; every pane draws one, so its absence fails here, not as a
    timeout."""
    selector = f'[data-pane-toggle="{pane_id}"]'
    assert page.locator(selector).count() == 1, f"no toggle {selector} on the page"
    page.click(selector, timeout=5000)


def _click_the_text(page: Any, pane_id: str) -> None:
    """A click on the text's box, outside the pane that is open over it."""
    drawn = _boxes(page, pane_id)
    centre, pane = drawn["centre"], drawn["panes"][pane_id]["box"]
    if pane["left"] <= centre["left"]:
        x = max(centre["left"], pane["right"]) + 30
    else:
        x = min(centre["right"], pane["left"]) - 30
    assert centre["left"] < x < centre["right"], (centre, pane)
    assert not (pane["left"] <= x <= pane["right"]), (centre, pane)
    page.mouse.click(x, centre["top"] + 120)


def _version_page(
    page: Any, browser_server: str, member_of: Any, new_document: Any, commit_version: Any
) -> tuple[Any, Any]:
    """A document with headings and its author's page on its version; the author and the
    document."""
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    commit_version(document, author, BODY, "edit")
    _sign_in(page, browser_server, client)
    return author, document


def _goto(page: Any, url: str, ready: str | None = None) -> None:
    page.goto(url, wait_until="load")
    if ready is not None:
        page.wait_for_function(ready, timeout=60_000)


EDITOR_READY = "() => document.getElementById('editor').editor !== undefined"


# A collapsed pane is a strip.


def _collapses_whole(page: Any, pane_id: str) -> None:
    before = _boxes(page, pane_id)
    pane_before = before["panes"][pane_id]["box"]["width"]
    centre_before = before["centre"]["width"]
    assert pane_before > STRIP, f"`#{pane_id}` is not open to begin with: {before}"

    _toggle(page, pane_id)
    collapsed = _boxes(page, pane_id)
    pane = collapsed["panes"][pane_id]
    assert pane["box"]["width"] <= STRIP, (pane_id, collapsed)
    assert page.is_visible(f'[data-pane-toggle="{pane_id}"]'), (pane_id, collapsed)
    assert pane["toggle"] is not None and pane["hit"], (pane_id, collapsed)
    assert pane["toggle"]["left"] >= pane["box"]["left"] - 1, (pane_id, collapsed)
    assert pane["toggle"]["right"] <= pane["box"]["right"] + 1, (pane_id, collapsed)
    assert collapsed["centre"]["width"] >= centre_before + (pane_before - STRIP), (
        pane_id,
        {"before": before, "collapsed": collapsed},
    )

    _toggle(page, pane_id)
    restored = _boxes(page, pane_id)
    assert abs(restored["panes"][pane_id]["box"]["width"] - pane_before) <= NEAR, (
        pane_id,
        {"before": before, "restored": restored},
    )
    assert abs(restored["centre"]["width"] - centre_before) <= NEAR, (
        pane_id,
        {"before": before, "restored": restored},
    )


def test_the_outline_collapses_whole(
    browser_server: str, page: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """On a version's page at 1400 × 900, the outline and then the panel each collapse to a
    strip, give the text their width, and come back as they were."""
    page.set_viewport_size(WIDE)
    _, document = _version_page(page, browser_server, member_of, new_document, commit_version)
    _goto(page, f"{browser_server}/document/{document.number}/")

    _collapses_whole(page, "outline-pane")
    _collapses_whole(page, "panel")


# The person's collapse is kept.


def _widths(page: Any) -> dict[str, float]:
    drawn = _boxes(page, "outline-pane", "panel")
    return {pane_id: drawn["panes"][pane_id]["box"]["width"] for pane_id in drawn["panes"]}


def test_a_collapse_is_kept(
    browser_server: str, page: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """At 1400 px: the outline collapsed on one version's page is collapsed after a reload and on
    another document's page; the panel's state is its own; expanding and reloading shows the
    pane expanded."""
    page.set_viewport_size(WIDE)
    author, first = _version_page(page, browser_server, member_of, new_document, commit_version)
    second = new_document(author, "Another synthetic procedure")
    commit_version(second, author, BODY, "edit")
    first_url = f"{browser_server}/document/{first.number}/"
    second_url = f"{browser_server}/document/{second.number}/"

    _goto(page, first_url)
    assert _widths(page)["outline-pane"] > STRIP, _widths(page)
    assert _widths(page)["panel"] > STRIP, _widths(page)
    _toggle(page, "outline-pane")
    assert _widths(page)["outline-pane"] <= STRIP, _widths(page)

    page.reload(wait_until="load")
    kept = _widths(page)
    assert kept["outline-pane"] <= STRIP, kept
    assert kept["panel"] > STRIP, kept

    _goto(page, second_url)
    elsewhere = _widths(page)
    assert elsewhere["outline-pane"] <= STRIP, elsewhere
    assert elsewhere["panel"] > STRIP, elsewhere

    # The panel apart from the outline: collapsing it leaves the outline as it was, and each
    # survives the reload on its own.
    _toggle(page, "panel")
    page.reload(wait_until="load")
    both = _widths(page)
    assert both["outline-pane"] <= STRIP and both["panel"] <= STRIP, both

    _toggle(page, "outline-pane")
    page.reload(wait_until="load")
    expanded = _widths(page)
    assert expanded["outline-pane"] > STRIP, expanded
    assert expanded["panel"] <= STRIP, expanded

    _goto(page, first_url)
    back = _widths(page)
    assert back["outline-pane"] > STRIP, back
    assert back["panel"] <= STRIP, back


# A narrow window keeps the text (DL-0526).


def _narrow_window_keeps_the_text(
    page: Any, url: str, panel_id: str, ready: str | None = None
) -> None:
    """The page already open at 900 × 900: the rule's four points, then the resize and the fresh
    load at 1400 px."""
    ids = ("outline-pane", panel_id)
    loaded = _boxes(page, *ids)
    for pane_id in ids:
        assert loaded["panes"][pane_id]["box"]["width"] <= STRIP, (pane_id, loaded)
    assert loaded["centre"]["width"] >= TEXT, loaded
    text_left = loaded["centre"]["left"]
    text_width = loaded["centre"]["width"]

    for pane_id in ids:
        _toggle(page, pane_id)
        opened = _boxes(page, *ids)
        pane = opened["panes"][pane_id]["box"]
        assert pane["width"] >= OPEN, (pane_id, opened)
        assert page.is_visible(f"#{pane_id}"), (pane_id, opened)
        assert abs(opened["centre"]["width"] - text_width) <= NEAR, (pane_id, loaded, opened)
        assert abs(opened["centre"]["left"] - text_left) <= NEAR, (pane_id, loaded, opened)

        _click_the_text(page, pane_id)
        closed = _boxes(page, *ids)
        assert closed["panes"][pane_id]["box"]["width"] <= STRIP, (pane_id, closed)

    # Not the person's choice: a wide window draws the panes open at their widths, no reload.
    page.set_viewport_size(WIDE)
    page.wait_for_function("() => window.innerWidth === 1400")
    # The window's `resize` event is dispatched with the next frame, after the new width reads.
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    resized = _boxes(page, *ids)
    for pane_id in ids:
        expected = DEFAULTS.get(pane_id, OPEN)
        width = resized["panes"][pane_id]["box"]["width"]
        if pane_id in DEFAULTS:
            assert abs(width - expected) <= NEAR, (pane_id, resized)
        else:
            assert width >= expected, (pane_id, resized)

    # And a fresh load at 1400 px after the load at 900 px.
    _goto(page, url, ready)
    fresh = _boxes(page, *ids)
    for pane_id in ids:
        assert fresh["panes"][pane_id]["box"]["width"] > STRIP, (pane_id, fresh)


def test_a_narrow_window_keeps_the_text(
    browser_server: str, page: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """On a version's page at 900 × 900 both panes load collapsed and the text keeps 560 px; a
    toggle opens its pane over the text; a click on the text closes it; a resize to 1400 px opens
    the panes, as does a fresh load there."""
    page.set_viewport_size(NARROW)
    _, document = _version_page(page, browser_server, member_of, new_document, commit_version)
    url = f"{browser_server}/document/{document.number}/"
    _goto(page, url)

    _narrow_window_keeps_the_text(page, url, "panel")


# Every page with panes.


@pytest.mark.parametrize("which", ["review", "draft", "compare"])
def test_a_narrow_window_on_every_page(
    which: str,
    browser_server: str,
    page: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    editing: Any,
    migrated_tenant: Any,
) -> None:
    """A narrow window on the review page, as a holder of *accept* with a run pending, on the
    draft's page as the holder, and on a comparison of two versions."""
    page.set_viewport_size(NARROW)
    if which == "review":
        from access.rights import Right

        reviewer_client, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
        _, author, author_membership = member_of("the.author@example.test")
        document = new_document(reviewer)
        link_group(document, [Right.ACCEPT], [reviewer_membership], reviewer)
        link_group(document, [Right.EDIT], [author_membership], reviewer)
        commit_version(document, author, BODY, "edit")
        _sign_in(page, browser_server, reviewer_client)
        url = f"{browser_server}/document/{document.number}/pending/"
        _goto(page, url)
        _narrow_window_keeps_the_text(page, url, "run-panel")
    elif which == "compare":
        client, author, _ = member_of("the.author@example.test")
        document = new_document(author)
        commit_version(document, author, BODY, "edit")
        commit_version(document, author, BODY.replace("ten days", "five days"), "edit")
        _sign_in(page, browser_server, client)
        first, second = _two_newest(author, document, migrated_tenant)
        url = f"{browser_server}/document/{document.number}/compare/?from={first}&to={second}"
        _goto(page, url)
        _narrow_window_keeps_the_text(page, url, "panel")
    else:
        document = editing(BODY)
        url = f"{browser_server}/document/{document.number}/edit/"
        _narrow_window_keeps_the_text(page, url, "parts-panel", EDITOR_READY)


def _two_newest(user: Any, document: Any, tenant: Any) -> tuple[str, str]:
    from review.history import reachable
    from tenancy.schemas import schema_context

    with schema_context(tenant.number):
        numbers = [number for number, _version in reachable(user, document)]
    return numbers[-2], numbers[-1]


# The panel's sections stack and collapse on their own (DL-0536).

APPENDIX = [{"number": 1, "title": "Synthetic appendix"}]
APPENDIX_FILES = {"appendices/1.md": b"# Synthetic appendix\n\nAn appendix sentence.\n"}

# The panel's box and each section's name and body: the box of each, whether it is visible, and
# the name's text.
SECTIONS = """(panel) => {
  const box = (e) => {
    if (!e) return null;
    const r = e.getBoundingClientRect();
    return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width};
  };
  const shown = (e) => !!e && e.getClientRects().length > 0
    && getComputedStyle(e).visibility !== 'hidden';
  const root = document.querySelector(panel);
  const out = {panel: box(root), sections: {}};
  for (const section of root ? root.querySelectorAll('[data-section]') : []) {
    const name = section.querySelector('[data-section-toggle]');
    const body = section.querySelector('.section-body');
    out.sections[section.getAttribute('data-section')] = {
      name: {box: box(name), shown: shown(name), text: name ? name.textContent.trim() : null},
      body: {box: box(body), shown: shown(body)},
    };
  }
  return out;
}"""


def _sections(page: Any, panel: str = "#panel") -> dict[str, Any]:
    drawn = page.evaluate(SECTIONS, panel)
    assert drawn["panel"] is not None, f"no `{panel}` on the page"
    return drawn


def _name_inside(section: dict[str, Any], panel: dict[str, Any]) -> bool:
    name = section["name"]["box"]
    return (
        name is not None
        and section["name"]["shown"]
        and bool(section["name"]["text"])
        and name["left"] >= panel["left"] - 1
        and name["right"] <= panel["right"] + 1
    )


def _section_name(page: Any, which: str) -> None:
    selector = f'#panel [data-section="{which}"] [data-section-toggle]'
    assert page.locator(selector).count() == 1, f"no section name {selector} on the page"
    page.click(selector, timeout=5000)


def test_the_panel_sections_collapse_and_are_named(
    browser_server: str,
    page: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
) -> None:
    """On a version's page at 1400 px the panel stacks *Parts* and *Generated views*, both open
    on load; a section's name collapses its body alone; with every section collapsed the panel
    is a strip that still shows each name, and a name opens the panel on that section. The
    review page's one-section panel collapses on its toggle with its name in the strip."""
    from access.rights import Right

    page.set_viewport_size(WIDE)
    client, author, membership = member_of("the.author@example.test")
    link_client, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    document = new_document(author)
    link_group(document, [Right.ACCEPT], [reviewer_membership], author)
    link_group(document, [Right.EDIT], [membership], author)
    commit_version(document, author, BODY, "edit", files=APPENDIX_FILES, appendices=APPENDIX)
    _sign_in(page, browser_server, client)
    _goto(page, f"{browser_server}/document/{document.number}/")

    # Both sections open on load, the icon row gone.
    loaded = _sections(page)
    assert set(loaded["sections"]) == {"parts", "generated"}, loaded
    assert page.locator("[data-panel-switch]").count() == 0
    for which in ("parts", "generated"):
        assert loaded["sections"][which]["body"]["shown"], (which, loaded)
        assert _name_inside(loaded["sections"][which], loaded["panel"]), (which, loaded)

    # One section collapsed: its body gone, its name there, the other untouched.
    _section_name(page, "parts")
    one = _sections(page)
    assert not one["sections"]["parts"]["body"]["shown"], one
    assert _name_inside(one["sections"]["parts"], one["panel"]), one
    assert one["sections"]["generated"]["body"]["shown"], one
    # Untouched: the other section's body keeps its width, the panel its column.
    assert (
        abs(
            one["sections"]["generated"]["body"]["box"]["width"]
            - loaded["sections"]["generated"]["body"]["box"]["width"]
        )
        <= NEAR
    ), (loaded, one)
    assert abs(one["panel"]["width"] - loaded["panel"]["width"]) <= NEAR, (loaded, one)

    # Every section collapsed: a strip, each name visible inside it.
    _section_name(page, "generated")
    strip = _sections(page)
    assert strip["panel"]["width"] <= STRIP, strip
    for which in ("parts", "generated"):
        assert not strip["sections"][which]["body"]["shown"], (which, strip)
        assert _name_inside(strip["sections"][which], strip["panel"]), (which, strip)

    # A name opens the panel on its section.
    _section_name(page, "generated")
    opened = _sections(page)
    assert opened["panel"]["width"] >= OPEN, opened
    assert opened["sections"]["generated"]["body"]["shown"], opened
    assert not opened["sections"]["parts"]["body"]["shown"], opened

    # The review page's panel is one section: the pane's toggle collapses the column, the name
    # stays in the strip.
    _sign_in(page, browser_server, link_client)
    _goto(page, f"{browser_server}/document/{document.number}/pending/")
    review = _sections(page, "#run-panel")
    assert review["panel"]["width"] > STRIP, review
    assert len(review["sections"]) == 1, review
    _toggle(page, "run-panel")
    collapsed = _sections(page, "#run-panel")
    assert collapsed["panel"]["width"] <= STRIP, collapsed
    (section,) = collapsed["sections"].values()
    assert _name_inside(section, collapsed["panel"]), collapsed


# A kept collapse and a narrowed panel across a resize.

FRAMES = "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"


def _resize(page: Any, size: dict[str, int]) -> None:
    page.set_viewport_size(size)
    page.wait_for_function(f"() => window.innerWidth === {size['width']}")
    page.evaluate(FRAMES)


def test_a_kept_collapse_opened_over_the_text_stays_kept(
    browser_server: str, page: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """The outline kept collapsed, opened over the text in a narrow window, and the window widened:
    the outline is collapsed again, as the person keeps it."""
    page.set_viewport_size(WIDE)
    _, document = _version_page(page, browser_server, member_of, new_document, commit_version)
    url = f"{browser_server}/document/{document.number}/"
    _goto(page, url)
    with page.expect_response(lambda r: "/preferences/outline-shut/" in r.url):
        _toggle(page, "outline-pane")
    _resize(page, NARROW)
    _toggle(page, "outline-pane")
    assert _boxes(page, "outline-pane")["panes"]["outline-pane"]["box"]["width"] >= OPEN

    _resize(page, WIDE)
    assert _boxes(page, "outline-pane")["panes"]["outline-pane"]["box"]["width"] <= STRIP


def test_a_narrowed_panel_restored_shows_its_sections(
    browser_server: str, page: Any, member_of: Any, new_document: Any, commit_version: Any
) -> None:
    """At 900 px the panel opened from its strip on *Parts*, *Parts* collapsed — the panel with it —
    and the window widened: the panel is restored with its sections open, not a column of names."""
    page.set_viewport_size(NARROW)
    _, document = _version_page(page, browser_server, member_of, new_document, commit_version)
    _goto(page, f"{browser_server}/document/{document.number}/")
    _section_name(page, "parts")
    _section_name(page, "parts")
    assert _boxes(page, "panel")["panes"]["panel"]["box"]["width"] <= STRIP

    _resize(page, WIDE)
    drawn = _sections(page)
    assert drawn["panel"]["width"] >= OPEN
    assert all(section["body"]["shown"] for section in drawn["sections"].values()), drawn

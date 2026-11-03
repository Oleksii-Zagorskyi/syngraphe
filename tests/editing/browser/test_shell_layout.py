"""The shell's layout holds where a person reaches for it: a right on the groups grid is a target
the height of its row, the bar fits its window with the switcher and a long organisation name, an
address field and a dialog's title are as wide as what they hold, and a document's acts stand
apart.

Text is invented English; people are synthetic examples at `@example.test`."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

pytestmark = pytest.mark.browser

# Wide enough to lay the bar out on one line until the switcher and a long name join it.
VIEWPORT = {"width": 1280, "height": 800}


def _sign_in(page: Any, browser_server: str, client: Client) -> None:
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])


def test_a_right_on_the_grid_is_a_target(browser_server: str, page: Any, member_of: Any) -> None:
    """A right the group neither holds nor inherits draws an empty button; it keeps the height of
    a click, not of its padding."""
    client, _, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    _sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/administration/tenant/groups/", wait_until="load")
    with page.expect_navigation(wait_until="load"):
        page.fill("#name", "Synthetic group")
        page.press("#name", "Enter")
    heights = page.evaluate(
        """() => [...document.querySelectorAll('.grid td.right button')]
             .filter(b => b.textContent.trim() === '')
             .map(b => b.getBoundingClientRect().height)"""
    )

    assert heights, "no empty right was drawn"
    assert min(heights) >= 20, heights


def test_the_bar_fits_with_the_switcher(
    browser_server: str, page: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    """A member of two organisations, one of them named at length: the bar's items move to a
    second line whole, nothing is broken inside, and the page never scrolls sideways."""
    from identity.models import Membership

    client, user, _ = member_of("a.member.of.two@example.test")
    elsewhere = make_tenant_schema("A synthetic organisation with a rather long name to show")
    Membership.objects.create(tenant=elsewhere, user=user, actor_kind="system")
    page.set_viewport_size(VIEWPORT)
    _sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/folder/1/", wait_until="load")
    layout = page.evaluate(
        """() => ({
          switcher: !!document.querySelector('form.switcher select'),
          overflow: document.documentElement.scrollWidth - window.innerWidth,
          broken: [...document.querySelectorAll(
              'header.shell .menu a, header.shell .organisation, header.shell .user > *')]
            .filter(e => e.getClientRects().length > 1
                      || e.getBoundingClientRect().height > 40)
            .map(e => e.textContent.trim()),
        })"""
    )

    assert layout["switcher"], "the switcher was not drawn"
    assert layout["overflow"] <= 0, layout
    assert layout["broken"] == [], layout


def test_an_address_field_holds_an_address(browser_server: str, page: Any, member_of: Any) -> None:
    client, _, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    _sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/administration/tenant/users/invite/", wait_until="load")
    address = "a.rather.long.invited.address@example.test"
    page.fill("input[type=email]", address)
    room = page.evaluate(
        "() => { const f = document.querySelector('input[type=email]');"
        " return f.clientWidth - f.scrollWidth; }"
    )

    assert room >= 0, f"the field scrolls its text by {-room} px"


def test_the_acts_stand_apart(
    browser_server: str, page: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """The acts hung from the chosen version, on one line: no two of them touch."""
    from access.rights import Right

    client, author, membership = member_of("the.author@example.test", is_tenant_admin=True)
    document = new_document(author)
    link_group(document, [Right.ACCEPT, Right.FREEZE, Right.MAKE_CANONICAL], [membership], author)
    _sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/document/{document.number}/", wait_until="load")
    gaps = page.evaluate(
        """() => {
          const acts = [...document.querySelector('nav.path .phase-acts').children]
            .map(e => e.getBoundingClientRect()).filter(r => r.width > 0);
          const gaps = [];
          for (let i = 1; i < acts.length; i++) {
            const sameLine = Math.abs(acts[i].top - acts[i - 1].top) < 4;
            if (sameLine) gaps.push(acts[i].left - acts[i - 1].right);
          }
          return {count: acts.length, gaps};
        }"""
    )

    assert gaps["count"] >= 2, gaps
    assert gaps["gaps"] and min(gaps["gaps"]) >= 6, gaps


def test_a_title_field_holds_a_title(
    browser_server: str, page: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """The copy dialog's title, prefilled with the source's, is shown whole."""
    from access.rights import Right

    client, author, membership = member_of("the.author@example.test")
    document = new_document(author, "A synthetic travel procedure for the regional offices")
    link_group(document, [Right.CREATE_AND_EDIT], [membership], author)
    _sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/document/{document.number}/copy/", wait_until="load")
    room = page.evaluate(
        "() => { const f = document.querySelector('#copy-document input[name=title]');"
        " return f.clientWidth - f.scrollWidth; }"
    )

    assert room >= 0, f"the field scrolls its text by {-room} px"


def _policed_fixture() -> Any:
    """The content policy's fixture, loaded by path: a test module is not importable by name
    under `--import-mode=importlib`."""
    import importlib.util
    import sys
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "content_policy_fixtures_layout", Path(__file__).resolve().parent / "test_content_policy.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_policy = _policed_fixture()
policed = _policy.policed


def test_the_members_block_opens_in_view(
    browser_server: str, policed: Any, member_of: Any, migrated_tenant: Any
) -> None:
    """*members…* of a group low on a long grid opens the block above the grid, in view, and
    *Close* takes it away (DL-0506)."""
    from access.models import AccessGroup
    from tenancy.schemas import schema_context

    page, violations, documents, console = policed
    page.set_viewport_size(VIEWPORT)
    client, admin, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    with schema_context(migrated_tenant.number):
        for n in range(30):
            AccessGroup.objects.create(
                name=f"Synthetic group {n:02}", created_by=admin, actor_kind="user"
            )
    _sign_in(page, browser_server, client)
    page.goto(f"{browser_server}/administration/tenant/groups/", wait_until="load")

    with page.expect_response(lambda r: "/members/" in r.url):
        page.locator('a[href$="/members/"]').last.click()
    # htmx scrolls after the swap settles; a block never brought into view times the wait out.
    page.wait_for_function(
        "() => { const b = document.querySelector('#dialog .members');"
        " return b !== null && b.getBoundingClientRect().top > -1; }",
        timeout=5000,
    )
    placed = page.evaluate(
        """() => ({
          top: document.querySelector('#dialog .members').getBoundingClientRect().top,
          grid: document.querySelector('table.grid').getBoundingClientRect().top,
        })"""
    )

    # In view, to within the sub-pixel the scroll may leave; above the grid.
    assert -1 < placed["top"] < placed["grid"], placed
    with page.expect_navigation(wait_until="load"):
        page.click("#dialog .members form.close button")
    assert page.locator("#dialog .members").count() == 0
    _policy._assert_nothing_refused(violations, console)


def test_the_chips_share_a_line(
    browser_server: str, policed: Any, member_of: Any, migrated_tenant: Any, make_document: Any
) -> None:
    """A document linked to three groups draws its three chips on one line (DL-0511)."""
    from access.models import AccessGroup, DocumentGroup
    from tenancy.schemas import schema_context

    page, violations, documents, console = policed
    page.set_viewport_size(VIEWPORT)
    client, admin, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    document = make_document(title="Synthetic example", created_by=admin)
    with schema_context(migrated_tenant.number):
        for name in ("Readers", "Editors", "Reviewers"):
            group = AccessGroup.objects.create(name=name, created_by=admin, actor_kind="user")
            DocumentGroup.link(document, group, by=admin)
    _sign_in(page, browser_server, client)
    page.goto(f"{browser_server}/administration/tenant/document-links/", wait_until="load")

    tops = page.evaluate(
        "() => [...document.querySelectorAll('.chips > .chip')]"
        ".map(c => c.getBoundingClientRect().top)"
    )

    assert len(tops) == 3 and len(set(tops)) == 1, tops
    _policy._assert_nothing_refused(violations, console)


def test_the_textareas_take_the_width(browser_server: str, policed: Any, member_of: Any) -> None:
    """The stylesheet's box and the template's outline take the width of what holds them
    (DL-0511)."""
    page, violations, documents, console = policed
    page.set_viewport_size(VIEWPORT)
    client, _, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    _sign_in(page, browser_server, client)

    widths = []
    for path, selector in (
        ("/administration/tenant/styles/", "#stylesheet-text"),
        ("/administration/tenant/template/", "textarea.outline"),
    ):
        page.goto(f"{browser_server}{path}", wait_until="load")
        widths.append(
            page.evaluate(
                f"""() => {{
                  const box = document.querySelector('{selector}');
                  const around = box.parentElement;
                  const style = getComputedStyle(around);
                  return [box.getBoundingClientRect().width,
                          around.clientWidth - parseFloat(style.paddingLeft)
                            - parseFloat(style.paddingRight)];
                }}"""
            )
        )

    for box, form in widths:
        assert abs(box - form) < 2, widths
    _policy._assert_nothing_refused(violations, console)


def test_the_settings_page_runs_under_the_policy(
    browser_server: str, policed: Any, member_of: Any
) -> None:
    """The organisation's settings refuse a value out of bounds beside its field, then apply a
    good one and say *Applied*, with nothing refused (DL-0511)."""
    page, violations, documents, console = policed
    client, _, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    _sign_in(page, browser_server, client)
    url = f"{browser_server}/administration/tenant/settings/"

    page.goto(url, wait_until="load")
    page.fill("input[name=attachment_max_mb]", "0")
    with page.expect_navigation(wait_until="load"):
        page.click("#tenant-settings button[type=submit]")
    assert page.locator("#tenant-settings .err").count() >= 1
    assert page.locator('#tenant-settings [role="status"]').count() == 0

    page.fill("input[name=attachment_max_mb]", "6")
    with page.expect_navigation(wait_until="load"):
        page.click("#tenant-settings button[type=submit]")
    assert page.url == url + "?applied=1"
    assert page.locator('#tenant-settings [role="status"]').count() == 1
    assert page.locator("#tenant-settings .err").count() == 0
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)


def test_the_editor_is_as_wide_as_the_text(
    browser_server: str, page: Any, editing: Any, migrated_tenant: Any
) -> None:
    """The editor's column on the draft's page and the text's on the version's page measure the
    same at one window width (DL-0513)."""
    document = editing("A synthetic sentence.\n")
    editor = page.evaluate(
        "() => document.querySelector('.panes.edit-panes > .centre').getBoundingClientRect().width"
    )
    page.goto(f"{browser_server}/document/{document.number}/", wait_until="load")
    text = page.evaluate(
        "() => document.querySelector('.panes > .centre').getBoundingClientRect().width"
    )

    assert abs(editor - text) < 1, (editor, text)


def test_the_text_keeps_its_column_before_the_take(
    browser_server: str, page: Any, member_of: Any, new_document: Any
) -> None:
    """A draft's page reached from elsewhere waits on *Start editing* with no parts panel yet: the
    text keeps its column beside the outline, never the outline's edge track."""
    import re

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    _sign_in(page, browser_server, client)

    def as_from_elsewhere(route: Any) -> None:
        response = route.fetch()
        body = response.text().replace('data-take-on-mount="true"', 'data-take-on-mount="false"')
        route.fulfill(response=response, body=body)

    page.route(re.compile(rf".*/document/{document.number}/edit/$"), as_from_elsewhere)
    page.goto(f"{browser_server}/document/{document.number}/edit/")
    page.wait_for_selector("button[data-command=start]")
    width = page.evaluate(
        "() => document.querySelector('.panes.edit-panes > .centre').getBoundingClientRect().width"
    )

    assert width > 300, width

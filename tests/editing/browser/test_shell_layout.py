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
    browser_server: str, page: Any, member_of: Any, new_document: Any
) -> None:
    """The document's acts above its tabs: no two of them touch on one line."""
    client, author, _ = member_of("the.author@example.test", is_tenant_admin=True)
    document = new_document(author)
    _sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/document/{document.number}/", wait_until="load")
    gaps = page.evaluate(
        """() => {
          const acts = [...document.querySelector('.document-actions').children]
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

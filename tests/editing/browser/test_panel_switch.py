"""The document page's right panel (DL-0356, DL-0448, DL-0536): it stacks its sections, parts and
the generated views, one under another, each collapsing on its own name; the icon row that once
showed them in turn is gone. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser

# A section's name and body.
SHOWN = """(which) => {
  const section = document.querySelector(`#panel [data-section="${which}"]`);
  const shown = (e) => !!e && e.getClientRects().length > 0
    && getComputedStyle(e).visibility !== 'hidden';
  return section ? {
    name: shown(section.querySelector('[data-section-toggle]')),
    body: shown(section.querySelector('.section-body')),
  } : null;
}"""


def _shown(page: Any, which: str) -> dict[str, bool]:
    drawn = page.evaluate(SHOWN, which)
    assert drawn is not None, f'no `#panel [data-section="{which}"]` on the page'
    return drawn


def test_the_panel_stacks_its_sections(
    browser_server: str, page: Any, member_of: Any, new_document: Any
) -> None:
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/", wait_until="load")

    assert page.locator("[data-panel-switch]").count() == 0
    assert _shown(page, "parts") == {"name": True, "body": True}
    assert _shown(page, "generated") == {"name": True, "body": True}

    page.click('#panel [data-section="parts"] [data-section-toggle]', timeout=5000)
    assert _shown(page, "parts") == {"name": True, "body": False}
    assert _shown(page, "generated") == {"name": True, "body": True}

    page.click('#panel [data-section="generated"] [data-section-toggle]', timeout=5000)
    assert _shown(page, "parts") == {"name": True, "body": False}
    assert _shown(page, "generated") == {"name": True, "body": False}

    page.click('#panel [data-section="parts"] [data-section-toggle]', timeout=5000)
    assert _shown(page, "parts") == {"name": True, "body": True}
    assert _shown(page, "generated") == {"name": True, "body": False}

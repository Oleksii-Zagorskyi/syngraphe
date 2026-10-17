"""The document page's right panel (DL-0356, DL-0448): it opens on parts, and its icon row shows the
generated views and parts in turn. Invented text."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.browser


def test_the_panel_switches(
    browser_server: str, page: Any, member_of: Any, new_document: Any
) -> None:
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])
    page.goto(f"{browser_server}/document/{document.number}/")

    parts = "[data-panel-pane=parts]"
    generated = "[data-panel-pane=generated]"
    assert page.is_visible(parts) and not page.is_visible(generated)
    page.click("[data-panel-switch=generated]")
    assert page.is_visible(generated) and not page.is_visible(parts)
    assert page.get_attribute("[data-panel-switch=generated]", "aria-pressed") == "true"
    page.click("[data-panel-switch=parts]")
    assert page.is_visible(parts) and not page.is_visible(generated)

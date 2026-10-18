"""The title page switched and its text written in the edit tab, in Chromium (DL-0463, DL-0476):
the panel's form saved, the tab drawn again with the draft's values. People are synthetic
examples; the text is invented."""

from __future__ import annotations

from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

BODY = "# Purpose\n\nThe first synthetic sentence.\n"


def test_the_switch_in_the_edit_tab(
    browser_server: str,
    page: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
    queued_authorship: list[Any],
) -> None:
    from access.rights import Right
    from editing import holds
    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    client, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT], [own], holder)
    commit_version(document, holder, BODY)
    session = client.cookies["sessionid"].value
    page.context.add_cookies([{"name": "sessionid", "value": session, "url": browser_server}])

    page.goto(f"{browser_server}/document/{document.number}/edit/")
    page.wait_for_selector("#parts-panel:not([hidden])")
    page.check(".title-page-panel input[name=title_page]")
    page.fill("#title-page-text", "Register entry: EX-1\nSecond line")
    with page.expect_response(lambda r: r.url.endswith("/edit/title-page/")) as posted:
        page.click(".title-page-panel button[type=submit]")
    assert posted.value.status == 303
    # The tab drawn again from the draft, not the form as it was typed.
    page.wait_for_load_state("load")
    page.wait_for_selector("#parts-panel:not([hidden])")

    assert page.is_checked(".title-page-panel input[name=title_page]")
    assert page.input_value("#title-page-text") == "Register entry: EX-1\nSecond line"
    with schema_context(migrated_tenant.number):
        frontmatter = Draft.objects.get(hold=holds.open_hold(document)).content["frontmatter"]
    assert frontmatter["title_page"] is True
    assert frontmatter["title_page_text"] == "Register entry: EX-1\nSecond line"

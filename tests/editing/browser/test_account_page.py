"""The account page under the content policy (DL-0493, DL-0500): Chromium opens `/account/`,
chooses *English* and *Apply*; the page returns in English, saying so, and nothing is refused.

The person is a synthetic example at `@example.test`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.browser

# The policy's fixture and its assertions, loaded by path: a test module is not importable by
# name under `--import-mode=importlib`.
_spec = importlib.util.spec_from_file_location(
    "content_policy_fixtures_account", Path(__file__).resolve().parent / "test_content_policy.py"
)
assert _spec is not None and _spec.loader is not None
_policy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _policy
_spec.loader.exec_module(_policy)

policed = _policy.policed


def test_the_account_page_runs_under_the_policy(
    browser_server: str, policed: Any, member_of: Any, settings: Any
) -> None:
    settings.LANGUAGE_CODE = "uk"
    page, violations, documents, console = policed
    client, _, _ = member_of("a.member@example.test")
    _policy._sign_in(page, browser_server, client)

    opened = page.goto(f"{browser_server}/account/", wait_until="load")
    assert opened.status == 200
    assert page.get_attribute("html", "lang") == "uk"
    page.select_option("select[name=language]", "en")
    with page.expect_navigation(wait_until="load"):
        page.click("form[action='/account/'] button[type=submit]")

    assert page.get_attribute("html", "lang") == "en"
    assert page.locator(".user a[href='/account/']").inner_text() == "My account"
    assert page.locator("[role=status]").inner_text() == "Applied"
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)

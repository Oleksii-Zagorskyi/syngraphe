"""Changing organisation from the shell (DL-0525, DL-0497) under the content policy: the
organisation's name opens a window listing the person's organisations, and choosing one switches
the session to it.

People and organisations are synthetic examples at `@example.test`."""

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
    "content_policy_fixtures_switch", Path(__file__).resolve().parent / "test_content_policy.py"
)
assert _spec is not None and _spec.loader is not None
_policy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _policy
_spec.loader.exec_module(_policy)

policed = _policy.policed


def test_the_window(
    browser_server: str, policed: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    from identity.models import Membership

    page, violations, documents, console = policed
    client, person, _ = member_of("two.places@example.test")
    other = make_tenant_schema("Another synthetic organisation")
    Membership.objects.create(tenant=other, user=person, actor_kind="system")
    _policy._sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/folder/1/", wait_until="load")
    assert not page.is_visible("#organisations-window")
    page.click("header.shell a.organisation")
    assert page.is_visible("#organisations-window")
    with page.expect_navigation(wait_until="load"):
        page.click(f"#organisations-window button.linklike:has-text('{other.name}')")

    assert page.locator("header.shell a.organisation").inner_text() == other.name
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)

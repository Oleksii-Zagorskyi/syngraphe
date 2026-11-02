"""The member's page under the content policy (DL-0493, DL-0505): Chromium opens it with the
listener of `test_content_policy.py` installed; choosing a group in *Add* and submitting swaps
`#member-groups` through htmx — one document response, no full load — and nothing is refused.

People and groups are synthetic examples at `@example.test`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

# The policy's fixture and its assertions, from the module that defines them — a test module is
# not importable by name under `--import-mode=importlib`, so it is loaded by path, as
# `tests/editions/conftest.py` loads the review fixtures.
_spec = importlib.util.spec_from_file_location(
    "content_policy_fixtures", Path(__file__).resolve().parent / "test_content_policy.py"
)
assert _spec is not None and _spec.loader is not None
_policy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _policy
_spec.loader.exec_module(_policy)

policed = _policy.policed

ADD_SELECT = '#member-groups form[data-act="add"] select[name="group"]'
ADD_BUTTON = '#member-groups form[data-act="add"] button[type="submit"]'


def test_the_members_page_runs_under_the_policy(
    browser_server: str, policed: Any, migrated_tenant: Any, member_of: Any
) -> None:
    """Row 12: the page loads with no violation; *Add* of a group swaps `#member-groups` without a
    full load — the one request is htmx's, with `HX-Request`."""
    from access.models import AccessGroup, GroupMember

    page, violations, documents, console = policed
    administrator, admin_user, _ = member_of("an.administrator@example.test", is_tenant_admin=True)
    _, _, membership = member_of("a.member@example.test")
    with schema_context(migrated_tenant.number):
        editors = AccessGroup.objects.create(
            name="Editors", created_by=admin_user, actor_kind="user"
        )
        editors.add_member(membership, by=admin_user)
        reviewers = AccessGroup.objects.create(
            name="Reviewers", created_by=admin_user, actor_kind="user"
        )
    _policy._sign_in(page, browser_server, administrator)
    url = f"{browser_server}/administration/tenant/users/{membership.id}/"

    answer = page.goto(url, wait_until="load")
    assert answer.status == 200, answer.status
    page.wait_for_function(f"() => document.querySelector('{ADD_SELECT}') !== null", timeout=5000)
    page.select_option(ADD_SELECT, str(reviewers.id))
    with page.expect_response(
        lambda r: r.url == f"{url}groups/" and r.request.method == "POST"
    ) as posted:
        page.click(ADD_BUTTON)
    swapped = posted.value
    added = f'#member-groups li[data-group="{reviewers.id}"]'
    page.wait_for_function(f"() => document.querySelector('{added}') !== null", timeout=5000)

    assert swapped.status == 200
    assert swapped.request.headers.get("hx-request") == "true"
    assert swapped.request.resource_type != "document"
    assert page.url == url
    # The page itself was the only document response: the swap was no full load.
    assert [seen for seen, _ in documents] == [url]
    assert page.query_selector(f'#member-groups li[data-group="{editors.id}"]') is not None
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)
    with schema_context(migrated_tenant.number):
        assert GroupMember.objects.filter(group=reviewers, membership=membership).exists()

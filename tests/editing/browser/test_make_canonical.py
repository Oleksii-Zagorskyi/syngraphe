"""The *make canonical* confirmation under the content policy (DL-0493, DL-0515): an unfrozen
document with a version committed and accepted by a second person; the approver opens
`/document/N/make-canonical/` in Chromium with the listener of `test_content_policy.py` installed —
the confirmation loads at 200, names no freeze, and nothing is refused.

People and groups are synthetic examples at `@example.test`; the text is invented."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from access.rights import Right
from review import services as review
from tenancy.schemas import schema_context

pytestmark = pytest.mark.browser

# The policy's fixture and its assertions, loaded by path as `tests/editions/conftest.py` loads
# the review fixtures: a test module is not importable by name under `--import-mode=importlib`.
_spec = importlib.util.spec_from_file_location(
    "content_policy_fixtures", Path(__file__).resolve().parent / "test_content_policy.py"
)
assert _spec is not None and _spec.loader is not None
_policy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _policy
_spec.loader.exec_module(_policy)

policed = _policy.policed

FIRST = "# General provisions\n\nA request for approval is made in writing.\n"


def test_the_confirmation_runs_under_the_policy(
    browser_server: str,
    policed: Any,
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    settings: Any,
) -> None:
    """Row 10a: the confirmation of an unfrozen, accepted document loads at 200 for the approver,
    without *and the freeze ends*; no violation."""
    from editions.models import open_freeze

    settings.LANGUAGE_CODE = "en"
    page, violations, documents, console = policed
    _, author, author_membership = member_of("the.author@example.test")
    _, reviewer, reviewer_membership = member_of("the.reviewer@example.test")
    approver_client, _, approver_membership = member_of("the.approver@example.test")
    document = new_document(author)
    link_group(document, [Right.EDIT], [author_membership], author)
    link_group(document, [Right.ACCEPT], [reviewer_membership], author)
    link_group(document, [Right.FREEZE, Right.MAKE_CANONICAL], [approver_membership], author)
    commit_version(document, author, FIRST, "edit")
    with schema_context(migrated_tenant.number):
        assert review.accept(document, reviewer).number == "0.1"
        assert open_freeze(document) is None
    _policy._sign_in(page, browser_server, approver_client)
    url = f"{browser_server}/document/{document.number}/make-canonical/"

    answer = page.goto(url, wait_until="load")
    # Before the wait: a refusal redirects to the document page, which also answers 200.
    assert page.url == url, page.url
    assert answer.status == 200, answer.status
    page.wait_for_function(
        "() => document.querySelector('.make-canonical-confirm') !== null", timeout=5000
    )
    text = " ".join(page.inner_text(".make-canonical-confirm").split())

    assert "Version 0.1 becomes edition 1.0." in text, text
    assert "and the freeze ends" not in text, text
    assert "An edition is never undone: the next one supersedes it." in text, text
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)

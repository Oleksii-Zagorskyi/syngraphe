"""The walk's corrections under the content policy (DL-0493, DL-0511): the choice of an
organisation for a person of several, its *Switch* landing on the documents; a kept draft on a
frozen document, read only. Nothing is refused.

People and organisations are synthetic examples at `@example.test`; the text is invented."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.browser


def _load(name: str, path: Path) -> Any:
    """A test module by its path: none is importable by name under `--import-mode=importlib`."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_policy = _load("content_policy_fixtures_walk", Path(__file__).parent / "test_content_policy.py")
_back = _load("take_back_scene_walk", Path(__file__).parents[1] / "test_take_back.py")
policed = _policy.policed
scene = _back.scene


def test_the_choice_of_an_organisation_runs_under_the_policy(
    browser_server: str, policed: Any, migrated_tenant: Any, make_tenant_schema: Any
) -> None:
    from django.test import Client

    from identity.models import Membership, User

    page, violations, documents, console = policed
    person = User.objects.create_user("two.orgs@example.test", "test-only-not-a-password")
    other = make_tenant_schema("Second Synthetic Org")
    for tenant in (migrated_tenant, other):
        Membership.objects.create(tenant=tenant, user=person, actor_kind="system")
    client = Client(headers={"host": "localhost"})
    client.force_login(person)
    _policy._sign_in(page, browser_server, client)

    page.goto(f"{browser_server}/", wait_until="load")
    assert page.locator("form[action='/organisation/switch/']").count() == 2
    with page.expect_navigation(wait_until="load"):
        page.locator(
            f"form[action='/organisation/switch/']:has(input[value='{migrated_tenant.number}'])"
            " button"
        ).click()

    assert page.url.endswith("/folder/1/"), page.url
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)


def test_a_kept_draft_on_a_frozen_document_runs_under_the_policy(
    browser_server: str,
    policed: Any,
    migrated_tenant: Any,
    scene: Any,
    member_of: Any,
    link_group: Any,
) -> None:
    page, violations, documents, console = policed
    _back.ended_reservation(migrated_tenant, scene)
    _back._frozen(migrated_tenant, scene, member_of, link_group)
    _policy._sign_in(page, browser_server, scene.holder_client)

    page.goto(f"{browser_server}/document/{scene.document.number}/", wait_until="load")
    with page.expect_navigation(wait_until="load"):
        page.click(f"a[href='/document/{scene.document.number}/edit/']")

    assert page.locator("form[action$='/edit/discard-draft/']").count() == 1
    assert page.locator("form[action$='/edit/take-back/']").count() == 0
    _policy._assert_headers(documents)
    _policy._assert_nothing_refused(violations, console)

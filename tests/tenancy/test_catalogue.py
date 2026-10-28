"""The organisation's pages of the `tenancy` app render in Ukrainian from the one catalogue: the
settings page, as stored and with every bound refused.

People and organisations are synthetic examples."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_spec = importlib.util.spec_from_file_location(
    "tenancy_catalogue", Path(__file__).resolve().parents[1] / "review" / "test_catalogue.py"
)
assert _spec is not None and _spec.loader is not None
_review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_review)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_the_settings_page(member_of: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "uk"
    admin, _, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    ids = _review.message_ids(_review.CATALOGUE.read_text(encoding="utf-8"))
    page = "/administration/tenant/settings/"
    bodies = {
        "as stored": admin.get(page).content.decode(),
        "under the bounds": admin.post(
            page, {"attachment_max_mb": "0", "hold_inactivity_minutes": "4"}
        ).content.decode(),
        "over the bounds": admin.post(
            page, {"attachment_max_mb": "100000", "hold_inactivity_minutes": "481"}
        ).content.decode(),
        "the frame": admin.get("/administration/").content.decode(),
    }
    # The bounds are format strings, whose ids never match the page as drawn.
    own = [
        "Attachment size cap",
        "Inactivity timeout",
        "Distinct approver check",
        "From 1 to",
        "From 5 to",
    ]
    for name, body in bodies.items():
        shown = _review.text_of(body)
        leaked = [message for message in [*ids, *own] if message in shown]
        assert leaked == [], (name, leaked)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_catalogue_covers_the_switch_page(
    migrated_tenant: Any, make_tenant_schema: Any, settings: Any
) -> None:
    """The page a switch made on an organisation's domain answers with (DL-0497), for both of its
    links: to the other organisation's domain, and to the platform host."""
    from django.test import Client

    from identity.models import Membership, User
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import TenantDomain

    settings.LANGUAGE_CODE = "uk"
    with_domain = make_tenant_schema("Друга синтетична")
    without = make_tenant_schema("Третя синтетична")
    person = User.objects.create_user("two.places@example.test", "test-only-not-a-password")
    for tenant in (migrated_tenant, with_domain, without):
        Membership.objects.create(tenant=tenant, user=person, actor_kind="system")
    for tenant, host in (
        (migrated_tenant, "first.example.test"),
        (with_domain, "second.example.test"),
    ):
        TenantDomain.objects.create(tenant=tenant, host=host, is_default=True, actor_kind="system")
    invalidate_host_cache()
    client = Client(headers={"host": "first.example.test"})
    client.force_login(person)
    ids = _review.message_ids(_review.CATALOGUE.read_text(encoding="utf-8"))
    bodies = {
        "to a domain": client.post("/organisation/switch/", {"organisation": with_domain.number}),
        "to the platform": client.post("/organisation/switch/", {"organisation": without.number}),
    }
    own = ["Switch organisation", "Work in", "Switch", "Cancel"]
    for name, answer in bodies.items():
        assert answer.status_code == 200, name
        shown = _review.text_of(answer.content.decode())
        leaked = [message for message in [*ids, *own] if message in shown]
        assert leaked == [], (name, leaked)

"""Administration › styles (ST-0046, DL-0230, DL-0464, DL-0465): the organisation's stylesheet,
checked at *Apply* with every refusal named by its line, saved and audited; empty, the platform's
default.

People and stylesheets are synthetic examples."""

from __future__ import annotations

import html
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/tenant/styles/"
VALID = 'h1 { font-family: "DejaVu Serif"; color: #1f3864; }\n@page { margin: 20mm; }\n'


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    settings.LANGUAGE_CODE = "en"


def _row(migrated_tenant: Any) -> Any:
    from rendering.models import Stylesheet

    with schema_context(migrated_tenant.number):
        return Stylesheet.objects.get()


def test_every_organisation_starts_with_the_default(migrated_tenant: Any) -> None:
    from rendering.models import Stylesheet

    with schema_context(migrated_tenant.number):
        rows = list(Stylesheet.objects.all())

    assert [(row.text, row.actor_kind) for row in rows] == [("", "system")]


def test_apply_checks_saves_and_audits(
    migrated_tenant: Any, member_of: Any, signed_in_without_tenant: Any
) -> None:
    from audit.models import AuditEvent

    admin, admin_user, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    member, _, _ = member_of("a.member@example.test")
    platform = signed_in_without_tenant("p.admin@example.test", is_platform_admin=True)
    session = platform.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    for client in (admin, platform):
        page = html.unescape(client.get(PAGE).content.decode())
        for font in ("DejaVu Sans", "DejaVu Serif Condensed", "monospace"):
            assert font in page
        assert "Used by every document of the organisation." in page
    assert member.get(PAGE).status_code == 404
    assert member.post(PAGE, {"text": VALID}).status_code == 404

    applied = admin.post(PAGE, {"text": VALID.replace("\n", "\r\n")})
    refused = admin.post(PAGE, {"text": "h1 { color: #123456; }\nh2 { background: url(x.png) }\n"})

    assert applied.status_code == 303 and applied["Location"] == PAGE
    row = _row(migrated_tenant)
    assert (row.text, row.updated_by_id) == (VALID, admin_user.pk)
    (event,) = AuditEvent.objects.filter(action="stylesheet.changed")
    assert (event.before, event.after) == ({"text": ""}, {"text": VALID})
    assert event.object_type == "stylesheet" and event.object_id == row.pk
    assert refused.status_code == 400
    assert "Line 2: background fetches from outside the platform." in html.unescape(
        refused.content.decode()
    )
    assert _row(migrated_tenant).text == VALID
    assert AuditEvent.objects.filter(action="stylesheet.changed").count() == 1
    # Empty text: the platform's default again.
    assert admin.post(PAGE, {"text": ""}).status_code == 303
    assert _row(migrated_tenant).text == ""

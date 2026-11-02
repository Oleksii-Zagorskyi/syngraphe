"""Administration › Settings (ST-0053; DL-0458, DL-0469, DL-0115): the attachment cap, the
inactivity timeout and the distinct-approver check, set by the organisation's administrators on one
page, bounded by the form and — the stored bounds — by the database, every change audited.

People and organisations are synthetic examples."""

from __future__ import annotations

import html
import re
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.test import Client

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/tenant/settings/"
MB = 1024 * 1024
DOMAIN = "settings.example.test"


@pytest.fixture(autouse=True)
def english(settings: Any) -> None:
    # The bounds' wording is read in English; the catalogue test reads the page in `uk`.
    settings.LANGUAGE_CODE = "en"


def _tenant(migrated_tenant: Any) -> Any:
    from tenancy.models import Tenant

    return Tenant.objects.get(pk=migrated_tenant.pk)


def _events() -> list[Any]:
    from audit.models import AuditEvent

    return list(AuditEvent.objects.filter(action="tenant.settings_changed").order_by("at"))


def _tokenless(body: bytes) -> bytes:
    return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", body)


def test_settings_are_saved_and_audited(migrated_tenant: Any, member_of: Any) -> None:
    admin, person, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    shown = admin.get(PAGE)
    assert shown.status_code == 200
    page = html.unescape(shown.content.decode())
    assert re.search(r'name="attachment_max_mb"[^>]*value="5"', page)
    assert re.search(r'name="hold_inactivity_minutes"[^>]*value="30"', page)
    assert 'name="require_distinct_approver"' in page
    assert "checked" not in re.search(r"<input[^>]*require_distinct_approver[^>]*>", page)[0]

    saved = admin.post(
        PAGE,
        {
            "attachment_max_mb": "8",
            "hold_inactivity_minutes": "60",
            "require_distinct_approver": "on",
        },
    )

    assert saved.status_code == 303 and saved["Location"] == PAGE + "?applied=1"
    tenant = _tenant(migrated_tenant)
    assert tenant.attachment_max_bytes == 8 * MB
    assert tenant.hold_inactivity_minutes == 60
    assert tenant.require_distinct_approver is True
    assert tenant.updated_by_id == person.pk
    [event] = _events()
    assert event.actor_id == person.pk and event.tenant_id == tenant.pk
    assert event.object_type == "tenant" and event.object_id == tenant.pk
    assert event.before == {
        "attachment_max_bytes": 5 * MB,
        "hold_inactivity_minutes": 30,
        "require_distinct_approver": False,
    }
    assert event.after == {
        "attachment_max_bytes": 8 * MB,
        "hold_inactivity_minutes": 60,
        "require_distinct_approver": True,
    }


def test_an_unchanged_save_records_nothing(migrated_tenant: Any, member_of: Any) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    saved = admin.post(PAGE, {"attachment_max_mb": "5", "hold_inactivity_minutes": "30"})

    assert saved.status_code == 303
    assert _events() == []


def test_only_the_changed_fields_are_recorded(migrated_tenant: Any, member_of: Any) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    admin.post(PAGE, {"attachment_max_mb": "5", "hold_inactivity_minutes": "45"})

    [event] = _events()
    assert event.before == {"hold_inactivity_minutes": 30}
    assert event.after == {"hold_inactivity_minutes": 45}


@pytest.mark.parametrize(
    ("cap", "timeout", "named"),
    [
        ("0", "30", "1"),
        ("21", "30", "20"),
        ("5", "4", "5"),
        ("5", "481", "480"),
        ("2.5", "30", "whole"),
    ],
)
def test_bounds_are_named_and_refused(
    migrated_tenant: Any, member_of: Any, settings: Any, cap: str, timeout: str, named: str
) -> None:
    settings.UPLOAD_MAX_BYTES = 20 * MB
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    refused = admin.post(PAGE, {"attachment_max_mb": cap, "hold_inactivity_minutes": timeout})

    assert refused.status_code == 400
    page = html.unescape(refused.content.decode())
    errors = " ".join(re.findall(r'<p class="err">([^<]*)</p>', page))
    assert named in errors, errors
    tenant = _tenant(migrated_tenant)
    assert (tenant.attachment_max_bytes, tenant.hold_inactivity_minutes) == (5 * MB, 30)
    assert _events() == []


def test_the_help_text_names_each_bound(
    migrated_tenant: Any, member_of: Any, settings: Any
) -> None:
    settings.UPLOAD_MAX_BYTES = 20 * MB
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    page = html.unescape(admin.get(PAGE).content.decode())

    assert "From 1 to 20 MB" in page
    assert "From 5 to 480 minutes" in page


def test_a_cap_above_a_lowered_maximum_is_shown_and_refused_until_lowered(
    migrated_tenant: Any, member_of: Any, settings: Any
) -> None:
    from tenancy.models import Tenant

    Tenant.objects.filter(pk=migrated_tenant.pk).update(attachment_max_bytes=20 * MB)
    settings.UPLOAD_MAX_BYTES = 10 * MB
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    page = html.unescape(admin.get(PAGE).content.decode())
    assert re.search(r'name="attachment_max_mb"[^>]*value="20"', page)
    refused = admin.post(PAGE, {"attachment_max_mb": "20", "hold_inactivity_minutes": "45"})
    assert refused.status_code == 400
    assert _tenant(migrated_tenant).hold_inactivity_minutes == 30

    saved = admin.post(PAGE, {"attachment_max_mb": "10", "hold_inactivity_minutes": "45"})
    assert saved.status_code == 303
    assert _tenant(migrated_tenant).attachment_max_bytes == 10 * MB


def test_the_service_refuses_past_the_platform_maximum(
    migrated_tenant: Any, member_of: Any, settings: Any
) -> None:
    from tenancy.services import Refused, change_settings

    settings.UPLOAD_MAX_BYTES = 20 * MB
    _, person, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    with pytest.raises(Refused):
        change_settings(
            _tenant(migrated_tenant),
            by=person,
            attachment_max_bytes=21 * MB,
            hold_inactivity_minutes=30,
            require_distinct_approver=False,
        )
    assert _tenant(migrated_tenant).attachment_max_bytes == 5 * MB
    assert _events() == []


@pytest.mark.parametrize(
    "change",
    [
        {"hold_inactivity_minutes": 481},
        {"hold_inactivity_minutes": 4},
        {"attachment_max_bytes": 100},
        {"attachment_max_bytes": MB + 1},
    ],
)
def test_bounds_are_stored(migrated_tenant: Any, change: dict[str, int]) -> None:
    from tenancy.models import Tenant

    with pytest.raises(IntegrityError, match="tenancy_tenant_"), transaction.atomic():
        Tenant.objects.filter(pk=migrated_tenant.pk).update(**change)


def test_who_reaches_the_page(
    migrated_tenant: Any, member_of: Any, signed_in_without_tenant: Any
) -> None:
    from identity.models import User
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import TenantDomain

    member, _, _ = member_of("a.member@example.test")
    nothing = _tokenless(member.get("/no-such-address/").content)
    answer = member.get(PAGE)
    assert answer.status_code == 404 and _tokenless(answer.content) == nothing
    posted = member.post(PAGE, {"attachment_max_mb": "8", "hold_inactivity_minutes": "60"})
    assert posted.status_code == 404 and _events() == []

    chosen = signed_in_without_tenant("p.admin@example.test", is_platform_admin=True)
    session = chosen.session
    session["tenant_number"] = migrated_tenant.number
    session.save()
    assert chosen.get(PAGE).status_code == 200

    TenantDomain.objects.create(
        tenant=migrated_tenant, host=DOMAIN, is_default=True, actor_kind="system"
    )
    invalidate_host_cache()
    on_domain = Client(headers={"host": DOMAIN})
    on_domain.force_login(User.objects.get(email="p.admin@example.test"))
    assert on_domain.get(PAGE).status_code == 200

    unchosen = signed_in_without_tenant("q.admin@example.test", is_platform_admin=True)
    answer = unchosen.get(PAGE)
    assert answer.status_code == 404
    assert _tokenless(answer.content) == _tokenless(unchosen.get("/no-such-address/").content)

    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    put = admin.put(PAGE)
    assert put.status_code == 404
    assert _tokenless(put.content) == _tokenless(admin.get("/no-such-address/").content)


def test_an_administrator_of_another_organisation_is_turned_away(
    migrated_tenant: Any, member_of: Any, make_tenant_schema: Any
) -> None:
    from tenancy.models import Tenant

    other = make_tenant_schema("Other Org")
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    session = admin.session
    session["tenant_number"] = other.number
    session.save()

    assert admin.get(PAGE).status_code in (302, 404)
    admin.post(PAGE, {"attachment_max_mb": "8", "hold_inactivity_minutes": "60"})
    assert Tenant.objects.get(pk=other.pk).hold_inactivity_minutes == 30
    assert _events() == []


def test_a_post_without_its_token_is_refused(migrated_tenant: Any, member_of: Any) -> None:
    _, person, _ = member_of("an.admin@example.test", is_tenant_admin=True)
    client = Client(headers={"host": "127.0.0.1"}, enforce_csrf_checks=True)
    client.force_login(person)
    session = client.session
    session["tenant_number"] = migrated_tenant.number
    session.save()

    refused = client.post(PAGE, {"attachment_max_mb": "8", "hold_inactivity_minutes": "60"})

    assert refused.status_code == 403
    assert _events() == []


def test_the_cap_is_bounded_by_what_the_row_holds(
    migrated_tenant: Any, member_of: Any, settings: Any
) -> None:
    """A platform maximum configured past what the column holds — 2,047 MB — bounds the cap at
    the column's limit instead, refused by the form rather than by the database."""
    settings.UPLOAD_MAX_BYTES = 4096 * MB
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    assert "From 1 to 2047 MB" in html.unescape(admin.get(PAGE).content.decode())
    refused = admin.post(PAGE, {"attachment_max_mb": "2048", "hold_inactivity_minutes": "30"})
    assert refused.status_code == 400
    saved = admin.post(PAGE, {"attachment_max_mb": "2047", "hold_inactivity_minutes": "30"})
    assert saved.status_code == 303
    assert _tenant(migrated_tenant).attachment_max_bytes == 2047 * MB


def test_a_refused_bound_is_named_once(migrated_tenant: Any, member_of: Any, settings: Any) -> None:
    """The bound a refused value breaks is said once, under its field — not again as the help
    line (DL-0511)."""
    settings.UPLOAD_MAX_BYTES = 20 * MB
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    refused = admin.post(PAGE, {"attachment_max_mb": "0", "hold_inactivity_minutes": "30"})

    page = html.unescape(refused.content.decode())
    assert refused.status_code == 400
    assert page.count("From 1 to 20 MB") == 1
    assert re.search(r'<p class="err">[^<]*From 1 to 20 MB', page)


def test_an_applied_change_says_so(migrated_tenant: Any, member_of: Any) -> None:
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    saved = admin.post(PAGE, {"attachment_max_mb": "6", "hold_inactivity_minutes": "30"})

    assert saved.status_code == 303 and saved["Location"] == PAGE + "?applied=1"
    applied = admin.get(saved["Location"]).content.decode()
    assert '<p class="note" role="status">' in applied
    assert 'role="status"' not in admin.get(PAGE).content.decode()


def test_an_error_of_another_kind_keeps_the_bound(
    migrated_tenant: Any, member_of: Any, settings: Any
) -> None:
    """A value that is not a number says so, and the bound stays to read; *Applied* belongs to
    a saved change alone, never to a refused one."""
    settings.UPLOAD_MAX_BYTES = 20 * MB
    admin, _, _ = member_of("an.admin@example.test", is_tenant_admin=True)

    refused = admin.post(
        PAGE + "?applied=1", {"attachment_max_mb": "abc", "hold_inactivity_minutes": "30"}
    )

    page = html.unescape(refused.content.decode())
    assert refused.status_code == 400
    assert "From 1 to 20 MB" in page
    assert 'role="status"' not in page

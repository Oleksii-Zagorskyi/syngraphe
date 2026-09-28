"""The shell: the organisation's name, the navigation a person's rights allow, the frame."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

CATALOGUE = Path(__file__).resolve().parents[2] / "src/shell/locale/uk/LC_MESSAGES/django.po"


def message_ids(catalogue: str) -> list[str]:
    """Every non-empty msgid, continuation lines joined."""
    ids: list[str] = []
    current: list[str] | None = None
    for line in catalogue.splitlines():
        if line.startswith("msgid "):
            current = [line[len("msgid ") :].strip('"')]
        elif line.startswith('"') and current is not None:
            current.append(line.strip('"'))
        elif line.startswith("msgstr") and current is not None:
            joined = "".join(current)
            if joined:
                ids.append(joined)
            current = None
    return ids


def test_single_membership_shows_name_no_switcher(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("an.admin@example.test", tenant=tenant, is_tenant_admin=True)

    response = client.get("/")
    body = response.content.decode()

    assert response.status_code == 200
    assert tenant.name in body
    assert 'class="switcher"' not in body
    assert "<select" not in body
    assert 'href="/administration/"' in body


def test_administration_hidden_from_members(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("a.member@example.test", tenant=tenant)

    body = client.get("/").content.decode()

    assert tenant.name in body
    assert 'href="/administration/"' not in body


def test_platform_admin_sees_both_panes(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("an.operator@example.test", is_platform_admin=True)

    response = client.get("/administration/")
    body = response.content.decode()

    assert response.status_code == 200
    assert 'class="pane platform"' in body
    assert 'class="pane organisation"' in body
    assert 'name="organisation"' in body
    assert tenant.name in body


def test_tenant_admin_sees_the_organisation_pane_only(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("an.admin@example.test", tenant=tenant, is_tenant_admin=True)

    body = client.get("/administration/").content.decode()

    assert 'class="pane organisation"' in body
    assert 'class="pane platform"' not in body
    assert 'name="organisation"' not in body


def test_organisation_selector_writes_the_session(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("an.operator@example.test", is_platform_admin=True)

    response = client.post("/administration/organisation/", {"organisation": tenant.number})

    assert response.status_code == 302
    assert client.session["tenant_number"] == tenant.number
    assert tenant.name in client.get("/").content.decode()


def test_selector_is_closed_to_others_like_a_missing_page(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("a.member@example.test", tenant=tenant)

    missing = client.get("/no-such-page/")
    got = client.get("/administration/organisation/")
    posted = client.post("/administration/organisation/", {"organisation": tenant.number})

    assert got.status_code == posted.status_code == 404
    assert got.content == missing.content or "csrfmiddlewaretoken" in got.content.decode()
    assert client.session.get("tenant_number") == tenant.number  # unchanged by the refusal


def test_a_demoted_administrator_loses_the_chosen_organisation(signed_in: Any, tenant: Any) -> None:
    client, user = signed_in("an.operator@example.test", is_platform_admin=True)
    client.post("/administration/organisation/", {"organisation": tenant.number})
    assert tenant.name in client.get("/").content.decode()

    user.is_platform_admin = False
    user.save()

    assert tenant.name not in client.get("/").content.decode()
    assert "tenant_number" not in client.session


def test_no_selector_on_the_organisations_own_domain(signed_in: Any, tenant: Any) -> None:
    from tenancy.models import TenantDomain

    TenantDomain.objects.create(
        tenant=tenant, host="docs.example.test", is_default=True, actor_kind="system"
    )
    client, _ = signed_in("an.operator@example.test", is_platform_admin=True)
    client.defaults["HTTP_HOST"] = "docs.example.test"

    body = client.get("/administration/").content.decode()
    posted = client.post("/administration/organisation/", {"organisation": tenant.number})

    assert 'class="pane platform"' in body
    assert 'name="organisation"' not in body
    assert posted.status_code == 404


def test_anonymous_is_sent_to_sign_in() -> None:
    from django.test import Client

    response = Client(headers={"host": "127.0.0.1"}).get("/administration/")

    assert response.status_code == 302
    assert response["Location"].startswith("/signin/")


def test_catalogue_covers_the_shell(signed_in: Any, tenant: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "uk"
    client, _ = signed_in("an.operator@example.test", tenant=tenant, is_platform_admin=True)
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))
    assert ids, "the catalogue has message ids"

    for path in ("/", "/administration/", "/no-such-page/"):
        body = client.get(path).content.decode()
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
        assert leaked == [], f"{path} shows message ids verbatim: {leaked}"

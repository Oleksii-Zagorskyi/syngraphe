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

    response = client.get("/administration/", follow=True)
    body = response.content.decode()

    assert response.status_code == 200
    assert tenant.name in body
    assert 'class="switcher"' not in body
    assert "<select" not in body
    assert 'href="/administration/"' in body


def test_administration_hidden_from_members(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("a.member@example.test", tenant=tenant)

    # The shell is on every page, the not-found page included.
    body = client.get("/no-such-page/").content.decode()

    assert tenant.name in body
    assert 'href="/administration/"' not in body


def test_platform_admin_sees_both_panes(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("an.operator@example.test", is_platform_admin=True)

    response = client.get("/administration/", follow=True)
    body = response.content.decode()

    assert response.status_code == 200
    assert 'class="pane platform"' in body
    assert 'class="pane organisation"' in body
    assert 'name="organisation"' in body
    assert tenant.name in body
    assert 'href="/administration/platform/mail/"' in body
    assert 'href="/administration/platform/audit/"' in body
    assert body.index("/platform/mail/") < body.index("/platform/audit/")


def test_tenant_admin_sees_the_organisation_pane_only(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("an.admin@example.test", tenant=tenant, is_tenant_admin=True)

    body = client.get("/administration/", follow=True).content.decode()

    assert 'class="pane organisation"' in body
    assert 'class="pane platform"' not in body
    assert 'name="organisation"' not in body
    assert 'href="/administration/platform/mail/"' not in body
    assert 'href="/administration/tenant/sending-address/"' in body
    assert 'href="/administration/tenant/users/"' in body
    assert 'href="/administration/tenant/document-types/"' in body
    assert 'href="/administration/tenant/folders/"' in body
    assert 'href="/administration/tenant/archive/"' in body
    assert 'href="/administration/tenant/template/"' in body
    assert 'href="/administration/tenant/styles/"' in body
    assert body.index("/tenant/archive/") < body.index("/tenant/styles/")
    # In the order `pages.md` gives: after the document types, before the sending address.
    assert (
        body.index("/tenant/document-types/")
        < body.index("/tenant/template/")
        < body.index("/tenant/sending-address/")
    )
    assert 'href="/administration/tenant/settings/"' in body
    assert body.index("/tenant/template/") < body.index("/tenant/settings/")
    assert body.index("/tenant/settings/") < body.index("/tenant/sending-address/")
    assert 'href="/administration/tenant/access-history/"' in body
    assert body.index("/tenant/styles/") < body.index("/tenant/access-history/")


def test_organisation_selector_writes_the_session(signed_in: Any, tenant: Any) -> None:
    client, _ = signed_in("an.operator@example.test", is_platform_admin=True)

    response = client.post("/administration/organisation/", {"organisation": tenant.number})

    assert response.status_code == 302
    assert client.session["tenant_number"] == tenant.number
    assert tenant.name in client.get("/administration/", follow=True).content.decode()


def test_selector_lists_blocked_organisations_marked(
    signed_in: Any, tenant: Any, settings: Any
) -> None:
    """A blocked organisation is listed and marked, so a platform administrator reaches it from
    the platform host (DL-0376); one being set up is never listed (DL-0291)."""
    from tenancy.models import Tenant

    settings.LANGUAGE_CODE = "en"
    client, _ = signed_in("an.operator@example.test", is_platform_admin=True)
    tenant.state = "blocked"
    tenant.save(update_fields=["state"])
    setting_up = Tenant.objects.create(
        name="Synthetic, being set up", state="migrating", actor_kind="system"
    )

    page = client.get("/administration/", follow=True).content.decode()
    chosen = client.post("/administration/organisation/", {"organisation": tenant.number})
    refused = client.post("/administration/organisation/", {"organisation": setting_up.number})

    option = page.split(f'value="{tenant.number}"', 1)[1].split("</option>", 1)[0]
    assert tenant.name in option and "blocked" in option
    assert setting_up.name not in page
    assert chosen.status_code == 302 and client.session["tenant_number"] == tenant.number
    assert refused.status_code == 404


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
    assert tenant.name in client.get("/administration/", follow=True).content.decode()

    user.is_platform_admin = False
    user.save()

    assert tenant.name not in client.get("/no-such-page/").content.decode()
    assert "tenant_number" not in client.session


def test_no_selector_on_the_organisations_own_domain(signed_in: Any, tenant: Any) -> None:
    from tenancy.models import TenantDomain

    TenantDomain.objects.create(
        tenant=tenant, host="docs.example.test", is_default=True, actor_kind="system"
    )
    client, _ = signed_in("an.operator@example.test", is_platform_admin=True)
    client.defaults["HTTP_HOST"] = "docs.example.test"

    body = client.get("/administration/", follow=True).content.decode()
    posted = client.post("/administration/organisation/", {"organisation": tenant.number})

    assert 'class="pane platform"' in body
    assert 'name="organisation"' not in body
    assert posted.status_code == 404


def test_anonymous_is_sent_to_sign_in() -> None:
    from django.test import Client

    response = Client(headers={"host": "127.0.0.1"}).get("/administration/")

    assert response.status_code == 302
    assert response["Location"].startswith("/signin/")


def test_no_bell_without_a_page_to_open(signed_in: Any, tenant: Any) -> None:
    """The count is drawn only where `/notifications/` answers: never to someone signed out, nor
    to someone signed in with no organisation who is not a platform administrator."""
    from django.test import Client

    anonymous = Client(headers={"host": "127.0.0.1"}).get("/signin/").content.decode()
    client, _ = signed_in("no.organisation@example.test")
    alone = client.get("/help/").content.decode()
    member, _ = signed_in("a.member@example.test", tenant=tenant)

    assert 'class="notifications"' not in anonymous
    assert 'class="notifications"' not in alone
    assert 'class="notifications"' in member.get("/help/").content.decode()


def test_catalogue_covers_the_shell(signed_in: Any, tenant: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "uk"
    client, _ = signed_in("an.operator@example.test", tenant=tenant, is_platform_admin=True)
    ids = message_ids(CATALOGUE.read_text(encoding="utf-8"))
    assert ids, "the catalogue has message ids"

    for path in ("/", "/administration/", "/no-such-page/"):
        # The landing opens its first section, whose page is the one read.
        body = client.get(path, follow=path == "/administration/").content.decode()
        assert path == "/" or "<html" in body, path
        leaked = [i for i in ids if re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", body)]
        assert leaked == [], f"{path} shows message ids verbatim: {leaked}"


def test_an_unmarked_request_gets_no_selector(signed_in: Any, tenant: Any) -> None:
    """A request the tenancy middleware did not mark is treated as an organisation's own domain
    by every consumer, the frame included: nothing to choose."""
    from django.test import RequestFactory

    from shell.views import frame

    _, user = signed_in("p.admin@example.test", tenant=tenant, is_platform_admin=True)
    request = RequestFactory().get("/administration/")
    request.user = user

    assert frame(request)["selector"] is False


def test_health_reports_backup_without_changing_status(
    client: Any, tmp_path: Path, settings: Any
) -> None:
    import json
    from datetime import UTC, datetime, timedelta

    settings.BACKUP_STATE_DIR = tmp_path
    clean = (datetime.now(UTC) - timedelta(minutes=40)).strftime("%Y%m%dT%H%M%SZ")
    (tmp_path / "worker").mkdir()
    (tmp_path / "backup").mkdir()
    (tmp_path / "worker" / "run").write_text(
        json.dumps(
            {
                "newest_marker": {
                    "start": clean,
                    "failures": [{"tenant": 4, "document": 91, "stage": "copy", "since": clean}],
                },
                "newest_clean": clean,
            }
        )
    )
    (tmp_path / "backup" / "wal").write_text(
        json.dumps({"waiting_bytes": 123, "last_archived": "20260929T115900Z"})
    )

    response = client.get("/health/")
    body = response.json()

    assert response.status_code == 200
    assert body["backup"]["repositories_failing"] is True
    assert 2390 <= body["backup"]["clean_marker_age_seconds"] <= 2500
    assert body["backup"]["wal_waiting_bytes"] == 123
    assert body["backup"]["last_archived"] == "2026-09-29T11:59:00Z"
    assert "91" not in response.content.decode() and '"4"' not in response.content.decode()


def test_health_without_backup_state(client: Any, tmp_path: Path, settings: Any) -> None:
    settings.BACKUP_STATE_DIR = tmp_path

    body = client.get("/health/").json()

    assert body["backup"] == {
        "clean_marker_age_seconds": None,
        "repositories_failing": False,
        "last_archived": None,
        "wal_waiting_bytes": None,
    }


def test_the_landing_opens_the_first_section(signed_in: Any, tenant: Any) -> None:
    """`/administration/` opens the first section the person may use (DL-0511): the platform's
    *Hosts* for a platform administrator, the organisation's *Users* for its administrator; to a
    member it is not there."""
    platform, _ = signed_in("an.operator@example.test", is_platform_admin=True)
    admin, _ = signed_in("an.admin@example.test", tenant=tenant, is_tenant_admin=True)
    member, _ = signed_in("a.member@example.test", tenant=tenant)

    to_platform = platform.get("/administration/")
    to_users = admin.get("/administration/")

    assert (to_platform.status_code, to_platform["Location"]) == (
        302,
        "/administration/platform/hosts/",
    )
    assert (to_users.status_code, to_users["Location"]) == (302, "/administration/tenant/users/")
    assert member.get("/administration/").status_code == 404


# The one row (DL-0525): the menu, the bell, the organisation and the person's own name.

ROW = re.compile(r'<header class="shell">(.*?)</header>', re.DOTALL)


def _row(body: str) -> str:
    found = ROW.search(body)
    assert found is not None, "no shell header on the page"
    return found.group(1)


@pytest.mark.parametrize("named", [True, False])
def test_one_row(signed_in: Any, tenant: Any, named: bool) -> None:
    """A member of one organisation without a reservation: the menu, *Help*, the bell, the
    organisation's name plain, and their display name — or their address — linking the account
    page; no *My reservations*, no *Sign out*, no switcher."""
    from identity.models import User

    client, user = signed_in("a.member@example.test", tenant=tenant)
    if named:
        User.objects.filter(pk=user.pk).update(display_name="Синтетична Особа")

    row = _row(client.get("/folder/1/").content.decode())

    shown = "Синтетична Особа" if named else "a.member@example.test"
    link = rf'<a class="account-link" href="/account/"[^>]*>{re.escape(shown)}</a>'
    assert re.search(link, row), row
    assert 'href="/folder/1/"' in row and 'href="/help/"' in row
    assert 'class="notifications"' in row
    assert f'<span class="organisation">{tenant.name}</span>' in row
    assert "/my-reservations/" not in row
    assert 'action="/signout/"' not in row
    assert "<select" not in row and 'class="user"' not in row
    assert 'href="/organisation/"' not in row
    order = [row.index(s) for s in ("/help/", 'class="notifications"', 'class="account-link"')]
    assert order == sorted(order)

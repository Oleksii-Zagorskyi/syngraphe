"""Signing in and out: one answer for every failure, a session of twelve hours (ST-0008, T-14)."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

SIGNIN = "/signin/"
PASSWORD = "Tr4vel-Plan-Ok"


def sign_in(client: Client, email: str, password: str = PASSWORD) -> Any:
    return client.post(SIGNIN, {"email": email, "password": password})


def masked(response: Any, *typed: str) -> str:
    """The body without what differs by construction: the CSRF token and the address typed."""
    body = re.sub(
        r'value="[^"]*" name="csrfmiddlewaretoken"|name="csrfmiddlewaretoken" value="[^"]*"',
        "CSRF",
        response.content.decode(),
    )
    for text in typed:
        body = body.replace(text, "TYPED")
    return body


def test_signin_succeeds(client: Client, person: Any) -> None:
    from tenancy.models import Tenant

    user = person("a.person@example.test", "Example Org")
    other = person("b.person@example.test", "Example Org", "Sandbox")

    response = sign_in(client, "A.Person@example.test")
    second = Client(headers={"host": "127.0.0.1"})
    sign_in(second, other.email)

    user.refresh_from_db()
    assert response.status_code == 302 and response["Location"] == "/"
    assert "sessionid" in response.cookies
    assert user.last_login_at is not None
    assert client.session["_auth_user_id"] == str(user.id)
    assert client.session["tenant_number"] == Tenant.objects.get(name="Example Org").number
    assert second.session["_auth_user_id"] == str(other.id)
    assert "tenant_number" not in second.session


def test_session_lasts_twelve_hours_from_sign_in(client: Client, person: Any) -> None:
    person("a.person@example.test")

    sign_in(client, "a.person@example.test")

    expiry = client.session.get_expiry_date()
    remaining = expiry - timezone.now()
    assert timedelta(hours=11, minutes=59) < remaining <= timedelta(hours=12)

    session = client.session
    session["a later write"] = True
    session.save()
    assert client.session.get_expiry_date() == expiry


def test_failure_indistinguishable_by_address(client: Client, person: Any) -> None:
    person("a.person@example.test")

    known = sign_in(client, "a.person@example.test", "Wr0ng-password!")
    malformed = sign_in(
        Client(headers={"host": "127.0.0.1"}, REMOTE_ADDR="192.0.2.12"), "not-an-address"
    )
    # Each from its own client, so the throttle refuses none of them and each reaches its path.
    unknown = sign_in(
        Client(headers={"host": "127.0.0.1"}, REMOTE_ADDR="192.0.2.11"),
        "nobody@example.test",
        "Wr0ng-password!",
    )
    assert known.status_code == unknown.status_code == 200
    assert [t.name for t in known.templates] == [t.name for t in unknown.templates]
    assert masked(known, "a.person@example.test") == masked(unknown, "nobody@example.test")
    assert masked(known, "a.person@example.test") == masked(malformed, "not-an-address")


def test_signout(client: Client, person: Any) -> None:
    person("a.person@example.test", is_platform_admin=True)
    sign_in(client, "a.person@example.test")

    out = client.post("/signout/")
    after = client.get("/administration/")

    assert out.status_code == 302
    assert "_auth_user_id" not in client.session
    assert after.status_code == 302 and after["Location"].startswith("/signin/")


def test_signout_by_get_answers_not_found(client: Client, person: Any) -> None:
    person("a.person@example.test")
    sign_in(client, "a.person@example.test")

    response = client.get("/signout/")

    assert response.status_code == 404
    assert "_auth_user_id" in client.session


def test_next_followed_only_within_the_site(client: Client, person: Any) -> None:
    person("a.person@example.test")

    inside = client.post(
        f"{SIGNIN}?next=/administration/", {"email": "a.person@example.test", "password": PASSWORD}
    )
    client.post("/signout/")
    outside = client.post(
        f"{SIGNIN}?next=https://elsewhere.example/",
        {"email": "a.person@example.test", "password": PASSWORD},
    )

    assert inside["Location"] == "/administration/"
    assert outside["Location"] == "/"


def test_signin_page_renders(client: Client) -> None:
    response = client.get(SIGNIN)

    assert response.status_code == 200
    assert 'name="email"' in response.content.decode()


def test_no_organisation_chosen_without_one_active_membership(person: Any) -> None:
    from tenancy.models import Tenant

    person("none@example.test")
    person("blocked@example.test", "Sandbox")
    Tenant.objects.filter(name="Sandbox").update(state="blocked")

    for email in ("none@example.test", "blocked@example.test"):
        client = Client(headers={"host": "127.0.0.1"}, REMOTE_ADDR="192.0.2.20")
        response = sign_in(client, email)
        assert response.status_code == 302
        assert "tenant_number" not in client.session


def test_signin_on_an_organisation_domain_chooses_nothing(person: Any) -> None:
    from tenancy.models import Tenant, TenantDomain

    person("a.person@example.test", "Example Org")
    tenant = Tenant.objects.get(name="Example Org")
    TenantDomain.objects.create(tenant=tenant, host="docs.example.test", actor_kind="system")
    client = Client(headers={"host": "docs.example.test"})

    response = sign_in(client, "a.person@example.test")

    assert response.status_code == 302
    assert "tenant_number" not in client.session


def test_signin_needs_the_csrf_token(person: Any) -> None:
    person("a.person@example.test")
    client = Client(headers={"host": "127.0.0.1"}, enforce_csrf_checks=True)

    response = sign_in(client, "a.person@example.test")

    assert response.status_code == 403
    assert "_auth_user_id" not in client.session


def test_signed_in_person_is_sent_on(client: Client, person: Any) -> None:
    person("a.person@example.test")
    sign_in(client, "a.person@example.test")

    response = client.get(SIGNIN)

    assert response.status_code == 302 and response["Location"] == "/"


def test_reset_link_on_the_page(client: Client) -> None:
    body = client.get(SIGNIN).content.decode()

    assert 'href="/reset/"' in body

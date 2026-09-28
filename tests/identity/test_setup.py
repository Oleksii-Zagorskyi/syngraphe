"""The first run: a token printed by the install command, then the first platform administrator."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

SETUP = "/setup/"
PASSWORD = "Tr4vel-Plan-Ok"
NOT_FOUND = "shell/nothing_to_show.html"


def setup_token(*args: str) -> str:
    out = StringIO()
    call_command("setup_token", *args, stdout=out)
    return out.getvalue().strip()


def templates(response: Any) -> list[str]:
    return [t.name for t in response.templates if t.name]


def through_the_token(client: Client, token: str) -> Any:
    return client.post(SETUP, {"token": token})


def create_administrator(client: Client, email: str = "first.admin@example.test") -> Any:
    return client.post(SETUP, {"email": email, "password": PASSWORD, "password_again": PASSWORD})


def test_token_stored_hashed_with_expiry() -> None:
    from identity.models import SetupToken
    from tenancy.models import PlatformHost

    token = setup_token("--host", "docs.example.test")

    row = SetupToken.objects.get()
    assert "\n" not in token and token
    assert row.token_hash != token
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    expected = timezone.now() + timedelta(minutes=60)
    assert abs((row.expires_at - expected).total_seconds()) < 60
    assert PlatformHost.objects.get(host="docs.example.test").is_default
    assert PlatformHost.objects.filter(is_default=True).count() == 1


def test_second_call_replaces_the_row() -> None:
    from identity.models import SetupToken

    first = setup_token()
    second = setup_token()

    assert first != second
    assert SetupToken.objects.get().token_hash == hashlib.sha256(second.encode()).hexdigest()


def test_first_administrator_created(client: Client) -> None:
    from audit.models import AuditEvent
    from identity.models import SetupToken, User

    token = setup_token()

    step_one = through_the_token(client, token)
    assert step_one.status_code == 302
    assert token not in str(dict(client.session.items()))
    done = create_administrator(client)

    admin = User.objects.get(email="first.admin@example.test")
    assert done.status_code == 302 and done["Location"] == "/administration/"
    assert admin.is_platform_admin and not admin.is_superuser
    assert admin.actor_kind == "system" and admin.created_by is None
    assert admin.check_password(PASSWORD)
    assert not SetupToken.objects.exists()
    event = AuditEvent.objects.get(action="platform.first_administrator_created")
    assert event.actor is None and event.actor_kind == "system" and event.object_id == admin.id
    assert client.session["_auth_user_id"] == str(admin.id)


def test_token_is_single_use(client: Client) -> None:
    token = setup_token()
    through_the_token(client, token)
    create_administrator(client)

    again = through_the_token(Client(headers={"host": "127.0.0.1"}), token)

    assert again.status_code == 404
    assert NOT_FOUND in templates(again)


def test_expired_token_is_not_found(client: Client) -> None:
    from identity.models import SetupToken

    token = setup_token()
    SetupToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    page = client.get(SETUP)
    posted = through_the_token(client, token)

    assert page.status_code == 404 and NOT_FOUND in templates(page)
    assert posted.status_code == 404


def test_page_closed_once_an_administrator_exists(client: Client) -> None:
    from identity.models import SetupToken, User

    token = setup_token()
    User.objects.create_user("an.admin@example.test", PASSWORD, is_platform_admin=True)
    out, err = StringIO(), StringIO()

    with pytest.raises(SystemExit) as exit_:
        call_command("setup_token", stdout=out, stderr=err)
    page = client.get(SETUP)
    posted = through_the_token(client, token)

    assert exit_.value.code == 1
    assert out.getvalue() == ""
    assert err.getvalue().strip() == "A platform administrator already exists."
    assert SetupToken.objects.count() == 1
    assert page.status_code == 404 and NOT_FOUND in templates(page)
    assert posted.status_code == 404


def test_wrong_token_indistinguishable(client: Client) -> None:
    setup_token()

    wrong = through_the_token(client, "not-the-token")
    missing = client.get("/no-such-page/")

    assert wrong.status_code == missing.status_code == 404
    assert templates(wrong) == templates(missing)
    assert "setup_token_hash" not in client.session


def test_administrator_step_needs_the_token_first(client: Client) -> None:
    from identity.models import User

    setup_token()

    posted = create_administrator(client)

    assert posted.status_code == 404 and NOT_FOUND in templates(posted)
    assert not User.objects.exists()


def test_refused_password_keeps_the_token(client: Client) -> None:
    from identity.models import SetupToken, User

    token = setup_token()
    through_the_token(client, token)

    refused = client.post(
        SETUP,
        {"email": "first.admin@example.test", "password": "short", "password_again": "short"},
    )
    differ = client.post(
        SETUP,
        {"email": "first.admin@example.test", "password": PASSWORD, "password_again": "x"},
    )

    assert refused.status_code == 200 and refused.context["form"].errors["password"]
    assert differ.status_code == 200 and differ.context["form"].errors["password_again"]
    assert 'value="short"' not in refused.content.decode()
    assert not User.objects.exists()
    assert SetupToken.objects.exists()


def test_address_already_in_use_refused(client: Client) -> None:
    from identity.models import User

    User.objects.create_superuser("an.operator@example.test", PASSWORD)
    token = setup_token()
    through_the_token(client, token)

    refused = create_administrator(client, "An.Operator@example.test")

    assert refused.status_code == 200 and refused.context["form"].errors["email"]
    assert not User.objects.filter(is_platform_admin=True).exists()


def test_other_methods_answer_not_found(client: Client) -> None:
    setup_token()

    response = client.put(SETUP)

    assert response.status_code == 404 and NOT_FOUND in templates(response)


def test_wrong_token_headers_match_a_missing_page(client: Client) -> None:
    setup_token()

    wrong = through_the_token(client, "not-the-token")
    missing = client.get("/no-such-page/")

    def headers(response: Any) -> dict[str, str]:
        return {k: v for k, v in response.headers.items() if k not in ("X-Request-Id", "Expires")}

    assert headers(wrong) == headers(missing)


def test_session_key_changes_with_the_token(client: Client) -> None:
    token = setup_token()
    client.get(SETUP)
    client.session.save()
    before = client.session.session_key

    through_the_token(client, token)

    assert client.session.session_key != before


def test_page_refused_on_an_organisation_domain() -> None:
    from tenancy.models import Tenant, TenantDomain

    tenant = Tenant.objects.create(name="Example Org", state="active", actor_kind="system")
    TenantDomain.objects.create(tenant=tenant, host="docs.example.test", actor_kind="system")
    setup_token()

    page = Client(headers={"host": "docs.example.test"}).get(SETUP)

    assert page.status_code == 404 and NOT_FOUND in templates(page)


def test_every_refusal_of_the_administrator_form_at_once(client: Client) -> None:
    token = setup_token()
    through_the_token(client, token)

    similar = create_administrator_with(client, "first.admin@example.test", "First.admin@example1")
    bad_address = create_administrator_with(client, "not-an-address", PASSWORD)
    both = client.post(
        SETUP, {"email": "first.admin@example.test", "password": "short", "password_again": "x"}
    )

    assert "password_too_similar" in codes(similar, "password")
    assert codes(bad_address, "email") and not codes(bad_address, "password")
    assert codes(both, "password") and codes(both, "password_again")


def create_administrator_with(client: Client, email: str, password: str) -> Any:
    return client.post(SETUP, {"email": email, "password": password, "password_again": password})


def codes(response: Any, field: str) -> list[str]:
    return [e.code or "" for e in response.context["form"].errors.as_data().get(field, [])]


def test_host_change_audited_once() -> None:
    from audit.models import AuditEvent

    setup_token("--host", "docs.example.test")
    setup_token("--host", "docs.example.test")

    assert AuditEvent.objects.filter(action="host.added").count() == 1
    event = AuditEvent.objects.get(action="host.made_default")
    assert event.actor is None
    assert event.before == {"default": "127.0.0.1"}
    assert event.after == {"host": "docs.example.test", "belongs_to": "platform", "default": True}


def test_existing_host_made_default() -> None:
    from tenancy.models import PlatformHost

    setup_token("--host", "LOCALHOST")

    assert PlatformHost.objects.get(is_default=True).host == "localhost"
    assert PlatformHost.objects.filter(host="localhost").count() == 1


@pytest.mark.parametrize("host", ["http://docs.example.test", "docs example", "docs.example:99999"])
def test_malformed_host_refused(host: str) -> None:
    from django.core.management.base import CommandError

    from identity.models import SetupToken

    with pytest.raises(CommandError):
        setup_token("--host", host)
    assert not SetupToken.objects.exists()


def test_organisation_domain_refused_as_platform_host() -> None:
    from django.core.management.base import CommandError

    from tenancy.models import Tenant, TenantDomain

    tenant = Tenant.objects.create(name="Example Org", state="active", actor_kind="system")
    TenantDomain.objects.create(tenant=tenant, host="docs.example.test", actor_kind="system")

    with pytest.raises(CommandError):
        setup_token("--host", "docs.example.test")

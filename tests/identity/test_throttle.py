"""Throttling with a growing delay, never a lock: by client, and by address typed and client
together (DL-0116, DL-0289)."""

from __future__ import annotations

import ipaddress
import re
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

SIGNIN = "/signin/"
PASSWORD = "Tr4vel-Plan-Ok"
WRONG = "Wr0ng-password!"
OWNER = "a.person@example.test"


def fail(client: Client, email: str = OWNER, **extra: Any) -> Any:
    return client.post(SIGNIN, {"email": email, "password": WRONG}, **extra)


def pair(email: str, client: str = "127.0.0.1") -> str:
    from identity.throttle import pair_key

    return pair_key(email, client)


def row(key: str) -> Any:
    from identity.models import SignInAttempt

    return SignInAttempt.objects.get(key=key)


def seconds_until(moment: Any) -> float:
    return (moment - timezone.now()).total_seconds()


def masked(response: Any) -> str:
    token = r'name="csrfmiddlewaretoken" value="[^"]*"'
    return re.sub(token, "CSRF", response.content.decode())


def test_delay_doubles_per_address(client: Client, person: Any) -> None:
    person(OWNER)
    first = fail(client)
    fail(client)
    fail(client)

    fourth = client.post(SIGNIN, {"email": OWNER, "password": PASSWORD})

    assert fourth.status_code == first.status_code == 200
    assert "_auth_user_id" not in client.session
    assert masked(fourth) == masked(first)
    assert row(pair(OWNER)).consecutive_failures == 4
    assert 6 < seconds_until(row(pair(OWNER)).next_allowed_at) <= 8


def test_others_failures_never_delay_the_owner(person: Any) -> None:
    person(OWNER)
    stranger = Client(headers={"host": "127.0.0.1"}, REMOTE_ADDR="192.0.2.44")
    for _ in range(12):
        fail(stranger)

    owner = Client(headers={"host": "127.0.0.1"}, REMOTE_ADDR="198.51.100.20")
    response = owner.post(SIGNIN, {"email": OWNER, "password": PASSWORD})

    assert response.status_code == 302
    assert "_auth_user_id" in owner.session


def test_delay_ceiling(client: Client) -> None:
    for _ in range(12):
        fail(client, "nobody@example.test")

    fail(client, "nobody@example.test")

    assert 58 < seconds_until(row(pair("nobody@example.test")).next_allowed_at) <= 60
    assert 58 < seconds_until(row("127.0.0.1").next_allowed_at) <= 60


def test_success_resets(client: Client, person: Any) -> None:
    from identity.models import SignInAttempt

    person(OWNER)
    fail(client)
    fail(client)
    SignInAttempt.objects.update(next_allowed_at=timezone.now() - timedelta(seconds=1))

    ok = client.post(SIGNIN, {"email": OWNER, "password": PASSWORD})

    assert ok.status_code == 302
    assert row(pair(OWNER)).consecutive_failures == 0
    assert row(pair(OWNER)).next_allowed_at is None
    # The client's own count is not the owner's to clear (DL-0289).
    assert row("127.0.0.1").consecutive_failures == 2


def test_client_address_from_trusted_proxy_only(client: Client, settings: Any) -> None:
    from identity.models import SignInAttempt

    settings.TRUSTED_PROXIES = (ipaddress.ip_network("10.0.0.1/32"),)

    fail(client, REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.9, 203.0.113.7")
    fail(
        client,
        "b.person@example.test",
        REMOTE_ADDR="192.0.2.5",
        HTTP_X_FORWARDED_FOR="203.0.113.99",
    )

    keys = set(SignInAttempt.objects.filter(key_kind="address").values_list("key", flat=True))
    assert keys == {"203.0.113.7", "192.0.2.5"}


def test_ipv6_client_counts_by_its_64(client: Client) -> None:
    from identity.models import SignInAttempt

    fail(client, REMOTE_ADDR="2001:db8:1:2::10")
    fail(client, "b.person@example.test", REMOTE_ADDR="2001:db8:1:2:ffff::1")

    assert list(SignInAttempt.objects.filter(key_kind="address").values_list("key", flat=True)) == [
        "2001:db8:1:2::/64"
    ]
    assert row("2001:db8:1:2::/64").consecutive_failures == 2


def test_the_address_typed_is_never_stored(client: Client) -> None:
    from identity.models import SignInAttempt

    fail(client)

    assert not any(OWNER in key for key in SignInAttempt.objects.values_list("key", flat=True))


def test_an_address_that_is_not_one_counts_by_client_only(client: Client) -> None:
    from identity.models import SignInAttempt

    fail(client, "10.0.0.7")
    fail(client, "x" * 300 + "@example.test")

    assert list(SignInAttempt.objects.values_list("key_kind", flat=True)) == ["address"]


def test_sweep_removes_rows_older_than_a_day(client: Client) -> None:
    from identity.models import SignInAttempt
    from identity.tasks import sweep_sign_in_attempts

    fail(client, "old@example.test")
    SignInAttempt.objects.filter(key=pair("old@example.test")).update(
        last_failure_at=timezone.now() - timedelta(days=1, seconds=1)
    )

    removed = sweep_sign_in_attempts()

    assert removed == 1
    assert set(SignInAttempt.objects.values_list("key", flat=True)) == {"127.0.0.1"}


def test_ipv4_mapped_client_counts_as_itself(client: Client) -> None:
    from identity.models import SignInAttempt

    fail(client, REMOTE_ADDR="::ffff:192.0.2.7")

    assert list(SignInAttempt.objects.filter(key_kind="address").values_list("key", flat=True)) == [
        "192.0.2.7"
    ]

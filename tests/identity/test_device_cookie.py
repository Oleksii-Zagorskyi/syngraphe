"""A browser that has signed in before gets past its shared address's delay (DL-0293)."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

SIGNIN = "/signin/"
PASSWORD = "Tr4vel-Plan-Ok"
WRONG = "Wr0ng-password!"
OFFICE = "198.51.100.40"


def browser() -> Client:
    return Client(headers={"host": "127.0.0.1"}, REMOTE_ADDR=OFFICE)


def sign_in(client: Client, email: str, password: str = PASSWORD) -> Any:
    return client.post(SIGNIN, {"email": email, "password": password})


def signed_in_before(email: str) -> Client:
    """A browser that signed in once, then signed out: it keeps its device cookie."""
    client = browser()
    assert sign_in(client, email).status_code == 302
    client.post("/signout/")
    return client


def lock_the_address() -> None:
    neighbour = browser()
    for _ in range(12):
        sign_in(neighbour, "someone.else@example.test", WRONG)


def test_a_browser_that_signed_in_before_passes_its_shared_address(person: Any) -> None:
    person("a.person@example.test")
    owner = signed_in_before("a.person@example.test")
    lock_the_address()

    response = sign_in(owner, "a.person@example.test")

    assert response.status_code == 302
    assert "_auth_user_id" in owner.session


def test_without_the_cookie_the_address_delay_holds(person: Any) -> None:
    person("a.person@example.test")
    lock_the_address()

    response = sign_in(browser(), "a.person@example.test")

    assert response.status_code == 200


def test_the_cookie_speaks_for_its_own_address_only(person: Any) -> None:
    person("a.person@example.test")
    person("b.person@example.test")
    owner = signed_in_before("a.person@example.test")
    lock_the_address()

    response = sign_in(owner, "b.person@example.test")

    assert response.status_code == 200


def test_an_altered_cookie_counts_for_nothing(person: Any) -> None:
    from identity.throttle import device_cookie_name

    person("a.person@example.test")
    owner = signed_in_before("a.person@example.test")
    owner.cookies[device_cookie_name()] = owner.cookies[device_cookie_name()].value + "x"
    lock_the_address()

    assert sign_in(owner, "a.person@example.test").status_code == 200


def test_failures_with_the_cookie_delay_the_cookie(person: Any) -> None:
    person("a.person@example.test")
    owner = signed_in_before("a.person@example.test")
    sign_in(owner, "a.person@example.test", WRONG)
    sign_in(owner, "a.person@example.test", WRONG)

    response = sign_in(owner, "a.person@example.test")

    assert response.status_code == 200


def test_the_cookie_is_kept_from_scripts_and_names_no_address(person: Any) -> None:
    from identity.throttle import device_cookie_name

    person("a.person@example.test")
    client = browser()

    response = sign_in(client, "a.person@example.test")

    cookie = response.cookies[device_cookie_name()]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"
    assert int(cookie["max-age"]) == 90 * 24 * 3600
    assert "a.person" not in cookie.value


def test_refusals_while_the_device_waits_keep_charging_it(person: Any) -> None:
    from identity.models import SignInAttempt

    person("a.person@example.test")
    owner = signed_in_before("a.person@example.test")
    for _ in range(3):
        sign_in(owner, "a.person@example.test", WRONG)

    device = SignInAttempt.objects.get(key_kind="device")
    assert device.consecutive_failures == 3


def test_a_password_change_retires_the_cookie(person: Any) -> None:
    user = person("a.person@example.test")
    owner = signed_in_before("a.person@example.test")
    user.set_password("An0ther-password!")
    user.save()
    lock_the_address()

    assert sign_in(owner, "a.person@example.test", "An0ther-password!").status_code == 200


def test_signing_in_again_keeps_one_device(person: Any) -> None:
    from identity.models import SignInAttempt

    person("a.person@example.test")
    owner = signed_in_before("a.person@example.test")
    sign_in(owner, "a.person@example.test", WRONG)
    owner.post("/signout/")
    for _ in range(2):
        SignInAttempt.objects.update(next_allowed_at=None)
        sign_in(owner, "a.person@example.test")
        owner.post("/signout/")

    assert SignInAttempt.objects.filter(key_kind="device").count() == 1


def test_an_expired_cookie_falls_back(person: Any, monkeypatch: Any) -> None:
    from identity import throttle

    person("a.person@example.test")
    owner = signed_in_before("a.person@example.test")
    monkeypatch.setattr(throttle, "DEVICE_SECONDS", -1)
    lock_the_address()

    assert sign_in(owner, "a.person@example.test").status_code == 200


def test_a_failure_looks_the_same_with_or_without_a_cookie(person: Any) -> None:
    import re

    person("a.person@example.test")
    owner = signed_in_before("a.person@example.test")
    stranger = Client(headers={"host": "127.0.0.1"}, REMOTE_ADDR="192.0.2.90")

    with_cookie = sign_in(owner, "a.person@example.test", WRONG)
    without = sign_in(stranger, "a.person@example.test", WRONG)

    def body(response: Any) -> str:
        return re.sub(r'name="csrfmiddlewaretoken" value="[^"]*"', "", response.content.decode())

    assert with_cookie.status_code == without.status_code == 200
    assert body(with_cookie) == body(without)
    # A failure issues no device cookie, with one presented or not.
    from identity.throttle import device_cookie_name

    assert device_cookie_name() not in with_cookie.cookies
    assert device_cookie_name() not in without.cookies

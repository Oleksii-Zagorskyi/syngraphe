"""A person's own account page (DL-0499, DL-0500): `/account/`, reached from the user menu as
*My account*, shows the address read-only, the interface's language with *Apply*, and, apart at
its foot, *Block my account…* — disabled with its reason for the last platform administrator
(DL-0315), absent for a person already blocked.

People are synthetic examples at `@example.test`."""

from __future__ import annotations

import re
from typing import Any

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db,
    pytest.mark.usefixtures("in_english"),
]

ACCOUNT = "/account/"


def _language_rows(user: Any) -> list[str]:
    from identity.models import UserPreference

    return list(
        UserPreference.objects.filter(user=user, key="language").values_list("value", flat=True)
    )


def test_the_page_shows_the_address_the_language_and_the_block(member_of: Any) -> None:
    client, user, _ = member_of("a.member@example.test")

    page = client.get(ACCOUNT)

    assert page.status_code == 200
    body = page.content.decode()
    assert "My account" in body
    assert "a.member@example.test" in body
    assert not re.search(r'<input[^>]*value="a\.member@example\.test"', body)
    select = re.search(r'<select[^>]*name="language"[^>]*>(.*?)</select>', body, re.S)
    assert select is not None
    assert re.search(r'<option value="en" selected[ >]', select.group(1))
    assert 'value="uk"' in select.group(1)
    assert "Apply" in body
    assert body.index('href="/account/block/"') > body.index('name="language"')
    assert "Block my account…" in body
    assert "Applied" not in body


def test_apply_writes_the_preference(member_of: Any) -> None:
    client, user, _ = member_of("a.member@example.test")
    _, other, _ = member_of("another.member@example.test")

    answer = client.post(ACCOUNT, {"language": "uk"})

    assert answer.status_code == 303
    assert answer["Location"] == "/account/?applied=1"
    assert _language_rows(user) == ["uk"]
    assert _language_rows(other) == []
    applied = client.get(answer["Location"]).content.decode()
    assert '<html lang="uk">' in applied
    assert 'role="status"' in applied
    back = client.post(ACCOUNT, {"language": "en"})
    assert back.status_code == 303 and _language_rows(user) == ["en"]
    assert '<html lang="en">' in client.get(ACCOUNT).content.decode()


def test_a_stray_value_is_refused(member_of: Any) -> None:
    client, user, _ = member_of("a.member@example.test")

    answer = client.post(ACCOUNT, {"language": "xx"})

    assert answer.status_code == 400
    assert _language_rows(user) == []
    body = answer.content.decode()
    assert 'name="language"' in body
    assert re.search(
        r'<p class="err" role="alert">Choose one of the interface languages offered\.</p>', body
    )
    assert 'role="alert"' not in client.get(ACCOUNT).content.decode()


def test_other_methods_answer_as_missing(member_of: Any) -> None:
    client, _, _ = member_of("a.member@example.test")

    assert client.put(ACCOUNT).status_code == 404


def test_the_last_platform_administrator_cannot_block(migrated_tenant: Any) -> None:
    from django.test import Client

    from identity.models import User

    admin = User.objects.create_user(
        "p.admin@example.test", "test-only-not-a-password", is_platform_admin=True
    )
    client = Client(headers={"host": "127.0.0.1"})
    client.force_login(admin)

    body = client.get(ACCOUNT).content.decode()

    assert 'aria-disabled="true"' in body
    assert "The last platform administrator cannot block their own account." in body
    assert 'href="/account/block/"' not in body


def test_a_blocked_person_sees_no_block(member_of: Any) -> None:
    from identity.models import User

    client, user, _ = member_of("a.member@example.test")
    User.objects.filter(pk=user.pk).update(self_blocked=True)

    page = client.get(ACCOUNT)

    assert page.status_code == 200
    body = page.content.decode()
    assert "Block my account" not in body
    assert 'name="language"' in body

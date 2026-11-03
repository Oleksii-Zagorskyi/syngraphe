"""Each person's interface language (DL-0498, DL-0501): a `language` preference, read by
`language_of`, activated on every request by a middleware after authentication and deactivated on
the way out; a person who has not chosen sees the installation's default.

People are synthetic examples at `@example.test`."""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponse
from django.test import Client
from django.utils import translation

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

LANG = re.compile(r'<html lang="([a-z-]*)"')


def _prefer(user: Any, value: str) -> None:
    """The row as the account page writes it."""
    from identity.views.preferences import _keep

    _keep(user, "language", value)


def _lang(page: bytes) -> str:
    found = LANG.search(page.decode())
    assert found is not None
    return found.group(1)


def test_no_preference_is_the_installations_default(member_of: Any, settings: Any) -> None:
    from identity.language import language_of

    settings.LANGUAGE_CODE = "en"
    _, user, _ = member_of("no.choice@example.test")

    assert language_of(user) == "en"
    assert language_of(None) == "en"
    assert language_of(AnonymousUser()) == "en"


def test_the_preference_is_read(member_of: Any, settings: Any) -> None:
    from identity.language import language_of

    settings.LANGUAGE_CODE = "uk"
    _, english, _ = member_of("english.reader@example.test")
    _, ukrainian, _ = member_of("ukrainian.reader@example.test")
    _, stray, _ = member_of("stray.value@example.test")
    _prefer(english, "en")
    _prefer(ukrainian, "uk")
    _prefer(stray, "xx")

    assert (language_of(english), language_of(ukrainian), language_of(stray)) == ("en", "uk", "uk")


def test_the_middleware_follows_tenancy(settings: Any) -> None:
    middleware = list(settings.MIDDLEWARE)

    assert middleware.index("identity.middleware.LanguageMiddleware") == (
        middleware.index("tenancy.middleware.TenancyMiddleware") + 1
    )
    # After authentication: the request's person is known when the language is chosen.
    assert middleware.index("identity.middleware.LanguageMiddleware") > middleware.index(
        "django.contrib.auth.middleware.AuthenticationMiddleware"
    )


def test_each_request_takes_its_persons_language(member_of: Any, settings: Any) -> None:
    settings.LANGUAGE_CODE = "uk"
    client, english, _ = member_of("english.reader@example.test")
    _prefer(english, "en")

    page = client.get("/folder/1/").content
    assert _lang(page) == "en"
    assert "All documents" in page.decode()

    other, _, _ = member_of("no.choice@example.test")
    assert _lang(other.get("/folder/1/").content) == "uk"
    anonymous = Client(headers={"host": "127.0.0.1"})
    assert _lang(anonymous.get("/signin/").content) == "uk"


def test_the_language_is_deactivated_on_the_way_out(member_of: Any, settings: Any) -> None:
    """The known negative: without the deactivation the thread keeps the last person's language,
    which a response answered ahead of the middleware on that thread would carry."""
    from identity.middleware import LanguageMiddleware

    settings.LANGUAGE_CODE = "uk"
    _, english, _ = member_of("english.reader@example.test")
    _prefer(english, "en")
    request = HttpRequest()
    request.user = english
    seen: list[str] = []

    def answer(request: HttpRequest) -> HttpResponse:
        seen.append(translation.get_language())
        return HttpResponse("")

    def fails(request: HttpRequest) -> HttpResponse:
        raise RuntimeError("a synthetic failure")

    translation.activate("uk")
    LanguageMiddleware(answer)(request)
    assert seen == ["en"]
    assert request.LANGUAGE_CODE == "en"  # type: ignore[attr-defined]
    assert translation.get_language() == "uk"

    with pytest.raises(RuntimeError):
        LanguageMiddleware(fails)(request)
    assert translation.get_language() == "uk"


def test_the_health_probe_reads_no_session() -> None:
    """`/health/` answers before the tables can be trusted (DL-0295): the language is not looked
    up there, so the person — and the session behind them — is never read."""
    from identity.middleware import LanguageMiddleware

    class Unreadable:
        @property
        def is_authenticated(self) -> bool:
            raise RuntimeError("the session table cannot be read")

    request = HttpRequest()
    request.path = "/health/"
    request.user = Unreadable()  # type: ignore[assignment]

    answer = LanguageMiddleware(lambda request: HttpResponse("ok"))(request)

    assert answer.content == b"ok"

"""People with memberships in organisations, for the sign-in tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

PASSWORD = "Tr4vel-Plan-Ok"


@pytest.fixture
def person() -> Callable[..., Any]:
    """A user with an active membership in each named organisation, created as needed."""

    def make(email: str, *organisations: str, **fields: Any) -> Any:
        from identity.models import Membership, User
        from tenancy.models import Tenant

        user = User.objects.create_user(email, PASSWORD, **fields)
        for name in organisations:
            tenant, _ = Tenant.objects.get_or_create(
                name=name, defaults={"state": "active", "actor_kind": "system"}
            )
            Membership.objects.create(tenant=tenant, user=user, actor_kind="system")
        return user

    return make


# Values the masking replaces in a page or an email before two of them are compared (ASR-17):
# a link's token, Django's per-render CSRF value, and headers that differ by construction.
_TOKEN_LINK = r"/(invitation|reset)/[A-Za-z0-9_-]{43}/"
_CSRF = r'value="[^"]*" name="csrfmiddlewaretoken"|name="csrfmiddlewaretoken" value="[^"]*"'
_DROPPED_HEADERS = ("X-Request-Id", "Expires", "Set-Cookie")


@pytest.fixture
def in_english(settings: Any) -> None:
    """Pages and emails in the message ids' own language, so a test reads the sentences named."""
    settings.LANGUAGE_CODE = "en"


@pytest.fixture
def masked_text() -> Callable[..., str]:
    """A text with the addresses under test, the CSRF value and every link's token replaced."""
    import re

    def mask(text: str, *addresses: str) -> str:
        text = re.sub(_CSRF, "CSRF", text)
        text = re.sub(_TOKEN_LINK, r"/\1/TOKEN/", text)
        for address in addresses:
            text = text.replace(address, "ADDRESS")
        return text

    return mask


@pytest.fixture
def masked(masked_text: Callable[..., str]) -> Callable[..., tuple[int, dict[str, str], str]]:
    """A response as two-address tests compare it: its status, its headers without those that
    differ by construction — the names of the cookies it sets kept, their values not — and its
    body masked."""

    def mask(response: Any, *addresses: str) -> tuple[int, dict[str, str], str]:
        headers = {k: v for k, v in response.headers.items() if k not in _DROPPED_HEADERS}
        headers["cookies set"] = " ".join(sorted(response.cookies))
        body = masked_text(response.content.decode(), *addresses)
        return response.status_code, headers, body

    return mask


@pytest.fixture
def sending_address() -> Callable[..., Any]:
    """A sending address in an organisation's schema, or the platform's for `None`."""

    def make(number: int | None, address: str = "mail@example.test") -> Any:
        from mail.models import MailSender
        from tenancy.schemas import schema_context

        with schema_context(number):
            return MailSender.objects.create(
                host="127.0.0.1",
                port=2525,
                address=address,
                display_name="Synthetic",
                username="",
                password_encrypted=b"",
                security="none",
            )

    return make


@pytest.fixture
def no_sending_address() -> Callable[..., None]:
    """No sending address in the named organisations' schemas nor in the platform's."""

    def clear(*numbers: int) -> None:
        from mail.models import MailSender
        from tenancy.schemas import schema_context

        for number in (None, *numbers):
            with schema_context(number):
                MailSender.objects.all().delete()

    return clear


@pytest.fixture
def outbox() -> Callable[[int | None], list[Any]]:
    """The outbox rows of an organisation's schema, or the shared ones for `None`, oldest first."""

    def rows(number: int | None) -> list[Any]:
        from mail.models import EmailOutbox
        from tenancy.schemas import schema_context

        with schema_context(number):
            return list(EmailOutbox.objects.order_by("created_at", "id"))

    return rows


@pytest.fixture
def invited(sending_address: Callable[..., Any]) -> Callable[..., str]:
    """A person invited into `tenant` through the service, a sending address added to its schema
    when it has none; the token the invitation's email carries."""

    def make(tenant: Any, email: str, *, by: Any, groups: tuple[Any, ...] = ()) -> str:
        import re

        from identity.invitations import invite
        from mail.models import EmailOutbox, MailSender
        from tenancy.schemas import schema_context

        with schema_context(tenant.number):
            has_sender = MailSender.objects.exists()
        if not has_sender:
            sending_address(tenant.number)
        with schema_context(tenant.number):
            invite(tenant, email, list(groups), by=by)
            body = EmailOutbox.objects.filter(recipient=email).latest("created_at").body
        [token] = re.findall(r"/invitation/([A-Za-z0-9_-]{43})/", body)
        return str(token)

    return make

"""The platform's sending address (DL-0202, DL-0203, DL-0368, DL-0371): saved by a platform
administrator on the platform's host, its password stored only encrypted and never shown, every
value checked, every change audited without the password; *Send a test email* run by the worker,
its three steps kept on the row; the platform's row read whatever organisation the session names.

People, addresses and passwords are synthetic examples; every address ends in `@example.test`.
"""

from __future__ import annotations

import re
import socket
from collections.abc import Iterator
from typing import Any

import pytest
from django.test import Client

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/platform/mail/"
PASSWORD = "synthetic-password-typed-once"


def values(**changed: Any) -> dict[str, Any]:
    form = {
        "action": "save",
        "host": "smtp.example.test",
        "port": "587",
        "address": "platform.sender@example.test",
        "display_name": "Synthetic platform",
        "username": "platform.sender@example.test",
        "password": PASSWORD,
        "security": "starttls",
    }
    form.update(changed)
    return form


@pytest.fixture
def operator(member_of: Any) -> tuple[Client, Any]:
    """A platform administrator on the platform's host, an organisation chosen in the session."""
    client, user, _ = member_of("o.synthetic@example.test", is_platform_admin=True)
    return client, user


@pytest.fixture
def queued_tests(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The test emails a page asks the worker for, recorded rather than sent."""
    queued: list[Any] = []
    monkeypatch.setattr("mail.tasks.test_sender.delay", lambda *args: queued.append(args))
    return queued


def test_save_stores_the_password_encrypted_and_audits_without_it(operator: Any) -> None:
    from audit.models import AuditEvent
    from mail import secrets
    from mail.models import MailSender

    client, user = operator
    response = client.post(PAGE, values())
    assert response.status_code == 302

    with schema_context(None):
        [row] = MailSender.objects.all()
    assert PASSWORD.encode() not in bytes(row.password_encrypted)
    assert secrets.decrypt(bytes(row.password_encrypted)) == PASSWORD
    assert (row.host, row.port, row.address, row.display_name, row.security) == (
        "smtp.example.test",
        587,
        "platform.sender@example.test",
        "Synthetic platform",
        "starttls",
    )
    [event] = AuditEvent.objects.filter(action="mail.sender_saved")
    assert event.actor_id == user.pk and event.tenant_id is None
    assert event.after == {
        "host": "smtp.example.test",
        "address": "platform.sender@example.test",
        "security": "starttls",
        "password_change": "replaced",
    }
    assert PASSWORD not in str(event.before) + str(event.after)


def test_reopened_form_never_shows_the_password(operator: Any) -> None:
    from mail import secrets
    from mail.models import MailSender

    client, _ = operator
    client.post(PAGE, values())
    page = client.get(PAGE).content.decode()

    password = re.search(r'<input[^>]*name="password"[^>]*>', page)
    assert password is not None and "value=" not in password.group(0)
    assert PASSWORD not in page
    assert "data-password-stored" in page
    assert 'value="smtp.example.test"' in page and 'value="587"' in page

    # Saved again with the password left empty, the stored one stays.
    client.post(PAGE, values(password="", display_name="Another name"))
    with schema_context(None):
        row = MailSender.objects.get()
    assert row.display_name == "Another name"
    assert secrets.decrypt(bytes(row.password_encrypted)) == PASSWORD


def test_reads_the_platform_row_whatever_tenant_the_session_names(
    operator: Any, migrated_tenant: Any, sender: Any
) -> None:
    client, _ = operator
    sender(migrated_tenant.number, host="tenant.example.test")
    sender(None, host="platform.example.test")

    page = client.get(PAGE).content.decode()
    assert 'value="platform.example.test"' in page
    assert "tenant.example.test" not in page


def test_a_test_email_reports_three_steps(
    operator: Any, sender: Any, sink: Any, queued_tests: list[Any], settings: Any
) -> None:
    from mail.models import MailSender
    from mail.tasks import test_sender

    settings.LANGUAGE_CODE = "en"
    client, _ = operator
    saved = sender(None)
    form = {
        "host": saved.host,
        "port": str(saved.port),
        "address": saved.address,
        "display_name": saved.display_name,
        "username": "",
        "password": "",
        "security": "none",
    }

    assert client.post(f"{PAGE}test/", form).status_code == 302
    assert queued_tests == [(None,)]
    test_sender(None)

    with schema_context(None):
        row = MailSender.objects.get()
    assert row.last_test_at is not None
    page = client.get(PAGE).content.decode()
    assert 'data-step="connected" data-outcome="done"' in page
    assert 'data-step="signed_in" data-outcome="not_needed"' in page
    assert 'data-step="sent" data-outcome="done"' in page
    [received] = sink.messages
    assert received.mail_from == saved.address and received.rcpt_tos == [saved.address]
    assert received.message["Subject"] == "Test message"
    assert saved.host in received.body


@pytest.fixture
def refusing_sign_in() -> Iterator[int]:
    """An SMTP server on a free local port that offers sign-in and refuses every attempt."""
    from aiosmtpd.controller import Controller
    from aiosmtpd.smtp import AuthResult

    class Handler:
        async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:
            return "250 OK"

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    controller = Controller(
        Handler(),
        hostname="127.0.0.1",
        port=port,
        authenticator=lambda *args: AuthResult(success=False),
        auth_require_tls=False,
    )
    controller.start()
    try:
        yield port
    finally:
        controller.stop()


def test_a_failing_step_is_named(operator: Any, sender: Any, refusing_sign_in: int) -> None:
    from mail import secrets
    from mail.models import MailSender
    from mail.tasks import test_sender

    client, _ = operator
    sender(
        None,
        port=refusing_sign_in,
        username="u.synthetic@example.test",
        password_encrypted=secrets.encrypt(PASSWORD),
    )
    test_sender(None)

    with schema_context(None):
        row = MailSender.objects.get()
    assert PASSWORD not in row.last_test_result
    page = client.get(PAGE).content.decode()
    assert 'data-step="connected" data-outcome="done"' in page
    assert 'data-step="signed_in" data-outcome="failed"' in page
    # The refusal's reason is shown with the failed step, in the page's words.
    failed = re.search(r'<li data-step="signed_in" data-outcome="failed">(.*?)</li>', page, re.S)
    assert failed is not None and "data-error-code=" in failed.group(1)
    assert 'data-step="sent" data-outcome="done"' not in page
    assert PASSWORD not in page


@pytest.mark.parametrize(
    ("field", "value"),
    [("port", "70000"), ("address", "no-at-sign.example.test"), ("host", "smtp://example.test")],
)
def test_every_value_has_its_rule(operator: Any, field: str, value: str) -> None:
    from mail.models import MailSender

    client, _ = operator
    response = client.post(PAGE, values(**{field: value}))

    assert response.status_code == 200
    assert f'data-error-for="{field}"' in response.content.decode()
    with schema_context(None):
        assert not MailSender.objects.exists()


def test_platform_pages_closed_to_others(member_of: Any, make_tenant_schema: Any) -> None:
    from identity.models import User
    from tenancy.middleware import invalidate_host_cache
    from tenancy.models import TenantDomain

    tenant_admin, _, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    elsewhere = make_tenant_schema("Another synthetic organisation")
    TenantDomain.objects.create(
        tenant=elsewhere, host="docs.example.test", is_default=True, actor_kind="system"
    )
    invalidate_host_cache()
    operator = User.objects.create_user(
        "o2.synthetic@example.test", "test-only-not-a-password", is_platform_admin=True
    )
    on_domain = Client(headers={"host": "docs.example.test"})
    on_domain.force_login(operator)

    for client in (tenant_admin, on_domain):
        missing = client.get("/folder/999/").content
        for page in (PAGE, f"{PAGE}?part=result"):
            refused = client.get(page)
            assert refused.status_code == 404, page
            assert re.sub(
                rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", refused.content
            ) == re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", missing), page
        assert client.post(PAGE, {"action": "remove"}).status_code == 404
        assert client.post(PAGE, values()).status_code == 404
        assert client.post(f"{PAGE}test/", values()).status_code == 404


def test_without_a_sender_the_page_says_so(operator: Any) -> None:
    client, _ = operator
    page = client.get(PAGE).content.decode()

    assert "data-no-sender" in page
    assert f'action="{PAGE}test/"' not in page


def test_no_sign_in_in_the_clear_but_to_the_same_machine(operator: Any) -> None:
    """DL-0388: a user name with an unencrypted connection only to a loopback server."""
    from mail.models import MailSender

    client, _ = operator
    refused = client.post(PAGE, values(security="none"))
    assert refused.status_code == 200
    assert 'data-error-for="security"' in refused.content.decode()
    with schema_context(None):
        assert not MailSender.objects.exists()

    assert client.post(PAGE, values(security="none", host="127.0.0.1")).status_code == 302
    assert client.post(PAGE, values(security="none", username="", password="")).status_code == 302

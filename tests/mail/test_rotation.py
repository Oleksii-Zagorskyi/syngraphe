"""Rotating the sending passwords' key (DL-0202, DL-0372): with the new key current and the old one
previous, `rotate_mail_key` re-encrypts every stored password — the platform's and each
organisation's — under the new key, so the previous one can be removed; it audits that it ran,
never a value.

Keys are generated for each test; the passwords are synthetic examples.
"""

from __future__ import annotations

from typing import Any

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


def test_the_previous_key_can_go_once_rotated(
    migrated_tenant: Any, sender: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from audit.models import AuditEvent
    from mail import secrets
    from mail.models import MailSender

    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("MAIL_PASSWORD_KEY", old)
    monkeypatch.delenv("MAIL_PASSWORD_KEY_PREVIOUS", raising=False)
    sender(None, password_encrypted=secrets.encrypt("synthetic-platform-password"))
    sender(migrated_tenant.number, password_encrypted=secrets.encrypt("synthetic-tenant-password"))

    monkeypatch.setenv("MAIL_PASSWORD_KEY", new)
    monkeypatch.setenv("MAIL_PASSWORD_KEY_PREVIOUS", old)
    call_command("rotate_mail_key")
    call_command("rotate_mail_key")
    monkeypatch.delenv("MAIL_PASSWORD_KEY_PREVIOUS")

    with schema_context(None):
        platform = MailSender.objects.get()
    with schema_context(migrated_tenant.number):
        tenant = MailSender.objects.get()
    assert secrets.decrypt(bytes(platform.password_encrypted)) == "synthetic-platform-password"
    assert secrets.decrypt(bytes(tenant.password_encrypted)) == "synthetic-tenant-password"
    events = AuditEvent.objects.filter(action="mail.key_rotated")
    # Each run audits each schema it visited: the shared one and the organisation's.
    assert events.count() == 4
    assert all("password" not in str(event.after) for event in events)


def test_a_sender_without_sign_in_is_passed_over(
    migrated_tenant: Any, sender: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sender that signs in nowhere stores no password; the rotation goes on past it."""
    from mail import secrets
    from mail.models import MailSender

    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("MAIL_PASSWORD_KEY", old)
    monkeypatch.delenv("MAIL_PASSWORD_KEY_PREVIOUS", raising=False)
    sender(None, password_encrypted=b"")
    sender(migrated_tenant.number, password_encrypted=secrets.encrypt("synthetic-tenant-password"))

    monkeypatch.setenv("MAIL_PASSWORD_KEY", new)
    monkeypatch.setenv("MAIL_PASSWORD_KEY_PREVIOUS", old)
    call_command("rotate_mail_key")
    monkeypatch.delenv("MAIL_PASSWORD_KEY_PREVIOUS")

    with schema_context(None):
        assert bytes(MailSender.objects.get().password_encrypted) == b""
    with schema_context(migrated_tenant.number):
        tenant = MailSender.objects.get()
    assert secrets.decrypt(bytes(tenant.password_encrypted)) == "synthetic-tenant-password"

"""The organisation's own sending address (DL-0202, DL-0367, DL-0385): saved by its administrators,
or by a platform administrator who has chosen it; its mail leaves from it, the platform's address
carrying the rest; removing it falls back to the platform's; the page lists the organisation's
own outbox and states that delivery needs the domain's DNS records.

People, addresses and texts are synthetic examples; every address ends in `@example.test`.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

PAGE = "/administration/tenant/sending-address/"


def values(**changed: Any) -> dict[str, Any]:
    form = {
        "action": "save",
        "host": "smtp.example.test",
        "port": "587",
        "address": "own.sender@example.test",
        "display_name": "Synthetic organisation",
        "username": "",
        "password": "",
        "security": "starttls",
    }
    form.update(changed)
    return form


def queued_for(tenant: Any, people: Any) -> list[Any]:
    """`version_committed` written to the reviewer, its email queued; that email's rows."""
    from mail.models import EmailOutbox
    from notifications.models import Category, Event
    from notifications.services import notify

    with schema_context(tenant.number):
        made = notify(
            users=[people["r"]],
            category=Category.DOCUMENT,
            event=Event.VERSION_COMMITTED,
            actor=people["a"],
            document=people.document,
        )
        return list(EmailOutbox.objects.filter(notification_id__in=[n.pk for n in made]))


def test_the_organisations_address_sends_its_mail(
    migrated_tenant: Any, member_of: Any, cast: Any, sender: Any
) -> None:
    from audit.models import AuditEvent
    from mail.models import MailSender

    admin, _, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    sender(None)
    assert admin.post(PAGE, values()).status_code == 302
    with schema_context(migrated_tenant.number):
        assert MailSender.objects.get().address == "own.sender@example.test"
    with schema_context(None):
        assert MailSender.objects.get().address == "platform.sender@example.test"
    event = AuditEvent.objects.get(action="mail.sender_saved")
    assert event.tenant_id == migrated_tenant.pk

    people = cast(editors=("a",), reviewers=("r",))
    [row] = queued_for(migrated_tenant, people)
    assert row.sender == "own.sender@example.test"


def test_fallback_per_organisation(
    migrated_tenant: Any, make_tenant_schema: Any, member_of: Any, cast: Any, sender: Any
) -> None:
    from mail import services as mail

    other = make_tenant_schema("Another synthetic organisation")
    sender(None)
    sender(migrated_tenant.number)
    with schema_context(migrated_tenant.number):
        own = mail.queue(migrated_tenant, "r1.synthetic@example.test", "Subject", "A letter.")
    with schema_context(other.number):
        fallback = mail.queue(other, "r2.synthetic@example.test", "Subject", "A letter.")
    assert own is not None and own.sender == f"tenant{migrated_tenant.number}.sender@example.test"
    assert fallback is not None and fallback.sender == "platform.sender@example.test"


def test_remove_falls_back_to_the_platform(
    migrated_tenant: Any, member_of: Any, cast: Any, sender: Any
) -> None:
    from audit.models import AuditEvent
    from mail.models import MailSender

    admin, _, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    sender(None)
    sender(migrated_tenant.number)
    assert admin.post(PAGE, {"action": "remove"}).status_code == 302
    with schema_context(migrated_tenant.number):
        assert not MailSender.objects.exists()
    assert AuditEvent.objects.filter(action="mail.sender_removed").count() == 1

    people = cast(editors=("a",), reviewers=("r",))
    [row] = queued_for(migrated_tenant, people)
    assert row.sender == "platform.sender@example.test"


def test_closed_to_members(member_of: Any) -> None:
    member, _, _ = member_of("m.synthetic@example.test")

    refused = member.get(PAGE)
    assert refused.status_code == 404
    missing = member.get("/folder/999/")
    assert re.sub(rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", refused.content) == re.sub(
        rb'name="csrfmiddlewaretoken" value="[^"]*"', b"", missing.content
    )
    assert member.post(PAGE, values()).status_code == 404
    assert member.post(f"{PAGE}test/", values()).status_code == 404


def test_dns_note_and_write_only_password(
    migrated_tenant: Any, member_of: Any, sender: Any
) -> None:
    from mail import secrets

    admin, _, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    sender(
        migrated_tenant.number,
        username="own.sender@example.test",
        password_encrypted=secrets.encrypt("synthetic-organisation-password"),
    )
    page = admin.get(PAGE).content.decode()

    assert "data-dns-note" in page
    password = re.search(r'<input[^>]*name="password"[^>]*>', page)
    assert password is not None and "value=" not in password.group(0)
    assert "synthetic-organisation-password" not in page
    assert "data-password-stored" in page


def test_the_organisations_outbox_lists_its_own_mail(
    migrated_tenant: Any, make_tenant_schema: Any, member_of: Any
) -> None:
    from mail.models import EmailOutbox

    admin, _, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    other = make_tenant_schema("Another synthetic organisation")
    rows = []
    with schema_context(migrated_tenant.number):
        for n in (1, 2):
            rows.append(
                EmailOutbox.objects.create(
                    tenant=migrated_tenant,
                    sender="own.sender@example.test",
                    recipient=f"own{n}.synthetic@example.test",
                    subject="Synthetic subject",
                    body="A synthetic letter.",
                )
            )
    with schema_context(other.number):
        EmailOutbox.objects.create(
            tenant=other,
            sender="other.sender@example.test",
            recipient="other.synthetic@example.test",
            subject="Synthetic subject",
            body="A synthetic letter.",
        )
    with schema_context(None):
        EmailOutbox.objects.create(
            sender="platform.sender@example.test",
            recipient="platform.synthetic@example.test",
            subject="Synthetic subject",
            body="A synthetic letter.",
        )

    page = admin.get(PAGE).content.decode()
    assert re.findall(r'data-outbox="([0-9a-f-]+)"', page) == [str(rows[1].pk), str(rows[0].pk)]
    assert page.count('data-status="queued" data-attempts="0"') == 2
    assert "other.synthetic@example.test" not in page
    assert "platform.synthetic@example.test" not in page


def test_a_test_email_on_the_organisations_row(
    migrated_tenant: Any, member_of: Any, sender: Any, sink: Any, monkeypatch: Any
) -> None:
    from mail.models import MailSender
    from mail.tasks import test_sender

    queued: list[Any] = []
    monkeypatch.setattr("mail.tasks.test_sender.delay", lambda *args: queued.append(args))
    admin, _, _ = member_of("t.synthetic@example.test", is_tenant_admin=True)
    saved = sender(migrated_tenant.number)
    values = values_for(saved)
    assert admin.post(f"{PAGE}test/", values).status_code == 302
    assert queued == [(migrated_tenant.number,)]
    test_sender(migrated_tenant.number)

    page = admin.get(PAGE).content.decode()
    assert 'data-step="sent" data-outcome="done"' in page
    [received] = sink.messages
    assert received.rcpt_tos == [saved.address]
    with schema_context(None):
        assert not MailSender.objects.exists()


def test_a_platform_administrator_with_the_organisation_chosen_saves_it(
    migrated_tenant: Any, member_of: Any
) -> None:
    from audit.models import AuditEvent
    from mail.models import MailSender

    operator, _, _ = member_of("o.synthetic@example.test", is_platform_admin=True)
    assert operator.post(PAGE, values()).status_code == 302
    with schema_context(migrated_tenant.number):
        assert MailSender.objects.count() == 1
    with schema_context(None):
        assert not MailSender.objects.exists()
    assert AuditEvent.objects.get(action="mail.sender_saved").tenant_id == migrated_tenant.pk


def values_for(saved: Any) -> dict[str, Any]:
    return values(
        host=saved.host,
        port=str(saved.port),
        address=saved.address,
        display_name=saved.display_name,
        security="none",
    )

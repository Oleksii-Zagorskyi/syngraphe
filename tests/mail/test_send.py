"""Sending (DL-0202, DL-0203): the periodic task sends each due row through its schema's sender; a
refusal is retried five minutes later, and the third refusal fails the row and tells the
organisation's administrators and the platform's in the application; two runs at once send a row
once.

People, groups, addresses and texts are synthetic examples; every address ends in `@example.test`.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any

import pytest
from django.db import DatabaseError, connection

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

FIVE_MINUTES = timedelta(minutes=5)
WRITTEN = "Синтетичне речення першої правки.\n"
RECIPIENT = "m.synthetic@example.test"
# The password `tests/mail/conftest.py`'s signing sink accepts.
SINK_PASSWORD = "synthetic-sink-password"


def queued_row(tenant: Any) -> Any:
    """One email queued in the tenant's schema, naming no notification."""
    from mail import services as mail

    with schema_context(tenant.number):
        row = mail.queue(tenant, RECIPIENT, "Синтетична тема", "Синтетичний лист без тексту.")
    assert row is not None
    return row


def reread(tenant_number: int | None, row: Any) -> Any:
    with schema_context(tenant_number):
        row.refresh_from_db()
    return row


def test_three_attempts_five_minutes_apart(
    migrated_tenant: Any, cast: Any, commit_version: Any, sender: Any, sink: Any
) -> None:
    from mail.models import EmailOutbox, Status
    from mail.tasks import send_outbox
    from notifications.models import Category, Event, Notification
    from notifications.services import notify

    people = cast(editors=("a",), reviewers=("r",))
    version = commit_version(people.document, people["a"], WRITTEN, "edit")
    sending = sender(migrated_tenant.number)
    number = migrated_tenant.number
    with schema_context(number):
        (notification,) = notify(
            users=[people["r"]],
            category=Category.DOCUMENT,
            event=Event.VERSION_COMMITTED,
            actor=people["a"],
            document=people.document,
            version=version,
        )
        row = EmailOutbox.objects.get(notification_id=notification.pk)
    sink.refuse_next = 2
    start = row.next_attempt_at

    send_outbox(now=start)
    reread(number, row)
    assert (row.status, row.attempts) == (Status.QUEUED, 1)
    assert row.next_attempt_at == start + FIVE_MINUTES
    # The server's own answer, under its code; never an exception's text.
    assert row.last_error.startswith("smtp:451 ")
    assert len(sink.refused) == 1 and not sink.messages

    # Not yet due: nothing is tried.
    send_outbox(now=start + FIVE_MINUTES - timedelta(seconds=1))
    reread(number, row)
    assert row.attempts == 1 and len(sink.refused) == 1

    send_outbox(now=start + FIVE_MINUTES)
    reread(number, row)
    assert (row.status, row.attempts) == (Status.QUEUED, 2)
    assert row.next_attempt_at == start + 2 * FIVE_MINUTES
    assert len(sink.refused) == 2 and not sink.messages

    send_outbox(now=start + 2 * FIVE_MINUTES)
    reread(number, row)
    assert row.status == Status.SENT
    assert row.attempts == 2
    assert row.sent_at == start + 2 * FIVE_MINUTES

    assert len(sink.messages) == 1
    received = sink.messages[0]
    assert received.mail_from == sending.address
    assert received.rcpt_tos == ["r.synthetic@example.test"]
    assert received.message["Subject"] == row.subject
    with schema_context(number):
        assert Notification.objects.get(pk=notification.pk).emailed_at is not None

    # Sent is done: a later run sends nothing again.
    send_outbox(now=start + 3 * FIVE_MINUTES)
    assert len(sink.messages) == 1


def test_final_failure_notifies_both_sets_of_administrators_in_the_application(
    migrated_tenant: Any, member_of: Any, sender: Any, sink: Any
) -> None:
    from identity.models import User
    from mail import secrets
    from mail.models import Status
    from mail.tasks import send_outbox
    from notifications.models import Event, Notification
    from tenancy.models import PlatformNotification

    password = "synthetic-password-never-shown"
    _, tenant_admin_1, _ = member_of("t1.synthetic@example.test", is_tenant_admin=True)
    _, tenant_admin_2, _ = member_of("t2.synthetic@example.test", is_tenant_admin=True)
    member_of("plain.member@example.test")
    platform_admins = [
        User.objects.create_user(
            f"o{n}.synthetic@example.test", "test-only-not-a-password", is_platform_admin=True
        )
        for n in (1, 2)
    ]
    sender(migrated_tenant.number, password_encrypted=secrets.encrypt(password))
    sink.always_refuse = True
    number = migrated_tenant.number
    row = queued_row(migrated_tenant)
    start = row.next_attempt_at

    def failed_told() -> tuple[list[Any], list[Any]]:
        with schema_context(number):
            tenant_side = list(
                Notification.objects.filter(event=Event.EMAIL_FAILED).values_list(
                    "user_id", flat=True
                )
            )
        with schema_context(None):
            platform_side = list(
                PlatformNotification.objects.filter(event=Event.EMAIL_FAILED).values_list(
                    "user_id", flat=True
                )
            )
        return tenant_side, platform_side

    for attempt in (1, 2):
        send_outbox(now=start + (attempt - 1) * FIVE_MINUTES)
        reread(number, row)
        assert (row.status, row.attempts) == (Status.QUEUED, attempt)
        assert failed_told() == ([], [])

    send_outbox(now=start + 2 * FIVE_MINUTES)
    reread(number, row)
    assert row.status == Status.FAILED
    assert row.attempts == 3
    assert row.sent_at is None
    # The server's own answer, under its code; never an exception's text.
    assert row.last_error.startswith("smtp:451 ")
    assert password not in row.last_error
    assert sink.refusals_to(RECIPIENT) == 3
    assert not sink.messages

    tenant_side, platform_side = failed_told()
    assert sorted(tenant_side) == sorted([tenant_admin_1.pk, tenant_admin_2.pk])
    assert sorted(platform_side) == sorted(admin.pk for admin in platform_admins)

    # Told in the application alone: the outbox holds the one email that failed.
    from mail.models import EmailOutbox

    with schema_context(number):
        assert EmailOutbox.objects.count() == 1
    with schema_context(None):
        assert not EmailOutbox.objects.exists()

    # No fourth attempt, and nobody is told twice.
    send_outbox(now=start + 3 * FIVE_MINUTES)
    send_outbox(now=start + 4 * FIVE_MINUTES)
    assert len(sink.refused) == 3
    reread(number, row)
    assert (row.status, row.attempts) == (Status.FAILED, 3)
    assert sink.refusals_to(RECIPIENT) == 3
    tenant_again, platform_again = failed_told()
    assert sorted(tenant_again) == sorted(tenant_side)
    assert sorted(platform_again) == sorted(platform_side)


def test_a_row_is_sent_once_under_two_runs(migrated_tenant: Any, sender: Any, sink: Any) -> None:
    from mail.models import Status
    from mail.tasks import send_outbox

    sender(migrated_tenant.number)
    row = queued_row(migrated_tenant)
    now = row.next_attempt_at
    # Each message is held a moment, so the two runs overlap.
    sink.delay = 0.5
    ready = threading.Barrier(2)
    errors: list[BaseException] = []

    def run() -> None:
        try:
            ready.wait(timeout=30)
            send_outbox(now=now)
        except BaseException as error:
            errors.append(error)
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == []

    assert len(sink.messages) == 1
    assert sink.messages[0].rcpt_tos == [RECIPIENT]
    assert not sink.refused
    reread(migrated_tenant.number, row)
    assert row.status == Status.SENT
    assert row.attempts == 0


def test_a_sign_in_sends_and_a_refused_one_keeps_no_trace_of_the_password(
    migrated_tenant: Any, signing_sink: Any
) -> None:
    """The one place a password is decrypted signs in with it; a password the connection cannot
    carry is refused without a character of it, or its length, in the row."""
    from mail import secrets
    from mail.models import MailSender, Security, Status
    from mail.tasks import send_outbox

    number = migrated_tenant.number
    with schema_context(number):
        sending = MailSender.objects.create(
            host="127.0.0.1",
            port=signing_sink.port,
            address="tenant.sender@example.test",
            username="tenant.sender@example.test",
            password_encrypted=secrets.encrypt(SINK_PASSWORD),
            security=Security.NONE,
        )
    row = queued_row(migrated_tenant)
    send_outbox(now=row.next_attempt_at)
    assert reread(number, row).status == Status.SENT

    password = "синтетичний-пароль-é"
    with schema_context(number):
        MailSender.objects.filter(pk=sending.pk).update(
            password_encrypted=secrets.encrypt(password)
        )
    row = queued_row(migrated_tenant)
    send_outbox(now=row.next_attempt_at)
    reread(number, row)
    assert row.attempts == 1
    assert "position" not in row.last_error
    for character in set(password) - set(" -"):
        assert character not in row.last_error, character


def test_a_failure_in_one_schema_stops_no_other_and_resends_nothing(
    migrated_tenant: Any, make_tenant_schema: Any, sender: Any, sink: Any, monkeypatch: Any
) -> None:
    from mail import services
    from mail.models import Status
    from mail.tasks import send_outbox

    other = make_tenant_schema("Інша синтетична організація")
    sender(migrated_tenant.number)
    sender(other.number)
    first = queued_row(migrated_tenant)
    second = queued_row(other)
    original = services._emailed
    calls: list[int] = []

    def emailed(row: Any, now: Any) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise DatabaseError("synthetic failure after acceptance")
        original(row, now)

    monkeypatch.setattr(services, "_emailed", emailed)
    now = max(first.next_attempt_at, second.next_attempt_at)
    send_outbox(now=now)
    send_outbox(now=now + FIVE_MINUTES)

    assert reread(migrated_tenant.number, first).status == Status.SENT
    assert reread(other.number, second).status == Status.SENT
    assert len(sink.messages) == 2


def test_an_email_queued_under_a_changed_address_leaves_from_the_sender_there_now(
    migrated_tenant: Any, sender: Any, sink: Any
) -> None:
    from mail.models import MailSender, Status
    from mail.tasks import send_outbox

    sending = sender(migrated_tenant.number)
    row = queued_row(migrated_tenant)
    with schema_context(migrated_tenant.number):
        MailSender.objects.filter(pk=sending.pk).update(address="renamed.sender@example.test")
    send_outbox(now=row.next_attempt_at)

    reread(migrated_tenant.number, row)
    assert row.status == Status.SENT
    assert row.sender == "renamed.sender@example.test"
    assert sink.messages[0].mail_from == "renamed.sender@example.test"


def test_a_slow_run_still_waits_five_minutes_before_the_next_attempt(
    migrated_tenant: Any, sender: Any, sink: Any, monkeypatch: Any
) -> None:
    """Without a given time, each row's attempt is dated when it is made: a run that started
    long ago never sets a next attempt already due."""
    from django.utils import timezone

    from mail import tasks

    sender(migrated_tenant.number)
    row = queued_row(migrated_tenant)
    sink.always_refuse = True
    started = row.next_attempt_at + FIVE_MINUTES
    later = started + timedelta(minutes=6)
    # The clock reads the run's start once, then a time six minutes on.
    moments = iter([started])
    monkeypatch.setattr(timezone, "now", lambda: next(moments, later))

    tasks.send_outbox()

    reread(migrated_tenant.number, row)
    assert row.attempts == 1
    assert row.next_attempt_at == later + FIVE_MINUTES


def test_the_platforms_mail_is_sent_and_its_failure_told_to_platform_administrators_alone(
    migrated_tenant: Any, member_of: Any, sender: Any, sink: Any
) -> None:
    from identity.models import User
    from mail.models import EmailOutbox, Status
    from mail.tasks import send_outbox
    from notifications.models import Event, Notification
    from notifications.services import notify_platform
    from tenancy.models import PlatformNotification
    from tenancy.schemas import current_tenant

    member_of("t.synthetic@example.test", is_tenant_admin=True)
    operator = User.objects.create_user(
        "o.synthetic@example.test", "test-only-not-a-password", is_platform_admin=True
    )
    sender(None)
    [told] = notify_platform(event=Event.BACKUP_CONDITION, users=[operator])
    with schema_context(None):
        row = EmailOutbox.objects.get()
    with schema_context(migrated_tenant.number):
        send_outbox(now=row.next_attempt_at)
        assert current_tenant(connection) == migrated_tenant.number
    with schema_context(None):
        row.refresh_from_db()
        assert row.status == Status.SENT
        assert PlatformNotification.objects.get(pk=told.pk).emailed_at is not None

    sink.always_refuse = True
    notify_platform(event=Event.BACKUP_CONDITION, users=[operator])
    with schema_context(None):
        failing = EmailOutbox.objects.get(status=Status.QUEUED)
    for attempt in range(3):
        send_outbox(now=failing.next_attempt_at + attempt * FIVE_MINUTES)
    with schema_context(None):
        failing.refresh_from_db()
        assert failing.status == Status.FAILED
        assert PlatformNotification.objects.filter(event=Event.EMAIL_FAILED).count() == 1
        assert EmailOutbox.objects.count() == 2
    with schema_context(migrated_tenant.number):
        assert not Notification.objects.filter(event=Event.EMAIL_FAILED).exists()


def test_a_migrating_organisations_mail_waits(migrated_tenant: Any, sender: Any, sink: Any) -> None:
    from mail.models import Status
    from mail.tasks import send_outbox
    from tenancy.models import Tenant

    sender(migrated_tenant.number)
    row = queued_row(migrated_tenant)
    Tenant.objects.filter(pk=migrated_tenant.pk).update(state="migrating")
    send_outbox(now=row.next_attempt_at)

    assert reread(migrated_tenant.number, row).status == Status.QUEUED
    assert not sink.messages


def test_an_email_whose_recipient_lost_the_document_is_not_sent(
    migrated_tenant: Any, cast: Any, commit_version: Any, sender: Any, sink: Any
) -> None:
    """DL-0387: the right is read again at the send; lost meanwhile, the email fails quietly."""
    from access.models import GroupMember
    from mail.models import EmailOutbox, Status
    from mail.tasks import send_outbox
    from notifications.models import Category, Event, Notification
    from notifications.services import notify

    people = cast(editors=("a",), reviewers=("r",))
    sender(migrated_tenant.number)
    number = migrated_tenant.number
    with schema_context(number):
        [told] = notify(
            users=[people["r"]],
            category=Category.DOCUMENT,
            event=Event.FROZEN,
            document=people.document,
        )
        row = EmailOutbox.objects.get(notification_id=told.pk)
        GroupMember.objects.filter(membership=people.memberships["r"]).delete()
    send_outbox(now=row.next_attempt_at)

    reread(number, row)
    assert row.status == Status.FAILED
    assert row.last_error == "unreadable"
    assert not sink.messages and not sink.refused
    with schema_context(number):
        assert not Notification.objects.filter(event=Event.EMAIL_FAILED).exists()


def test_an_email_waits_for_a_missing_key_and_leaves_once_it_is_set(
    migrated_tenant: Any, signing_sink: Any, monkeypatch: Any
) -> None:
    """DL-0389: the key missing on the worker holds the email; its attempts stay untouched."""
    from mail import secrets
    from mail.models import MailSender, Security, Status
    from mail.tasks import send_outbox

    number = migrated_tenant.number
    with schema_context(number):
        MailSender.objects.create(
            host="127.0.0.1",
            port=signing_sink.port,
            address="tenant.sender@example.test",
            username="tenant.sender@example.test",
            password_encrypted=secrets.encrypt(SINK_PASSWORD),
            security=Security.NONE,
        )
    row = queued_row(migrated_tenant)
    key = secrets.keys()[0]
    monkeypatch.delenv("MAIL_PASSWORD_KEY")
    for minute in range(4):
        send_outbox(now=row.next_attempt_at + timedelta(minutes=minute))
    reread(number, row)
    assert (row.status, row.attempts) == (Status.QUEUED, 0)
    assert row.last_error == "key_missing"

    monkeypatch.setenv("MAIL_PASSWORD_KEY", key)
    send_outbox(now=row.next_attempt_at + timedelta(minutes=5))
    assert reread(number, row).status == Status.SENT
    assert len(signing_sink.messages) == 1


def test_an_email_waits_while_no_sending_address_is_set(
    migrated_tenant: Any, sender: Any, sink: Any
) -> None:
    """DL-0395: the address removed and none left, the email waits, its attempts untouched, and
    nobody is told; it leaves once an address is set."""
    from mail.models import MailSender, Status
    from mail.tasks import send_outbox
    from notifications.models import Notification
    from tenancy.models import PlatformNotification

    number = migrated_tenant.number
    sender(number)
    row = queued_row(migrated_tenant)
    with schema_context(number):
        MailSender.objects.all().delete()
    for minute in (0, 5, 10, 15):
        send_outbox(now=row.next_attempt_at + timedelta(minutes=minute))
    reread(number, row)
    assert (row.status, row.attempts, row.last_error) == (Status.QUEUED, 0, "no_sender")
    with schema_context(number):
        assert not Notification.objects.filter(event="email_failed").exists()
    assert not PlatformNotification.objects.filter(event="email_failed").exists()

    sender(number)
    send_outbox(now=row.next_attempt_at + timedelta(minutes=20))
    assert reread(number, row).status == Status.SENT
    assert len(sink.messages) == 1


def test_a_password_the_key_cannot_open_waits_with_its_own_reason(
    migrated_tenant: Any, signing_sink: Any, monkeypatch: Any
) -> None:
    """A key that is valid but not the one the password was stored under is not a missing key:
    the email waits with a reason that asks for the password again."""
    from cryptography.fernet import Fernet

    from mail import secrets
    from mail.models import MailSender, Security, Status
    from mail.tasks import send_outbox

    number = migrated_tenant.number
    with schema_context(number):
        MailSender.objects.create(
            host="127.0.0.1",
            port=signing_sink.port,
            address="tenant.sender@example.test",
            username="tenant.sender@example.test",
            password_encrypted=secrets.encrypt(SINK_PASSWORD),
            security=Security.NONE,
        )
    row = queued_row(migrated_tenant)
    monkeypatch.setenv("MAIL_PASSWORD_KEY", Fernet.generate_key().decode())
    for minute in (0, 5, 10, 15):
        send_outbox(now=row.next_attempt_at + timedelta(minutes=minute))
    reread(number, row)
    assert (row.status, row.attempts, row.last_error) == (Status.QUEUED, 0, "key_wrong")


def test_a_run_stops_claiming_once_its_time_is_spent(
    migrated_tenant: Any, sender: Any, sink: Any, monkeypatch: Any, settings: Any
) -> None:
    """A run ends within its minute, leaving what it did not reach for the next; a run the
    scheduler could not start in time is dropped rather than queued behind the others."""
    from mail import tasks
    from mail.models import Status

    entry = settings.CELERY_BEAT_SCHEDULE["send-outbox"]
    assert entry["options"]["expires"] < 60
    sender(migrated_tenant.number)
    rows = [queued_row(migrated_tenant) for _ in range(3)]
    monkeypatch.setattr(tasks, "RUN_SECONDS", 0)
    tasks.send_outbox()
    assert [reread(migrated_tenant.number, row).status for row in rows] == [Status.QUEUED] * 3
    assert all(row.attempts == 0 for row in rows)

    monkeypatch.undo()
    tasks.send_outbox()
    assert [reread(migrated_tenant.number, row).status for row in rows] == [Status.SENT] * 3


def test_an_email_whose_notification_is_gone_is_never_sent(
    migrated_tenant: Any, sender: Any, sink: Any
) -> None:
    """A notification removed after its email was queued — a restore's pruning — takes the email
    with it: the row fails as withdrawn, nothing leaves, and nobody is told."""
    import uuid

    from mail import services as mail
    from mail.models import Status
    from mail.tasks import send_outbox
    from notifications.models import Notification

    number = migrated_tenant.number
    sender(number)
    with schema_context(number):
        row = mail.queue(
            migrated_tenant,
            RECIPIENT,
            "Синтетична тема",
            "Синтетичний лист.",
            notification_id=uuid.uuid4(),
        )
    assert row is not None
    send_outbox(now=row.next_attempt_at)
    reread(number, row)
    assert (row.status, row.last_error) == (Status.FAILED, "withdrawn")
    assert sink.messages == []
    with schema_context(number):
        assert not Notification.objects.filter(event="email_failed").exists()


def test_every_schema_gets_its_turn_under_a_busy_one(
    migrated_tenant: Any, sender: Any, sink: Any, monkeypatch: Any
) -> None:
    """Each run starts at another schema, so an outbox that fills every run's time cannot keep
    another's mail waiting."""
    import time as clock

    from mail import services as mail
    from mail import tasks
    from mail.models import Status

    sender(None)
    sender(migrated_tenant.number)
    with schema_context(None):
        for n in range(3):
            mail.queue(None, f"p{n}.synthetic@example.test", "Синтетична тема", "Синтетичний лист.")
    row = queued_row(migrated_tenant)
    real = mail.send

    def slow(*args: Any, **kwargs: Any) -> bool:
        clock.sleep(0.2)
        return real(*args, **kwargs)

    monkeypatch.setattr(mail, "send", slow)
    monkeypatch.setattr(tasks, "RUN_SECONDS", 0.1)
    turns = iter(range(10))
    monkeypatch.setattr(tasks, "_turn", lambda: next(turns))
    tasks.send_outbox()
    tasks.send_outbox()
    assert reread(migrated_tenant.number, row).status == Status.SENT


CREDENTIAL_TOKEN = "A" * 43


@pytest.mark.parametrize("path", ["invitation", "reset"])
def test_a_credential_link_is_not_kept_once_sent(
    migrated_tenant: Any, sender: Any, sink: Any, path: str
) -> None:
    """The email leaves with its link; the outbox keeps the record without the token (DL-0406)."""
    from mail import services as mail
    from mail.models import EmailOutbox, Status
    from mail.tasks import send_outbox

    sender(migrated_tenant.number)
    body = f"Синтетичний лист.\nhttps://docs.example.test/{path}/{CREDENTIAL_TOKEN}/\n"
    with schema_context(migrated_tenant.number):
        row = mail.queue(migrated_tenant, RECIPIENT, "Синтетична тема", body)
        assert row is not None

    send_outbox(now=row.next_attempt_at)

    with schema_context(migrated_tenant.number):
        row = EmailOutbox.objects.get(pk=row.pk)
    assert row.status == Status.SENT
    assert CREDENTIAL_TOKEN in sink.messages[0].body
    assert CREDENTIAL_TOKEN not in row.body
    assert f"https://docs.example.test/{path}/" in row.body


def test_a_credential_link_is_not_kept_once_failed(
    migrated_tenant: Any, sender: Any, sink: Any
) -> None:
    from mail import services as mail
    from mail.models import EmailOutbox, Status
    from mail.tasks import send_outbox

    sender(migrated_tenant.number)
    sink.always_refuse = True
    body = f"https://docs.example.test/reset/{CREDENTIAL_TOKEN}/\n"
    with schema_context(migrated_tenant.number):
        row = mail.queue(migrated_tenant, RECIPIENT, "Синтетична тема", body)
        assert row is not None
    start = row.next_attempt_at

    for attempt in range(3):
        send_outbox(now=start + attempt * FIVE_MINUTES)
        with schema_context(migrated_tenant.number):
            stored = EmailOutbox.objects.get(pk=row.pk)
        if attempt < 2:
            # Still to be tried again: the link must survive until the last attempt.
            assert CREDENTIAL_TOKEN in stored.body

    assert stored.status == Status.FAILED
    assert CREDENTIAL_TOKEN not in stored.body

"""The outbox (DL-0203, DL-0205, DL-0367): what an email says, which sender carries it, where it is
queued and how it is sent. An email is written to the outbox of the current schema before any
attempt to send it; it carries the event's sentence — the document's number and title — the
author of a version awaiting review, the time and one link, never a line of a document, a change
summary or a reason (DL-0113, DL-0369)."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timedelta
from email.utils import formataddr
from typing import Any

from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend
from django.db import DatabaseError, connection, transaction
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _

from mail import secrets
from mail.models import EmailOutbox, MailSender, Security, Status
from syngraphe.config import ConfigurationError
from tenancy.schemas import current_tenant, schema_context

ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=5)

logger = logging.getLogger(__name__)


def sender_for_queue() -> MailSender | None:
    """The sender an email queued now would leave from: the current schema's own, else the
    platform's; `None` when neither exists, and then nothing is queued (DL-0367)."""
    own = MailSender.objects.first()
    if own is not None or current_tenant(connection) is None:
        return own
    with schema_context(None):
        return MailSender.objects.first()


def queue(
    tenant: Any, recipient: str, subject: str, body: str, *, notification_id: Any = None
) -> EmailOutbox | None:
    """One email written to the current schema's outbox, due now, from the sender
    `sender_for_queue` finds; `None`, and nothing written, without one."""
    sender = sender_for_queue()
    if sender is None:
        return None
    return EmailOutbox.objects.create(
        tenant=tenant,
        sender=sender.address,
        recipient=recipient,
        subject=subject[:255],
        body=body,
        status=Status.QUEUED,
        next_attempt_at=timezone.now(),
        notification_id=notification_id,
    )


def link(tenant: Any, path: str) -> str:
    """An absolute address of `path`: on the tenant's default domain, else the platform's
    default host (ADR-0008); `https` when the site is served over it."""
    from tenancy.models import PlatformHost, TenantDomain

    host = None
    if tenant is not None:
        host = (
            TenantDomain.objects.filter(tenant=tenant, is_default=True)
            .values_list("host", flat=True)
            .first()
        )
    if host is None:
        host = PlatformHost.objects.filter(is_default=True).values_list("host", flat=True).first()
    scheme = "https" if settings.SITE_HTTPS else "http"
    return f"{scheme}://{host or ''}{path}"


def _tenant_of(row: Any) -> Any:
    from notifications.models import Notification
    from tenancy.models import Tenant

    number = current_tenant(connection)
    if not isinstance(row, Notification) or number is None:
        return None
    return Tenant.objects.filter(number=number).first()


def compose(row: Any) -> tuple[str, str]:
    """The subject and body of the email of a `Notification` or a `PlatformNotification`, in the
    installation's language: the entry's sentence, the version's author where a version awaits
    review, the time, and one link."""
    from identity.naming import person
    from notifications.events import describe, tag

    with translation.override(settings.LANGUAGE_CODE):
        sentence = describe(row)
        marked = tag(row)
        lines = [sentence + (f" — {marked}" if marked else "")]
        version = getattr(row, "version", None)
        if version is not None and row.event == "version_committed":
            lines.append(_("Version by %(person)s.") % {"person": person(version.author)})
        moment = timezone.localtime(row.created_at, timezone=_display_zone())
        lines.append(formats.date_format(moment, "DATETIME_FORMAT"))
        # The notification itself: opening it marks it read and leads where its entry leads
        # (DL-0394); its id is random, so the link names nothing another person can reach.
        lines.append(link(_tenant_of(row), f"/notifications/{row.pk}/"))
        return sentence, "\n".join(lines) + "\n"


def _display_zone() -> Any:
    from zoneinfo import ZoneInfo

    return ZoneInfo(settings.DISPLAY_TIMEZONE)


def backend_for(sender: MailSender) -> EmailBackend:
    """A connection to `sender`'s server; its password decrypted here, never kept."""
    signs_in = bool(sender.username)
    return EmailBackend(
        host=sender.host,
        port=sender.port,
        username=sender.username if signs_in else None,
        password=secrets.decrypt(bytes(sender.password_encrypted)) if signs_in else None,
        use_tls=sender.security == Security.STARTTLS,
        use_ssl=sender.security == Security.TLS,
        timeout=10,
        fail_silently=False,
    )


def _sender_of(row: EmailOutbox) -> MailSender | None:
    """The sender the row names — the schema's own with its address, else the platform's — or,
    the address changed or removed since the row was queued, the sender a new email would use."""
    own = MailSender.objects.filter(address=row.sender).first()
    if own is not None:
        return own
    if current_tenant(connection) is not None:
        with schema_context(None):
            shared = MailSender.objects.filter(address=row.sender).first()
        if shared is not None:
            return shared
    return sender_for_queue()


def _error(error: Exception) -> str:
    """What a refusal records: a reason code a page words in its own language, and the server's
    own answer where it gave one — never an exception's text, which can quote what it could not
    encode."""
    import socket
    import ssl

    if isinstance(error, smtplib.SMTPResponseException):
        answer = error.smtp_error
        if isinstance(answer, bytes):
            answer = answer.decode("utf-8", "replace")
        return f"smtp:{error.smtp_code} {answer}"[:500]
    codes: tuple[tuple[type[BaseException], str], ...] = (
        (smtplib.SMTPNotSupportedError, "no_sign_in"),
        (smtplib.SMTPServerDisconnected, "disconnected"),
        (ssl.SSLCertVerificationError, "certificate"),
        (ssl.SSLError, "tls"),
        (socket.gaierror, "name_not_found"),
        (TimeoutError, "timeout"),
        (ConnectionRefusedError, "refused"),
        (OSError, "unreachable"),
    )
    for kind, code in codes:
        if isinstance(error, kind):
            return code
    return "other"


def send(row: EmailOutbox, now: datetime | None = None) -> bool:
    """Try to send `row` once; `True` only when the server accepted it. A refusal is recorded
    on the row and tried again five minutes later, until the third. `now`, when not given, is
    the moment of the attempt."""
    withheld = _withheld(row)
    if withheld is not None:
        row.status = Status.FAILED
        row.last_error = withheld
        row.save(update_fields=["status", "last_error"])
        return False
    sender = _sender_of(row)
    if sender is None:
        _held(row, NO_SENDER)
        return False
    try:
        message = EmailMessage(
            row.subject,
            row.body,
            from_email=formataddr((sender.display_name, sender.address)),
            to=[row.recipient],
        )
        accepted = backend_for(sender).send_messages([message])
        if accepted != 1:
            raise RuntimeError("the server accepted no message")
    except ConfigurationError:
        _held(row, KEY_MISSING)
        return False
    except InvalidToken:
        _held(row, KEY_WRONG)
        return False
    except Exception as error:  # noqa: BLE001 — every refusal is the row's, recorded below
        _refused(row, error, now or timezone.now())
        return False
    moment = now or timezone.now()
    row.status = Status.SENT
    row.sent_at = moment
    # The outbox records the address the email left from.
    row.sender = sender.address
    row.save(update_fields=["status", "sent_at", "sender"])
    try:
        with transaction.atomic():
            _emailed(row, moment)
    except DatabaseError:
        # The email left; marking its notification is not worth sending it again.
        logger.exception("an email's notification not marked", extra={"outbox": str(row.pk)})
    return True


# Reason codes a page words in its own language (`mail.views.common.reason`).
UNREADABLE = "unreadable"
WITHDRAWN = "withdrawn"
KEY_MISSING = "key_missing"
KEY_WRONG = "key_wrong"
NO_SENDER = "no_sender"
# Why an email waits rather than counting a refusal: a state the installation's own people
# set, which they lift (DL-0389, DL-0395).
HELD = {
    KEY_MISSING: "an email waits for the mail key",
    KEY_WRONG: "an email waits: the mail key does not open its sender's password",
    NO_SENDER: "an email waits for a sending address",
}


def _withheld(row: EmailOutbox) -> str | None:
    """Why an email may not leave, read again at the send, or `None`: its notification gone —
    pruned with what a restore undid — or a document its person can no longer open (DL-0387).
    An email that carries no notification is sent as queued."""
    from access.rights import readable
    from notifications.models import Notification
    from tenancy.models import PlatformNotification

    if row.notification_id is None:
        return None
    if current_tenant(connection) is None:
        found = PlatformNotification.objects.filter(pk=row.notification_id).exists()
        return None if found else WITHDRAWN
    notification = (
        Notification.objects.filter(pk=row.notification_id).select_related("user").first()
    )
    if notification is None:
        return WITHDRAWN
    if notification.document_id is None:
        return None
    if notification.document_id in readable(notification.user, [notification.document_id]):
        return None
    return UNREADABLE


def _held(row: EmailOutbox, reason: str) -> None:
    """An email that cannot leave for a reason of the installation's own — no key, a key that
    does not open the password, no sending address — waits, its attempts untouched (DL-0389,
    DL-0395); the reason is recorded, and logged when it first appears."""
    if row.last_error != reason:
        logger.error(HELD[reason], extra={"outbox": str(row.pk)})
        row.last_error = reason
        row.save(update_fields=["last_error"])


def _emailed(row: EmailOutbox, now: datetime) -> None:
    from notifications.models import Notification
    from tenancy.models import PlatformNotification

    if row.notification_id is None:
        return
    table = Notification if current_tenant(connection) is not None else PlatformNotification
    table.objects.filter(pk=row.notification_id).update(emailed_at=now)


def _refused(row: EmailOutbox, error: Exception, now: datetime) -> None:
    row.attempts += 1
    row.last_error = _error(error)
    if row.attempts < ATTEMPTS:
        row.next_attempt_at = now + RETRY_AFTER
        row.save(update_fields=["attempts", "last_error", "next_attempt_at"])
        return
    row.status = Status.FAILED
    row.save(update_fields=["attempts", "last_error", "status"])
    _tell_administrators(row)


def _tell_administrators(row: EmailOutbox) -> None:
    """A failed email told in the application only (DL-0203): to the organisation's
    administrators in its schema and to the platform's."""
    from access.rights import administrators
    from notifications.models import Category, Event
    from notifications.services import notify, notify_platform

    number = current_tenant(connection)
    facts: dict[str, Any] = {"outbox": str(row.pk)}
    if number is not None:
        notify(
            users=administrators(number),
            category=Category.ADMINISTRATIVE,
            event=Event.EMAIL_FAILED,
            facts=facts,
        )
        facts = {**facts, "tenant": number}
    notify_platform(event=Event.EMAIL_FAILED, facts=facts)


STEPS = ("connected", "signed_in", "sent")


def try_sender(sender: MailSender, now: datetime) -> dict[str, Any]:
    """*Send a test email* (DL-0202): from the address to itself, step by step — connected, signed
    in, sent — and which step failed, with the server's answer; never the password."""
    import ssl

    done: list[str] = []
    skipped: list[str] = []
    server: smtplib.SMTP | None = None
    try:
        if sender.security == Security.TLS:
            server = smtplib.SMTP_SSL(
                sender.host, sender.port, timeout=10, context=ssl.create_default_context()
            )
        else:
            server = smtplib.SMTP(sender.host, sender.port, timeout=10)
            if sender.security == Security.STARTTLS:
                server.starttls(context=ssl.create_default_context())
        done.append("connected")
        if sender.username:
            server.login(sender.username, secrets.decrypt(bytes(sender.password_encrypted)))
            done.append("signed_in")
        else:
            skipped.append("signed_in")
        with translation.override(settings.LANGUAGE_CODE):
            moment = timezone.localtime(now, timezone=_display_zone())
            message = EmailMessage(
                _("Test message"),
                _("Test email from %(host)s, sent at %(time)s")
                % {"host": sender.host, "time": formats.date_format(moment, "DATETIME_FORMAT")},
                from_email=formataddr((sender.display_name, sender.address)),
                to=[sender.address],
            )
        server.send_message(message.message(), sender.address, [sender.address])
        done.append("sent")
        return {"done": done, "skipped": skipped}
    except (ConfigurationError, InvalidToken):
        failed = next(step for step in STEPS if step not in done + skipped)
        return {"done": done, "skipped": skipped, "failed": failed, "error": KEY_MISSING}
    except Exception as error:  # noqa: BLE001 — the failing step is the result, not a fault
        failed = next(step for step in STEPS if step not in done + skipped)
        return {"done": done, "skipped": skipped, "failed": failed, "error": _error(error)}
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:  # noqa: BLE001, S110 — the connection is closing either way
                pass

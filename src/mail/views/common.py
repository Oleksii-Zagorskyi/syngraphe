"""What the platform's and an organisation's sending-address pages share: the form saved and
audited, a test asked for one at a time, its steps read back, the outbox listed — every reason
worded in the page's language."""

from __future__ import annotations

import json
import time
from datetime import timedelta
from typing import Any, cast

from django.db import transaction
from django.db.models import F, Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from audit.record import record
from identity.models import User
from mail import secrets
from mail.forms import SERVER, SenderForm
from mail.models import EmailOutbox, MailSender
from mail.services import STEPS
from syngraphe.config import ConfigurationError

# How long the page waits for a test's result, and how long a test asked for holds the next.
POLL_SECONDS = 30
# The outbox's newest emails a page draws (DL-0392).
OUTBOX_SHOWN = 200
FIELDS = ("host", "port", "security", "address", "display_name", "username")


def stored(sender: MailSender | None) -> dict[str, Any]:
    """The stored values the form compares a new entry with: the password only as present."""
    if sender is None:
        return {}
    values: dict[str, Any] = {field: getattr(sender, field) for field in FIELDS}
    values["password"] = bool(sender.password_encrypted)
    return values


def initial(sender: MailSender | None) -> dict[str, Any]:
    if sender is None:
        return {"security": "starttls"}
    return {field: getattr(sender, field) for field in FIELDS}


def save(request: HttpRequest, form: SenderForm, sender: MailSender | None, tenant: Any) -> bool:
    """The sender written from a valid form; `False`, and the form told why, when the key the
    password is encrypted under is not set. Audited when something changed — host, address and
    security, and that the password was replaced or removed, never its value nor the port
    (DL-0202, DL-0203). A changed server forgets the last test's result."""
    data = form.cleaned_data
    row = sender or MailSender()
    before = stored(sender) or None
    # Read before the row changes: `row` and `sender` are one object.
    audited_before = (
        None
        if sender is None
        else {"host": sender.host, "address": sender.address, "security": sender.security}
    )
    password = None
    if not data["username"]:
        password = "removed" if sender is not None and sender.password_encrypted else None
        row.password_encrypted = b""
    elif data["password"]:
        try:
            row.password_encrypted = secrets.encrypt(data["password"])
        except ConfigurationError as error:
            form.add_error(
                "password",
                _("The key sending passwords are kept under is not set: %(keys)s.")
                % {"keys": ", ".join(error.missing + error.malformed)},
            )
            return False
        password = "replaced"
    changed = [field for field in FIELDS if before is None or before[field] != data[field]]
    if not changed and password is None:
        return True
    for field in FIELDS:
        setattr(row, field, data[field])
    if password or any(field in SERVER for field in changed) or "address" in changed:
        row.last_test_at = None
        row.last_test_result = ""
    row.updated_at = timezone.now()
    with transaction.atomic():
        row.save()
        _audit_saved(request, row, audited_before, password, tenant)
    return True


def _audit_saved(
    request: HttpRequest,
    row: MailSender,
    before: dict[str, Any] | None,
    password: Any,
    tenant: Any,
) -> None:
    after: dict[str, Any] = {"host": row.host, "address": row.address, "security": row.security}
    if password:
        # Named so the audit's guard against secrets lets it pass: it carries no value.
        after["password_change"] = password
    record(
        actor=cast(User, request.user),
        action="mail.sender_saved",
        obj=row,
        before=before,
        after=after,
        tenant=tenant,
    )


def remove(request: HttpRequest, sender: MailSender, tenant: Any) -> None:
    """The sender removed, with its audit, as one act; mail queued for it waits (DL-0395)."""
    with transaction.atomic():
        record(
            actor=cast(User, request.user),
            action="mail.sender_removed",
            obj=sender,
            before={"host": sender.host, "address": sender.address, "security": sender.security},
            after=None,
            tenant=tenant,
        )
        sender.delete()


def test_running(sender: MailSender | None) -> bool:
    """Whether a test asked for in the last thirty seconds has no result yet (DL-0392)."""
    if sender is None or sender.last_test_requested_at is None:
        return False
    recent = timezone.now() - sender.last_test_requested_at < timedelta(seconds=POLL_SECONDS)
    answered = sender.last_test_at is not None and (
        sender.last_test_at >= sender.last_test_requested_at
    )
    return recent and not answered


def claim_test(sender: MailSender) -> bool:
    """The test asked for, if no other is running: one conditional update, so of two requests
    that both found none running, one claims it and the other is refused (DL-0392). The last
    result is forgotten, the moment kept."""
    now = timezone.now()
    free = (
        Q(last_test_requested_at__isnull=True)
        | Q(last_test_requested_at__lte=now - timedelta(seconds=POLL_SECONDS))
        | Q(last_test_at__gte=F("last_test_requested_at"))
    )
    # PostgreSQL re-reads the condition of a row another update held, so the second is refused.
    claimed = MailSender.objects.filter(free, pk=sender.pk).update(
        last_test_requested_at=now, last_test_at=None, last_test_result=""
    )
    return claimed == 1


def reason(code: str) -> str:
    """A refusal's reason, recorded as a code, in the page's words."""
    if code.startswith("smtp:"):
        return _("The server answered: %(answer)s") % {"answer": code.removeprefix("smtp:")}
    return {
        "timeout": _("The server did not answer in time."),
        "name_not_found": _("No server of that name was found."),
        "refused": _("The server refused the connection."),
        "unreachable": _("The server could not be reached."),
        "certificate": _("The server's certificate was not accepted."),
        "tls": _("No encrypted connection could be made."),
        "no_sign_in": _("The server offers no sign-in."),
        "disconnected": _("The server closed the connection."),
        "key_missing": _("The sending password cannot be read until the mail key is set."),
        "key_wrong": _("The mail key does not open the sending password: enter it again."),
        "no_sender": _("No sending address is set."),
        "unreadable": _("The recipient may no longer open the document."),
        "withdrawn": _("The notification this email carried no longer exists."),
        "": "",
    }.get(code, _("The email could not be sent."))


def steps(sender: MailSender | None) -> list[dict[str, str]]:
    """The last test's steps in order: done, not needed or failed; those after a failure are not
    listed."""
    if sender is None or not sender.last_test_result:
        return []
    result = json.loads(sender.last_test_result)
    labels = {"connected": _("Connection"), "signed_in": _("Sign-in"), "sent": _("Sending")}
    shown = []
    for step in STEPS:
        if step in result.get("done", []):
            shown.append({"step": step, "label": labels[step], "outcome": "done"})
        elif step in result.get("skipped", []):
            shown.append({"step": step, "label": labels[step], "outcome": "not_needed"})
        elif step == result.get("failed"):
            shown.append(
                {
                    "step": step,
                    "label": labels[step],
                    "outcome": "failed",
                    "code": result["error"],
                    "reason": reason(result["error"]),
                }
            )
            break
    return shown


def listed(rows: list[EmailOutbox]) -> list[dict[str, Any]]:
    """The outbox's rows as the page shows them, each status and reason in the page's words."""
    labels = {"queued": _("Queued"), "sent": _("Sent"), "failed": _("Failed")}
    return [
        {"row": row, "status": labels[row.status], "reason": reason(row.last_error)} for row in rows
    ]


def outbox() -> tuple[list[EmailOutbox], bool]:
    """The current schema's newest emails, and whether there are more than the page draws."""
    rows = list(EmailOutbox.objects.order_by("-created_at", "-id")[: OUTBOX_SHOWN + 1])
    return rows[:OUTBOX_SHOWN], len(rows) > OUTBOX_SHOWN


def _testing(request: HttpRequest) -> int | None:
    try:
        return int(request.GET.get("testing", ""))
    except ValueError:
        return None


def page(
    request: HttpRequest,
    sender: MailSender | None,
    form: SenderForm,
    *,
    scope: str,
    page_url: str,
    test_url: str,
    rows: Any = None,
    frame: dict[str, Any],
    running: bool = False,
) -> HttpResponse:
    """The page, or with `part=result` the polled result alone. `rows` is a callable reading the
    outbox, so the polled part never reads it."""
    testing = _testing(request)
    fresh = (
        sender is not None
        and sender.last_test_at is not None
        and testing is not None
        and sender.last_test_at.timestamp() >= testing
    )
    waiting = testing is not None and not fresh
    within = testing is not None and 0 <= time.time() - testing < POLL_SECONDS
    context = {
        **frame,
        "scope": scope,
        "sender": sender,
        "form": form,
        "steps": steps(sender) if not waiting else [],
        "testing": testing if waiting and within else None,
        "pending": waiting and within,
        "no_result": waiting and not within,
        "running": running,
        "page_url": page_url,
        "test_url": test_url,
    }
    if request.GET.get("part") == "result":
        return render(request, "mail/test_result.html", context)
    if rows is not None:
        shown, capped = rows()
        context |= {"rows": listed(shown), "capped": capped, "shown": OUTBOX_SHOWN}
    return render(request, "mail/sender_form.html", context)


def after_test(page_url: str) -> HttpResponse:
    return HttpResponseRedirect(f"{page_url}?testing={int(time.time())}")

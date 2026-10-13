"""The outbox sent (DL-0203): every minute, each due email of the shared schema and of every
tenant the background work visits, claimed so that two runs never send one email twice. A failure
in one schema, or with one email, is logged and stops no other. One window stays: a process that
dies after the server accepted an email and before its record is committed sends it again."""

from __future__ import annotations

import logging
import time
from datetime import datetime

from celery import shared_task
from django.db import DatabaseError, transaction
from django.utils import timezone

from mail import services
from mail.models import EmailOutbox, Status
from tenancy.models import visited_by_background_work
from tenancy.schemas import schema_context

logger = logging.getLogger(__name__)
# A run ends inside its minute, leaving what it did not reach to the next, so runs never pile up
# behind a server that answers slowly; the schedule drops a run it could not start in time.
RUN_SECONDS = 45


def _send_due(due_by: datetime, now: datetime | None, deadline: float) -> None:
    """Each email of the current schema due by `due_by`, claimed and sent in a transaction of its
    own, so a refusal is recorded however the others fare; none claimed after `deadline`."""
    due = list(
        EmailOutbox.objects.filter(status=Status.QUEUED, next_attempt_at__lte=due_by)
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)
    )
    for pk in due:
        if time.monotonic() >= deadline:
            return
        try:
            with transaction.atomic():
                row = (
                    EmailOutbox.objects.select_for_update(skip_locked=True)
                    .filter(pk=pk, status=Status.QUEUED, next_attempt_at__lte=due_by)
                    .first()
                )
                if row is not None:
                    services.send(row, now)
        except DatabaseError:
            logger.exception("an email not sent", extra={"outbox": str(pk)})


@shared_task(name="mail.send_outbox")
def send_outbox(now: datetime | None = None) -> None:
    """Send what is due: the platform's mail, then each organisation's. Without `now`, each
    attempt is dated when it is made, so a slow run never sets a next attempt already due."""
    due_by = now or timezone.now()
    deadline = time.monotonic() + RUN_SECONDS
    for tenant_number in [None, *(tenant.number for tenant in visited_by_background_work())]:
        if time.monotonic() >= deadline:
            return
        try:
            with schema_context(tenant_number):
                _send_due(due_by, now, deadline)
        except DatabaseError:
            logger.exception("an outbox not sent", extra={"tenant": tenant_number})


@shared_task(name="mail.test_sender")
def test_sender(schema: int | None) -> None:
    """*Send a test email* for the sender of the schema numbered `schema`, or the platform's for
    `None`: run by the worker, which alone decrypts a password; its result kept on the row."""
    import json

    from mail.models import MailSender

    now = timezone.now()
    with schema_context(schema):
        sender = MailSender.objects.first()
        if sender is None:
            return
        result = services.try_sender(sender, now)
        # Written only on the sender as it was read: a save meanwhile forgot the last result.
        MailSender.objects.filter(pk=sender.pk, updated_at=sender.updated_at).update(
            last_test_at=now, last_test_result=json.dumps(result)
        )

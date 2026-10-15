"""No email carries document text (DL-0113, DL-0205): whatever event a notification records — those
the acts write themselves and those written here for every remaining event — its subject and body
name the document, the versions, the people and a link, never a sentence of the document, a
change summary or a reason given for a freeze or its end.

People, groups, addresses and texts are synthetic examples; every address ends in `@example.test`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.invariant,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

SENTENCE = "A synthetic request is considered by a board of three."
WRITTEN = f"# Synthetic provisions\n\n{SENTENCE}\nA request is considered within ten days.\n"
CORRECTED = WRITTEN.replace("ten days", "five working days")
SUMMARY = "The synthetic board named in full"
CORRECTION_SUMMARY = "The time for a synthetic request shortened"
REASON = "Synthetic reason: waiting for the supervisory board to decide"
END_REASON = "Synthetic reason for the end: the decision has arrived"

FORBIDDEN = (
    SENTENCE,
    "A request is considered within ten days.",
    "A request is considered within five working days.",
    SUMMARY,
    CORRECTION_SUMMARY,
    REASON,
    END_REASON,
)

# The events an organisation's administrators are told of, as against a document's people.
ADMINISTRATIVE = {
    "access_granted",
    "document_created",
    "document_copied",
    "email_failed",
    "backup_condition",
    "reservation_started",
}
# Written below through the paths that write them, not directly: the platform's own in the shared
# schema, which `notify` refuses in an organisation's.
WRITTEN_BY_THEIR_PATH = {
    "correction_notice",
    "email_failed",
    "backup_condition",
    "user_partially_blocked",
    "tenant_without_admin",
}


def test_no_email_carries_document_text(
    migrated_tenant: Any,
    member_of: Any,
    cast: Any,
    link_group: Any,
    commit_version: Any,
    sender: Any,
    sink: Any,
) -> None:
    from access.rights import Right
    from editions import services as editions
    from identity.models import User
    from mail import services as mail
    from mail.models import EmailOutbox
    from mail.tasks import send_outbox
    from notifications.models import Category, Event, Notification
    from notifications.services import notify, notify_platform
    from review import services as review
    from tenancy.models import PlatformNotification

    number = migrated_tenant.number
    member_of("t.synthetic@example.test", is_tenant_admin=True)
    operator = User.objects.create_user(
        "o.synthetic@example.test", "test-only-not-a-password", is_platform_admin=True
    )
    sender(number)
    # Every email fails, so `email_failed` is written by the task as it is in use.
    sink.always_refuse = True

    people = cast(editors=("a",), reviewers=("r",))
    document = people.document
    _, approver, approver_membership = member_of("p.synthetic@example.test")
    link_group(document, [Right.FREEZE, Right.MAKE_CANONICAL], [approver_membership], people["a"])

    version = commit_version(document, people["a"], WRITTEN, "edit", summary=SUMMARY)
    commit_version(document, people["r"], CORRECTED, "reviewer_edit", summary=CORRECTION_SUMMARY)
    with schema_context(number):
        review.accept(document, people["r"])
        editions.freeze(document, approver, REASON)
        editions.make_canonical(document, approver)
        editions.freeze(document, approver, REASON)
        editions.end_freeze(document, END_REASON)

        # Every event no act above has written, written directly with the same document.
        present = set(Notification.objects.values_list("event", flat=True))
        for event in Event:
            if event.value in present or event.value in WRITTEN_BY_THEIR_PATH:
                continue
            notify(
                users=[people["r"]],
                category=(
                    Category.ADMINISTRATIVE if event.value in ADMINISTRATIVE else Category.DOCUMENT
                ),
                event=event,
                actor=people["a"],
                document=document,
                version=version,
            )
    notify_platform(event=Event.BACKUP_CONDITION, users=[operator])
    notify_platform(
        event=Event.USER_PARTIALLY_BLOCKED,
        users=[operator],
        facts={"user": str(people["r"].pk), "tenant": number},
    )
    notify_platform(event=Event.TENANT_WITHOUT_ADMIN, users=[operator], facts={"tenant": number})

    start = timezone.now()
    for attempt in range(3):
        send_outbox(now=start + attempt * timedelta(minutes=5))

    composed: list[tuple[str, str, str]] = []
    with schema_context(number):
        for row in Notification.objects.all():
            subject, body = mail.compose(row)
            composed.append((row.event, subject, body))
        outbox = [(row.subject, row.body) for row in EmailOutbox.objects.all()]
    with schema_context(None):
        for row in PlatformNotification.objects.all():
            subject, body = mail.compose(row)
            composed.append((row.event, subject, body))
        outbox += [(row.subject, row.body) for row in EmailOutbox.objects.all()]

    # Every event is among them, the failed email's included.
    assert {event for event, _, _ in composed} == set(Event.values)
    assert outbox, "no email was queued to look at"
    for event, subject, body in composed:
        for text in FORBIDDEN:
            assert text not in subject, (event, text)
            assert text not in body, (event, text)
    for subject, body in outbox:
        for text in FORBIDDEN:
            assert text not in subject and text not in body, text

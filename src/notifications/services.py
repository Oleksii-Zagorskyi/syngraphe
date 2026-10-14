"""The one writer of notifications, and the only reader of the platform's (DL-0367, DL-0382).

An organisation's notifications live in its schema; what platform administrators are told lives
in the shared schema, whatever request caused it. An act notifies through `notify` or
`notify_platform`; each notification and its email are written in one transaction, before any
attempt to send (DL-0203).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import connection, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from identity.models import User
from notifications.models import Category, Event, Notification
from tenancy.models import PlatformNotification, Tenant
from tenancy.schemas import current_tenant, schema_context


def _queue(row: Notification | PlatformNotification, tenant: Any) -> None:
    """The email of `row`, queued in the current schema's outbox in the row's own transaction,
    when a sender can carry it. A failed email is told in the application alone (DL-0203)."""
    from access.rights import readable
    from mail import services as mail

    if row.event == Event.EMAIL_FAILED or not row.user.email:
        return
    # An email never names a document its person cannot open (DL-0386).
    document_id = getattr(row, "document_id", None)
    if document_id is not None and document_id not in readable(row.user, [document_id]):
        return
    subject, body = mail.compose(row)
    mail.queue(tenant, row.user.email, subject, body, notification_id=row.pk)


def _refuse_the_actor(users: list[User], actor: User | None) -> None:
    # Nobody is told of their own act; a caller that forgot to leave the actor out fails here.
    if actor is not None and any(user.pk == actor.pk for user in users):
        raise ValueError("the actor is among the people to notify")


def notify(
    *,
    users: Iterable[User],
    category: Category,
    event: Event,
    actor: User | None = None,
    document: Any = None,
    version: Any = None,
    correction_notice: Any = None,
    facts: dict[str, Any] | None = None,
    at: datetime | None = None,
    email: bool = True,
) -> list[Notification]:
    """One `Notification` per person in the current organisation's schema, in one transaction,
    each with its email unless `email` is false — an act that sends its own (DL-0399).
    `ValueError` when `actor` is among `users`, or `category` is not the event's own."""
    from notifications.events import EVENTS
    from notifications.models import PLATFORM_EVENTS

    if EVENTS[Event(event)].category != category:
        raise ValueError(f"{event} is not a {category} event")
    # What only platform administrators are told never lands in an organisation's schema, where
    # its administrators read it (ASR-17); a failed email reaches both.
    if event in PLATFORM_EVENTS and event != Event.EMAIL_FAILED:
        raise ValueError(f"{event} is told to platform administrators alone")
    people = list(users)
    _refuse_the_actor(people, actor)
    moment = at or timezone.now()
    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("an organisation's notifications are written inside its schema")
    tenant = Tenant.objects.filter(number=number).first()
    rows = []
    with transaction.atomic():
        for user in people:
            row = Notification.objects.create(
                user=user,
                category=category,
                event=event,
                document=document,
                version=version,
                correction_notice=correction_notice,
                facts=facts or {},
                created_at=moment,
            )
            if email:
                _queue(row, tenant)
            rows.append(row)
    return rows


def others(user_ids: Iterable[Any], actor: User | None) -> list[User]:
    """The people of `user_ids` but the actor — nobody is told of their own act."""
    ids = set(user_ids) - ({actor.pk} if actor is not None else set())
    return list(User.objects.filter(pk__in=ids).order_by("email"))


def readers_and_administrators(document: Any) -> set[Any]:
    """Whom a freeze, its end and an edition tell: the people whose groups linked to the document
    let them open it — canonical text alone only once an edition exists (DL-0209) — and the
    organisation's administrators; a platform administrator only through a membership of their
    own, never by the role."""
    from access.rights import BEYOND_CANONICAL, LADDER, administrators, holders_of
    from editions.models import Edition

    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("a document's readers are read inside its organisation's schema")
    edition = Edition.objects.filter(version__document=document).exists()
    readers = holders_of(LADDER if edition else BEYOND_CANONICAL, [document.pk])[document.pk]
    return readers | {user.pk for user in administrators(number)}


def platform_administrators() -> QuerySet[User]:
    """Every platform administrator who holds the role today (DL-0308)."""
    return User.objects.filter(is_platform_admin=True, is_tombstoned=False, self_blocked=False)


def notify_platform(
    *,
    event: Event,
    users: Iterable[User] | None = None,
    actor: User | None = None,
    facts: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> list[PlatformNotification]:
    """One `PlatformNotification` per platform administrator in the shared schema, in one
    transaction: every one but the actor when `users` is not given. `ValueError` when `users`
    names the actor or anyone who is not a platform administrator."""
    administrators = platform_administrators()
    if users is None:
        people = list(administrators.exclude(pk=actor.pk) if actor is not None else administrators)
    else:
        people = list(users)
        if not {user.pk for user in people} <= set(administrators.values_list("pk", flat=True)):
            raise ValueError("only platform administrators are told in the shared schema")
    _refuse_the_actor(people, actor)
    moment = at or timezone.now()
    rows = []
    # The platform's rows and their emails belong to the shared schema alone, whatever schema
    # the request is in (DL-0367, DL-0382).
    with schema_context(None), transaction.atomic():
        for user in people:
            row = PlatformNotification.objects.create(
                user=user, event=event, facts=facts or {}, created_at=moment
            )
            _queue(row, None)
            rows.append(row)
    return rows


def platform_rows_for(user: Any) -> QuerySet[PlatformNotification]:
    """`user`'s notifications in the shared schema, newest first."""
    return PlatformNotification.objects.filter(user_id=user.pk).order_by("-created_at", "-id")


def mark_read_platform(user: Any, ids: Iterable[UUID] | None = None) -> int:
    """Mark `user`'s unread shared notifications read — those of `ids`, or all; the count."""
    rows = platform_rows_for(user).filter(read_at__isnull=True)
    if ids is not None:
        rows = rows.filter(pk__in=list(ids))
    return rows.update(read_at=timezone.now())


def openable(user: Any, rows: Iterable[Notification]) -> list[Notification]:
    """The rows of an organisation's notifications its reader may still see: those naming no
    document, and those whose document the reader can still open — an entry about one they no
    longer can is neither drawn nor counted, as a missing document would be (DL-0386)."""
    from access.rights import readable

    listed = list(rows)
    documents = {row.document_id for row in listed if row.document_id is not None}
    allowed = readable(user, documents) if documents else set()
    return [row for row in listed if row.document_id is None or row.document_id in allowed]


def unread_in_organisation(user: Any) -> int:
    """The person's unread notifications in the current organisation's schema that they may
    still see (DL-0386)."""
    from access.rights import readable

    unread = Notification.objects.filter(user_id=user.pk, read_at__isnull=True)
    documents = set(unread.exclude(document__isnull=True).values_list("document_id", flat=True))
    allowed = readable(user, documents) if documents else set()
    return unread.filter(Q(document__isnull=True) | Q(document_id__in=allowed)).count()

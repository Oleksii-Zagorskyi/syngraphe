"""Reserving a hold for editing (ADR-0009): a holder with *reserve for editing* keeps the hold
past the inactivity release; cancelling returns it to an ordinary hold; an administrator ends it
with a reason, the draft kept for its holder — or, on an ordinary hold, forces it free.

Every writer here takes the document's writer lock, then its row, then the hold's row, as `take`
and the blocks do (DL-0256): `accept` reads `reserved_at` under the same locks, so a reservation
either lands before an acceptance's refusal check and refuses it, or waits for its commit and
stands — review waits for a reservation, never the reverse (DL-0224).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from access.rights import Right, administrators, rights_on
from audit.record import record
from documents.locks import document_lock
from documents.models import Document
from editing.holds import LOCK_WAIT_SECONDS, tenant_number
from editing.models import Hold
from notifications.models import Category, Event
from notifications.services import notify
from tenancy.models import Tenant

if TYPE_CHECKING:
    from identity.models import User


class ReservationRefused(Exception):
    """The act may not be done now: `reason` is `not_allowed` — not the holder, or without the
    right — `released` — the hold ended meanwhile — `frozen`, `reserved` or `not_reserved`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@contextmanager
def _locked(hold: Hold) -> Iterator[Hold]:
    """`hold` read again under the document's writer lock and, in a transaction, the document's
    row and its own; `ReservationRefused("released")` once it is released."""
    number = tenant_number()
    with (
        document_lock(number, hold.document.number, timeout=LOCK_WAIT_SECONDS),
        transaction.atomic(),
    ):
        Document.objects.select_for_update().get(pk=hold.document_id)
        # The hold's row alone: the joined person's row is a self-block's, taken before the
        # document's.
        locked = (
            Hold.objects.select_for_update(of=("self",))
            .select_related("document", "user")
            .get(pk=hold.pk)
        )
        if locked.released_at is not None:
            raise ReservationRefused("released")
        yield locked


def refusal(hold: Hold, user: User) -> str | None:
    """Why `user` may not reserve `hold` now, or `None`; read again under the locks by `reserve`."""
    from editions.models import open_freeze

    if hold.user_id != user.pk or Right.RESERVE_FOR_EDITING not in rights_on(user, hold.document):
        return "not_allowed"
    if open_freeze(hold.document) is not None:
        return "frozen"
    if hold.reserved_at is not None:
        return "reserved"
    return None


def reserve(hold: Hold, user: User) -> Hold:
    """Reserve `hold` for its holder: `reserved_at` set, audited, the organisation's administrators
    told (DL-0226). `ReservationRefused` with the reason it may not be."""
    with _locked(hold) as locked:
        reason = refusal(locked, user)
        if reason is not None:
            raise ReservationRefused(reason)
        locked.reserved_at = timezone.now()
        locked.save(update_fields=["reserved_at"])
        record(
            actor=user,
            action="document.reserved",
            obj=locked.document,
            before=None,
            after={"number": locked.document.number},
            tenant=Tenant.objects.get(number=tenant_number()),
        )
        notify(
            users=[a for a in administrators(tenant_number()) if a.pk != user.pk],
            category=Category.ADMINISTRATIVE,
            event=Event.RESERVATION_STARTED,
            actor=user,
            document=locked.document,
            facts={"holder": str(user.pk)},
        )
    return locked


def cancel_reservation(hold: Hold, user: User) -> Hold:
    """Return `hold` to an ordinary hold, its inactivity clock started again; its holder's alone.
    `ReservationRefused` when it is not reserved or not theirs."""
    with _locked(hold) as locked:
        if locked.user_id != user.pk:
            raise ReservationRefused("not_allowed")
        if locked.reserved_at is None:
            raise ReservationRefused("not_reserved")
        locked.reserved_at = None
        locked.last_activity_at = timezone.now()
        locked.save(update_fields=["reserved_at", "last_activity_at"])
        record(
            actor=user,
            action="document.reservation_cancelled",
            obj=locked.document,
            before=None,
            after={"number": locked.document.number},
            tenant=Tenant.objects.get(number=tenant_number()),
        )
    return locked


class ReasonRefused(ValueError):
    """An administrator's reason outside its rule: one line of printable text, 1 to 500
    characters, no bidirectional controls (DL-0378)."""


def checked_reason(reason: str) -> str:
    """`reason` stripped, or `ReasonRefused` — the freeze reason's rule, and required, since the
    act is defined by it (DL-0353, DL-0378). The text stays out of the exception: it may quote
    the document, and an exception reaches a log (DL-0369)."""
    from documents.archive import ARCHIVED_REASON
    from editions.services import valid_reason

    reason = reason.strip()
    # Epic 10: the reason archiving writes is the platform's alone, never typed (DL-0456).
    if not reason or not valid_reason(reason) or reason.casefold() == ARCHIVED_REASON:
        raise ReasonRefused
    return reason


def end_reservation(hold: Hold, administrator: User, reason: str) -> bool:
    """End `hold`'s reservation against its holder (DL-0214, DL-0225): released `forced` with the
    administrator and the reason, the draft kept for the holder, who is told who ended it, when
    and why — the reason in the application, never in the email (DL-0369). Whether this call
    ended it. `ReasonRefused` for a reason outside its rule; `ReservationRefused` with
    `not_reserved` for a hold not reserved, `released` once it has ended, and `not_allowed` when
    `administrator`, read again under the locks, does not administer the organisation, or holds
    the reservation themselves — theirs is cancelled, not ended."""
    from editing import holds
    from editing.models import ReleaseKind
    from identity.blocking import administers

    reason = checked_reason(reason)
    with _locked(hold) as locked:
        tenant = Tenant.objects.get(number=tenant_number())
        if locked.user_id == administrator.pk or not administers(administrator, tenant.pk):
            raise ReservationRefused("not_allowed")
        if locked.reserved_at is None:
            raise ReservationRefused("not_reserved")
        ended = holds.release(
            locked,
            ReleaseKind.FORCED,
            actor=administrator,
            released_by=administrator,
            reason=reason,
        )
        locked.refresh_from_db(fields=["release_kind"])
        # A finish that had stopped after its commit was completed instead (DL-0414): nothing of
        # the holder's was ended, and nothing is said.
        if ended and locked.release_kind == ReleaseKind.FORCED:
            notify(
                users=[locked.user],
                category=Category.DOCUMENT,
                event=Event.RESERVATION_ENDED_BY_ADMIN,
                actor=administrator,
                document=locked.document,
                facts={"by": str(administrator.pk), "reason": reason},
            )
    return ended


def force_release(hold: Hold, administrator: User) -> bool:
    """Force an ordinary hold free (ADR-0006): released `forced` by the administrator, no reason
    asked, the draft kept for the holder — unless a finish of it had stopped after its commit,
    which is completed instead (DL-0414) — whose editor learns of it at its next heartbeat or
    capture. Whether this call released it. `ReservationRefused` with `reserved` for a reserved
    hold — it is ended, with a reason (DL-0225) — `released` once it has ended, and `not_allowed`
    when `administrator`, read again under the locks, does not administer the organisation, or
    holds it themselves."""
    from editing import holds
    from editing.models import ReleaseKind
    from identity.blocking import administers

    with _locked(hold) as locked:
        tenant = Tenant.objects.get(number=tenant_number())
        if locked.user_id == administrator.pk or not administers(administrator, tenant.pk):
            raise ReservationRefused("not_allowed")
        if locked.reserved_at is not None:
            raise ReservationRefused("reserved")
        return holds.release(
            locked, ReleaseKind.FORCED, actor=administrator, released_by=administrator
        )

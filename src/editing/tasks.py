"""The editing app's worker tasks: per-line authorship after each commit (DL-0135, ADR-0011); the
sweep that closes editors whose page went away without closing them (ASR-22); and the release of
holds left idle (ADR-0006, DL-0377)."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.db import DatabaseError

from documents import gitstore
from documents.locks import LockTimeout
from documents.models import Document
from editing import authorship
from tenancy.schemas import schema_context

logger = logging.getLogger(__name__)


@shared_task(name="editing.compute_authorship")
def compute_authorship(tenant_number: int, document_number: int, commit_sha: str) -> int:
    """Write the authorship rows of the version at `commit_sha`; returns how many. A commit whose
    version row is not there yet is left to the reconciler, which derives the row and queues this
    again; a failure of git is raised, for the reconciler's next pass to retry."""
    with schema_context(tenant_number):
        document = Document.objects.get(number=document_number)
        try:
            result = authorship.compute(
                document,
                commit_sha,
                repository_path=gitstore.repository_path(tenant_number, document_number),
            )
        except authorship.VersionMissing:
            logger.warning(
                "authorship waits for a version row",
                extra={"tenant": tenant_number, "document": document_number},
            )
            return 0
    return result.rows


@shared_task(name="editing.compute_authorship_at")
def compute_authorship_at(tenant_number: int, document_number: int, commit_sha: str) -> int:
    """A past version's rows, asked for by the historical page, kept for `KEPT_FOR`; returns how
    many. A commit without its version row is logged and left, as `compute_authorship` leaves it."""
    from django.utils import timezone

    from editing.past_authors import KEPT_FOR, asked_done

    try:
        with schema_context(tenant_number):
            document = Document.objects.get(number=document_number)
            try:
                result = authorship.compute(
                    document,
                    commit_sha,
                    repository_path=gitstore.repository_path(tenant_number, document_number),
                    expires_at=timezone.now() + KEPT_FOR,
                )
            except authorship.VersionMissing:
                logger.warning(
                    "authorship waits for a version row",
                    extra={"tenant": tenant_number, "document": document_number},
                )
                return 0
        return result.rows
    finally:
        asked_done(tenant_number, document_number, commit_sha)


@shared_task(name="editing.sweep_authorship")
def sweep_authorship() -> int:
    """Delete the on-demand authorship rows whose day has passed, in every organisation background
    work visits; returns how many."""
    from django.utils import timezone

    from editing.models import LineAuthorship
    from tenancy.models import visited_by_background_work

    swept = 0
    for number in visited_by_background_work().values_list("number", flat=True):
        # One organisation's failure leaves the others swept all the same.
        try:
            with schema_context(number):
                deleted, _ = LineAuthorship.objects.filter(expires_at__lt=timezone.now()).delete()
                swept += deleted
        except DatabaseError:
            logger.exception("authorship not swept", extra={"tenant": number})
    return swept


def queue_authorship(tenant_number: int, document_number: int, commit_sha: str) -> None:
    """Ask the worker for the authorship of one commit; the request path never computes it."""
    compute_authorship.delay(tenant_number, document_number, commit_sha)


@shared_task(name="editing.close_silent_editors")
def close_silent_editors() -> int:
    """Close every open editor whose heartbeat stopped — a tab closed without closing its editor —
    in every organisation background work visits (`visited_by_background_work`). Returns how many
    were closed."""
    from django.utils import timezone

    from editing.models import OpenEditor
    from editing.views.capture import SILENT_AFTER
    from tenancy.models import visited_by_background_work

    closed = 0
    cutoff = timezone.now() - SILENT_AFTER
    for number in visited_by_background_work().values_list("number", flat=True):
        # One organisation's failure leaves the others' editors to be closed all the same.
        try:
            with schema_context(number):
                closed += OpenEditor.objects.filter(
                    closed_at__isnull=True, last_seen_at__lt=cutoff
                ).update(closed_at=timezone.now())
        except DatabaseError:
            logger.exception("silent editors not closed", extra={"tenant": number})
    return closed


# How long a hold stays prompted before it is released: ten minutes after the organisation's
# timeout (DL-0377).
GRACE = timedelta(minutes=10)


@shared_task(name="editing.release_inactive_holds")
def release_inactive_holds() -> int:
    """The quiet hold (ADR-0006, DL-0377), in every organisation background work visits: a hold
    idle past the organisation's timeout — no activity for `hold_inactivity_minutes`, and not
    reserved — is notified to its holder once per idle spell (`hold_expiring`); still idle at the
    timeout plus `GRACE`, it is released `inactivity`, its draft kept — unless a finish of it had
    stopped after its commit, which is completed instead (DL-0414). A reserved hold is never
    touched. Returns how many holds were released."""
    from tenancy.models import visited_by_background_work

    released = 0
    for tenant in visited_by_background_work():
        # One organisation's failure leaves the others' holds to be visited all the same.
        try:
            with schema_context(tenant.number):
                released += _quiet_holds(tenant)
        except Exception:  # noqa: BLE001 — one organisation must not keep every later one held
            logger.exception("inactive holds not visited", extra={"tenant": tenant.number})
    return released


def _quiet_holds(tenant: Any) -> int:
    from django.utils import timezone

    from editing.models import Hold

    now = timezone.now()
    timeout = timedelta(minutes=tenant.hold_inactivity_minutes)
    idle = Hold.objects.filter(
        released_at__isnull=True, reserved_at__isnull=True, last_activity_at__lt=now - timeout
    ).select_related("document", "user")
    released = 0
    for hold in idle:
        try:
            if hold.last_activity_at < now - timeout - GRACE:
                released += _release_if_still_idle(tenant, hold, now - timeout - GRACE)
            else:
                _tell_once(hold)
        except LockTimeout:
            # The document's lock stays busy; the next minute's visit tries again.
            logger.info("inactive hold busy", extra={"document": hold.document.number})
        except Exception:  # noqa: BLE001 — one hold must not keep every later one held
            logger.exception("inactive hold not visited", extra={"document": hold.document.number})
    return released


def _release_if_still_idle(tenant: Any, hold: Any, cutoff: Any) -> int:
    """Release `hold` for inactivity, read again under the document's locks: a capture or an
    answer to the prompt that landed meanwhile keeps it."""
    from django.db import transaction

    from documents.locks import document_lock
    from editing import holds
    from editing.models import Hold, ReleaseKind

    with (
        document_lock(tenant.number, hold.document.number, timeout=holds.LOCK_WAIT_SECONDS),
        transaction.atomic(),
    ):
        Document.objects.select_for_update().get(pk=hold.document_id)
        locked = Hold.objects.select_for_update().get(pk=hold.pk)
        if (
            locked.released_at is not None
            or locked.reserved_at is not None
            or locked.last_activity_at >= cutoff
        ):
            return 0
        return int(holds.release(locked, ReleaseKind.INACTIVITY))


def _tell_once(hold: Any) -> None:
    """`hold_expiring` to the holder, once per idle spell: the spell is the activity it began
    after, recorded with the notification, so a later spell is told again (ST-0047). Decided on
    the hold as it stands, read again under its row's lock with the check and the write in one
    transaction: a holder active since the visit listed the hold is not told, and two visits at
    once tell once."""
    from django.db import transaction

    from editing.models import Hold
    from notifications.models import Category, Event, Notification
    from notifications.services import notify

    with transaction.atomic():
        # The document's row before the hold's, as every writer of a hold takes them.
        Document.objects.select_for_update().get(pk=hold.document_id)
        # The hold's row alone: the joined person's row is a self-block's, taken before the
        # document's.
        locked = (
            Hold.objects.select_for_update(of=("self",))
            .select_related("document", "user")
            .filter(pk=hold.pk, released_at__isnull=True, reserved_at__isnull=True)
            .first()
        )
        # Active since the visit listed it, or ended meanwhile: nothing to tell.
        if locked is None or locked.last_activity_at != hold.last_activity_at:
            return
        idle_since = locked.last_activity_at.isoformat()
        told = Notification.objects.filter(
            user=locked.user,
            event=Event.HOLD_EXPIRING,
            facts__hold=str(locked.pk),
            facts__idle_since=idle_since,
        ).exists()
        if not told:
            notify(
                users=[locked.user],
                category=Category.DOCUMENT,
                event=Event.HOLD_EXPIRING,
                document=locked.document,
                facts={"hold": str(locked.pk), "idle_since": idle_since},
            )

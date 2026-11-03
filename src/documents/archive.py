"""Archiving and restoring a document (ST-0015, ST-0016, DL-0084, DL-0449): an administrator's
acts, always allowed. Archiving releases an open hold as a force release does, the draft kept for
its holder, and ends a reservation with the reason the platform writes (DL-0456); a freeze and a
pending run are archived as they stand and restored so. Links stay, and apply as they stand on
restore.

Each act takes the document's writer lock, settles its head, then decides under the row's lock
(`review.services.settle_head`, the release-wide rule)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import connection, transaction

from audit.record import record
from documents.locks import document_lock
from documents.models import Document, DocumentState
from tenancy.models import Tenant
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from identity.models import User

# The reason an archive gives the hold it releases — written by the platform, never typed: a
# reservation's end refuses it as a typed reason (DL-0456).
ARCHIVED_REASON = "archived"


class ArchiveRefused(Exception):
    """`not_allowed` — `by` no longer administers the organisation; `creating` — the document
    has not been made yet."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def archive(document: Document, by: User) -> bool:
    """Archive `document`; whether this call changed its state. `LockTimeout` while another
    writer holds the document, `RecordIncomplete` when its record cannot be settled."""
    return _act(document, by, DocumentState.ARCHIVED)


def restore(document: Document, by: User) -> bool:
    """Bring an archived `document` back, exactly as it was; whether this call changed it."""
    return _act(document, by, DocumentState.ACTIVE)


def _act(document: Document, by: User, to: str) -> bool:
    from editing.holds import LOCK_WAIT_SECONDS
    from review.services import settle_head

    if connection.in_atomic_block:
        raise RuntimeError("an archive settles the record first; call it outside a transaction")
    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("a document is archived inside its organisation's schema")
    tenant = Tenant.objects.get(number=number)
    with document_lock(number, document.number, timeout=LOCK_WAIT_SECONDS):
        settle_head(document)
        with transaction.atomic():
            locked = Document.objects.select_for_update(of=("self",)).get(pk=document.pk)
            from identity.blocking import administers

            if not administers(by, tenant.pk):
                raise ArchiveRefused("not_allowed")
            if locked.state == DocumentState.CREATING:
                raise ArchiveRefused("creating")
            if locked.state == to:
                return False
            if to == DocumentState.ARCHIVED:
                _release_the_hold(locked, by)
            locked.state = to
            locked.updated_by = by
            locked.save(update_fields=["state", "updated_by", "updated_at"])
            record(
                actor=by,
                action="document.archived" if to == DocumentState.ARCHIVED else "document.restored",
                obj=locked,
                before=None,
                after={"number": locked.number},
                tenant=tenant,
            )
    document.state = to
    return True


def _release_the_hold(document: Document, by: User) -> None:
    """The open hold released as a force release releases it — the draft kept for its holder, a
    reservation ended — with the platform's reason, while the document is still active, and the
    holder told; a finish that stopped after its commit is completed instead, its reviewers told
    (DL-0414)."""
    from editing.holds import open_hold, release
    from editing.models import ReleaseKind

    hold = open_hold(document)
    if hold is None:
        return
    release(hold, ReleaseKind.FORCED, actor=by, released_by=by, reason=ARCHIVED_REASON)
    hold.refresh_from_db(fields=["release_kind"])
    if hold.release_kind != ReleaseKind.FORCED:
        # A stopped finish completed instead: the holder's version awaits review; nothing of
        # theirs was ended.
        return
    from editing.models import Draft
    from notifications.models import Category, Event
    from notifications.services import notify, others

    # An empty hold keeps nothing (DL-0514): the entry promises a kept draft only where one is.
    kept = Draft.objects.filter(hold=hold).exists()

    # No document attached: the holder may no longer open it, so the entry names its number
    # and who archived it, never its title (DL-0471); nobody is told of their own act.
    notify(
        users=others([hold.user_id], by),
        category=Category.DOCUMENT,
        event=Event.DOCUMENT_ARCHIVED,
        actor=by,
        facts={"number": document.number, "by": str(by.pk), "kept": kept},
    )

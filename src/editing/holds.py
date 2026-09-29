"""Taking and releasing a hold (ADR-0006).

A hold is opened under the document's writer lock and, inside it, with the document's row locked by
`select_for_update()` — the lock under which its group links change — and the right to edit is
decided there, so a link removed while the taker waited is seen. The draft starts as the head's
text: the frontmatter kept apart, the body what every editor, the validator and the normalizer see.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from django.db import connection, transaction
from django.utils import timezone

from access.rights import Right, rights_on
from audit.record import record
from documents import bundle, gitstore
from documents.locks import document_lock
from documents.models import Document, DocumentState
from editing.models import Draft, Hold, ReleaseKind
from tenancy.models import Tenant
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from identity.models import User

BODY = "document.md"
FRONTMATTER = "frontmatter"
# How long a request waits for a document's writer lock before it answers that the document is
# busy; a commit or a backup holds it for seconds at most.
LOCK_WAIT_SECONDS = 10.0


class HeldByOther(Exception):
    """Someone else holds the document."""


class NotEditable(Exception):
    """The person may not edit the document, or it is not open to editing, as the locks see it."""


def split(document_md: str) -> tuple[dict[str, Any], str]:
    """`document.md` as the draft keeps it: its frontmatter as data, and its body."""
    frontmatter, body = bundle.parse(document_md)
    return asdict(frontmatter), body


def join(frontmatter: dict[str, Any], body: str) -> str:
    """`document.md` again, byte for byte as the platform writes it."""
    return bundle.render(bundle.Frontmatter(**frontmatter), body)


def open_hold(document: Document) -> Hold | None:
    return Hold.objects.filter(document=document, released_at__isnull=True).first()


def tenant_number() -> int:
    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("a hold is taken inside a tenant's schema")
    return number


def take(document: Document, user: User) -> Hold:
    """The user's hold on `document` with its draft — the open one when they already hold it;
    `HeldByOther` when someone else does; `NotEditable` when, under the locks, they may not edit
    it or it is not active. `documents.locks.LockTimeout` when the lock stays busy."""
    number = tenant_number()
    with (
        document_lock(number, document.number, timeout=LOCK_WAIT_SECONDS),
        transaction.atomic(),
    ):
        locked = Document.objects.select_for_update().get(pk=document.pk)
        if locked.state != DocumentState.ACTIVE or Right.EDIT not in rights_on(user, locked):
            raise NotEditable(locked.number)
        existing = open_hold(locked)
        if existing is not None:
            if existing.user_id != user.pk:
                raise HeldByOther(locked.number)
            return existing
        repo = gitstore.open_repository(number, locked.number)
        base = gitstore.head(repo)
        if base is None:
            raise RuntimeError(f"document {locked.number} has no commit to edit")
        frontmatter, body = split(gitstore.read(repo, BODY, base).decode("utf-8"))
        now = timezone.now()
        hold = Hold.objects.create(
            document=locked, user=user, acquired_at=now, last_activity_at=now
        )
        Draft.objects.create(
            hold=hold, base_commit=base, content={BODY: body, FRONTMATTER: frontmatter}
        )
    return hold


def release(
    hold: Hold,
    kind: ReleaseKind,
    *,
    actor: User | None = None,
    released_by: User | None = None,
    reason: str = "",
) -> bool:
    """End `hold`, keeping its draft (ADR-0003); whether this call ended it. The caller holds the
    document's writer lock and, inside a transaction, its row lock, as `take` does, so a release
    never falls between the steps of a commit. `released_by` is who forced or blocked it, when
    someone did; `actor` is who acted, for the audit trail, `None` for the platform or an
    operator's command. Audited with the document's number, never a title."""
    locked = Hold.objects.select_for_update().get(pk=hold.pk)
    if locked.released_at is not None:
        return False
    locked.released_at = timezone.now()
    locked.release_kind = kind
    locked.released_by = released_by
    locked.release_reason = reason
    locked.save(update_fields=["released_at", "release_kind", "released_by", "release_reason"])
    document = Document.objects.get(pk=locked.document_id)
    record(
        actor=actor,
        action="document.hold_released",
        obj=document,
        before=None,
        after={"number": document.number, "release_kind": kind.value, "reason": reason},
        tenant=Tenant.objects.get(number=tenant_number()),
    )
    return True

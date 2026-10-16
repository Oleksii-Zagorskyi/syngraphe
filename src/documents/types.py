"""The organisation's own document types (DL-0235): added, renamed and retired by its
administrators; deleted only while no document names one. A label is the organisation's data,
never a catalogue string (DL-0310)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from audit.record import record
from documents.bundle import valid_title
from documents.models import Document, DocumentState, DocumentType
from syngraphe.provenance import ActorKind
from tenancy.models import Tenant
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from identity.models import User

LABEL_MAX = 100
# The type every organisation starts with: what loading and the reconciler's recovery give a
# document, so it is renamed and retired but never deleted (DL-10-002).
SEEDED = "document"


class TypeRefused(Exception):
    """An act on a type refused; `reason` is one of `label_invalid`, `label_taken`, `in_use`,
    `retired`, `archived`, `unchanged`, `last_type`; `gone` for a type another act deleted after
    the caller found it; `not_allowed` once `by` no longer administers the organisation;
    `seeded` for the seeded type's deletion."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _tenant() -> Tenant:
    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("document types are changed inside an organisation's schema")
    return Tenant.objects.get(number=number)


def _label(label: str, *, other_than: DocumentType | None = None) -> str:
    """`label` stripped when it is one printable line of 1 to 100 characters that no other type of
    the organisation carries, retired ones included, in any case."""
    label = label.strip()
    if not label or len(label) > LABEL_MAX or not valid_title(label):
        raise TypeRefused("label_invalid")
    others = DocumentType.objects.exclude(pk=other_than.pk) if other_than else DocumentType.objects
    folded = label.casefold()
    if any(str(taken).casefold() == folded for taken in others.values_list("label", flat=True)):
        raise TypeRefused("label_taken")
    return label


def _still_administers(by: User) -> None:
    """`by`'s authority read again under the act's locks, never from the request that queued the
    act, so a block that lands while it waits stops it."""
    from identity.blocking import administers

    if not administers(by, _tenant().pk):
        raise TypeRefused("not_allowed")


def _found(rows: Any, kind: DocumentType) -> DocumentType:
    """`kind` read again under the caller's lock; `gone` once another act deleted it."""
    found = rows.filter(pk=kind.pk).first()
    if found is None:
        raise TypeRefused("gone")
    return cast(DocumentType, found)


def _audit(action: str, kind: DocumentType, by: User) -> None:
    record(
        actor=by, action=action, obj=kind, before=None, after={"code": kind.code}, tenant=_tenant()
    )


def is_last(kind: DocumentType) -> bool:
    """Whether `kind` is the organisation's last type not retired: the create and copy dialogs
    always offer a type, so it is neither retired nor deleted (DL-10-001)."""
    return (
        kind.retired_at is None
        and not DocumentType.objects.filter(retired_at__isnull=True).exclude(pk=kind.pk).exists()
    )


def deletable(kind: DocumentType, documents: int) -> bool:
    """Whether the page offers `kind`'s *Delete*: no document carries it and it is not the seed."""
    return documents == 0 and kind.code != SEEDED


def in_use(kind: DocumentType) -> bool:
    """Whether any document row, in any state, names `kind` — what the `PROTECT` key refuses."""
    return Document.objects.filter(document_type=kind).exists()


def add_type(label: str, by: User) -> DocumentType:
    """A new type labelled `label`, its code generated and never shown."""
    try:
        with transaction.atomic():
            _still_administers(by)
            # Two administrators adding one label at once: the constraint refuses the second.
            kind = DocumentType.objects.create(
                code=f"type-{uuid.uuid4().hex[:12]}",
                label=_label(label),
                created_by=by,
                actor_kind=ActorKind.USER,
            )
            _audit("document_type.added", kind, by)
    except IntegrityError:
        raise TypeRefused("label_taken") from None
    return kind


def rename_type(kind: DocumentType, label: str, by: User) -> None:
    try:
        with transaction.atomic():
            locked = _found(DocumentType.objects.select_for_update(of=("self",)), kind)
            _still_administers(by)
            locked.label = _label(label, other_than=locked)
            locked.updated_by = by
            locked.save(update_fields=["label", "updated_by", "updated_at"])
            _audit("document_type.renamed", locked, by)
    except IntegrityError:
        raise TypeRefused("label_taken") from None
    kind.label = locked.label


def _lock_all() -> None:
    # Retiring or deleting two types at once must not leave none: the check reads every row.
    list(DocumentType.objects.select_for_update(of=("self",)).order_by("pk"))


def retire_type(kind: DocumentType, by: User) -> None:
    """Retired, the type stays on its documents and in the filter, and is offered nowhere a
    type is chosen; not undone in release 0.1 (B-050)."""
    with transaction.atomic():
        _lock_all()
        _still_administers(by)
        locked = _found(DocumentType.objects, kind)
        if locked.retired_at is not None:
            raise TypeRefused("retired")
        if is_last(locked):
            raise TypeRefused("last_type")
        locked.retired_at = timezone.now()
        locked.updated_by = by
        locked.save(update_fields=["retired_at", "updated_by", "updated_at"])
        _audit("document_type.retired", locked, by)
    kind.retired_at = locked.retired_at


def delete_type(kind: DocumentType, by: User) -> None:
    with transaction.atomic():
        _lock_all()
        _still_administers(by)
        locked = _found(DocumentType.objects, kind)
        if is_last(locked):
            raise TypeRefused("last_type")
        if locked.code == SEEDED:
            raise TypeRefused("seeded")
        if in_use(locked):
            raise TypeRefused("in_use")
        _audit("document_type.deleted", locked, by)
        locked.delete()


def change_type(document: Document, kind: DocumentType, by: User) -> None:
    """`document` given `kind`, by an administrator. A type is metadata, as a folder is
    (ASR-15): the row lock alone, no writer lock — nothing in git or derived from it changes."""
    with transaction.atomic():
        locked = (
            Document.objects.select_for_update(of=("self",))
            .select_related("document_type")
            .get(pk=document.pk)
        )
        _still_administers(by)
        if locked.state == DocumentState.ARCHIVED:
            raise TypeRefused("archived")
        # The target's row held against a retire or a delete, which lock every type and no
        # document, so the order here — the document, then the type — never meets theirs.
        target = _found(DocumentType.objects.select_for_update(no_key=True, of=("self",)), kind)
        if target.pk == locked.document_type_id:
            raise TypeRefused("unchanged")
        if target.retired_at is not None:
            raise TypeRefused("retired")
        before = locked.document_type.code
        locked.document_type = target
        locked.updated_by = by
        locked.save(update_fields=["document_type", "updated_by", "updated_at"])
        record(
            actor=by,
            action="document.type_changed",
            obj=locked,
            before=None,
            after={"number": locked.number, "from": before, "to": target.code},
            tenant=_tenant(),
        )
    document.document_type = target

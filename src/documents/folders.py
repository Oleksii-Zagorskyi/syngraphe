"""The administrator's acts on folders (ST-0012, DL-0453): create, rename, delete an empty one,
move documents. A folder is presentation only (ADR-0008, ASR-15): no act here takes a document's
writer lock or touches its repository.

Locks, in one order across the corpus's acts — a folder, then documents, then a type, which
document creation (`services.create_document`) and the type change follow too: create and rename
hold the parent's row, so two siblings never pass the name check
together, rename after the folder's own row, so a rename and a delete of one folder serialise;
delete holds the folder's row `FOR UPDATE` and a move the target's `FOR NO KEY UPDATE`, so a
delete and a move into the same folder serialise. No act locks a parent before its child.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db import IntegrityError, connection, transaction

from audit.record import record
from documents.bundle import valid_title
from documents.models import ROOT_FOLDER, Document, DocumentState, Folder, next_folder_number
from syngraphe.provenance import ActorKind
from tenancy.models import Tenant
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from identity.models import User

NAME_MAX = 200


class FolderRefused(Exception):
    """An act on a folder refused; `reason` is one of `name_invalid`, `name_taken`, `not_empty`
    (with `documents` and `folders`, what it holds), `root`, `archived`, `same_folder`,
    `not_in_folder` for a document no longer active in the folder it was chosen from; `gone` for
    a folder another act deleted after the caller found it; `not_allowed` once `by` no longer
    administers the organisation."""

    def __init__(self, reason: str, *, documents: int = 0, folders: int = 0) -> None:
        super().__init__(reason)
        self.reason = reason
        self.documents = documents
        self.folders = folders


def _tenant() -> Tenant:
    number = current_tenant(connection)
    if number is None:
        raise RuntimeError("folders are changed inside an organisation's schema")
    return Tenant.objects.get(number=number)


def _still_administers(by: User) -> None:
    """`by`'s authority read again under the act's locks, never from the request that queued it."""
    from identity.blocking import administers

    if not administers(by, _tenant().pk):
        raise FolderRefused("not_allowed")


def _found(rows: Any, folder: Folder) -> Folder:
    found = rows.filter(pk=folder.pk).first()
    if found is None:
        raise FolderRefused("gone")
    return cast(Folder, found)


def _locked(folder: Folder) -> Folder:
    return _found(Folder.objects.select_for_update(of=("self",)), folder)


def _lock_folder(folder: Folder) -> Folder:
    """The folder a delete reads, held `FOR UPDATE`: a move into it waits, or is waited for."""
    return _locked(folder)


def _lock_target(folder: Folder) -> Folder:
    """A move's target, held `FOR NO KEY UPDATE`: a delete of it waits, or is waited for."""
    return _found(Folder.objects.select_for_update(no_key=True, of=("self",)), folder)


def _name(name: str, parent: Folder, *, other_than: Folder | None = None) -> str:
    """`name` stripped when it is one printable line of 1 to 200 characters no sibling carries, in
    any case."""
    name = name.strip()
    if not name or len(name) > NAME_MAX or not valid_title(name):
        raise FolderRefused("name_invalid")
    siblings = Folder.objects.filter(parent=parent)
    if other_than is not None:
        siblings = siblings.exclude(pk=other_than.pk)
    folded = name.casefold()
    if any(str(taken).casefold() == folded for taken in siblings.values_list("name", flat=True)):
        raise FolderRefused("name_taken")
    return name


def holds(folder: Folder) -> tuple[int, int]:
    """What `folder` holds directly: every document row in any state — an archived one, and one
    still being created, as the `PROTECT` key counts them — and its subfolders."""
    return (
        Document.objects.filter(folder=folder).count(),
        Folder.objects.filter(parent=folder).count(),
    )


def create_folder(parent: Folder, name: str, by: User) -> Folder:
    try:
        with transaction.atomic():
            locked_parent = _locked(parent)
            _still_administers(by)
            folder = Folder.objects.create(
                number=next_folder_number(),
                parent=locked_parent,
                name=_name(name, locked_parent),
                created_by=by,
                actor_kind=ActorKind.USER,
            )
            # A folder's name is need-to-know (DL-0206): the trail keeps numbers only.
            record(
                actor=by,
                action="folder.created",
                obj=folder,
                before=None,
                after={"number": folder.number, "parent": locked_parent.number},
                tenant=_tenant(),
            )
    except IntegrityError:
        raise FolderRefused("name_taken") from None
    return folder


def rename_folder(folder: Folder, name: str, by: User) -> None:
    if folder.number == ROOT_FOLDER:
        raise FolderRefused("root")
    try:
        with transaction.atomic():
            locked = _locked(folder)
            assert locked.parent_id is not None  # only the root has none, refused above
            parent = Folder.objects.select_for_update(of=("self",)).get(pk=locked.parent_id)
            _still_administers(by)
            locked.name = _name(name, parent, other_than=locked)
            locked.updated_by = by
            locked.save(update_fields=["name", "updated_by", "updated_at"])
            record(
                actor=by,
                action="folder.renamed",
                obj=locked,
                before=None,
                after={"number": locked.number},
                tenant=_tenant(),
            )
    except IntegrityError:
        raise FolderRefused("name_taken") from None
    folder.name = locked.name


def delete_folder(folder: Folder, by: User) -> None:
    """Delete `folder` while it holds nothing; `not_empty` with what it holds otherwise."""
    if folder.number == ROOT_FOLDER:
        raise FolderRefused("root")
    with transaction.atomic():
        locked = _lock_folder(folder)
        _still_administers(by)
        documents, folders = holds(locked)
        if documents or folders:
            raise FolderRefused("not_empty", documents=documents, folders=folders)
        assert locked.parent_id is not None  # only the root has none, refused above
        parent = Folder.objects.get(pk=locked.parent_id)
        record(
            actor=by,
            action="folder.deleted",
            obj=locked,
            before=None,
            after={"number": locked.number, "parent": parent.number},
            tenant=_tenant(),
        )
        locked.delete()


def move_documents(
    documents: list[Document], to: Folder, by: User, *, source: Folder | None = None
) -> int:
    """Move `documents` to `to`, the folder alone changing; how many moved, a document already
    there skipped. Each is read again under its lock: a batch holding an archived document is
    refused whole (DL-0450), as is one holding a document not active, or no longer in `source`
    when the caller chose them from it."""
    with transaction.atomic():
        target = _lock_target(to)
        locked = list(
            Document.objects.select_for_update(of=("self",))
            .select_related("folder")
            .filter(pk__in=[d.pk for d in documents])
            .order_by("pk")
        )
        # Read once every row is held: a block that lands while the move waited stops it.
        _still_administers(by)
        if any(d.state == DocumentState.ARCHIVED for d in locked):
            raise FolderRefused("archived")
        if len(locked) != len({d.pk for d in documents}) or any(
            d.state != DocumentState.ACTIVE or (source is not None and d.folder_id != source.pk)
            for d in locked
        ):
            raise FolderRefused("not_in_folder")
        moving = [d for d in locked if d.folder_id != target.pk]
        if not moving:
            raise FolderRefused("same_folder")
        tenant = _tenant()
        for document in moving:
            before = document.folder.number
            document.folder = target
            document.updated_by = by
            document.save(update_fields=["folder", "updated_by", "updated_at"])
            record(
                actor=by,
                action="document.moved",
                obj=document,
                before=None,
                after={"number": document.number, "from": before, "to": target.number},
                tenant=tenant,
            )
    return len(moving)

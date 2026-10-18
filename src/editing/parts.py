"""A document's parts staged in its holder's draft (ADR-0005, DL-0175): appendices created, renamed,
reordered and deleted; attachments uploaded, replaced, renamed, reordered and deleted; a registered
frontmatter key changed (DL-0463). They reach the repository with the text, when the draft is
committed (`editing.services`).

Each service is an act — the document's writer lock, the head settled, the right decided under the
document's row (ADR-0007), the change written, audited — around one lock-free function,
`apply_to_draft`, which a caller already holding those locks, a revert, stages through. The draft's
lists are its frontmatter's; an appendix's text is the key `appendices/<n>.md` of its content; an
attachment's bytes, when the draft adds or replaces one, a `DraftFile` row, and otherwise the
draft's own snapshot, the file at `draft.base_commit`.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from access.rights import Right, rights_on
from audit.record import record
from documents import bundle, gitstore
from documents.loading import FILE_NAME_MAX
from documents.locks import document_lock
from documents.models import Document, DocumentState, PartIndex, PartKind
from editing import holds
from editing.markdown.serializer import esc
from editing.models import Draft, DraftFile, DraftFileKind, DraftFileOperation, Hold, OpenEditor
from tenancy.models import Tenant

if TYPE_CHECKING:
    from identity.models import User

logger = logging.getLogger(__name__)

APPENDICES = "appendices"
ATTACHMENTS = "attachments"


class PartRefused(Exception):
    """A part operation that cannot be staged: `reason` one of `not_holding`, `not_editable`,
    `frozen`, `no_right` (`detail["right"]`), `bad_title`, `bad_file_name`, `too_large`
    (`detail`: `file_name`, `size`, `limit`), `no_such_part`, `editor_open`, `bad_order`,
    `record_incomplete`, `unknown_key`, `bad_value`. Nothing is written."""

    def __init__(self, reason: str, **detail: Any) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def appendix_key(number: int) -> str:
    return f"{APPENDICES}/{number}.md"


def attachment_path(number: int) -> str:
    return f"{ATTACHMENTS}/{number}"


APPENDIX_FILE = re.compile(r"appendices/([1-9][0-9]*)\.md")


def number_of(file: str) -> int | None:
    """The appendix a draft key or an editor's file names, or `None` for any other."""
    found = APPENDIX_FILE.fullmatch(file)
    return int(found.group(1)) if found else None


def lists(draft: Draft, number: int) -> bool:
    """Whether the draft's list holds appendix `number`."""
    return number in _numbers(_lists(draft)[APPENDICES])


def _repo(draft: Draft) -> Any:
    return gitstore.open_repository(holds.tenant_number(), draft.hold.document.number)


def _lists(draft: Draft) -> dict[str, list[dict[str, Any]]]:
    frontmatter = draft.content[holds.FRONTMATTER]
    return {key: list(frontmatter.get(key, [])) for key in (APPENDICES, ATTACHMENTS)}


def _numbers(entries: list[dict[str, Any]]) -> list[int]:
    return [int(entry["number"]) for entry in entries]


def appendix_text(draft: Draft, number: int, repo: Any = None) -> str:
    """Appendix `number`'s text as the draft holds it; a listed appendix the draft holds no key
    for — a draft taken before appendices were loaded into it — reads as `draft.base_commit` has
    it. Every reader of a draft's appendix reads it here."""
    key = appendix_key(number)
    if key in draft.content:
        return str(draft.content[key])
    try:
        return gitstore.read(repo or _repo(draft), key, draft.base_commit).decode("utf-8")
    except KeyError:
        # Listed without its file, which the reconciler reports (`part_missing`): the empty
        # text, which the appendix's own rules then name.
        return ""


def head_lists(draft: Draft, repo: Any = None) -> dict[str, list[dict[str, Any]]]:
    """The part lists of the document's head — the side the commit judges a draft against."""
    repo = repo or _repo(draft)
    head = gitstore.head(repo)
    if head is None:
        raise RuntimeError("a draft of a document without a commit")
    frontmatter, _ = bundle.parse(gitstore.read(repo, holds.BODY, head).decode("utf-8"))
    return {APPENDICES: frontmatter.appendices, ATTACHMENTS: frontmatter.attachments}


# Marks that change the order a name is displayed in, so it would read as another name.
DIRECTION = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def valid_file_name(name: str) -> str | None:
    """`name` as an attachment's file name — NFC, one printable line beside the text, within the
    length the index holds, displayed in the order it is stored — or `None`; the loader's rule
    (`documents.loading`), and no direction control."""
    name = unicodedata.normalize("NFC", name)
    if "/" in name or "\\" in name or name.startswith(".") or DIRECTION.search(name):
        return None
    if not bundle.valid_title(name) or len(name) > FILE_NAME_MAX:
        return None
    return name


def upload_limit() -> int:
    """The largest attachment this organisation accepts: its own cap, never past the platform's
    upload maximum (DL-0432, DL-0469)."""
    tenant = Tenant.objects.get(number=holds.tenant_number())
    return min(tenant.attachment_max_bytes, settings.UPLOAD_MAX_BYTES)


def _next_number(draft: Draft, kind: str) -> int:
    """One past every number the document ever gave a part of `kind` and every number the draft
    holds for one (ADR-0008): a committed number is never given again."""
    index_kind = PartKind.APPENDIX if kind == APPENDICES else PartKind.ATTACHMENT
    used = list(
        PartIndex.objects.filter(document_id=draft.hold.document_id, kind=index_kind).values_list(
            "part_number", flat=True
        )
    )
    used += _numbers(_lists(draft)[kind])
    if kind == APPENDICES:
        used += [
            int(key.removeprefix(f"{APPENDICES}/").removesuffix(".md"))
            for key in draft.content
            if key.startswith(f"{APPENDICES}/") and key.removesuffix(".md")[11:].isdigit()
        ]
    else:
        used += [
            int(path.removeprefix(f"{ATTACHMENTS}/"))
            for path in draft.files.filter(kind=DraftFileKind.ATTACHMENT).values_list(
                "path", flat=True
            )
            if path.removeprefix(f"{ATTACHMENTS}/").isdigit()
        ]
    return max(used, default=0) + 1


def _entry(entries: list[dict[str, Any]], number: int) -> dict[str, Any]:
    for entry in entries:
        if int(entry["number"]) == number:
            return entry
    raise PartRefused("no_such_part", number=number)


def _reordered(entries: list[dict[str, Any]], order: list[int]) -> list[dict[str, Any]]:
    if sorted(order) != sorted(_numbers(entries)) or len(set(order)) != len(order):
        raise PartRefused("bad_order")
    by_number = {int(entry["number"]): entry for entry in entries}
    return [by_number[number] for number in order]


def _editor_open(draft: Draft, number: int) -> bool:
    return OpenEditor.objects.filter(
        draft=draft, file=appendix_key(number), closed_at__isnull=True
    ).exists()


def _rows(draft: Draft, number: int) -> Any:
    return draft.files.filter(kind=DraftFileKind.ATTACHMENT, path=attachment_path(number))


def _stage_bytes(draft: Draft, number: int, operation: str, file_name: str, data: bytes) -> str:
    """The attachment's bytes in one row of `operation`, the row rewritten where one exists."""
    digest = hashlib.sha256(data).hexdigest()
    row = _rows(draft, number).filter(operation=operation).first()
    if row is None:
        DraftFile.objects.create(
            draft=draft,
            kind=DraftFileKind.ATTACHMENT,
            path=attachment_path(number),
            operation=operation,
            content=data,
            file_name=file_name,
            sha256=digest,
            at=timezone.now(),
        )
    else:
        row.content = data
        row.file_name = file_name
        row.sha256 = digest
        row.at = timezone.now()
        row.save(update_fields=["content", "file_name", "sha256", "at"])
    return digest


def _described(entry: dict[str, Any], file_name: str, data: bytes, digest: str) -> None:
    # The list always describes the file the commit will write.
    entry.update(file_name=file_name, sha256=digest, bytes=len(data))


def apply_to_draft(draft: Draft, operation: str, **fields: Any) -> int | None:
    """Change `draft`, which the caller has locked with its hold and document, by `operation`:
    `create_appendix` (`title`), `rename_appendix` (`number`, `title`), `delete_appendix`
    (`number`), `reorder_appendices` (`order`), `add_attachment` (`title`, `file_name`, `data`),
    `replace_attachment` (`number`, `file_name`, `data`), `rename_attachment` (`number`, `title`),
    `delete_attachment` (`number`), `reorder_attachments` (`order`), `set_frontmatter` (`key`,
    `value`), `restore_appendix` (`number`, `title`, `text`, `position`) and `restore_attachment`
    (`number`, `entry`, `data`, `position`) — a restore puts the part back under its own number at
    its 1-based `position`, clamped to the list's end. Checks no right and audits nothing; refuses
    `no_such_part`, `bad_order`, and `editor_open` for dropping an appendix an editor has open.
    The new part's number for a creation or an upload; `None` otherwise."""
    content = copy.deepcopy(draft.content)
    frontmatter = content[holds.FRONTMATTER]
    appendices: list[dict[str, Any]] = frontmatter.setdefault(APPENDICES, [])
    attachments: list[dict[str, Any]] = frontmatter.setdefault(ATTACHMENTS, [])
    made: int | None = None
    if operation == "create_appendix":
        made = _next_number(draft, APPENDICES)
        appendices.append({"number": made, "title": fields["title"]})
        content[appendix_key(made)] = f"# {esc(fields['title'], False)}\n"
    elif operation == "rename_appendix":
        _entry(appendices, fields["number"])["title"] = fields["title"]
    elif operation == "delete_appendix":
        number = fields["number"]
        appendices.remove(_entry(appendices, number))
        if _editor_open(draft, number):
            raise PartRefused("editor_open", number=number)
        content.pop(appendix_key(number), None)
    elif operation == "reorder_appendices":
        frontmatter[APPENDICES] = _reordered(appendices, fields["order"])
    elif operation == "restore_appendix":
        number = fields["number"]
        appendices[:] = [e for e in appendices if int(e["number"]) != number]
        at = max(int(fields["position"]), 1) - 1
        appendices.insert(at, {"number": number, "title": fields["title"]})
        content[appendix_key(number)] = fields["text"]
    elif operation == "add_attachment":
        made = _next_number(draft, ATTACHMENTS)
        digest = _stage_bytes(
            draft, made, DraftFileOperation.ADD, fields["file_name"], fields["data"]
        )
        entry = {"number": made, "title": fields["title"]}
        _described(entry, fields["file_name"], fields["data"], digest)
        attachments.append(entry)
    elif operation == "replace_attachment":
        number = fields["number"]
        entry = _entry(attachments, number)
        added = _rows(draft, number).filter(operation=DraftFileOperation.ADD).exists()
        kind = DraftFileOperation.ADD if added else DraftFileOperation.REPLACE
        digest = _stage_bytes(draft, number, kind, fields["file_name"], fields["data"])
        _described(entry, fields["file_name"], fields["data"], digest)
    elif operation == "rename_attachment":
        _entry(attachments, fields["number"])["title"] = fields["title"]
    elif operation == "delete_attachment":
        number = fields["number"]
        attachments.remove(_entry(attachments, number))
        rows = _rows(draft, number)
        if rows.filter(operation=DraftFileOperation.ADD).exists():
            rows.delete()
        else:
            rows.exclude(operation=DraftFileOperation.REMOVE).delete()
            if not rows.exists():
                DraftFile.objects.create(
                    draft=draft,
                    kind=DraftFileKind.ATTACHMENT,
                    path=attachment_path(number),
                    operation=DraftFileOperation.REMOVE,
                    content=None,
                    at=timezone.now(),
                )
    elif operation == "reorder_attachments":
        frontmatter[ATTACHMENTS] = _reordered(attachments, fields["order"])
    elif operation == "restore_attachment":
        number = fields["number"]
        attachments[:] = [e for e in attachments if int(e["number"]) != number]
        _rows(draft, number).delete()
        entry = dict(fields["entry"], number=number)
        digest = _stage_bytes(
            draft, number, DraftFileOperation.ADD, str(entry["file_name"]), fields["data"]
        )
        _described(entry, str(entry["file_name"]), fields["data"], digest)
        attachments.insert(max(int(fields["position"]), 1) - 1, entry)
    elif operation == "set_frontmatter":
        frontmatter[fields["key"]] = fields["value"]
    else:
        raise ValueError(f"no part operation {operation!r}")
    draft.content = content
    draft.save(update_fields=["content", "updated_at"])
    return made


# --- the acts ---------------------------------------------------------------------------------


def _act(
    document: Document,
    user: User,
    action: str,
    stage: Callable[[Draft, frozenset[Right]], tuple[Any, dict[str, Any]]],
) -> Any:
    """Under the document's writer lock, the head settled, in one transaction: the document's row,
    the rights and state decided there, the caller's own open hold and its draft locked; `stage`
    checks what its operation needs and writes it, answering the result and the audit's fields."""
    from editions.models import open_freeze
    from review.services import RecordIncomplete, settle_head

    tenant_number = holds.tenant_number()
    with document_lock(tenant_number, document.number, timeout=holds.LOCK_WAIT_SECONDS):
        try:
            settle_head(document)
        except RecordIncomplete as incomplete:
            raise PartRefused("record_incomplete") from incomplete
        with transaction.atomic():
            locked = Document.objects.select_for_update(of=("self",)).get(pk=document.pk)
            rights = rights_on(user, locked)
            if locked.state != DocumentState.ACTIVE or Right.EDIT not in rights:
                raise PartRefused("not_editable")
            if open_freeze(locked) is not None and Right.ACCEPT not in rights:
                raise PartRefused("frozen")
            hold = holds.open_hold(locked)
            if hold is None or hold.user_id != user.pk:
                raise PartRefused("not_holding")
            hold = Hold.objects.select_for_update(of=("self",)).get(pk=hold.pk)
            draft = Draft.objects.select_for_update(of=("self",)).get(hold=hold)
            result, after = stage(draft, rights)
            hold.last_activity_at = timezone.now()
            hold.save(update_fields=["last_activity_at"])
            record(
                actor=user,
                action=action,
                obj=locked,
                before=None,
                after={"number": locked.number, **after},
                tenant=Tenant.objects.get(number=tenant_number),
            )
    return result


def _needs(rights: frozenset[Right], right: Right) -> None:
    if right not in rights:
        raise PartRefused("no_right", right=right)


def _title(title: str) -> str:
    if not isinstance(title, str) or not bundle.valid_title(title):
        raise PartRefused("bad_title")
    return title


def _file(file_name: str, data: bytes) -> str:
    name = valid_file_name(file_name) if isinstance(file_name, str) else None
    if name is None:
        raise PartRefused("bad_file_name")
    limit = upload_limit()
    if len(data) > limit:
        raise PartRefused("too_large", file_name=name, size=len(data), limit=limit)
    return name


def _staged(number: int, **more: Any) -> dict[str, Any]:
    return {"part": number, "staged": True, **more}


def create_appendix(document: Document, user: User, *, title: str) -> int:
    """A new appendix at the end of the draft's list, its text its title as its one heading."""

    def stage(draft: Draft, rights: frozenset[Right]) -> tuple[Any, dict[str, Any]]:
        _needs(rights, Right.CREATE_APPENDIX)
        made = apply_to_draft(draft, "create_appendix", title=_title(title))
        assert made is not None
        return made, _staged(made)

    return int(_act(document, user, "appendix.created", stage))


def rename_appendix(document: Document, user: User, number: int, *, title: str) -> None:
    def stage(draft: Draft, rights: frozenset[Right]) -> tuple[Any, dict[str, Any]]:
        apply_to_draft(draft, "rename_appendix", number=number, title=_title(title))
        return None, _staged(number)

    _act(document, user, "appendix.renamed", stage)


def _added_by(draft: Draft, kind: str, number: int) -> bool:
    """Whether the draft added part `number` itself, never committed: the head does not list it
    (DL-0473) — the head, not the draft's base, which a finish stopped after its commit leaves
    behind, so the act and the commit judge one side."""
    return number not in _numbers(head_lists(draft)[kind])


def delete_appendix(document: Document, user: User, number: int) -> None:
    """The appendix and its text dropped from the draft: with *delete appendix*, or for one this
    draft created, with *create appendix* — withdrawn, never committed (DL-0473)."""

    def stage(draft: Draft, rights: frozenset[Right]) -> tuple[Any, dict[str, Any]]:
        withdrawn = _added_by(draft, APPENDICES, number)
        _needs(rights, Right.CREATE_APPENDIX if withdrawn else Right.DELETE_APPENDIX)
        apply_to_draft(draft, "delete_appendix", number=number)
        return None, _staged(number)

    _act(document, user, "appendix.deleted", stage)


def reorder_appendices(document: Document, user: User, order: list[int]) -> None:
    def stage(draft: Draft, rights: frozenset[Right]) -> tuple[Any, dict[str, Any]]:
        apply_to_draft(draft, "reorder_appendices", order=list(order))
        return None, {"staged": True, "order": list(order)}

    _act(document, user, "appendix.reordered", stage)


def upload_attachment(
    document: Document, user: User, *, title: str, file_name: str, data: bytes
) -> int:
    """A new attachment at the end of the draft's list, its bytes staged as they came: never
    parsed, rendered or sniffed (T-15)."""

    def stage(draft: Draft, rights: frozenset[Right]) -> tuple[Any, dict[str, Any]]:
        _needs(rights, Right.UPLOAD_ATTACHMENT)
        checked_title = _title(title)
        name = _file(file_name, data)
        made = apply_to_draft(
            draft, "add_attachment", title=checked_title, file_name=name, data=data
        )
        assert made is not None
        return made, _staged(made, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    return int(_act(document, user, "attachment.uploaded", stage))


def replace_attachment(
    document: Document, user: User, number: int, *, file_name: str, data: bytes
) -> None:
    def stage(draft: Draft, rights: frozenset[Right]) -> tuple[Any, dict[str, Any]]:
        _needs(rights, Right.REPLACE_ATTACHMENT)
        name = _file(file_name, data)
        apply_to_draft(draft, "replace_attachment", number=number, file_name=name, data=data)
        return None, _staged(number, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())

    _act(document, user, "attachment.replaced", stage)


def rename_attachment(document: Document, user: User, number: int, *, title: str) -> None:
    def stage(draft: Draft, rights: frozenset[Right]) -> tuple[Any, dict[str, Any]]:
        apply_to_draft(draft, "rename_attachment", number=number, title=_title(title))
        return None, _staged(number)

    _act(document, user, "attachment.renamed", stage)


def delete_attachment(document: Document, user: User, number: int) -> None:
    """The attachment dropped from the draft: with *delete attachment*, or for one this draft
    uploaded, with *upload attachment* — withdrawn, never committed (DL-0473)."""

    def stage(draft: Draft, rights: frozenset[Right]) -> tuple[Any, dict[str, Any]]:
        withdrawn = _added_by(draft, ATTACHMENTS, number)
        _needs(rights, Right.UPLOAD_ATTACHMENT if withdrawn else Right.DELETE_ATTACHMENT)
        apply_to_draft(draft, "delete_attachment", number=number)
        return None, _staged(number)

    _act(document, user, "attachment.deleted", stage)


def reorder_attachments(document: Document, user: User, order: list[int]) -> None:
    def stage(draft: Draft, rights: frozenset[Right]) -> tuple[Any, dict[str, Any]]:
        apply_to_draft(draft, "reorder_attachments", order=list(order))
        return None, {"staged": True, "order": list(order)}

    _act(document, user, "attachment.reordered", stage)


# --- frontmatter kinds (DL-0463) ----------------------------------------------------------------


@dataclass(frozen=True)
class FrontmatterKind:
    """A frontmatter key that may change in a draft: how a value is checked, and how a change from
    one value to another reads in the list of changes, already translated."""

    key: str
    valid: Callable[[Any], bool]
    describe: Callable[[Any, Any], str]


# Registered by the apps that own a key, from their `AppConfig.ready`.
FRONTMATTER_KINDS: dict[str, FrontmatterKind] = {}


def register_frontmatter_kind(kind: FrontmatterKind) -> None:
    """Admit `kind`'s key to drafts. `ValueError` for a key the frontmatter cannot hold, one the
    part services own, or one registered already."""
    if kind.key not in bundle.KEYS or kind.key in (APPENDICES, ATTACHMENTS):
        raise ValueError(f"{kind.key!r} is not a frontmatter key a draft may stage")
    if kind.key in FRONTMATTER_KINDS:
        raise ValueError(f"{kind.key!r} is registered already")
    FRONTMATTER_KINDS[kind.key] = kind


def stage_frontmatter(document: Document, user: User, key: str, value: Any) -> None:
    """A registered key's new value in the holder's draft, with *edit* alone."""

    def stage(draft: Draft, rights: frozenset[Right]) -> tuple[Any, dict[str, Any]]:
        kind = FRONTMATTER_KINDS.get(key)
        if kind is None:
            raise PartRefused("unknown_key", key=key)
        if not kind.valid(value):
            raise PartRefused("bad_value", key=key)
        apply_to_draft(draft, "set_frontmatter", key=key, value=value)
        return None, {"key": key, "value": value}

    _act(document, user, "frontmatter.staged", stage)


@dataclass(frozen=True)
class FrontmatterChange:
    key: str
    older: Any
    newer: Any
    words: str


def frontmatter_changes(older: dict[str, Any], newer: dict[str, Any]) -> list[FrontmatterChange]:
    """One change per registered key whose value differs between two frontmatters."""
    return [
        FrontmatterChange(
            key, older.get(key), newer.get(key), kind.describe(older.get(key), newer.get(key))
        )
        for key, kind in FRONTMATTER_KINDS.items()
        if older.get(key) != newer.get(key)
    ]


# --- reads --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DraftParts:
    """The draft's lists, each entry as the frontmatter holds it; an attachment the draft adds or
    replaces carries `staged`."""

    appendices: list[dict[str, Any]]
    attachments: list[dict[str, Any]]


def draft_parts(draft: Draft) -> DraftParts:
    lists = _lists(draft)
    staged = set(
        draft.files.filter(
            kind=DraftFileKind.ATTACHMENT,
            operation__in=(DraftFileOperation.ADD, DraftFileOperation.REPLACE),
        ).values_list("path", flat=True)
    )
    return DraftParts(
        appendices=[dict(entry) for entry in lists[APPENDICES]],
        attachments=[
            {**entry, "staged": attachment_path(int(entry["number"])) in staged}
            for entry in lists[ATTACHMENTS]
        ],
    )


def draft_attachment(draft: Draft, number: int, repo: Any = None) -> tuple[dict[str, Any], bytes]:
    """Attachment `number` as the draft lists it, and its bytes: staged in the draft, or else the
    file at `draft.base_commit` — the draft's own snapshot, never the head's, which another holder
    may have changed since. `KeyError` for a number the draft does not list, `ValueError` when the
    bytes are not the ones the entry describes."""
    entry = next((e for e in _lists(draft)[ATTACHMENTS] if int(e["number"]) == number), None)
    if entry is None:
        raise KeyError(number)
    row = (
        _rows(draft, number)
        .filter(operation__in=(DraftFileOperation.ADD, DraftFileOperation.REPLACE))
        .first()
    )
    if row is not None and row.content is not None:
        data = bytes(row.content)
    else:
        data = gitstore.read(repo or _repo(draft), attachment_path(number), draft.base_commit)
    if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
        logger.error(
            "a draft's attachment does not match its listed hash",
            extra={"draft": str(draft.pk), "attachment": number},
        )
        raise ValueError(number)
    return dict(entry), data


# --- the changes a reader is shown -----------------------------------------------------------


@dataclass(frozen=True)
class AppendixChange:
    """An appendix whose text differs between two sides: `older` empty for one added, `newer`
    empty for one removed."""

    number: int
    title: str
    older: str
    newer: str


@dataclass(frozen=True)
class PartChanges:
    """What changed in the parts between two sides, beside the body: each appendix's text, the
    part operations (`documents.parts.part_operations`) and each registered frontmatter key."""

    appendices: list[AppendixChange]
    operations: list[Any]
    frontmatter: list[FrontmatterChange]

    def __bool__(self) -> bool:
        return bool(self.appendices or self.operations or self.frontmatter)


Side = tuple[dict[str, Any], dict[int, str]]


def side_at(repo: Any, commit: str) -> Side:
    """A commit's frontmatter, as data, and the text of each appendix it lists."""
    frontmatter, _ = holds.split(gitstore.read(repo, holds.BODY, commit).decode("utf-8"))
    texts = {}
    for entry in frontmatter.get(APPENDICES, []):
        number = int(entry["number"])
        try:
            texts[number] = gitstore.read(repo, appendix_key(number), commit).decode("utf-8")
        except KeyError:
            texts[number] = ""
    return frontmatter, texts


def draft_side(draft: Draft, texts: Callable[[int], str] | None = None) -> Side:
    """A draft's frontmatter and its appendices' texts, each through `texts` — as the commit will
    write it — or as the draft holds it."""
    frontmatter = draft.content[holds.FRONTMATTER]
    read = texts or (lambda number: appendix_text(draft, number))
    return frontmatter, {int(e["number"]): read(int(e["number"])) for e in frontmatter[APPENDICES]}


def changes_between(older: Side, newer: Side) -> PartChanges:
    """What changed from `older` to `newer`: each appendix whose text differs — in the newer
    side's list order, then those only the older lists — the part operations and the registered
    frontmatter keys."""
    from documents.parts import part_operations

    old_fm, old_texts = older
    new_fm, new_texts = newer
    titles = {int(e["number"]): str(e["title"]) for e in old_fm.get(APPENDICES, [])}
    titles |= {int(e["number"]): str(e["title"]) for e in new_fm.get(APPENDICES, [])}
    order = [int(e["number"]) for e in new_fm.get(APPENDICES, [])]
    order += [n for n in (int(e["number"]) for e in old_fm.get(APPENDICES, [])) if n not in order]
    appendices = [
        AppendixChange(n, titles[n], old_texts.get(n, ""), new_texts.get(n, ""))
        for n in order
        if old_texts.get(n, "") != new_texts.get(n, "")
    ]
    operations = part_operations(
        (old_fm.get(APPENDICES, []), old_fm.get(ATTACHMENTS, [])),
        (new_fm.get(APPENDICES, []), new_fm.get(ATTACHMENTS, [])),
    )
    return PartChanges(appendices, operations, frontmatter_changes(old_fm, new_fm))


def drawn(
    changes: PartChanges,
    context: Any,
    *,
    older_file: Callable[[int], str | None],
    newer_file: Callable[[int], str | None],
    appendix_link: Callable[[int], str],
    authors: dict[int, dict[int, str]] | None = None,
) -> dict[str, Any]:
    """What the part changes partial draws: each changed appendix's changes marked in place,
    rendered with the page's `context` — its lines attributed by `authors[number]` where given —
    and a row per part operation and frontmatter change, an attachment's files linked on each
    side it is on."""
    from django.utils.safestring import mark_safe

    from editing.diffview import render_changes

    appendices = [
        {
            "number": change.number,
            "title": change.title,
            # Built from text the whitelist accepted, by the renderer that escapes it.
            "changes": mark_safe(  # noqa: S308
                render_changes(
                    change.older.encode("utf-8"),
                    change.newer.encode("utf-8"),
                    authors=(authors or {}).get(change.number),
                    context=context,
                )
            ),
        }
        for change in changes.appendices
    ]
    rows = []
    for operation in changes.operations:
        if operation.change == "reordered":
            lists = "appendices" if operation.kind == "appendix" else "attachments"
            rows.append({"kind": operation.kind, "change": "reordered", "part": lists})
            continue
        entry = operation.newer or operation.older or {}
        attachment = operation.kind == "attachment"
        rows.append(
            {
                "kind": operation.kind,
                "change": operation.change,
                # What a revert names the row by (`review.revert`).
                "part": f"{operation.kind}:{operation.number}",
                "title": entry.get("title", ""),
                "older_title": (operation.older or {}).get("title", ""),
                "old": older_file(operation.number) if attachment and operation.older else None,
                "new": newer_file(operation.number) if attachment and operation.newer else None,
                "open": appendix_link(operation.number)
                if not attachment and operation.newer
                else None,
            }
        )
    return {
        "part_appendices": appendices,
        "part_rows": rows,
        "frontmatter_rows": [
            {"words": change.words, "part": f"frontmatter:{change.key}", "change": "changed"}
            for change in changes.frontmatter
        ],
    }

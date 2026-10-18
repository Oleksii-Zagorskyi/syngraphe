"""Reverting a part operation of the pending run (ST-0063, DL-0446, ADR-0001): a holder of *accept*
puts one part back as the run's base had it — an attachment added, removed, replaced or renamed,
an appendix added, removed or renamed, a list reordered, a registered frontmatter key — by staging
the inverse in their own draft, which joins their correction; *accept* alone suffices, and the
commit exempts the inverse from the part's own right while the draft still holds it. A part the
reviewer's draft has already changed is not reverted over it (DL-0474). While a revert waits in a
draft, the run is accepted only through it, with *accept as*, as an undo's is (DL-0427).
"""

from __future__ import annotations

import copy
import re
from typing import Any

from documents.parts import part_operations

# The forms a revert names: a part, a list's order, or a registered frontmatter key.
PART = re.compile(
    r"(appendix|attachment):([1-9][0-9]{0,9})|(appendices|attachments)|frontmatter:([a-z_]{1,40})"
)
HEAD = re.compile(r"[0-9a-f]{40}")
CHANGES = {
    "appendix": ("added", "removed", "renamed"),
    "attachment": ("added", "removed", "replaced", "renamed"),
}
REVERT = "revert"
FILE = ("sha256", "bytes", "file_name")


class RevertRefused(Exception):
    """A revert the document's state does not allow; `reason` names why: `not_a_reviewer`,
    `reserved`, `held`, `draft_kept`, `run_changed`, `nothing_to_revert`, `changed_in_draft` or
    `editor_open`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def well_formed(part: str, change: str, head: str) -> bool:
    """Whether the three fields name a revert at all: a part of the forms above, a change it can
    have had, a head's full id."""
    found = PART.fullmatch(part)
    if found is None or not HEAD.fullmatch(head):
        return False
    kind, _, lists, key = found.groups()
    if key is not None:
        return change == "changed"
    if lists is not None:
        return change == "reordered"
    return change in CHANGES[kind]


def refusal(document: Any, reviewer: Any) -> str | None:
    """What stops `reviewer` reverting anything on `document` now, as it stops an undo: no
    *accept*, a reservation — the reviewer's own included — someone else holding, or a kept draft
    of the reviewer's own."""
    from review import undo

    return undo.refusal(document, reviewer)


def _kind_and_number(part: str) -> tuple[str, int | None, str | None]:
    found = PART.fullmatch(part)
    assert found is not None
    kind, number, lists, key = found.groups()
    if key is not None:
        return "frontmatter", None, key
    if lists is not None:
        return ("appendix" if lists == "appendices" else "attachment"), None, None
    return kind, int(number), None


def _entries(frontmatter: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return list(frontmatter.get("appendices" if kind == "appendix" else "attachments", []))


def _entry(frontmatter: dict[str, Any], kind: str, number: int) -> dict[str, Any] | None:
    return next((e for e in _entries(frontmatter, kind) if int(e["number"]) == number), None)


def _property(
    frontmatter: dict[str, Any], kind: str, number: int | None, change: str, key: str | None
) -> Any:
    """The one property a row of `change` is about, as `frontmatter` holds it: the part's
    presence, its file, its title, the list's numbers in order, or a key's value."""
    if kind == "frontmatter":
        return frontmatter.get(key or "")
    if change == "reordered":
        return [int(e["number"]) for e in _entries(frontmatter, kind)]
    entry = _entry(frontmatter, kind, number or 0)
    if change in ("added", "removed"):
        return entry is not None
    if entry is None:
        return None
    if change == "replaced":
        return tuple(entry.get(k) for k in FILE)
    return entry.get("title")


def _same_order(one: list[int], other: list[int], among: set[int]) -> bool:
    return [n for n in one if n in among] == [n for n in other if n in among]


def _reverted_head(head_fm: dict[str, Any], base_fm: dict[str, Any], records: list[Any]) -> Any:
    """The head's frontmatter with the reverts already in the draft applied: what the draft is
    expected to hold where nothing else changed it."""
    expected = copy.deepcopy(head_fm)
    for record in records:
        kind, number, key = _kind_and_number(str(record.get("part", "")))
        change = str(record.get("change", ""))
        if kind == "frontmatter":
            expected[key or ""] = base_fm.get(key or "")
            continue
        name = "appendices" if kind == "appendix" else "attachments"
        listed = expected.setdefault(name, [])
        if change == "reordered":
            base_order = [int(e["number"]) for e in _entries(base_fm, kind)]
            common = [e for e in listed if int(e["number"]) in base_order]
            common.sort(key=lambda e: base_order.index(int(e["number"])))
            slots = iter(common)
            expected[name] = [next(slots) if int(e["number"]) in base_order else e for e in listed]
            continue
        base_entry = _entry(base_fm, kind, number or 0)
        here = next((e for e in listed if int(e["number"]) == number), None)
        if change == "added":
            listed[:] = [e for e in listed if int(e["number"]) != number]
        elif change == "removed" and base_entry is not None and here is None:
            position = [int(e["number"]) for e in _entries(base_fm, kind)].index(number or 0)
            listed.insert(position, dict(base_entry))
        elif here is not None and base_entry is not None:
            # Each revert puts back its own property alone: a part both replaced and renamed
            # is reverted row by row, in either order.
            for field in FILE if change == "replaced" else ("title",):
                here[field] = base_entry.get(field)
    return expected


def _ran(
    older: Any, newer: Any, kind: str, number: int | None, change: str, key: str | None
) -> bool:
    """Whether the run made this change: the row is one of its part operations, or a registered
    key whose value differs."""
    from editing import parts

    if kind == "frontmatter":
        return key in parts.FRONTMATTER_KINDS and older[0].get(key) != newer[0].get(key)
    operations = part_operations(
        (older[0].get("appendices", []), older[0].get("attachments", [])),
        (newer[0].get("appendices", []), newer[0].get("attachments", [])),
    )
    return any(o.kind == kind and o.number == number and o.change == change for o in operations)


def _stage(
    draft: Any,
    repo: Any,
    base_sha: str,
    base: Any,
    kind: str,
    number: int | None,
    change: str,
    key: str | None,
) -> Any:
    """The inverse of the row staged in the locked draft; the entry it leaves in the draft's list,
    `None` for a removal or a list's order."""
    from documents import gitstore
    from editing import parts

    base_fm, base_texts = base
    if kind == "frontmatter":
        parts.apply_to_draft(draft, "set_frontmatter", key=key, value=base_fm.get(key or ""))
        return base_fm.get(key or "")
    if change == "reordered":
        listed = _entries(draft.content["frontmatter"], kind)
        base_order = [int(e["number"]) for e in _entries(base_fm, kind)]
        numbers = [int(e["number"]) for e in listed]
        common = sorted((n for n in numbers if n in base_order), key=base_order.index)
        slots = iter(common)
        order = [next(slots) if n in base_order else n for n in numbers]
        operation = "reorder_appendices" if kind == "appendix" else "reorder_attachments"
        parts.apply_to_draft(draft, operation, order=order)
        return None
    assert number is not None
    base_entry = _entry(base_fm, kind, number)
    position = (
        [int(e["number"]) for e in _entries(base_fm, kind)].index(number) + 1
        if base_entry is not None
        else 1
    )
    if kind == "appendix":
        if change == "added":
            parts.apply_to_draft(draft, "delete_appendix", number=number)
        elif change == "removed":
            assert base_entry is not None
            parts.apply_to_draft(
                draft,
                "restore_appendix",
                number=number,
                title=base_entry["title"],
                text=base_texts.get(number, ""),
                position=position,
            )
        else:
            assert base_entry is not None
            parts.apply_to_draft(draft, "rename_appendix", number=number, title=base_entry["title"])
    else:
        if change == "added":
            parts.apply_to_draft(draft, "delete_attachment", number=number)
        elif change == "renamed":
            assert base_entry is not None
            parts.apply_to_draft(
                draft, "rename_attachment", number=number, title=base_entry["title"]
            )
        else:
            assert base_entry is not None
            data = gitstore.read(repo, parts.attachment_path(number), base_sha)
            if change == "removed":
                parts.apply_to_draft(
                    draft,
                    "restore_attachment",
                    number=number,
                    entry=dict(base_entry),
                    data=data,
                    position=position,
                )
            else:
                parts.apply_to_draft(
                    draft,
                    "replace_attachment",
                    number=number,
                    file_name=str(base_entry["file_name"]),
                    data=data,
                )
    return _entry(draft.content["frontmatter"], kind, number)


def apply(document: Any, reviewer: Any, *, part: str, change: str, head: str) -> Any:
    """Revert the run's `change` of `part` into the reviewer's draft — their open one, else one
    opened for it in the transaction that writes, so a refused revert leaves nobody holding. In
    `undo.apply`'s order: the reviewer's refusal; the record settled under the writer lock; the
    organisation's and the membership's rows; the writer lock; a head the rows do not know
    refused; the document's row and the refusal again; the head still `head`; the row among the
    run's; the hold taken and its draft locked; the draft's own change to the part found first
    (DL-0474); the inverse staged, recorded in `content["revert"]` with what it left, audited.
    Returns the hold; `RevertRefused` otherwise."""
    from django.db import connection, transaction
    from django.utils import timezone

    from audit.record import record
    from documents import gitstore
    from documents.locks import document_lock
    from documents.models import Document, Version
    from editing import holds, parts
    from editing.models import Draft, Hold, OpenEditor
    from identity.models import Membership
    from review.services import LOCK_WAIT_SECONDS, RecordIncomplete, base, settle_head
    from tenancy.models import Tenant

    refused = refusal(document, reviewer)
    if refused is not None:
        raise RevertRefused(refused)
    kind, number, key = _kind_and_number(part)
    tenant_number = holds.tenant_number()
    with document_lock(tenant_number, document.number, timeout=LOCK_WAIT_SECONDS):
        settle_head(document)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM tenancy_tenant WHERE number = %s FOR SHARE", [tenant_number]
            )
        list(
            Membership.objects.select_for_update(no_key=True, of=("self",)).filter(
                user=reviewer, tenant__number=tenant_number
            )
        )
        with document_lock(tenant_number, document.number, timeout=LOCK_WAIT_SECONDS):
            repo = gitstore.open_repository(tenant_number, document.number)
            current = gitstore.head(repo)
            if (
                current is not None
                and not Version.objects.filter(document=document, commit_sha=current).exists()
            ):
                raise RecordIncomplete("a commit the rows do not know")
            with transaction.atomic():
                locked = Document.objects.select_for_update(of=("self",)).get(pk=document.pk)
                refused = refusal(locked, reviewer)
                if refused is not None:
                    raise RevertRefused(refused)
                if current != head:
                    raise RevertRefused("run_changed")
                base_sha = base(locked).commit_sha
                older, newer = parts.side_at(repo, base_sha), parts.side_at(repo, head)
                if not _ran(older, newer, kind, number, change, key):
                    raise RevertRefused("nothing_to_revert")
                try:
                    hold = holds.hold_locked(locked, reviewer, tenant_number)
                except holds.HeldByOther as error:
                    raise RevertRefused("held") from error
                except holds.DraftPreserved as error:
                    raise RevertRefused("draft_kept") from error
                except (holds.NotEditable, holds.Frozen) as error:
                    raise RevertRefused("not_a_reviewer") from error
                hold = Hold.objects.select_for_update(of=("self",)).get(pk=hold.pk)
                draft = Draft.objects.select_for_update(of=("self",)).get(hold=hold)
                records = list(draft.content.get(REVERT, []))
                held = draft.content["frontmatter"]
                wanted = _property(older[0], kind, number, change, key)
                expected = _property(
                    _reverted_head(newer[0], older[0], records), kind, number, change, key
                )
                has = _property(held, kind, number, change, key)
                if change == "reordered":
                    among = (
                        set(wanted) & set(_property(newer[0], kind, None, change, None)) & set(has)
                    )
                    if _same_order(has, wanted, among):
                        raise RevertRefused("nothing_to_revert")
                    if not _same_order(has, expected, among):
                        raise RevertRefused("changed_in_draft")
                else:
                    if has == wanted:
                        raise RevertRefused("nothing_to_revert")
                    if has != expected:
                        raise RevertRefused("changed_in_draft")
                if kind == "appendix" and change in ("added", "removed") and number is not None:
                    if OpenEditor.objects.filter(
                        draft=draft, file=parts.appendix_key(number), closed_at__isnull=True
                    ).exists():
                        raise RevertRefused("editor_open")
                try:
                    staged = _stage(draft, repo, base_sha, older, kind, number, change, key)
                except parts.PartRefused as error:
                    raise RevertRefused(
                        "editor_open" if error.reason == "editor_open" else "nothing_to_revert"
                    ) from error
                draft.refresh_from_db()
                # Every earlier revert of this part names the entry the draft now holds: a part
                # both replaced and renamed is exempt at the commit whichever row went first.
                records = [
                    {**r, "staged": staged}
                    if r.get("part") == part and r.get("staged") is not None
                    else r
                    for r in records
                ]
                draft.content = {
                    **draft.content,
                    REVERT: [
                        *records,
                        {"part": part, "change": change, "head": head, "staged": staged},
                    ],
                }
                draft.save(update_fields=["content", "updated_at"])
                Hold.objects.filter(pk=hold.pk).update(last_activity_at=timezone.now())
                record(
                    actor=reviewer,
                    action="part.reverted",
                    obj=locked,
                    before=None,
                    after={"number": locked.number, "part": part, "change": change},
                    tenant=Tenant.objects.get(number=tenant_number),
                )
    return hold

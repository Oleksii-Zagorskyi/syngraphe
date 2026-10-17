"""Staging a document's parts in the holder's draft: the nine services of
`editing.parts`, their refusals and what each writes, the draft's appendix texts, the reads at the
draft's base, and the commit's check of a staged file's hash. Every title, file name, group and
person is a synthetic example; the file bytes are invented placeholders."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from django.db import transaction

from tenancy.schemas import schema_context

pytestmark = [
    pytest.mark.integration,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]

BODY = "The first synthetic sentence.\n\nThe second synthetic sentence.\n"
LATER = "The first synthetic sentence, revised.\n\nThe second synthetic sentence.\n"
NEWEST = "The first synthetic sentence, revised again.\n\nThe second synthetic sentence.\n"
TITLE = "Approval matrix (example)"
FILE_TITLE = "Budget model (example)"
FILE_NAME = "Budget model (example).xlsx"
# The right beyond *edit* each service needs; `None` for one that needs *edit* alone.
NEEDS = {
    "create_appendix": "CREATE_APPENDIX",
    "rename_appendix": None,
    "delete_appendix": "DELETE_APPENDIX",
    "reorder_appendices": None,
    "upload_attachment": "UPLOAD_ATTACHMENT",
    "replace_attachment": "REPLACE_ATTACHMENT",
    "rename_attachment": None,
    "delete_attachment": "DELETE_ATTACHMENT",
    "reorder_attachments": None,
}
PART_EVENTS = ("appendix.", "attachment.")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def attachment(number: int, title: str, file_name: str, data: bytes) -> dict[str, Any]:
    """An attachment entry as the frontmatter lists it."""
    return {
        "number": number,
        "title": title,
        "file_name": file_name,
        "sha256": sha(data),
        "bytes": len(data),
    }


def appendix(number: int, title: str) -> dict[str, Any]:
    return {"number": number, "title": title}


def take(tenant: Any, document: Any, user: Any) -> tuple[Any, Any]:
    """The user's hold on the document through the service, and its draft."""
    from editing import holds
    from editing.models import Draft

    with schema_context(tenant.number):
        hold = holds.take(document, user)
        return hold, Draft.objects.get(hold=hold)


def draft_now(tenant: Any, draft: Any) -> Any:
    from editing.models import Draft

    with schema_context(tenant.number):
        return Draft.objects.get(pk=draft.pk)


def listed(tenant: Any, draft: Any, kind: str) -> list[dict[str, Any]]:
    """The draft's list of `kind` — `appendices` or `attachments` — as the database holds it."""
    return list(draft_now(tenant, draft).content["frontmatter"][kind])


def rows(tenant: Any, draft: Any) -> list[tuple[str, str, str, bytes | None]]:
    """The draft's staged attachment rows: path, operation, sha256, bytes."""
    from editing.models import DraftFile

    with schema_context(tenant.number):
        return [
            (path, operation, sha256, None if content is None else bytes(content))
            for path, operation, sha256, content in DraftFile.objects.filter(
                draft_id=draft.pk, kind="attachment"
            )
            .order_by("path")
            .values_list("path", "operation", "sha256", "content")
        ]


def events(action: str) -> list[dict[str, Any]]:
    """The `after` of every audit event of `action`, in order."""
    from audit.models import AuditEvent

    return [dict(e.after or {}) for e in AuditEvent.objects.filter(action=action).order_by("at")]


def part_events() -> int:
    from audit.models import AuditEvent

    return sum(
        AuditEvent.objects.filter(action__startswith=prefix).count() for prefix in PART_EVENTS
    )


def refused(tenant: Any, call: Any, *args: Any, **kwargs: Any) -> Any:
    """The `PartRefused` that `call(*args, **kwargs)` raises inside the tenant's schema."""
    from editing import parts

    with schema_context(tenant.number), pytest.raises(parts.PartRefused) as caught:
        call(*args, **kwargs)
    return caught.value


def head_of(tenant: Any, document: Any) -> str:
    from documents import gitstore

    with schema_context(tenant.number):
        head = gitstore.head(gitstore.open_repository(tenant.number, document.number))
    assert head is not None
    return head


def base_file(tenant: Any, document: Any, path: str, commit: str) -> bytes:
    from documents import gitstore

    with schema_context(tenant.number):
        return gitstore.read(gitstore.open_repository(tenant.number, document.number), path, commit)


def test_a_new_appendix_takes_the_next_number_and_its_heading(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """ADR-0008: a number once committed is never given again, even after its part was deleted —
    the next appendix is 4 after 3 was listed and removed; its text is a heading of its title."""
    from access.rights import Right

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT, Right.CREATE_APPENDIX], [own], holder)
    commit_version(
        document,
        holder,
        BODY,
        appendices=[appendix(3, "Risk register (example)")],
        files={"appendices/3.md": b"# Risk register (example)\n"},
    )
    commit_version(document, holder, LATER, appendices=[], files={"appendices/3.md": None})
    hold, draft = take(migrated_tenant, document, holder)
    assert draft.content["frontmatter"]["appendices"] == []

    from editing import parts

    with schema_context(migrated_tenant.number):
        number = parts.create_appendix(document, holder, title=TITLE)

    assert number == 4
    assert listed(migrated_tenant, draft, "appendices") == [appendix(4, TITLE)]
    after = draft_now(migrated_tenant, draft)
    assert after.content["appendices/4.md"] == "# Approval matrix (example)\n"
    assert "appendices/3.md" not in after.content
    created = events("appendix.created")
    assert len(created) == 1
    assert created[0]["number"] == document.number
    assert created[0]["part"] == 4
    assert created[0]["staged"] is True
    with schema_context(migrated_tenant.number):
        hold.refresh_from_db()
        assert hold.last_activity_at > hold.acquired_at


def _call(parts: Any, service: str, document: Any, user: Any) -> Any:
    """Each service on a document whose draft lists appendix 1 and attachment 1."""
    data = b"a synthetic spreadsheet, replaced"
    calls = {
        "create_appendix": lambda: parts.create_appendix(document, user, title=TITLE),
        "rename_appendix": lambda: parts.rename_appendix(document, user, 1, title=TITLE),
        "delete_appendix": lambda: parts.delete_appendix(document, user, 1),
        "reorder_appendices": lambda: parts.reorder_appendices(document, user, [1]),
        "upload_attachment": lambda: parts.upload_attachment(
            document, user, title=FILE_TITLE, file_name=FILE_NAME, data=data
        ),
        "replace_attachment": lambda: parts.replace_attachment(
            document, user, 1, file_name=FILE_NAME, data=data
        ),
        "rename_attachment": lambda: parts.rename_attachment(document, user, 1, title=TITLE),
        "delete_attachment": lambda: parts.delete_attachment(document, user, 1),
        "reorder_attachments": lambda: parts.reorder_attachments(document, user, [1]),
    }
    return calls[service]()


@pytest.mark.parametrize("service", sorted(NEEDS))
def test_each_operation_needs_its_right(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    service: str,
) -> None:
    """The act's checks in their order: `not_holding` for anyone but the holder, whatever they
    hold; `frozen` for a holder without *accept* once a freeze opens; `no_right` for a holder of
    *edit* alone where the service needs a part right. A refusal writes nothing."""
    from django.utils import timezone

    from access.rights import PARTS, Right
    from editing.models import DraftFile
    from editions.models import Freeze

    _, holder, own = member_of("the.holder@example.test")
    _, other, theirs = member_of("the.other@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT], [own], holder)
    link_group(document, [Right.EDIT, Right.ACCEPT, *PARTS], [theirs], holder)
    old = b"a synthetic spreadsheet"
    commit_version(
        document,
        holder,
        BODY,
        appendices=[appendix(1, "Risk register (example)")],
        attachments=[attachment(1, FILE_TITLE, FILE_NAME, old)],
        files={"appendices/1.md": b"# Risk register (example)\n", "attachments/1": old},
    )
    _, draft = take(migrated_tenant, document, holder)
    before = draft_now(migrated_tenant, draft).content
    audited = part_events()

    from editing import parts

    # Everyone but the holder, whatever they hold.
    not_holding = refused(migrated_tenant, _call, parts, service, document, other)
    assert not_holding.reason == "not_holding"

    needed = NEEDS[service]
    if needed is not None:
        no_right = refused(migrated_tenant, _call, parts, service, document, holder)
        assert no_right.reason == "no_right"
        assert no_right.detail["right"] == Right[needed]

    with schema_context(migrated_tenant.number):
        Freeze.objects.create(document=document, frozen_by=other, frozen_at=timezone.now())
    # The freeze is seen before the right: the holder without *accept* is told *frozen*.
    frozen = refused(migrated_tenant, _call, parts, service, document, holder)
    assert frozen.reason == "frozen"

    assert draft_now(migrated_tenant, draft).content == before
    with schema_context(migrated_tenant.number):
        assert not DraftFile.objects.filter(draft_id=draft.pk).exists()
    assert part_events() == audited


def test_an_upload_is_checked_before_it_is_staged(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, settings: Any
) -> None:
    from access.rights import Right
    from tenancy.models import Tenant

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT, Right.UPLOAD_ATTACHMENT], [own], holder)
    Tenant.objects.filter(pk=migrated_tenant.pk).update(attachment_max_bytes=64)
    limit = min(64, int(settings.UPLOAD_MAX_BYTES))
    _, draft = take(migrated_tenant, document, holder)
    assert draft.content["frontmatter"]["attachments"] == []

    from editing import parts

    data = b"a synthetic spreadsheet of a few bytes"
    with schema_context(migrated_tenant.number):
        number = parts.upload_attachment(
            document, holder, title=FILE_TITLE, file_name=FILE_NAME, data=data
        )
    assert number == 1
    assert rows(migrated_tenant, draft) == [("attachments/1", "add", sha(data), data)]
    assert listed(migrated_tenant, draft, "attachments") == [
        attachment(1, FILE_TITLE, FILE_NAME, data)
    ]
    uploaded = events("attachment.uploaded")
    assert len(uploaded) == 1
    assert uploaded[0]["number"] == document.number
    assert uploaded[0]["part"] == 1
    assert uploaded[0]["staged"] is True
    assert uploaded[0]["bytes"] == len(data)
    assert uploaded[0]["sha256"] == sha(data)

    too_large = b"x" * (limit + 1)
    refusal = refused(
        migrated_tenant,
        parts.upload_attachment,
        document,
        holder,
        title=FILE_TITLE,
        file_name="Large model (example).xlsx",
        data=too_large,
    )
    assert refusal.reason == "too_large"
    assert refusal.detail["file_name"] == "Large model (example).xlsx"
    assert refusal.detail["size"] == limit + 1
    assert refusal.detail["limit"] == limit

    for bad_name in ("../x", ".hidden", "Budget\x07model.xlsx"):
        refusal = refused(
            migrated_tenant,
            parts.upload_attachment,
            document,
            holder,
            title=FILE_TITLE,
            file_name=bad_name,
            data=data,
        )
        assert refusal.reason == "bad_file_name", bad_name

    refusal = refused(
        migrated_tenant,
        parts.upload_attachment,
        document,
        holder,
        title="",
        file_name="Untitled model (example).xlsx",
        data=data,
    )
    assert refusal.reason == "bad_title"

    # An empty file is accepted; nothing of the refused ones was staged.
    with schema_context(migrated_tenant.number):
        assert (
            parts.upload_attachment(
                document, holder, title="Empty model (example)", file_name="Empty.xlsx", data=b""
            )
            == 2
        )
    assert rows(migrated_tenant, draft) == [
        ("attachments/1", "add", sha(data), data),
        ("attachments/2", "add", sha(b""), b""),
    ]
    assert [e["number"] for e in listed(migrated_tenant, draft, "attachments")] == [1, 2]
    assert len(events("attachment.uploaded")) == 2
    assert parts.valid_file_name("../x") is None
    assert parts.valid_file_name(".hidden") is None
    assert parts.valid_file_name("Budget\x07model.xlsx") is None
    assert parts.valid_file_name("") is None
    assert parts.valid_file_name("Budget model (example).xlsx") == "Budget model (example).xlsx"
    # NFC: a decomposed name comes back composed.
    assert parts.valid_file_name("Résumé (example).pdf") == "Résumé (example).pdf"


def test_replace_and_delete_on_listed_and_staged_attachments(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(
        document,
        [Right.EDIT, Right.UPLOAD_ATTACHMENT, Right.REPLACE_ATTACHMENT, Right.DELETE_ATTACHMENT],
        [own],
        holder,
    )
    old = b"a synthetic spreadsheet, committed"
    commit_version(
        document,
        holder,
        BODY,
        attachments=[attachment(1, FILE_TITLE, FILE_NAME, old)],
        files={"attachments/1": old},
    )
    _, draft = take(migrated_tenant, document, holder)

    from editing import parts

    added = b"a synthetic register, staged"
    with schema_context(migrated_tenant.number):
        assert (
            parts.upload_attachment(
                document,
                holder,
                title="Risk register (example)",
                file_name="Risk register (example).xlsx",
                data=added,
            )
            == 2
        )

    # The listed one: a replace row, rewritten by a second replace, never a second row.
    first, second = b"a synthetic spreadsheet, replaced once", b"replaced twice"
    with schema_context(migrated_tenant.number):
        parts.replace_attachment(
            document, holder, 1, file_name="Budget model v2 (example).xlsx", data=first
        )
    assert rows(migrated_tenant, draft) == [
        ("attachments/1", "replace", sha(first), first),
        ("attachments/2", "add", sha(added), added),
    ]
    with schema_context(migrated_tenant.number):
        parts.replace_attachment(
            document, holder, 1, file_name="Budget model v3 (example).xlsx", data=second
        )
    assert rows(migrated_tenant, draft) == [
        ("attachments/1", "replace", sha(second), second),
        ("attachments/2", "add", sha(added), added),
    ]
    assert listed(migrated_tenant, draft, "attachments")[0] == attachment(
        1, FILE_TITLE, "Budget model v3 (example).xlsx", second
    )

    # Deleting the listed one: a remove row, the replace row dropped, the entry gone.
    with schema_context(migrated_tenant.number):
        parts.delete_attachment(document, holder, 1)
    assert rows(migrated_tenant, draft) == [
        ("attachments/1", "remove", "", None),
        ("attachments/2", "add", sha(added), added),
    ]
    assert [e["number"] for e in listed(migrated_tenant, draft, "attachments")] == [2]

    # The added one: its add row rewritten, still `add`; then row and entry gone, no remove row.
    rewritten = b"a synthetic register, staged again"
    with schema_context(migrated_tenant.number):
        parts.replace_attachment(
            document, holder, 2, file_name="Risk register v2 (example).xlsx", data=rewritten
        )
    assert rows(migrated_tenant, draft) == [
        ("attachments/1", "remove", "", None),
        ("attachments/2", "add", sha(rewritten), rewritten),
    ]
    assert listed(migrated_tenant, draft, "attachments") == [
        attachment(2, "Risk register (example)", "Risk register v2 (example).xlsx", rewritten)
    ]
    with schema_context(migrated_tenant.number):
        parts.delete_attachment(document, holder, 2)
    assert rows(migrated_tenant, draft) == [("attachments/1", "remove", "", None)]
    assert listed(migrated_tenant, draft, "attachments") == []
    assert [e["part"] for e in events("attachment.replaced")] == [1, 1, 2]
    assert [e["part"] for e in events("attachment.deleted")] == [1, 2]
    assert all(e["staged"] is True for e in events("attachment.deleted"))


def test_a_reorder_is_a_permutation(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT], [own], holder)
    files = {f"attachments/{n}": f"synthetic file {n}".encode() for n in (1, 2, 3)}
    entries = [
        attachment(n, f"Synthetic attachment {n}", f"file-{n}.bin", files[f"attachments/{n}"])
        for n in (1, 2, 3)
    ]
    commit_version(document, holder, BODY, attachments=entries, files=files)
    _, draft = take(migrated_tenant, document, holder)

    from editing import parts

    for order in ([1, 2], [1, 2, 2], [1, 2, 7], [1, 2, 3, 3], []):
        refusal = refused(migrated_tenant, parts.reorder_attachments, document, holder, order)
        assert refusal.reason == "bad_order", order
        assert listed(migrated_tenant, draft, "attachments") == entries, order
    assert events("attachment.reordered") == []

    with schema_context(migrated_tenant.number):
        parts.reorder_attachments(document, holder, [3, 1, 2])
    assert listed(migrated_tenant, draft, "attachments") == [entries[2], entries[0], entries[1]]
    reordered = events("attachment.reordered")
    assert len(reordered) == 1
    assert reordered[0]["number"] == document.number
    assert reordered[0]["order"] == [3, 1, 2]
    assert reordered[0]["staged"] is True


def test_the_draft_holds_every_appendix(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right
    from editing.models import Draft

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT], [own], holder)
    one = "# Risk register (example)\n\nA synthetic register line.\n"
    two = "# Approval matrix (example)\n\nA synthetic matrix line.\n"
    commit_version(
        document,
        holder,
        BODY,
        appendices=[appendix(1, "Risk register (example)"), appendix(2, TITLE)],
        files={"appendices/1.md": one.encode(), "appendices/2.md": two.encode()},
    )

    _, draft = take(migrated_tenant, document, holder)

    assert draft.content["appendices/1.md"] == one
    assert draft.content["appendices/2.md"] == two
    assert draft.base_commit == head_of(migrated_tenant, document)

    from editing import parts

    edited = one + "\nA line the holder added.\n"
    with schema_context(migrated_tenant.number):
        content = dict(draft.content)
        del content["appendices/2.md"]
        content["appendices/1.md"] = edited
        Draft.objects.filter(pk=draft.pk).update(content=content)
        kept = Draft.objects.get(pk=draft.pk)
        assert parts.appendix_text(kept, 2) == two
        assert parts.appendix_text(kept, 1) == edited


def test_a_replace_rewrites_its_entry(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    from access.rights import Right
    from editing import services
    from editing.models import Draft, DraftFile, Hold

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT, Right.REPLACE_ATTACHMENT], [own], holder)
    old = b"a synthetic spreadsheet, committed"
    commit_version(
        document,
        holder,
        BODY,
        attachments=[attachment(1, FILE_TITLE, FILE_NAME, old)],
        files={"attachments/1": old},
    )
    head = head_of(migrated_tenant, document)
    hold, draft = take(migrated_tenant, document, holder)

    from editing import parts

    new = b"a synthetic spreadsheet, replaced"
    with schema_context(migrated_tenant.number):
        parts.replace_attachment(
            document, holder, 1, file_name="Budget model v2 (example).xlsx", data=new
        )
    assert listed(migrated_tenant, draft, "attachments") == [
        attachment(1, FILE_TITLE, "Budget model v2 (example).xlsx", new)
    ]
    assert rows(migrated_tenant, draft) == [("attachments/1", "replace", sha(new), new)]

    with schema_context(migrated_tenant.number):
        assert (
            DraftFile.objects.filter(draft_id=draft.pk, path="attachments/1").update(
                sha256="0" * 64
            )
            == 1
        )
        with pytest.raises(RuntimeError):
            services.commit_draft(hold, holder, "Replaces the budget model")
        assert Draft.objects.filter(pk=draft.pk).exists()
        assert Hold.objects.get(pk=hold.pk).released_at is None
        assert DraftFile.objects.filter(draft_id=draft.pk).count() == 1
    assert head_of(migrated_tenant, document) == head
    assert queued_authorship == []


def test_a_restored_attachment_keeps_its_number(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    """A part put back by a revert comes back under its own number and at its place;
    the next new part is numbered past it (ADR-0008)."""
    from access.rights import Right
    from editing.models import Draft

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT, Right.UPLOAD_ATTACHMENT], [own], holder)
    files = {f"attachments/{n}": f"synthetic file {n}".encode() for n in (1, 2, 3)}
    entries = {
        n: attachment(n, f"Synthetic attachment {n}", f"file-{n}.bin", files[f"attachments/{n}"])
        for n in (1, 2, 3)
    }
    commit_version(document, holder, BODY, attachments=list(entries.values()), files=files)
    commit_version(
        document, holder, LATER, attachments=[entries[1], entries[3]], files={"attachments/2": None}
    )
    _, draft = take(migrated_tenant, document, holder)
    assert [e["number"] for e in draft.content["frontmatter"]["attachments"]] == [1, 3]

    from editing import parts

    with schema_context(migrated_tenant.number), transaction.atomic():
        locked = Draft.objects.select_for_update().get(pk=draft.pk)
        parts.apply_to_draft(
            locked,
            "restore_attachment",
            number=2,
            entry=entries[2],
            data=files["attachments/2"],
            position=2,
        )
    assert listed(migrated_tenant, draft, "attachments") == [entries[1], entries[2], entries[3]]
    assert rows(migrated_tenant, draft) == [
        ("attachments/2", "add", sha(files["attachments/2"]), files["attachments/2"])
    ]

    new = b"a synthetic fourth file"
    with schema_context(migrated_tenant.number):
        number = parts.upload_attachment(
            document, holder, title="Synthetic attachment 4", file_name="file-4.bin", data=new
        )
    assert number == 4
    assert [e["number"] for e in listed(migrated_tenant, draft, "attachments")] == [1, 2, 3, 4]


def test_a_staged_addition_is_withdrawn_with_the_right_that_added_it(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    from access.rights import Right
    from editing.models import DraftFile

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(
        document, [Right.EDIT, Right.UPLOAD_ATTACHMENT, Right.CREATE_APPENDIX], [own], holder
    )
    _, draft = take(migrated_tenant, document, holder)

    from editing import parts

    data = b"a synthetic spreadsheet, staged"
    with schema_context(migrated_tenant.number):
        attached = parts.upload_attachment(
            document, holder, title=FILE_TITLE, file_name=FILE_NAME, data=data
        )
        appended = parts.create_appendix(document, holder, title=TITLE)
    assert (attached, appended) == (1, 1)
    assert f"appendices/{appended}.md" in draft_now(migrated_tenant, draft).content

    with schema_context(migrated_tenant.number):
        parts.delete_attachment(document, holder, attached)
        parts.delete_appendix(document, holder, appended)

    after = draft_now(migrated_tenant, draft)
    assert after.content["frontmatter"]["attachments"] == []
    assert after.content["frontmatter"]["appendices"] == []
    assert f"appendices/{appended}.md" not in after.content
    with schema_context(migrated_tenant.number):
        assert not DraftFile.objects.filter(draft_id=draft.pk).exists()
    deleted_attachment = events("attachment.deleted")
    deleted_appendix = events("appendix.deleted")
    assert len(deleted_attachment) == 1 and len(deleted_appendix) == 1
    assert deleted_attachment[0]["number"] == document.number
    assert deleted_attachment[0]["part"] == attached
    assert deleted_attachment[0]["staged"] is True
    assert deleted_appendix[0]["number"] == document.number
    assert deleted_appendix[0]["part"] == appended
    assert deleted_appendix[0]["staged"] is True


def test_a_committed_part_still_needs_the_deletion_right(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right
    from editing.models import DraftFile

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(
        document, [Right.EDIT, Right.UPLOAD_ATTACHMENT, Right.CREATE_APPENDIX], [own], holder
    )
    old = b"a synthetic spreadsheet, committed"
    commit_version(
        document,
        holder,
        BODY,
        appendices=[appendix(1, TITLE)],
        attachments=[attachment(1, FILE_TITLE, FILE_NAME, old)],
        files={"appendices/1.md": b"# Approval matrix (example)\n", "attachments/1": old},
    )
    _, draft = take(migrated_tenant, document, holder)
    before = draft_now(migrated_tenant, draft).content

    from editing import parts

    refusal = refused(migrated_tenant, parts.delete_attachment, document, holder, 1)
    assert refusal.reason == "no_right"
    assert refusal.detail["right"] == Right.DELETE_ATTACHMENT
    refusal = refused(migrated_tenant, parts.delete_appendix, document, holder, 1)
    assert refusal.reason == "no_right"
    assert refusal.detail["right"] == Right.DELETE_APPENDIX

    assert draft_now(migrated_tenant, draft).content == before
    with schema_context(migrated_tenant.number):
        assert not DraftFile.objects.filter(draft_id=draft.pk).exists()
    assert events("attachment.deleted") == []
    assert events("appendix.deleted") == []


def test_an_unstaged_attachment_is_read_at_the_drafts_base(
    migrated_tenant: Any,
    member_of: Any,
    new_document: Any,
    link_group: Any,
    commit_version: Any,
    queued_authorship: list[Any],
) -> None:
    """A kept draft reads an attachment it never touched at its own base, never at a head that
    has since moved on."""
    from access.rights import Right
    from editing import reservations, services
    from editing.models import Draft, ReleaseKind

    _, first, own = member_of("the.first.holder@example.test")
    _, second, theirs = member_of("the.second.holder@example.test")
    _, admin, _ = member_of("the.administrator@example.test", is_tenant_admin=True)
    document = new_document(first)
    link_group(document, [Right.EDIT, Right.REPLACE_ATTACHMENT], [own, theirs], first)
    files = {f"attachments/{n}": f"synthetic file {n}, committed".encode() for n in (1, 2)}
    entries = [
        attachment(n, f"Synthetic attachment {n}", f"file-{n}.bin", files[f"attachments/{n}"])
        for n in (1, 2)
    ]
    commit_version(document, first, BODY, attachments=entries, files=files)
    base = head_of(migrated_tenant, document)
    hold_a, draft_a = take(migrated_tenant, document, first)
    assert draft_a.base_commit == base

    with schema_context(migrated_tenant.number):
        assert reservations.force_release(hold_a, admin) is True
        hold_a.refresh_from_db()
        assert hold_a.release_kind == ReleaseKind.FORCED
        assert Draft.objects.filter(pk=draft_a.pk).exists()

    from editing import parts

    replaced = b"synthetic file 2, replaced by the second holder"
    hold_b, draft_b = take(migrated_tenant, document, second)
    with schema_context(migrated_tenant.number):
        parts.replace_attachment(document, second, 2, file_name="file-2-v2.bin", data=replaced)
        version = services.commit_draft(hold_b, second, "Replaces the second file")
    head = head_of(migrated_tenant, document)
    assert version.commit_sha == head and head != base
    assert base_file(migrated_tenant, document, "attachments/2", head) == replaced
    assert base_file(migrated_tenant, document, "attachments/2", base) == files["attachments/2"]

    with schema_context(migrated_tenant.number):
        kept = Draft.objects.get(pk=draft_a.pk)
        entry, data = parts.draft_attachment(kept, 2)
    assert entry == entries[1]
    assert data == files["attachments/2"]
    assert data != replaced
    assert sha(data) == entry["sha256"]
    with schema_context(migrated_tenant.number):
        with pytest.raises(KeyError):
            parts.draft_attachment(kept, 7)
        # The entry's hash no longer the bytes': `ValueError`, never silent bytes.
        tampered = dict(kept.content)
        tampered["frontmatter"] = {
            **kept.content["frontmatter"],
            "attachments": [entries[0], {**entries[1], "sha256": "0" * 64}],
        }
        Draft.objects.filter(pk=kept.pk).update(content=tampered)
        with pytest.raises(ValueError):
            parts.draft_attachment(Draft.objects.get(pk=kept.pk), 2)


def test_a_withdrawal_is_judged_against_the_head(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """A part a finish committed before it stopped is listed by the head though not by the
    draft's base: deleting it needs the deletion right, as at the commit (DL-0473)."""
    from access.rights import Right
    from editing import parts, services

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT, Right.CREATE_APPENDIX], [own], holder)
    hold, _ = take(migrated_tenant, document, holder)
    with schema_context(migrated_tenant.number):
        number = parts.create_appendix(document, holder, title=TITLE)
        with pytest.raises(services.InjectedFault):
            services.commit_draft(hold, holder, "An appendix", fault_at=1)
    caught = refused(migrated_tenant, parts.delete_appendix, document, holder, number)
    assert caught.reason == "no_right"
    assert caught.detail["right"] == Right.DELETE_APPENDIX


def test_a_file_name_holds_no_direction_control() -> None:
    """A right-to-left override or an isolate would show a name other than the one stored."""
    from editing import parts

    for name in ("report‮xcs.exe", "form⁦.txt", "plan‏.pdf", "list؜.csv"):
        assert parts.valid_file_name(name) is None, repr(name)
    assert parts.valid_file_name("Budget model (example).xlsx") == "Budget model (example).xlsx"


def test_a_restore_position_is_clamped_at_both_ends(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any, commit_version: Any
) -> None:
    from access.rights import Right
    from editing import parts
    from editing.models import Draft

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT], [own], holder)
    data = [b"first synthetic file", b"third synthetic file"]
    commit_version(
        document,
        holder,
        BODY,
        files={"attachments/1": data[0], "attachments/3": data[1]},
        attachments=[
            attachment(1, "First (example)", "first.txt", data[0]),
            attachment(3, "Third (example)", "third.txt", data[1]),
        ],
    )
    _, draft = take(migrated_tenant, document, holder)
    restored = b"second synthetic file"
    with schema_context(migrated_tenant.number), transaction.atomic():
        locked = Draft.objects.select_for_update().get(pk=draft.pk)
        parts.apply_to_draft(
            locked,
            "restore_attachment",
            number=2,
            entry=attachment(2, "Second (example)", "second.txt", restored),
            data=restored,
            position=0,
        )
    assert [e["number"] for e in listed(migrated_tenant, draft, "attachments")] == [2, 1, 3]


def test_an_open_editor_keeps_its_appendix(
    migrated_tenant: Any, member_of: Any, new_document: Any, link_group: Any
) -> None:
    """An appendix an editor is open on is not deleted: the editor would write into a key the
    draft no longer lists."""
    from django.utils import timezone

    from access.rights import Right
    from editing import parts
    from editing.models import OpenEditor

    _, holder, own = member_of("the.holder@example.test")
    document = new_document(holder)
    link_group(document, [Right.EDIT, Right.CREATE_APPENDIX], [own], holder)
    _, draft = take(migrated_tenant, document, holder)
    with schema_context(migrated_tenant.number):
        number = parts.create_appendix(document, holder, title=TITLE)
        OpenEditor.objects.create(
            draft_id=draft.pk,
            file=parts.appendix_key(number),
            range="whole",
            base_hash="0" * 64,
            last_seen_at=timezone.now(),
        )
        before = draft_now(migrated_tenant, draft).content
    caught = refused(migrated_tenant, parts.delete_appendix, document, holder, number)
    assert caught.reason == "editor_open"
    assert draft_now(migrated_tenant, draft).content == before

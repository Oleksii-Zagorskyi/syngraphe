"""A version's attachments: listed from `PART_INDEX` without reading git (ADR-0005), read from
the repository with their hash checked before a byte is served (DL-0342)."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from documents import bundle, gitstore
from documents.models import Document, PartIndex, PartKind, Version

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Attachment:
    number: int
    title: str
    file_name: str
    sha256: str
    bytes: int


def attachments(version: Version) -> list[Attachment]:
    """The attachments `version` lists, in their order."""
    return [
        Attachment(
            number=row.part_number,
            title=row.title,
            file_name=row.file_name,
            sha256=row.sha256,
            bytes=row.bytes or 0,
        )
        for row in PartIndex.objects.filter(version=version, kind=PartKind.ATTACHMENT).order_by(
            "position"
        )
    ]


@dataclass(frozen=True)
class AttachmentChange:
    """What became of attachment `number` from an older version to a newer one: `added`,
    `changed` — its file, its title or its file name differs — `removed` or `unchanged`, with
    the entry at each version, `None` where it is absent."""

    number: int
    change: str
    older: Attachment | None
    newer: Attachment | None


def changed_between(older: Version, newer: Version) -> list[AttachmentChange]:
    """Every attachment of either version, by its number, and what became of it (DL-0208); an
    attachment cannot be compared, so the change is the fact and the two files."""
    before = {a.number: a for a in attachments(older)}
    after = {a.number: a for a in attachments(newer)}
    found = []
    for number in sorted(before.keys() | after.keys()):
        old, new = before.get(number), after.get(number)
        if old is None:
            change = "added"
        elif new is None:
            change = "removed"
        else:
            # A rename is a change too: the reader is told the attachment is not as it was.
            same = (old.sha256, old.title, old.file_name) == (new.sha256, new.title, new.file_name)
            change = "unchanged" if same else "changed"
        found.append(AttachmentChange(number, change, old, new))
    return found


def read_attachment(
    tenant_number: int, document: Document, version: Version, number: int
) -> tuple[Attachment, bytes]:
    """Attachment `number` as `version`'s frontmatter lists it, and its bytes: `KeyError` when the
    version lists no such attachment or its file is absent, `ValueError` when the file's hash is
    not the one listed."""
    repo = gitstore.open_repository(tenant_number, document.number)
    text = gitstore.read(repo, "document.md", version.commit_sha).decode("utf-8")
    frontmatter, _ = bundle.parse(text)
    entry = next((e for e in frontmatter.attachments if int(e["number"]) == number), None)
    if entry is None:
        raise KeyError(number)
    data = gitstore.read(repo, f"attachments/{number}", version.commit_sha)
    attachment = Attachment(
        number=number,
        title=str(entry["title"]),
        file_name=str(entry["file_name"]),
        sha256=str(entry["sha256"]),
        bytes=int(entry["bytes"]),
    )
    if hashlib.sha256(data).hexdigest() != attachment.sha256:
        logger.error(
            "an attachment's file does not match its listed hash",
            extra={"document": document.number, "commit": version.commit_sha, "attachment": number},
        )
        raise ValueError(number)
    return attachment, data

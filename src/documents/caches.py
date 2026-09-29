"""The caches a version's rows carry: its headings and its parts, rebuilt from git at that version
(`data-model.md § Content index, entities, images`).

Headings are read with a regular expression over the ATX form of the constrained subset, four
levels deep (`technical-design.md § The constrained Markdown subset`).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from django.db import connection, transaction

from documents import bundle, gitstore
from documents.models import HeadingIndex, PartIndex, PartKind
from syngraphe.provenance import ActorKind
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from documents.models import Document, Version

logger = logging.getLogger(__name__)

ATX = re.compile(r"^(?P<marks>#{1,4})[ \t]+(?P<text>.*?)(?:[ \t]+#+)?[ \t]*$")
FENCE = re.compile(r"^(?P<fence>`{3,}|~{3,})")
HEADING_MAX = 1000
TITLE_MAX = 500


def headings(text: str) -> list[tuple[int, str, int]]:
    """`(depth, heading, line)` for every ATX heading, outside the frontmatter and fenced code.

    Lines are counted as git counts them, at line feeds only.
    """
    lines = [line.removesuffix("\r") for line in text.removeprefix("\ufeff").split("\n")]
    start = 0
    if lines and lines[0] == "---":
        for n, line in enumerate(lines[1:], 1):
            if line == "---":
                start = n + 1
                break
    found = []
    fence = ""
    for n in range(start, len(lines)):
        line = lines[n]
        opening = FENCE.match(line)
        if fence:
            if (
                opening
                and opening.group("fence")[0] == fence[0]
                and len(opening.group("fence")) >= len(fence)
                and not line[len(opening.group("fence")) :].strip()
            ):
                fence = ""
            continue
        if opening:
            fence = opening.group("fence")
            continue
        match = ATX.match(line)
        text_ = match.group("text").strip("#").strip() if match else ""
        if match and text_:
            found.append((len(match.group("marks")), match.group("text")[:HEADING_MAX], n + 1))
    return found


def _heading_rows(document: Document, version: Version, path: str, text: str) -> list[HeadingIndex]:
    return [
        HeadingIndex(
            document=document,
            version=version,
            file=path,
            position=position,
            depth=depth,
            heading=heading,
            line=line,
            actor_kind=ActorKind.SYSTEM,
        )
        for position, (depth, heading, line) in enumerate(headings(text), 1)
    ]


def rebuild(document: Document, version: Version) -> None:
    """Replace the version's heading and part rows with those its commit gives, in the tenant the
    connection is set to.

    The parts are the lists in `document.md`'s frontmatter at that commit. An appendix listed there
    and missing from the commit is logged and left out; the rest is still written.
    """
    tenant_number = current_tenant(connection)
    if tenant_number is None:
        raise RuntimeError("the caches are rebuilt inside a tenant's schema")
    repo = gitstore.open_repository(tenant_number, document.number)
    text = gitstore.read(repo, "document.md", version.commit_sha).decode("utf-8")
    frontmatter, _ = bundle.parse(text)
    parts = {"appendices": frontmatter.appendices, "attachments": frontmatter.attachments}
    rows = _heading_rows(document, version, "document.md", text)
    for item in parts["appendices"]:
        path = f"appendices/{int(item['number'])}.md"
        try:
            appendix = gitstore.read(repo, path, version.commit_sha).decode("utf-8")
        except KeyError:
            logger.error(
                "an appendix listed in the frontmatter is missing",
                extra={"document": document.number, "commit": version.commit_sha, "file": path},
            )
            continue
        rows.extend(_heading_rows(document, version, path, appendix))
    part_rows = [
        PartIndex(
            document=document,
            version=version,
            kind=kind,
            part_number=int(item["number"]),
            position=position,
            title=str(item.get("title", ""))[:TITLE_MAX],
            file_name=str(item.get("file_name", "")),
            sha256=str(item.get("sha256", "")),
            bytes=item.get("bytes"),
            actor_kind=ActorKind.SYSTEM,
        )
        for kind, key in ((PartKind.APPENDIX, "appendices"), (PartKind.ATTACHMENT, "attachments"))
        for position, item in enumerate(parts[key], 1)
    ]
    with transaction.atomic():
        HeadingIndex.objects.filter(version=version).delete()
        PartIndex.objects.filter(version=version).delete()
        HeadingIndex.objects.bulk_create(rows)
        PartIndex.objects.bulk_create(part_rows)

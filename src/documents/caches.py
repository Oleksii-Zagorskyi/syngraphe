"""The caches a version's rows carry: its headings and its parts, rebuilt from git at that version,
with the document's entities from the head and a record of each image
(`data-model.md § Content index, entities, images`).

Headings are read through the platform's own parser, as the reader sees them: four levels deep,
their text as it reads, marks removed (`technical-design.md § The constrained Markdown subset`).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pygit2
from django.db import connection, transaction

from documents import bundle, entities, gitstore, images
from documents.models import Entity, HeadingIndex, Image, PartIndex, PartKind, Version
from editing.markdown.parser import parser
from syngraphe.provenance import ActorKind
from tenancy.schemas import current_tenant

if TYPE_CHECKING:
    from markdown_it.token import Token

    from documents.models import Document

logger = logging.getLogger(__name__)

DEPTH_MAX = 4
HEADING_MAX = 1000
TITLE_MAX = 500


def _plain(inline: Token) -> str:
    """A heading's text as a reader reads it: the words of its marks and spans, no syntax."""
    words = []
    for child in inline.children or []:
        if child.type in ("text", "code_inline"):
            words.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            words.append(" ")
        elif child.type == "image":
            words.append(child.content)
    return "".join(words).strip()


def headings(text: str) -> list[tuple[int, str, int]]:
    """`(depth, heading, line)` for every heading down to level four, outside the frontmatter.

    Lines are counted as git counts them, at line feeds only, from the file's first line.
    """
    text = text.removeprefix("\ufeff").replace("\r\n", "\n")
    lines = text.split("\n")
    offset = 0
    if lines and lines[0] == "---":
        for n, line in enumerate(lines[1:], 1):
            if line == "---":
                offset = n + 1
                break
    tokens = parser().parse("\n".join(lines[offset:]))
    found = []
    for i, token in enumerate(tokens):
        if token.type != "heading_open" or token.map is None:
            continue
        depth = int(token.tag[1:])
        heading = _plain(tokens[i + 1])
        if depth <= DEPTH_MAX and heading:
            found.append((depth, heading[:HEADING_MAX], offset + token.map[0] + 1))
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
    and missing from the commit is logged and left out; the rest is still written. When the version
    is the head, the document's entity rows are replaced by its `entities.yaml`; each image of its
    tree the document does not yet record gains a row.
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
        try:
            kept = _kept(repo, document, version)
        except (LookupError, ValueError, pygit2.GitError):
            # A passport that cannot be read leaves every row: a cache is never worth a failed
            # derivation.
            logger.exception("heading rows not pruned", extra={"document": document.number})
        else:
            HeadingIndex.objects.filter(document=document).exclude(version__in=kept).delete()
        if gitstore.head(repo) == version.commit_sha:
            _mirror_entities(repo, document, version)
        _record_images(repo, document, version)


def _mirror_entities(repo: pygit2.Repository, document: Document, version: Version) -> None:
    """The document's entity rows replaced by the head's `entities.yaml`; a file that does not
    read is logged and the rows left as they are."""
    try:
        data = gitstore.read(repo, "entities.yaml", version.commit_sha)
    except KeyError:
        data = b"[]\n"
    try:
        declared = entities.parse(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        logger.exception("entities.yaml does not read", extra={"document": document.number})
        return
    Entity.objects.filter(document=document).delete()
    Entity.objects.bulk_create(
        Entity(
            document=document,
            kind=entry.kind,
            key=entry.key,
            label=entry.label,
            actor_kind=ActorKind.SYSTEM,
        )
        for entry in declared
    )


# The data model's content type for each image extension.
STORED_TYPES = {"png": "png", "jpg": "jpeg", "gif": "gif"}


def _record_images(repo: pygit2.Repository, document: Document, version: Version) -> None:
    """A row for each image of the version's tree the document does not yet record: who
    committed it first, and when."""
    recorded = set(Image.objects.filter(document=document).values_list("path", flat=True))
    for name in gitstore.listing(repo, images.FOLDER, version.commit_sha):
        path = f"{images.FOLDER}/{name}"
        match = images.NAME.fullmatch(name)
        if match is None or path in recorded:
            continue
        Image.objects.create(
            document=document,
            path=path,
            content_type=STORED_TYPES[match.group(1)],
            bytes=len(gitstore.read(repo, path, version.commit_sha)),
            uploaded_by_id=version.author_id,
            uploaded_at=version.committed_at,
            actor_kind=ActorKind.SYSTEM,
        )


def _kept(repo: pygit2.Repository, document: Document, version: Version) -> set[Any]:
    """The versions whose heading rows stay: the one just rebuilt, the head and its parent, the
    latest accepted content version as its acceptance's passport section names it, and every
    edition's. The head's parent covers an acceptance's own commit, rebuilt before its row exists;
    shas are read from git, since versions committed in one second cannot be ordered by time.
    The rows of any other version go; nothing reads them."""
    # Imported here: acceptances and editions are recorded by apps built on this one.
    from editions.models import Edition
    from review.models import Acceptance
    from review.services import accepted_sha

    shas: set[str] = set()
    head = gitstore.head(repo)
    if head is not None:
        # The head's parent too: an acceptance's own commit is rebuilt before its row exists, and
        # the version it accepted is that commit's parent.
        shas.add(str(head))
        shas.update(str(parent.id) for parent in gitstore.commit_at(repo, head).parents[:1])
    acceptances = Acceptance.objects.filter(version__document=document).select_related("version")
    latest = max(
        acceptances, key=lambda a: tuple(int(n) for n in a.number.split(".")), default=None
    )
    if latest is not None:
        # An acceptance made on top of an approval has the approval, not the accepted text, as
        # its parent: the passport names the version it decided on.
        shas.add(accepted_sha(latest, document.number))
    kept: set[Any] = {version.pk}
    kept.update(
        Version.objects.filter(document=document, commit_sha__in=shas).values_list("pk", flat=True)
    )
    kept.update(
        Edition.objects.filter(version__document=document).values_list("version", flat=True)
    )
    return kept

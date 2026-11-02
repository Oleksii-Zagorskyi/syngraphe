"""A past version's edit authors, worked out on demand (DL-0266, DL-0489): the historical page
asks the worker for a version without rows and shows the text without authors until they come;
the rows are kept a day and swept."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db.models import Q
from django.utils import timezone

from editing.authorship import DOCUMENT_FILE
from editing.models import LineAuthorship
from identity.naming import person

if TYPE_CHECKING:
    from documents.models import Document, Version

logger = logging.getLogger(__name__)

KEPT_FOR = timedelta(hours=24)
# How long the page waits on Redis for the mark before reading on without the authors.
MARK_WAIT_SECONDS = 2


def authors_at(document: Document, version: Version, offset: int) -> dict[int, str] | None:
    """Each line of the body of `document.md` at `version`, by its index from 0, to its edit
    author's name as the platform names a person; `None` while the version has no live rows. The
    rows count the lines of the whole file, so `offset` — the lines before the body — is taken
    off."""
    rows = (
        LineAuthorship.objects.filter(version=version, file=DOCUMENT_FILE)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        .select_related("introduced_by__author")
    )
    found = {row.line - 1 - offset: person(row.introduced_by.author) for row in rows}
    if not found:
        return None
    return {index: name for index, name in found.items() if index >= 0 and name}


# The longest one version's job is waited for before it may be asked again, should it never end.
ASKED_FOR = timedelta(minutes=10)


def asked_key(tenant_number: int, document_number: int, commit_sha: str) -> str:
    return f"syngraphe:authorship-at:{tenant_number}:{document_number}:{commit_sha}"


def ask(tenant_number: int, document: Document, version: Version) -> None:
    """Queue the worker for `version`'s rows, once while a job for it is under way: every reader
    shares the worker, and reloading the page is no reason to blame the same commit again. The
    job clears the mark when it ends. The authors are optional (DL-0266): Redis or the broker
    refusing is logged and the page reads on without them; a mark the queue never received is let
    go, so a reload asks again."""
    import redis
    from django.conf import settings

    from editing.tasks import compute_authorship_at

    key = asked_key(tenant_number, document.number, version.commit_sha)
    extra = {"document": document.number, "commit": version.commit_sha}
    client = redis.Redis.from_url(
        settings.REDIS_URL,
        socket_timeout=MARK_WAIT_SECONDS,
        socket_connect_timeout=MARK_WAIT_SECONDS,
    )
    try:
        try:
            if not client.set(key, 1, nx=True, ex=int(ASKED_FOR.total_seconds())):
                return
        except redis.RedisError:
            logger.exception("a version's edit authors could not be asked for", extra=extra)
            return
        try:
            compute_authorship_at.delay(tenant_number, document.number, version.commit_sha)
        except Exception:
            # The broker's errors are its own library's, not one class.
            logger.exception("a version's edit authors could not be queued", extra=extra)
            try:
                client.delete(key)
            except redis.RedisError:
                logger.exception("an unqueued request's mark stays its ten minutes", extra=extra)
    finally:
        client.close()


def asked_done(tenant_number: int, document_number: int, commit_sha: str) -> None:
    """The version may be asked for again: its job has ended, whatever it found."""
    import redis
    from django.conf import settings

    client = redis.Redis.from_url(settings.REDIS_URL)
    try:
        client.delete(asked_key(tenant_number, document_number, commit_sha))
    finally:
        client.close()


# The blocks a line's author is named on: each holds its own lines of the body.
NAMED_BLOCKS = ("paragraph_open", "heading_open", "tr_open")


def _by_line(inline: Any, first: int, authors: Mapping[int, str]) -> None:
    """A paragraph of several authors: each of its lines — a sentence — named in a span of its
    own, the clause's number left first. A mark running across a line break cannot be divided by
    line, and the paragraph is then left without names rather than drawn with broken markup."""
    from markdown_it.token import Token

    lead: list[Any] = []
    lines: list[list[Any]] = [[]]
    breaks: list[Any] = []
    depth = 0
    for child in inline.children or []:
        if child.meta.get("num"):
            lead.append(child)
        elif child.type in ("softbreak", "hardbreak"):
            if depth:
                return
            breaks.append(child)
            lines.append([])
        else:
            depth += child.nesting
            lines[-1].append(child)
    if depth:
        return
    children = list(lead)
    for n, line in enumerate(lines):
        if n:
            children.append(breaks[n - 1])
        name = authors.get(first + n)
        if not name or not line:
            children += line
            continue
        opened = Token("author_open", "span", 1)
        opened.attrSet("data-author", name)
        opened.attrSet("title", name)
        opened.attrSet("class", "by")
        children += [opened, *line, Token("author_close", "span", -1)]
    inline.children = children


def by_author(
    tokens: Sequence[Any], authors: Mapping[int, str], *, changed: set[int] | None = None
) -> None:
    """Name its edit author on each block of the reading view's `tokens` whose lines share one —
    `data-author`, a title on hover and the margin's name (`by`) — and on each sentence of a
    paragraph whose lines have several. A tight list's paragraph is
    not drawn, so its item carries the name, as it carries the clause's anchor. The tokens keep
    their anchors, so the outline and the generated views still reach every heading and clause.

    `changed` holds the lines changed against the version before; a block none of whose lines it
    holds names nobody (DL-0504). `None` — nothing before to compare with — names every block."""
    for i, token in enumerate(tokens):
        if token.type not in NAMED_BLOCKS or not token.map:
            continue
        if changed is not None and not changed.intersection(range(*token.map)):
            continue
        names = {authors[n] for n in range(*token.map) if n in authors}
        if len(names) > 1 and token.type == "paragraph_open":
            _by_line(tokens[i + 1], token.map[0], authors)
            continue
        if len(names) != 1:
            continue
        name = names.pop()
        target = token
        if token.hidden and i > 0 and tokens[i - 1].type == "list_item_open":
            target = tokens[i - 1]
        target.attrSet("data-author", name)
        target.attrSet("title", name)
        target.attrJoin("class", "by")

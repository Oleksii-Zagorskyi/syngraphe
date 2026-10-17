"""Mentions of other documents (DL-0436): which documents a text mentions, and which of them a
reader may follow — a document they may read while it is active (DL-0084, ASR-16). Any other
mention reads as its words alone, so a reader learns nothing of a document from its mention.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from markdown_it.token import Token

from editing.markdown import load_spec
from editing.markdown.words import read
from rendering.renderer import MENTION, RENDERER


@dataclass(frozen=True)
class Mention:
    """One mention: the document's number, the mention's words as a reader reads them, and the
    line every refusal names — the first of the block holding it."""

    number: int
    words: str
    line: int


def _mentions(tokens: Sequence[Token]) -> Iterator[Mention]:
    """The mentions of a text's `tokens`, read in one pass over each block's children: each open
    span keeps its words until its close, so a paragraph of many mentions costs about its
    parse."""
    pattern = load_spec().mention_id
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        line = (token.map[0] + 1) if token.map else 0
        # One entry per open entity span: where it opened, a mention's number and words, `None`
        # for another kind. A block's mentions are given in the order they open.
        spans: list[tuple[int, int, list[str]] | None] = []
        found: list[tuple[int, Mention]] = []
        for at, child in enumerate(token.children):
            if child.type == "entity_open":
                meta = child.meta or {}
                identifier = str(meta.get("id") or "")
                followed = meta.get("kind") == MENTION and pattern.match(identifier)
                spans.append((at, int(identifier), []) if followed else None)
            elif child.type == "entity_close":
                if spans and (closed := spans.pop()) is not None:
                    opened, number, words = closed
                    found.append((opened, Mention(number, " ".join("".join(words).split()), line)))
            elif spans and (part := read(child)):
                for open_ in spans:
                    if open_ is not None:
                        open_[2].append(part)
        yield from (mention for _, mention in sorted(found, key=lambda item: item[0]))


def targets(*bodies: str) -> list[Mention]:
    """Every mention of `bodies` with a document's number, in order of occurrence."""
    return [mention for body in bodies for mention in _mentions(RENDERER.parse(body))]


def targets_in(tokens: Sequence[Token]) -> list[Mention]:
    """`targets` of a text already parsed, so a page that renders it parses it once."""
    return list(_mentions(tokens))


def reachable(user: Any, numbers: Iterable[int]) -> frozenset[int]:
    """The numbers among `numbers` naming a document `user` may read while it is active; the same
    few queries whatever the count."""
    from access.rights import readable
    from documents.models import Document, DocumentState

    wanted = set(numbers)
    if not wanted or user is None or not user.is_authenticated:
        return frozenset()
    found = dict(
        Document.objects.filter(number__in=wanted, state=DocumentState.ACTIVE).values_list(
            "pk", "number"
        )
    )
    return frozenset(found[pk] for pk in readable(user, found))


@dataclass(frozen=True)
class SeeAlso:
    """A document the text mentions: its number, the first mention's words, and its title where
    the reader may follow it — `None` where not, and the words stand (DL-0437)."""

    number: int
    words: str
    title: str | None


def see_also(
    user: Any,
    found: Sequence[Mention],
    *,
    own: int,
    reachable: frozenset[int] | None = None,
) -> list[SeeAlso]:
    """Each document of the mentions `found` (`targets`), once, in order of first mention, the
    document `own` left out; titled where `user` may read it while it is active. `reachable`,
    where the page already holds it, is its reader's context's, so the panel and the text agree.
    A fixed number of queries."""
    from documents.models import Document

    first: dict[int, str] = {}
    for mention in found:
        if mention.number != own:
            first.setdefault(mention.number, mention.words)
    followed = reachable if reachable is not None else _reachable(user, first)
    titles = (
        dict(Document.objects.filter(number__in=followed).values_list("number", "title"))
        if followed
        else {}
    )
    return [SeeAlso(number, words, titles.get(number)) for number, words in first.items()]


# `see_also`'s keyword shadows the function inside it.
_reachable = reachable

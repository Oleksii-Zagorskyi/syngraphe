"""The role directory (DL-0073, DL-0448): each role the document declares, then any role marked
without a declaration, with every heading or clause marking it, numbered and linked to its place,
its text as the reader reads it. Derived at
render from the version shown; nothing is stored and no agent writes it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext as _
from markdown_it.token import Token

from documents import entities
from editing.markdown.words import words
from rendering.outline import anchor, clause_anchor, table_anchor
from rendering.renderer import RENDERER, RenderContext

ROLE = "role"
# The longest text a place shows as it reads; a longer clause shows its opening words.
SHOWN = 280


@dataclass(frozen=True)
class Stream:
    """One text's labelled tokens: the body, linking on its own page, or a part of the document
    whose places carry its page as `link` and its name before their number as `label`."""

    tokens: list[Token]
    link: str = ""
    label: str = ""


@dataclass(frozen=True)
class Place:
    """A heading or clause marking a role: its number, the address of its anchor, its text."""

    label: str
    href: str
    html: SafeString


@dataclass
class Role:
    """A role and its places: a declared one by its key and label; one marked with a key the file
    lacks by its key and its first words; one marked without a key by its words, `key` `None`."""

    key: str | None
    label: str
    places: list[Place] = field(default_factory=list)


def _marked(children: list[Token]) -> list[tuple[str | None, str]]:
    """Each role span of an inline's children: its key, or `None`, and the label the commit would
    declare it with — in order."""
    return [
        ((child.meta or {}).get("id"), entities.label(children, i))
        for i, child in enumerate(children)
        if child.type == "entity_open" and (child.meta or {}).get("kind") == ROLE
    ]


def _shown(children: list[Token], context: RenderContext | None) -> SafeString:
    """A place's text, its number left out: as the page renders it while the text is short;
    otherwise its words cut at `SHOWN` characters, so a clause holding many roles adds no more
    than that for each — the directory stays linear in the text."""
    text = [child for child in children if not (child.meta or {}).get("num")]
    plain = words(text)
    if len(plain) > SHOWN:
        return SafeString(escape(plain[:SHOWN].rstrip()) + "…")
    env: dict[str, Any] = {"context": context}
    html = str(RENDERER.renderer.renderInline(text, RENDERER.options, env))  # type: ignore[attr-defined]
    return mark_safe(html.strip())  # noqa: S308


def roles(
    streams: Sequence[Stream], declared: list[Any], *, context: RenderContext | None
) -> list[Role]:
    """The directory over `streams` in turn: each declared role in the file's order, each with its
    places in text order; then the roles marked without a declaration, by key or by words, in the
    order first met. A declared role marked nowhere has no places."""
    found: dict[tuple[str, str], Role] = {
        ("key", e.key): Role(e.key, e.label) for e in declared if e.kind == ROLE
    }
    for stream in streams:
        tokens = stream.tokens
        tables = within = 0
        # The heading or clause a table follows, which its cells' places name: cells carry no
        # number of their own. A table before any names itself.
        last: tuple[str, str] | None = None
        for i, token in enumerate(tokens):
            if token.type == "table_open":
                tables += 1
                within += 1
            elif token.type == "table_close":
                within -= 1
            if token.type != "inline" or not token.children:
                continue
            children = token.children
            first = children[0]
            if (first.meta or {}).get("num"):
                number = str(first.meta["label"])
                opener = tokens[i - 1].type if i else ""
                last = (
                    number,
                    anchor(number) if opener == "heading_open" else clause_anchor(number),
                )
                label, target = number, last[1]
            elif within and last is not None:
                label, target = f"{last[0]} {_('(table)')}", last[1]
            elif within:
                label, target = _("(table)"), table_anchor(tables)
            else:
                continue
            shown: SafeString | None = None
            seen: set[tuple[str, str]] = set()
            for key, named in _marked(children):
                group = ("key", key) if key else ("words", named)
                if group in seen:
                    continue
                seen.add(group)
                role = found.setdefault(group, Role(key or None, named))
                # Rendered once for the clause, however many roles it marks.
                shown = shown if shown is not None else _shown(children, context)
                role.places.append(
                    Place(f"{stream.label}{label}", f"{stream.link}#{target}", shown)
                )
    return list(found.values())

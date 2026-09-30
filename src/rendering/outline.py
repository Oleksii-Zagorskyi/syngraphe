"""The outline (DL-0195): every heading of the version shown, nested by level, each with the number
the text shows beside it.

Read from the tokens the reading view renders, so the outline names exactly the headings on the
page.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from markdown_it.token import Token


@dataclass
class Heading:
    """One heading: its number, its text as a reader reads it, the anchor the page gives it, and
    the headings under it."""

    label: str
    text: str
    anchor: str
    children: list[Heading] = field(default_factory=list)


def _text(inline: Token) -> str:
    words = []
    for child in inline.children or []:
        if (child.meta or {}).get("num"):
            continue
        if child.type in ("text", "code_inline"):
            words.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            words.append(" ")
    return "".join(words).strip()


def anchor(label: str) -> str:
    return f"h-{label}"


def outline(tokens: Sequence[Token]) -> list[Heading]:
    """The headings of labelled tokens (`rendering.renderer.labelled`), as a tree: a heading holds
    every deeper heading after it, up to the next of its level or shallower. Each heading token
    gains its anchor as its `id`, so the outline's links reach it."""
    roots: list[Heading] = []
    open_: list[tuple[int, Heading]] = []
    for i, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        inline = tokens[i + 1]
        first = inline.children[0] if inline.children else None
        if first is None or not (first.meta or {}).get("num"):
            continue
        label = first.meta["label"]
        heading = Heading(label, _text(inline), anchor(label))
        token.attrSet("id", heading.anchor)
        level = int(token.tag[1:])
        while open_ and open_[-1][0] >= level:
            open_.pop()
        (open_[-1][1].children if open_ else roots).append(heading)
        open_.append((level, heading))
    return roots

"""The outline (DL-0195): every heading of the version shown, nested by level, each with the number
the text shows beside it; and the anchors the role directory links to — `c-<label>` on each clause
of the view, `t-<n>` on each table.

Read from the tokens the reading view renders, so the outline names exactly the headings on the
page.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from markdown_it.token import Token

from editing.markdown.words import words


@dataclass
class Heading:
    """One heading: its number, its text as a reader reads it, the anchor the page gives it, and
    the headings under it."""

    label: str
    text: str
    anchor: str
    children: list[Heading] = field(default_factory=list)


def _text(inline: Token) -> str:
    return words([child for child in inline.children or [] if not (child.meta or {}).get("num")])


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


def clause_anchor(label: str) -> str:
    return f"c-{label}"


def table_anchor(number: int) -> str:
    return f"t-{number}"


def anchor_clauses(tokens: Sequence[Token]) -> None:
    """Each labelled clause of labelled tokens gains its anchor as its `id`, as each heading does
    in `outline`, and each table its own, counted in order, so the role directory's places reach
    them. A tight list draws no paragraph of its own: its item carries the clause's anchor. Set in
    the view's tokens alone: the text rendered anywhere else carries none."""
    tables = 0
    for i, token in enumerate(tokens):
        if token.type == "table_open":
            tables += 1
            token.attrSet("id", table_anchor(tables))
            continue
        if token.type != "paragraph_open" or i + 1 >= len(tokens):
            continue
        children = tokens[i + 1].children or []
        first = children[0] if children else None
        if first is None or not (first.meta or {}).get("num"):
            continue
        holder = (
            tokens[i - 1]
            if token.hidden and i and tokens[i - 1].type == "list_item_open"
            else token
        )
        holder.attrSet("id", clause_anchor(first.meta["label"]))

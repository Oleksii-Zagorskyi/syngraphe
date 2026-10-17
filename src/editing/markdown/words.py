"""A text's words as a reader reads them: one reading for every place that names something by its
words — an entity's label, a mention's words, a place in the role directory, a heading in the
outline — so two of them never disagree about the same span.
"""

from __future__ import annotations

from collections.abc import Sequence

from markdown_it.token import Token


def read(token: Token) -> str:
    """What one inline token reads as: its text, inline code's text, a line break a space; any
    other token — markup, an image — nothing."""
    if token.type in ("text", "code_inline"):
        return token.content
    if token.type in ("softbreak", "hardbreak"):
        return " "
    return ""


def words(children: Sequence[Token]) -> str:
    """The words of inline children, runs of space one."""
    return " ".join("".join(read(child) for child in children).split())


def span_words(children: Sequence[Token], start: int) -> str:
    """The words of the span opening at `children[start]`, up to its close, the spans inside it
    included. Read in place: a copy of the rest of the paragraph per span costs the square of the
    spans a paragraph holds."""
    parts: list[str] = []
    depth = 0
    for at in range(start + 1, len(children)):
        child = children[at]
        if child.type == "entity_open":
            depth += 1
        elif child.type == "entity_close":
            if not depth:
                break
            depth -= 1
        else:
            parts.append(read(child))
    return " ".join("".join(parts).split())

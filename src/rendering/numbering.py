"""Clause numbers, derived at render and never stored (DL-0065): `1.1-3` is the heading path, a
hyphen, and the paragraph's index within its section.

The twin of `src/editing/js/gutter.js::clauseNumbers`, so a reader and an editor see the same
numbers: every paragraph outside a table counts, inside lists, quotes and callouts too; a paragraph
holding an image alone does not; a skipped heading level counts as 1; a paragraph before the first
heading carries its index alone. Headings carry their path, as Epic 7's numbering planned.
"""

from __future__ import annotations

from collections.abc import Sequence

from markdown_it.token import Token


def _image_alone(inline: Token | None) -> bool:
    children = (inline.children if inline is not None else None) or []
    return len(children) == 1 and children[0].type == "image"


def labels(tokens: Sequence[Token]) -> dict[int, str]:
    """Each labelled `heading_open` and `paragraph_open` token's label, by its index."""
    path: list[int] = []
    index = 0
    tables = 0
    found: dict[int, str] = {}
    for i, token in enumerate(tokens):
        if token.type == "table_open":
            tables += 1
        elif token.type == "table_close":
            tables -= 1
        elif token.type == "heading_open":
            level = int(token.tag[1:])
            if len(path) > level:
                del path[level:]
            else:
                path.extend([0] * (level - len(path)))
            path[level - 1] += 1
            for j in range(level - 1):
                path[j] = path[j] or 1
            index = 0
            found[i] = ".".join(map(str, path))
        elif token.type == "paragraph_open" and not tables:
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            if _image_alone(inline):
                continue
            index += 1
            heading = ".".join(map(str, path))
            found[i] = f"{heading}-{index}" if heading else str(index)
    return found

"""A heading's own number, stripped (DL-0441): a heading is numbered by its place in the text and
the number is never stored (DL-0065), so a number its author typed — or a Markdown export wrote
(DL-0363) — before its text goes, where it equals the number the outline gives it. The inverse of
`rendering.export.markdown.number_headings` for every heading with text.
"""

from __future__ import annotations

import re

from editing.markdown.parser import parser

OWN = r"^({label})\.?[ \t]+(?=\S)"
# A heading line: its hashes, the spaces after them, its text.
LINE = re.compile(r"^(#{1,6}[ \t]+)(.*)$")
# Lines as markdown-it counts them, each break kept to be written back as it came.
BREAK = re.compile(r"(\r\n?|\n)")


def strip_own_numbers(text: str) -> str:
    """`text` with each heading's own number taken from before its text: exactly its label,
    optionally followed by a full stop, then spaces or tabs. Any other heading, and every other
    line and line break, is left as it stands."""
    from rendering.numbering import heading_labels

    parts = BREAK.split(text)
    lines, breaks = parts[0::2], parts[1::2]
    headings = [t for t in parser().parse(text) if t.type == "heading_open" and t.map is not None]
    labels = heading_labels([int(t.tag[1:]) for t in headings])
    for token, label in zip(headings, labels, strict=True):
        assert token.map is not None
        found = LINE.match(lines[token.map[0]])
        if found is None:
            continue
        marks, title = found.groups()
        lines[token.map[0]] = marks + re.sub(OWN.format(label=re.escape(label)), "", title, count=1)
    return "".join(line + brk for line, brk in zip(lines, [*breaks, ""], strict=True))

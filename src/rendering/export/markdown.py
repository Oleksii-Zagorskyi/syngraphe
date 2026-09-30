"""The Markdown export (DL-0181, DL-0184): the source view saved — the stored text with each
paragraph's lines joined into one, every mark as stored, no frontmatter.
"""

from __future__ import annotations

import re

from markdown_it.token import Token

from editing.markdown.parser import parser

# A line that opens a block of its own and never continues a paragraph: a callout's marker.
MARKER = re.compile(r"^[ \t]*(?:>[ \t]*)+\[![^\]]+\][ \t]*$")
# The escapes a sentence carries only for starting a line (`serializer.js::esc`): a marker, a
# heading's hashes, a number's stop, a leading `=`. Joined into its paragraph it no longer starts
# one, and the source view writes it without them; `*` is escaped anywhere and keeps its escape.
LINE_START = (
    (re.compile(r"^\\([+\->])"), r"\1"),
    (re.compile(r"^(\s*)\\(#{1,6})(\s|$)"), r"\1\2\3"),
    (re.compile(r"^(\s*[0-9]+)\\([.)])(\s|$)"), r"\1\2\3"),
    (re.compile(r"^\\="), "="),
)


def _unescaped(sentence: str) -> str:
    for pattern, replacement in LINE_START:
        sentence = pattern.sub(replacement, sentence)
    return sentence


def _prefix(line: str) -> int:
    """The length of a continuation line's own prefix: quote markers and the indent of a list
    item's content."""
    at = 0
    while at < len(line) and line[at] in " \t>":
        at += 1
    return at


def join_paragraphs(body: str) -> str:
    """`body`, as stored, with every paragraph on one line: its continuation lines lose their
    quote markers or list indent and join the first with a space. Headings, table rows, blank
    lines, a quote's empty line and a callout's marker stay as they are."""
    lines = body.split("\n")
    joined: dict[int, int] = {}
    tokens: list[Token] = parser().parse(body)
    for token in tokens:
        if token.type != "paragraph_open" or token.map is None:
            continue
        start, end = token.map
        if start < len(lines) and MARKER.match(lines[start]):
            start += 1
        for n in range(start + 1, end):
            joined[n] = start
    out: list[str] = []
    heads: dict[int, int] = {}
    for n, line in enumerate(lines):
        if n in joined:
            head = heads[joined[n]]
            sentence = _unescaped(line[_prefix(line) :].strip())
            out[head] = f"{out[head].rstrip()} {sentence}"
            continue
        heads[n] = len(out)
        out.append(line)
    return "\n".join(out).rstrip("\n") + "\n"

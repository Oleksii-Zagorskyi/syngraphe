"""*canonicalise* — the submitted text in canonical form, and its layout: which lines are the
sentences of a paragraph and which are anything else (DL-0112, DL-0240, ASR-20).

Canonical form is Unicode NFC, no trailing whitespace, and the one spelling per construct; the
canonical table row — one space inside each cell edge, no alignment padding, a delimiter row
keeping only its alignment colons — is the serialiser's table writer, so a prettifier's padding
canonicalises back to the stored bytes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from editing.markdown.parser import parser
from editing.normalizer.spellings import respell

TRAILING = re.compile(r"(\\*)[ \t]+$", re.MULTILINE)
# A list marker in a line's prefix; a continuation line carries spaces of the same width.
LIST_MARKER = re.compile(r"-[ ]|[0-9]+\.[ ]")
# The escapes the serialiser writes only at a line's start (`serializer.esc`), which mean nothing
# inside a line: a sentence that moves off a line's start is the same text without them.
LINE_START_ESCAPE = re.compile(r"^\\(?=[-+>=#])|^([0-9]+)\\(?=[.)])")


def canonicalise(text: str) -> str:
    """`text` in NFC, trailing whitespace removed, in the one stored spelling."""
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return TRAILING.sub(_trailing, respell(TRAILING.sub(_trailing, text)))


def _trailing(m: re.Match[str]) -> str:
    """Trailing whitespace removed — but for one space after an odd run of backslashes, which would
    otherwise turn a literal backslash into a line break."""
    backslashes = m.group(1)
    return backslashes + (" " if len(backslashes) % 2 else "")


def unescaped(line: str) -> str:
    """A line's text as it reads inside a paragraph: a line-start escape removed."""
    return LINE_START_ESCAPE.sub(lambda m: m.group(1) or "", line, count=1)


@dataclass(frozen=True)
class Paragraph:
    """A paragraph's lines: where they are in the file, the prefix each carries — quote markers,
    indentation, a list marker on the first — and their text. `text` is the paragraph as one
    line, which is how every path compares: the lines joined by a space."""

    first: int
    prefixes: tuple[str, ...]
    lines: tuple[str, ...]

    @property
    def text(self) -> str:
        return " ".join([self.lines[0], *(unescaped(line) for line in self.lines[1:])])

    @property
    def continuation(self) -> str:
        if len(self.prefixes) > 1:
            return self.prefixes[1]
        return LIST_MARKER.sub(lambda m: " " * len(m.group(0)), self.prefixes[0])


@dataclass(frozen=True)
class Layout:
    """A text's lines and its paragraphs; every other line — a heading, a table row, a blank
    line, a callout marker — is `kinds[i]`: `heading`, `row`, `delimiter` or `other`."""

    lines: tuple[str, ...]
    paragraphs: tuple[Paragraph, ...]
    kinds: dict[int, str]


def layout(text: str) -> Layout:
    """The layout of a text in stored form."""
    lines = text.split("\n")
    kinds: dict[int, str] = {}
    paragraphs: list[Paragraph] = []
    tokens = parser().parse(text)
    for index, token in enumerate(tokens):
        if token.map is None:
            continue
        start, stop = token.map
        if token.type == "heading_open":
            kinds[start] = "heading"
        elif token.type == "table_open":
            for number in range(start, stop):
                kinds[number] = "delimiter" if number == start + 1 else "row"
        elif token.type == "paragraph_open":
            found = _paragraph(lines, start, stop, tokens[index + 1].content)
            if found is not None:
                paragraphs.append(found)
    return Layout(tuple(lines), tuple(paragraphs), kinds)


def _paragraph(lines: list[str], start: int, stop: int, content: str) -> Paragraph | None:
    """A paragraph from its source lines and its inline content; `None` when the content cannot
    be laid over the lines — then its lines are carried whole, like any other line."""
    texts = content.split("\n")
    first = stop - len(texts)  # a callout's marker line precedes its first paragraph's text
    if not content or first < start:
        return None
    prefixes = []
    for number, line_text in enumerate(texts, start=first):
        if not lines[number].endswith(line_text):
            return None
        prefixes.append(lines[number][: len(lines[number]) - len(line_text)])
    return Paragraph(first, tuple(prefixes), tuple(texts))

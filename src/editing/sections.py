"""A body's sections as ranges of its lines, for the editors open on one section of a draft.

A section runs from a heading to the line before the next heading of the same or a shallower depth,
or to the end of the body; the text before the first heading belongs to none. A heading is what the
platform's own parser takes for one at the top level, so a `#` line inside a quote, a list or a
code block is not. A `load` asks for a section by its heading's ordinal, `"section:<n>"`, and the
whole body by `"whole"`; an open section editor is stored by its span — `"section:<n>"`, or
`"section:<n>:<count>"` when its text holds more headings than its own. The server finds the span
again from the ordinal, compares, splices, and moves the other editors' ordinals by the shift.

Every index counts lines as `body.splitlines(keepends=True)` splits them, so joining the lines
gives the body back byte for byte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from editing.markdown.parser import parser

WHOLE = "whole"

# No body under the size allowed holds a million headings: a longer ordinal is no section.
SECTION = re.compile(r"section:(0|[1-9][0-9]{0,5})")
# The line endings the parser counts lines by (CommonMark's); `splitlines` counts more.
LINE_ENDING = re.compile(r"\r\n?|\n")


@dataclass(frozen=True)
class Range:
    """A section: `start` its heading's line, `end` one past its last line, `level` the heading's
    depth, 1 for `#`."""

    start: int
    end: int
    level: int


def _lines(body: str) -> list[str]:
    return body.splitlines(keepends=True)


def ranges(body: str) -> list[Range]:
    """Every section of `body`, in body order; none for a body without a heading."""
    lines = _lines(body)
    # The parser's line `k` starts where its k-th line ending closes; `splitlines` also breaks at
    # a line separator, a form feed and the like, so its index for the same place can be later.
    parser_starts = [0] + [m.end() for m in LINE_ENDING.finditer(body)]
    index_at: dict[int, int] = {}
    offset = 0
    for index, line in enumerate(lines):
        index_at[offset] = index
        offset += len(line)
    headings = [
        (index_at[parser_starts[token.map[0]]], int(token.tag[1]))
        for token in parser().parse(body)
        if token.type == "heading_open" and token.level == 0 and token.map is not None
    ]
    # One pass: a heading ends every open section of its own or a deeper level. Scanning ahead
    # from each heading instead costs the square of their number, under the document's lock.
    ends = [len(lines)] * len(headings)
    waiting: list[int] = []
    for position, (start, level) in enumerate(headings):
        while waiting and headings[waiting[-1]][1] >= level:
            ends[waiting.pop()] = start
        waiting.append(position)
    return [Range(start, ends[i], level) for i, (start, level) in enumerate(headings)]


def section_text(body: str, section: Range) -> str:
    """The section's lines exactly as they stand, its ending newline included."""
    return "".join(_lines(body)[section.start : section.end])


def splice(body: str, section: Range, text: str) -> str:
    """The body with the section's lines replaced by `text`. A text without a final newline gets
    one when lines follow it, so the next line does not join it; an empty text removes the lines."""
    lines = _lines(body)
    after = lines[section.end :]
    if text and after and not text.endswith(("\n", "\r")):
        text += "\n"
    return "".join(lines[: section.start]) + text + "".join(after)


def ordinal_of(value: str) -> int | None:
    """The ordinal a `"section:<n>"` value names, `n` in ASCII digits without a sign or leading
    zeros; `None` for `"whole"` and anything else."""
    m = SECTION.fullmatch(value)
    return int(m.group(1)) if m else None


def shift(old_body: str, new_body: str, ordinal: int) -> int:
    """How far the splice of the section at `ordinal`, which turned `old_body` into `new_body`,
    moved the ordinals after it; the server adds it to every other open editor's ordinal greater
    than `ordinal`.

    It is the change in the whole count of sections. The splice changed only that section's
    lines, so every heading added or removed lies at or before it, and the sections after it are
    the same sections, each moved by this much. `ordinal` names which splice is meant; the count
    does not need it.
    """
    return len(ranges(new_body)) - len(ranges(old_body))


# What an open section editor spans: from its heading, through every heading its own text holds —
# its subsections, and any heading typed into it, which does not split the editor (ADR-0006) — to
# the line before the next heading or the end of the body. Stored as `section:<n>`, or
# `section:<n>:<count>` when its text holds more than its own heading.
SPAN = re.compile(r"section:(0|[1-9][0-9]{0,5})(?::([2-9]|[1-9][0-9]{1,5}))?")


def span_of(value: str) -> tuple[int, int] | None:
    """The ordinal and the count of headings a stored section editor's range names; `None` for
    `"whole"` and anything else."""
    m = SPAN.fullmatch(value)
    if m is None:
        return None
    return int(m.group(1)), int(m.group(2) or 1)


def span_name(ordinal: int, count: int) -> str:
    """The stored range of a section editor over `count` headings from `ordinal`."""
    return f"section:{ordinal}" if count == 1 else f"section:{ordinal}:{count}"


def headings_in(text: str) -> int:
    """How many headings `text` holds, as `ranges` counts them."""
    return len(ranges(text))


def extent(body: str, ordinal: int, count: int) -> Range | None:
    """The lines a section editor over `count` headings from `ordinal` spans in `body`; `None`
    when the body has no such headings."""
    found = ranges(body)
    if ordinal + count > len(found):
        return None
    end = found[ordinal + count].start if ordinal + count < len(found) else len(_lines(body))
    return Range(found[ordinal].start, end, found[ordinal].level)

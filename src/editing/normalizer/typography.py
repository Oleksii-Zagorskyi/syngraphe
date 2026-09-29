"""*typography* — quote and dash typography (DL-0273), over text the edit touched and
*reuse* left, before any boundary is placed.

Straight double quotes around a run of text become the language's quotation marks, in matched
pairs only; a spaced hyphen between words becomes a spaced em dash; a doubled hyphen an em dash;
three dots an ellipsis. The apostrophe is never rewritten. The splitter's masking keeps link
destinations, attribute blocks, image syntax and autolinks out of every rule. Nothing else.
"""

from __future__ import annotations

import re

from editing.normalizer.splitter import SPACE, mask

QUOTES = {"uk": ("«", "»"), "en": ("“", "”")}
SPACED_HYPHEN = re.compile(r"(?<=[^ \t\n|]) - (?=[^ \t\n|])")
DOUBLED_HYPHEN = re.compile(r"(?<!-)--(?!-)")
THREE_DOTS = re.compile(r"(?<!\.)\.\.\.(?!\.)")


def _quote_pairs(masked: str) -> list[tuple[int, int]]:
    """The straight double quotes that open and close a run of text, paired in order: an opening
    quote follows a space or the start and precedes a non-space; a closing one the reverse. An
    escaped quote takes no part, and an unmatched quote is left as it is."""
    pairs, opened = [], -1
    for i, character in enumerate(masked):
        if character != '"' or (i > 0 and masked[i - 1] == "\\"):
            continue
        before = masked[i - 1] if i > 0 else " "
        after = masked[i + 1] if i + 1 < len(masked) else " "
        opening = after not in SPACE and (before in SPACE or before in "([«“")
        if opened < 0 and opening:
            opened = i
        elif opened >= 0 and opening and before in SPACE:
            opened = -1  # a second opening quote: the pair is unbalanced, both stay straight
        elif opened >= 0 and before not in SPACE:
            pairs.append((opened, i))
            opened = -1
    return pairs


def typeset(text: str, language: str, masked: str | None = None) -> str:
    """`text` with the typography rules applied outside its masked ranges. `masked` is `text`'s
    mask when the caller computed it over a wider context."""
    masked = mask(text) if masked is None else masked
    replacements: dict[int, tuple[int, str]] = {}
    marks = QUOTES.get(language)
    if marks is not None:
        for opening, closing in _quote_pairs(masked):
            replacements[opening] = (1, marks[0])
            replacements[closing] = (1, marks[1])
    for pattern, replacement in (
        (SPACED_HYPHEN, " — "),
        (DOUBLED_HYPHEN, "—"),
        (THREE_DOTS, "…"),
    ):
        for m in pattern.finditer(masked):
            replacements.setdefault(m.start(), (m.end() - m.start(), replacement))
    out, i = [], 0
    for start in sorted(replacements):
        if start < i:
            continue
        length, replacement = replacements[start]
        out.append(text[i:start])
        out.append(replacement)
        i = start + length
    out.append(text[i:])
    return "".join(out)


def typeset_row(row: str, language: str) -> str:
    """A table row with each cell typeset on its own, so no rule reaches across a pipe."""
    cells, start, escaped = [], 0, False
    for i, character in enumerate(row):
        if character == "|" and not escaped:
            cells.append(row[start:i])
            start = i + 1
        escaped = character == "\\" and not escaped
    cells.append(row[start:])
    return "|".join(typeset(cell, language) for cell in cells)

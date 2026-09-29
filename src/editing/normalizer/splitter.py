"""*split* — the platform's own sentence splitter (ADR-0012): rules written once, parameterised by
the language's two abbreviation lists, over one inline block's Markdown source.

Before any rule runs, link destinations, attribute blocks, image syntax and autolinks are masked
with filler of the same length, so no boundary can fall inside them and offsets survive. The
capitalisation tests read Unicode letters, so a capitalised Cyrillic word counts, and use `str`
methods, not regular expressions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

FILLER = "\x00"
TERMINAL = ".!?…"
# Closing quotation marks, brackets and emphasis delimiters that may follow terminal punctuation;
# the filler stands for a masked destination or attribute block after a link's or span's text.
CLOSING = "»\"')]*_”’" + FILLER
# Opening marks are transparent when reading the first letter of the next sentence or the word
# before a stop.
OPENING = "«\"'([*_“„‘"
# The whitespace that may separate two sentences: the space and the tab, and the Unicode spaces a
# paste from a word processor carries — the no-break space among them.
SPACE = " \t" + "".join(
    chr(c) for c in [0xA0, 0x1680, *range(0x2000, 0x200B), 0x202F, 0x205F, 0x3000]
)
# A web address written as plain text; its trailing punctuation stays outside, so a sentence may
# still end after it.
BARE_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]{1,31}://[^ \t\n<>]*[^ \t\n<>.,;:!?)»”]")
AUTOLINK = re.compile(r"<[A-Za-z][A-Za-z0-9+.\-]{1,31}:[^<> \t\n]*>")


class _Language(Protocol):
    code: str

    def never_final_list(self) -> list[str]: ...

    def may_be_final_list(self) -> list[str]: ...


@dataclass(frozen=True)
class Lists:
    """A language's code and its two abbreviation lists as loaded: *never final* — a stop after
    them never ends a sentence — and *may be final* — a stop after them ends one only before a
    capitalised word. Loaded by the caller, so the rules run without a database."""

    language: str
    never_final: tuple[str, ...]
    may_be_final: tuple[str, ...]

    @classmethod
    def of(cls, language: _Language) -> Lists:
        """The lists of a `LANGUAGE` row."""
        return cls(
            language.code, tuple(language.never_final_list()), tuple(language.may_be_final_list())
        )


@dataclass(frozen=True)
class Boundary:
    """A sentence boundary: `end` is where the sentence stops — after its terminal punctuation
    and closing marks — and `start` is the first character of the next one."""

    end: int
    start: int


def _closing_paren(text: str, at: int) -> int:
    """The index of the `)` that closes the `(` at `at`, or -1: escapes skipped, nesting counted."""
    depth, i = 0, at
    while i < len(text):
        character = text[i]
        if character == "\\":
            i += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return i
        elif character == "\n":
            return -1
        i += 1
    return -1


def _closing_bracket(text: str, at: int) -> int:
    """The index of the `]` that closes the `[` at `at`, or -1."""
    depth, i = 0, at
    while i < len(text):
        character = text[i]
        if character == "\\":
            i += 2
            continue
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def mask(text: str) -> str:
    """`text` with every link destination `(…)`, attribute block `{…}`, image `![…](…)`, autolink
    `<…>` and web address written as text replaced by filler of the same length."""
    chars = list(text)

    def fill(start: int, stop: int) -> None:
        chars[start:stop] = FILLER * (stop - start)

    for m in AUTOLINK.finditer(text):
        fill(m.start(), m.end())
    for m in BARE_URL.finditer(text):
        fill(m.start(), m.end())
    i = 0
    while i < len(text):
        character = text[i]
        if character == "\\":
            i += 2
            continue
        if character == "!" and text.startswith("![", i):
            label_end = _closing_bracket(text, i + 1)
            if label_end > 0 and text.startswith("(", label_end + 1):
                end = _closing_paren(text, label_end + 1)
                if end > 0:
                    fill(i, end + 1)
                    i = end + 1
                    continue
        if character == "]" and text.startswith("(", i + 1):
            end = _closing_paren(text, i + 1)
            if end > 0:
                fill(i + 1, end + 1)
                i = end + 1
                continue
        if character == "]" and text.startswith("{", i + 1):
            end = text.find("}", i + 1)
            if end > 0 and "\n" not in text[i + 1 : end]:
                fill(i + 1, end + 1)
                i = end + 1
                continue
        i += 1
    return "".join(chars)


def _word_before(masked: str, stop: int) -> str:
    """The word that ends at the terminal punctuation at `stop`, opening marks removed."""
    start = stop
    while start > 0 and masked[start - 1] not in SPACE:
        start -= 1
    return masked[start:stop].lstrip(OPENING)


def _first_letter(masked: str, start: int) -> str:
    """The first character of the word at `start`, opening marks passed over."""
    i = start
    while i < len(masked) and masked[i] in OPENING:
        i += 1
    return masked[i] if i < len(masked) else ""


def boundaries(text: str, lists: Lists) -> list[Boundary]:
    """Every sentence boundary the rules place in one inline block's source."""
    masked = mask(text)
    never_final = {word.lower() for word in lists.never_final}
    may_be_final = {word.lower() for word in lists.may_be_final}
    found: list[Boundary] = []
    for stop, character in enumerate(masked):
        if character not in TERMINAL:
            continue
        end = stop + 1
        while end < len(masked) and masked[end] in CLOSING:
            end += 1
        start = end
        while start < len(masked) and masked[start] in SPACE:
            start += 1
        if start == end or start == len(masked):
            continue
        letter = _first_letter(masked, start)
        capitalised = letter.isupper()
        if character in "!?":
            ends = True
        elif character == "…":
            ends = capitalised
        else:
            word = _word_before(masked, stop)
            if letter.islower() or letter.isdigit():
                ends = False
            elif len(word) == 1 and word.isupper():
                ends = False  # an initial
            elif word.lower() in never_final:
                ends = False
            elif word.lower() in may_be_final:
                ends = capitalised
            else:
                ends = True
        if ends:
            found.append(Boundary(end, start))
    return found


def split(text: str, lists: Lists) -> list[str]:
    """`text` as its sentences, the whitespace between them dropped."""
    sentences, at = [], 0
    for boundary in boundaries(text, lists):
        sentences.append(text[at : boundary.end])
        at = boundary.start
    sentences.append(text[at:])
    return sentences

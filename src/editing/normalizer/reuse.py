"""*reuse* — moved and unchanged text keeps its stored lines (DL-0244, DL-0112), before anything
is split: whole paragraphs equal to a stored paragraph anywhere in the file; then alignment in
place, carrying the stored lines of the paragraph at the same place across the unchanged spans;
then, in what is still unmatched, the previous version's stored lines anywhere in the file, found
as runs that stand as sentences, longest first and without overlap. A stored line is carried, in
place or from elsewhere, only where it stands as a sentence of its own — each end an edge of the
paragraph or a sentence's end (DL-0323) — never out of the middle of a longer sentence. Only the
remainder reaches *typography* and *split*.

Where one text matches several identical stored lines any choice leaves the same bytes; which
author it keeps is the authorship worker's (ADR-0011).
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from editing.normalizer.canonical import Layout, Paragraph, unescaped
from editing.normalizer.splitter import CLOSING, SPACE, TERMINAL, mask


@dataclass(frozen=True)
class Piece:
    """One run of a submitted paragraph's text: `start` and `end` in the paragraph's one-line
    text; `stored` the (paragraph, line) of the stored line it reuses, or `None` for remainder."""

    start: int
    end: int
    stored: tuple[int, int] | None = None


class Store:
    """The previous version's paragraphs and lines, indexed for lookup."""

    def __init__(self, previous: Layout) -> None:
        self.layout = previous
        self.paragraphs = previous.paragraphs
        self.lines = frozenset(previous.lines)
        self.by_text: dict[str, int] = {}
        for index, paragraph in enumerate(self.paragraphs):
            self.by_text.setdefault(paragraph.text, index)
        found: dict[str, tuple[int, int]] = {}
        for p, paragraph in enumerate(self.paragraphs):
            for n, line in enumerate(paragraph.lines):
                for key in (line, unescaped(line)):
                    if key.strip(SPACE):
                        found.setdefault(key, (p, n))
        self.keys = sorted(found.items(), key=lambda item: -len(item[0]))
        self.by_first_word: dict[str, list[tuple[str, tuple[int, int]]]] = {}
        for key, stored in self.keys:
            self.by_first_word.setdefault(first_word(key), []).append((key, stored))

    def raw(self, stored: tuple[int, int]) -> str:
        """The stored line's bytes, without its prefix."""
        return self.paragraphs[stored[0]].lines[stored[1]]

    def full(self, stored: tuple[int, int]) -> str:
        """The stored line's bytes, with its prefix."""
        paragraph = self.paragraphs[stored[0]]
        return paragraph.prefixes[stored[1]] + paragraph.lines[stored[1]]


def first_word(text: str) -> str:
    """`text` up to its first whitespace."""
    for i, character in enumerate(text):
        if character in SPACE:
            return text[:i]
    return text


def align(submitted: tuple[Paragraph, ...], store: Store) -> dict[int, int]:
    """Each submitted paragraph's stored paragraph at the same place, where there is one: equal
    paragraphs matched by the diff, and within a changed stretch paired in order."""
    matcher = SequenceMatcher(
        None, [p.text for p in store.paragraphs], [p.text for p in submitted], autojunk=False
    )
    paired: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("equal", "replace"):
            for k in range(min(i2 - i1, j2 - j1)):
                paired[j1 + k] = i1 + k
    return paired


def _ends_sentence(masked: str, end: int) -> bool:
    """Whether the text up to `end` ends a sentence: terminal punctuation, then closing marks."""
    while end > 0 and masked[end - 1] in CLOSING:
        end -= 1
    return end > 0 and masked[end - 1] in TERMINAL


def _starts(text: str, masked: str, start: int) -> bool:
    """Whether a sentence may start at `start`: the paragraph's start, or after a sentence's end
    and whitespace."""
    if start == 0:
        return True
    before = start
    if text[before - 1] not in SPACE:
        return False
    while before > 0 and text[before - 1] in SPACE:
        before -= 1
    return _ends_sentence(masked, before)


def _stands(text: str, masked: str, start: int, end: int) -> bool:
    """Whether `text[start:end]` stands as a sentence of its own: it starts where a sentence may,
    and it ends at the paragraph's end or with a sentence's end before whitespace (DL-0323)."""
    if not _starts(text, masked, start):
        return False
    return end == len(text) or (text[end] in SPACE and _ends_sentence(masked, end))


def _find(text: str, masked: str, key: str, lower: int, upper: int) -> int:
    """The first occurrence of `key` inside `text[lower:upper]` that stands as a sentence, or -1."""
    at = text.find(key, lower, upper)
    while at >= 0:
        if _stands(text, masked, at, at + len(key)):
            return at
        at = text.find(key, at + 1, upper)
    return -1


def pieces(text: str, in_place: int | None, store: Store) -> list[Piece]:
    """A submitted paragraph's one-line text as stored lines it reuses and remainder."""
    whole = store.by_text.get(text)
    if whole is not None:
        if in_place is not None and store.paragraphs[in_place].text == text:
            whole = in_place
        spans, at = [], 0
        for n, line in enumerate(store.paragraphs[whole].lines):
            key = line if n == 0 else unescaped(line)
            spans.append(Piece(at, at + len(key), (whole, n)))
            at += len(key) + 1
        return spans

    runs: list[Piece] = []
    masked = mask(text)
    if in_place is not None:
        at = 0
        for n, line in enumerate(store.paragraphs[in_place].lines):
            for key in dict.fromkeys((line, unescaped(line))):
                found = _find(text, masked, key, at, len(text))
                if found >= 0:
                    runs.append(Piece(found, found + len(key), (in_place, n)))
                    at = found + len(key)
                    break

    runs += _elsewhere(text, masked, _gaps(text, runs), store)
    runs.sort(key=lambda piece: piece.start)
    out: list[Piece] = []
    at = 0
    for run in [*runs, Piece(len(text), len(text))]:
        out += _remainder(text, at, run.start)
        if run.stored is not None:
            out.append(run)
        at = run.end
    return out


def _elsewhere(text: str, masked: str, gaps: list[tuple[int, int]], store: Store) -> list[Piece]:
    """The stored lines found in the unmatched stretches, standing as sentences: every candidate
    at every place a sentence may start, then the longest first, without overlap."""
    candidates: list[tuple[int, int, tuple[int, int]]] = []
    for lower, upper in gaps:
        for at in range(lower, upper):
            if text[at] in SPACE or not _starts(text, masked, at):
                continue
            for key, stored in store.by_first_word.get(first_word(text[at:upper]), ()):
                end = at + len(key)
                if end <= upper and text.startswith(key, at) and _stands(text, masked, at, end):
                    candidates.append((at, end, stored))
    candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
    taken: list[Piece] = []
    for start, end, stored in candidates:
        if all(end <= piece.start or start >= piece.end for piece in taken):
            taken.append(Piece(start, end, stored))
    return taken


def _gaps(text: str, runs: list[Piece]) -> list[tuple[int, int]]:
    """The stretches of `text` no run covers and that hold more than whitespace."""
    gaps, at = [], 0
    for run in sorted(runs, key=lambda piece: piece.start):
        if text[at : run.start].strip(SPACE):
            gaps.append((at, run.start))
        at = run.end
    if text[at:].strip(SPACE):
        gaps.append((at, len(text)))
    return gaps


def _remainder(text: str, start: int, end: int) -> list[Piece]:
    """The unmatched text between two runs, its surrounding whitespace dropped."""
    while start < end and text[start] in SPACE:
        start += 1
    while end > start and text[end - 1] in SPACE:
        end -= 1
    return [Piece(start, end)] if start < end else []

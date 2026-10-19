"""The normalizer (DL-0317): the stored form of a submitted text, a function of the previous
version and the submission, run at commit. Its stages, named and never numbered, in this order:

- *canonicalise* the submission — NFC, trailing whitespace, the canonical table row, the one
  spelling per construct (`canonical`, `spellings`) — and decide what the edit *touched*: a line
  whose canonical form differs from the stored line;
- *reuse* stored lines for unchanged and moved text (`reuse`);
- *typography* over what *reuse* left, on touched lines only (`typography`), once the invisible
  format characters are removed from it (DL-0487);
- *split* that remainder into sentences (`splitter`);
- *check* every new boundary by the parse-preservation invariant, joining the two sentences of a
  boundary that fails it (`invariant`).

A stored line the edit did not touch comes out byte-identical (ASR-20); a line whose bytes differ
from the stored line it carries — a list item renumbered — is touched (DL-0324). The output is
checked before it is returned: accepted by the validator, and written back unchanged by the
serialiser; anything else is a defect, raised rather than stored — except a stored form over the
size ceiling, refused as the draft being too large (`TooLarge`). Every path — the rich
editor, the source view, an outside paste — is treated alike: each submitted paragraph's lines are
joined before anything is compared, and the editor's line breaks only make an untouched paragraph
arrive equal to its stored lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from editing.markdown.rules import is_invisible, without_invisibles
from editing.markdown.serializer import escape_line_start, serialize
from editing.markdown.validator import Refusal, validate
from editing.normalizer import invariant, reuse, splitter, typography
from editing.normalizer.canonical import Paragraph, canonicalise, layout
from editing.normalizer.splitter import Lists
from editing.normalizer.version import RULESET, trailer

__all__ = [
    "RULESET",
    "Lists",
    "Emptied",
    "NormalizerDefect",
    "Normalised",
    "TooLarge",
    "joined",
    "normalize",
    "run",
    "trailer",
]

HEADING = re.compile(r"^(#{1,6}[ ])(.*)$")
BREAKS = re.compile(r"\r\n?")
TRAILING = re.compile(r"[ \t]+$", re.MULTILINE)


class NormalizerDefect(Exception):
    """The normalizer produced a text the validator refuses or the serialiser rewrites."""


class Emptied(NormalizerDefect):
    """Removing the invisible characters of a changed line left a construct empty (DL-0487): the
    draft is refused by the validator's `refusals`, each naming its submitted line."""

    def __init__(self, refusals: list[Refusal]) -> None:
        super().__init__(", ".join(f"{r.code} at line {r.line}" for r in refusals))
        self.refusals = refusals


class TooLarge(NormalizerDefect):
    """The stored form would exceed the size the platform accepts (DL-0329): typography can add
    a few bytes to a draft that stood just under the ceiling. Not a defect of the normalizer — the
    draft is refused as too large, as the editor refuses it."""


@dataclass(frozen=True)
class Normalised:
    """The stored form, and the numbers of its lines, from 0, that the edit touched. The commit
    path stores the text alone; `touched` is what the tests of ASR-20 assert on — that every line
    outside it is byte-identical to the stored line it carries."""

    text: str
    touched: frozenset[int]


def normalize(previous: bytes, submitted: str, lists: Lists) -> bytes:
    """The bytes to store for `submitted` — the draft's body, frontmatter split off — given the
    head's body `previous`, with the document language's `lists`. `submitted` must stand inside
    the whitelist; `spellings.OutsideWhitelist` otherwise."""
    return run(previous, submitted, lists).text.encode("utf-8")


def run(previous: bytes, submitted: str, lists: Lists) -> Normalised:
    """`normalize`, with the lines it touched, for the tests of ASR-20."""
    if submitted == previous.decode("utf-8"):
        return Normalised(submitted, frozenset())
    result = _run(previous, submitted, lists)
    fault = _fault(result.text)
    if fault == [Refusal(1, "too-large")]:
        raise TooLarge(len(result.text.encode("utf-8")))
    if fault is not None:
        emptied = _emptied(previous, submitted)
        if emptied:
            raise Emptied(emptied)
        found = ", ".join(f"{r.code} at line {r.line}" for r in fault) or "not a fixed point"
        raise NormalizerDefect(found)
    return result


def _fault(text: str) -> list[Refusal] | None:
    """`None` when `text` is accepted by the validator and written back unchanged by the
    serialiser; else the validator's refusals, empty when only the serialiser rewrites it."""
    refusals = validate(text)
    if refusals or serialize(text) != text:
        return refusals
    return None


def _emptied(previous: bytes, submitted: str) -> list[Refusal]:
    """The submission's refusals once each line it changed loses its invisible characters, by the
    submitted line: a construct holding nothing else — a list item, a span, a bold run of a
    zero-width space — reads as empty and is refused as what it reads as (DL-0487)."""
    stored = set(previous.decode("utf-8").split("\n"))
    lines = canonicalise(submitted).split("\n")
    return validate(
        "\n".join(line if line in stored else without_invisibles(line) for line in lines)
    )


def _run(previous: bytes, submitted: str, lists: Lists) -> Normalised:
    """The stored form and its touched lines, unchecked."""
    store = reuse.Store(layout(previous.decode("utf-8")))
    canonical = layout(canonicalise(submitted))
    paired = reuse.align(canonical.paragraphs, store)
    by_first = {p.first: (j, p) for j, p in enumerate(canonical.paragraphs)}

    out: list[str] = []
    touched: set[int] = set()
    number = 0
    while number < len(canonical.lines):
        if number in by_first:
            j, paragraph = by_first[number]
            for text, is_touched in _paragraph(paragraph, paired.get(j), store, lists):
                if is_touched:
                    touched.add(len(out))
                out.append(text)
            number += len(paragraph.lines)
            continue
        line = canonical.lines[number]
        if line not in store.lines:
            touched.add(len(out))
            line = _typeset_line(
                without_invisibles(line), canonical.kinds.get(number), lists.language
            )
        out.append(line)
        number += 1
    return Normalised("\n".join(out), frozenset(touched))


def _typeset_line(line: str, kind: str | None, language: str) -> str:
    """A touched heading or table row with typography applied; the splitter divides neither, and
    a delimiter row is never rewritten."""
    if kind == "heading":
        m = HEADING.match(line)
        return m.group(1) + typography.typeset(m.group(2), language) if m else line
    if kind == "row":
        return typography.typeset_row(line, language)
    return line


def _paragraph(
    paragraph: Paragraph, in_place: int | None, store: reuse.Store, lists: Lists
) -> list[tuple[str, bool]]:
    """A submitted paragraph's stored lines, each with its prefix, and whether it is touched."""
    text = paragraph.text
    exposed = bool(text) and is_invisible(text[0])
    masked = splitter.mask(text)
    sentences: list[tuple[str, tuple[int, int] | None]] = []
    for piece in reuse.pieces(text, in_place, store):
        if piece.stored is not None:
            sentences.append((store.raw(piece.stored), piece.stored))
            continue
        # New text loses its invisible characters, the mask kept in step (DL-0487).
        kept = [i for i in range(piece.start, piece.end) if not is_invisible(text[i])]
        typeset = typography.typeset(
            "".join(text[i] for i in kept), lists.language, "".join(masked[i] for i in kept)
        )
        sentences += [(s, None) for s in splitter.split(typeset, lists)]

    if not sentences:
        pairs = zip(paragraph.prefixes, paragraph.lines, strict=True)
        return [
            (prefix + line, False)
            if prefix + line in store.lines
            else (prefix + without_invisibles(line), True)
            for prefix, line in pairs
        ]
    out = []
    for n, (line, stored) in enumerate(
        _check([s for s, _ in sentences], [stored for _, stored in sentences])
    ):
        prefix = paragraph.prefixes[0] if n == 0 else paragraph.continuation
        if stored is None:
            # New text: written as the serialiser writes a sentence at a line's start. The first
            # sentence stands where it was submitted, already escaped — unless an invisible
            # character removed from before it exposed a marker (DL-0487).
            full = prefix + (escape_line_start(line) if n or exposed else line)
            out.append((full, True))
        else:
            full = prefix + line
            out.append((full, full != store.full(stored)))
    return out


def _check(
    texts: list[str], stored: list[tuple[int, int] | None]
) -> list[tuple[str, tuple[int, int] | None]]:
    """The paragraph's lines: each new boundary kept only where the paragraph's parse is the same
    with it as without it; a boundary between two consecutive lines of one stored paragraph is
    not new. Each line with the stored line it is, or `None` for new text or a join."""
    existing = [
        a is not None and b is not None and a[0] == b[0] and b[1] == a[1] + 1
        for a, b in zip(stored, stored[1:], strict=False)
    ]
    if all(existing):
        return list(zip(texts, stored, strict=True))

    def joined(breaks: list[bool]) -> str:
        out = texts[0]
        for text, is_break in zip(texts[1:], breaks, strict=True):
            out += ("\n" if is_break else " ") + text
        return out

    kept = list(existing)
    baseline = invariant.html(joined(existing))
    for k, is_existing in enumerate(existing):
        if is_existing:
            continue
        kept[k] = True
        if invariant.html(joined(kept)) != baseline:
            kept[k] = False

    lines: list[tuple[str, tuple[int, int] | None]] = []
    group = [0]
    for k, is_break in enumerate([*kept, True]):
        if is_break:
            text = " ".join(texts[i] for i in group)
            lines.append((text, stored[group[0]] if len(group) == 1 else None))
            group = [k + 1]
        else:
            group.append(k + 1)
    return lines


def joined(submitted: str, lists: Lists) -> list[int]:
    """The submitted lines, from 1, after which the stored form keeps no line break although the
    submission broke a paragraph there (DL-0441): a sentence carried over a line is joined into
    one line, which the loader reports. Compared by words, so typography and escapes do not
    move a break."""
    stored = layout(run(b"", submitted, lists).text).paragraphs
    # Laid out as stored text is — every break a newline, no trailing space — which keeps each
    # line where it stands.
    given = layout(TRAILING.sub("", BREAKS.sub("\n", submitted))).paragraphs
    if len(stored) != len(given):
        return []
    found: list[int] = []
    for before, after in zip(given, stored, strict=True):
        if len(before.lines) < 2:
            continue
        kept, count = set(), 0
        for line in after.lines:
            count += len(line.split())
            kept.add(count)
        count = 0
        for offset, line in enumerate(before.lines[:-1]):
            count += len(line.split())
            if count not in kept:
                found.append(before.first + offset + 1)
    return found

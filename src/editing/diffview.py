"""Changes shown word by word inside the rendered text (DL-0170, DL-0195): the whole document, the
changes in place. The line diff finds the changed sentences — a sentence is a stored line — and
only those are compared word by word; a change to formatting alone carries its own marker.

The caller passes normalised text: *my edits* the draft normalised against the head, *pending edits*
the head against the last accepted text, a comparison two committed versions. The new text is
rendered as the reading view renders it — its lists, quotes, callouts, tables and clause numbers —
and the marks are spliced into its tokens; both texts are parsed, so each stored line is known by
the block it belongs to and its words as a reader reads them. A removed line stands in its block
where that block keeps other lines, else as a struck block of its kind beside the block it stood by.
This is the one presentation every diff of the product shows. A changed sentence is classified
(`classify`): one whose words are unchanged is a change of *style*, shown formatted and collapsed,
its earlier form opened on click; any other is a change of *sense*, shown with its new formatting,
the inserted words marked inside it and the removed words struck where they stood (DL-0331); one
whose words stand while a link, an image or an entity it points at changed is struck and inserted
whole. A change to a line that holds no words — a callout's type, a callout made or unmade, a
table's alignment — is shown as that line, marked as a change of formatting. Given the authors of
the new text's lines, each line carries its author (DL-0040); lines a mark spans carry one only when
they share it.

The comparison is bounded: the lines, and the words of a changed line, are aligned on what occurs
once on each side (patience sorting), which is near-linear; only a stretch with no such anchor is
aligned by `SequenceMatcher`, and one too large for that is shown as removed and inserted whole —
so no text makes a diff cost more than a bounded amount.
"""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from html import escape
from typing import Any

from django.utils.translation import gettext
from markdown_it.token import Token

from editing.markdown import load_spec
from rendering.renderer import RENDERER, labelled, render_inline, render_tokens

BLOCK_PREFIX = re.compile(r"^((?:[ \t]*>[ \t]?)*[ \t]*(?:[-+*][ \t]+|[0-9]+[.)][ \t]+)?)")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$")
# Possessive throughout, so a line that fails to match costs its length, never its square.
CALLOUT_MARKER = re.compile(r"^[ \t]*+>[ \t]*+\[![^\]]++\][ \t]*+$")
QUOTE_ONLY = re.compile(r"^(?:[ \t]*+>)++[ \t]*+$")
DELIMITER_ROW = re.compile(
    r"^\|?+[ \t]*+:?+-++:?+[ \t]*+(?:\|[ \t]*+:?+-++:?+[ \t]*+)*+\|?+[ \t]*+$"
)
WORD = re.compile(r"\S+|\s+")
# What `SequenceMatcher` may cost: on few distinct elements it compares each pair once per block it
# finds, so a region of n by m costs up to n·m·min(n, m). One region may cost `ALIGN_MOST`, and
# one diff — its lines and every changed line's words — `ALIGN_BUDGET` in all; a region past
# either is shown as removed and inserted whole.
ALIGN_MOST = 2_000_000
ALIGN_BUDGET = 5_000_000
# Typographic characters folded to their plain forms, so a change of typography alone reads as a
# change of style.
TYPOGRAPHY = str.maketrans(
    {"«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "—": "-", "–": "-", "…": "..."}
)
# Below this share of words in common, two sentences at one place are shown as one removed and
# one inserted, never as one rewritten.
SAME_SENTENCE = 0.5
SPACING = re.compile(r"\s+")
# A hard break at a line's end: a backslash not itself escaped.
HARD_BREAK = re.compile(r"(?<!\\)\\$")
# The blocks that hold others, whose nesting a removed block is placed back into.
CONTAINERS = frozenset(
    {
        "blockquote_open",
        "callout_open",
        "bullet_list_open",
        "ordered_list_open",
        "list_item_open",
        "table_open",
        "thead_open",
        "tbody_open",
    }
)


class Change(StrEnum):
    """What a changed sentence changed: its words, or only how they look."""

    SENSE = "sense"
    STYLE = "style"


Opcode = tuple[str, int, int, int, int]


def _anchors(a: list[str], b: list[str], alo: int, ahi: int, blo: int, bhi: int) -> list[int]:
    """Positions in `a` of the elements met exactly once on each side, kept in the longest run
    whose order agrees on both sides; each maps to its one position in `b` (patience sorting)."""
    once_a: dict[str, int] = {}
    for i in range(alo, ahi):
        once_a[a[i]] = -1 if a[i] in once_a else i
    once_b: dict[str, int] = {}
    for j in range(blo, bhi):
        once_b[b[j]] = -1 if b[j] in once_b else j
    pairs = [(i, once_b[x]) for x, i in once_a.items() if i >= 0 and once_b.get(x, -1) >= 0]
    pairs.sort()
    # The longest increasing run of `b` positions, by patience sorting.
    tops: list[int] = []
    back: list[int] = []
    at: list[int] = []
    for n, (_, j) in enumerate(pairs):
        k = bisect_left(tops, j)
        if k == len(tops):
            tops.append(j)
            at.append(n)
        else:
            tops[k] = j
            at[k] = n
        back.append(at[k - 1] if k else -1)
    run: list[int] = []
    n = at[-1] if at else -1
    while n >= 0:
        run.append(n)
        n = back[n]
    return [pairs[n][0] for n in reversed(run)]


# What the diff being rendered may still spend on alignment; unset outside `render_changes`, where
# each alignment has only its own bound.
_BUDGET: ContextVar[list[int] | None] = ContextVar("_BUDGET", default=None)


def _charged(cost: int) -> bool:
    """Whether an alignment of this cost may run, drawing it from the diff's budget."""
    if cost > ALIGN_MOST:
        return False
    budget = _BUDGET.get()
    if budget is None:
        return True
    if cost > budget[0]:
        return False
    budget[0] -= cost
    return True


def _matched(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    """Pairs of equal elements, in order on both sides."""
    found: list[tuple[int, int]] = []
    regions = [(0, len(a), 0, len(b))]
    while regions:
        alo, ahi, blo, bhi = regions.pop()
        while alo < ahi and blo < bhi and a[alo] == b[blo]:
            found.append((alo, blo))
            alo, blo = alo + 1, blo + 1
        while alo < ahi and blo < bhi and a[ahi - 1] == b[bhi - 1]:
            ahi, bhi = ahi - 1, bhi - 1
            found.append((ahi, bhi))
        if alo == ahi or blo == bhi:
            continue
        anchors = _anchors(a, b, alo, ahi, blo, bhi)
        if anchors:
            index_b = {b[j]: j for j in range(blo, bhi)}
            previous_a, previous_b = alo, blo
            for i in anchors:
                j = index_b[a[i]]
                found.append((i, j))
                regions.append((previous_a, i, previous_b, j))
                previous_a, previous_b = i + 1, j + 1
            regions.append((previous_a, ahi, previous_b, bhi))
        elif _charged((ahi - alo) * (bhi - blo) * min(ahi - alo, bhi - blo)):
            matcher = SequenceMatcher(None, a[alo:ahi], b[blo:bhi], autojunk=False)
            for i, j, size in matcher.get_matching_blocks():
                found.extend((alo + i + k, blo + j + k) for k in range(size))
    found.sort()
    return found


def opcodes(a: list[str], b: list[str]) -> list[Opcode]:
    """Opcodes in `SequenceMatcher`'s form for `a` against `b`, bounded as the module says."""
    found: list[Opcode] = []
    i = j = 0
    for mi, mj in [*_matched(a, b), (len(a), len(b))]:
        if mi > i or mj > j:
            tag = "replace" if mi > i and mj > j else ("delete" if mi > i else "insert")
            found.append((tag, i, mi, j, mj))
        if mi < len(a):
            if found and found[-1][0] == "equal" and found[-1][2] == mi:
                _, i1, _, j1, _ = found[-1]
                found[-1] = ("equal", i1, mi + 1, j1, mj + 1)
            else:
                found.append(("equal", mi, mi + 1, mj, mj + 1))
        i, j = mi + 1, mj + 1
    return found


def _content(line: str) -> tuple[str, str]:
    """A line's block kind and its inline text."""
    heading = HEADING.match(line)
    if heading:
        return f"h{min(len(heading.group(1)), load_spec().heading_max_depth)}", heading.group(2)
    if line.lstrip().startswith("|"):
        return "row", " · ".join(cell.strip() for cell in line.strip().strip("|").split("|"))
    prefix = BLOCK_PREFIX.match(line)
    kind = "p"
    if prefix and ">" in prefix.group(1):
        kind = "quote"
    elif prefix and prefix.group(1).strip():
        kind = "item"
    return kind, line[prefix.end() if prefix else 0 :]


def _structural(line: str) -> bool:
    """A line that holds no words of its own: a blank line, a quote's empty line, a table's
    delimiter row, a callout's marker line."""
    return not line.strip() or bool(
        QUOTE_ONLY.match(line) or DELIMITER_ROW.match(line) or CALLOUT_MARKER.match(line)
    )


def _inline(text: str) -> str:
    return render_inline(text)


def _plain(text: str) -> str:
    """The words a reader sees in an inline text, markup removed."""
    tokens = RENDERER.parseInline(text)
    out: list[str] = []
    for token in tokens:
        for child in token.children or []:
            if child.type in ("text", "code_inline"):
                out.append(child.content)
            elif child.type in ("softbreak", "hardbreak"):
                out.append(" ")
    return "".join(out)


def _folded(text: str) -> str:
    """The words of an inline text as a comparison of sense sees them: markup removed, the
    normalizer's typography folded back, runs of space made one."""
    folded = _plain(text).translate(TYPOGRAPHY)
    return SPACING.sub(" ", folded).strip()


def _references(text: str) -> list[tuple[str, ...]]:
    """What an inline text points at, beside its words: each link's target, each image's file and
    description, each entity span's kind and identifier."""
    found: list[tuple[str, ...]] = []
    for token in RENDERER.parseInline(text):
        for child in token.children or []:
            if child.type == "link_open":
                found.append(("link", str(child.attrs.get("href", ""))))
            elif child.type == "image":
                found.append(("image", str(child.attrs.get("src", "")), child.content))
            elif child.type == "entity_open":
                meta = child.meta or {}
                found.append(("entity", str(meta.get("kind")), str(meta.get("id"))))
    return found


def classify(old_sentence: str, new_sentence: str) -> Change:
    """*Style* when the two sentences say the same words and point at the same things — differing
    only in emphasis, underline or typography; *sense* otherwise, a changed link target, image or
    entity included. Both are accepted with the run (ASR-04)."""
    return _classified(_content(old_sentence)[1], _content(new_sentence)[1])


def _classified(old_text: str, new_text: str) -> Change:
    same = _folded(old_text) == _folded(new_text)
    return Change.STYLE if same and _references(old_text) == _references(new_text) else Change.SENSE


def _images(text: str) -> list[Token]:
    return [
        child
        for token in RENDERER.parseInline(text)
        for child in token.children or []
        if child.type == "image"
    ]


def _marked(new_text: str, old_text: str) -> str:
    """`new_text` rendered with its formatting, its words compared with `old_text`'s: inserted
    words marked inside the formatting they carry, removed words struck in plain text before the
    word that follows them; an image the old text lacks marked inserted, one it had struck."""
    old_plain = _plain(old_text)
    old_images = {str(image.attrs.get("src", "")) for image in _images(old_text)}
    new_images = {str(image.attrs.get("src", "")) for image in _images(new_text)}
    tokens = RENDERER.parseInline(new_text)
    children = tokens[0].children or [] if tokens else []
    new_plain = _plain(new_text)
    a, b = WORD.findall(old_plain), WORD.findall(new_plain)
    starts = [0]
    for word in b:
        starts.append(starts[-1] + len(word))
    inserted = [False] * len(new_plain)
    removed: dict[int, list[str]] = {}
    for tag, i1, i2, j1, j2 in opcodes(a, b):
        if tag in ("replace", "delete"):
            removed.setdefault(starts[j1], []).append("".join(a[i1:i2]))
        if tag in ("replace", "insert"):
            for k in range(starts[j1], starts[j2]):
                inserted[k] = True
    out: list[str] = []
    at = 0

    def removed_at(position: int) -> None:
        for words in removed.pop(position, []):
            out.append(f"<del>{escape(words)}</del>")

    def words(text: str) -> None:
        # `text` is the next stretch of `new_plain`: split where the marks change.
        nonlocal at
        i = 0
        while i < len(text):
            removed_at(at + i)
            j = i + 1
            while j < len(text) and inserted[at + j] == inserted[at + i] and at + j not in removed:
                j += 1
            piece = escape(text[i:j])
            out.append(f"<ins>{piece}</ins>" if inserted[at + i] else piece)
            i = j
        at += len(text)

    for child in children:
        if child.type == "text":
            words(child.content)
        elif child.type == "code_inline":
            out.append("<code>")
            words(child.content)
            out.append("</code>")
        elif child.type in ("softbreak", "hardbreak"):
            words(" ")
        else:
            # Removed words stand before any formatting that opens where they were.
            if child.nesting >= 0:
                removed_at(at)
            html = str(RENDERER.renderer.renderInline([child], RENDERER.options, {}))  # type: ignore[attr-defined]
            added = child.type == "image" and str(child.attrs.get("src", "")) not in old_images
            out.append(f"<ins>{html}</ins>" if added else html)
    removed_at(len(new_plain))
    for image in _images(old_text):
        if str(image.attrs.get("src", "")) not in new_images:
            html = str(RENDERER.renderer.renderInline([image], RENDERER.options, {}))  # type: ignore[attr-defined]
            out.append(f"<del>{html}</del>")
    return "".join(out).strip()


def _changed_text(old_text: str, new_text: str) -> str:
    """One sentence rewritten: collapsed when only its formatting changed; struck and inserted
    whole when its words stand but what they point at changed; else marked word by word."""
    if _classified(old_text, new_text) is Change.STYLE:
        # Collapsed: the sentence as it now reads; its earlier form shown when opened.
        label = escape(gettext("formatting only"))
        return (
            f'<span class="format-changed" tabindex="0" data-label="{label}">'
            f'{_inline(new_text)}<span class="format-old">{_inline(old_text)}</span></span>'
        )
    if _folded(old_text) == _folded(new_text):
        return f"<del>{_inline(old_text)}</del><ins>{_inline(new_text)}</ins>"
    return _marked(new_text, old_text)


def _alike(old_text: str, new_text: str) -> bool:
    """Whether two sentences at one place share enough words to be shown as one rewritten; the
    measure is a multiset's, linear in the words."""
    a = _plain(old_text).split()
    b = _plain(new_text).split()
    return SequenceMatcher(None, a, b, autojunk=False).quick_ratio() >= SAME_SENTENCE


def _html(content: str, *, block: bool = False) -> Token:
    """A token that renders `content` as it is: the renderer escapes nothing it did not parse, so
    `content` is built only from `escape()` and the renderer's own output."""
    token = Token("html_block" if block else "html_inline", "", 0)
    token.content = content
    return token


@dataclass
class _Line:
    """What a stored line is in its text's parse: the block it belongs to — the index of its
    `paragraph_open`, `heading_open` or `tr_open` — its words as the parse reads them, with list
    markers, quote prefixes, a callout's marker and a hard break's backslash gone, a row's cells,
    and the containers around its block, outermost first, by their opening tokens' indices."""

    block: int
    text: str
    cells: list[str]
    chain: tuple[int, ...]


def _read(tokens: list[Token], lines: list[str]) -> list[_Line | None]:
    """Each line's `_Line`, or `None` for a line holding no words."""
    found: list[_Line | None] = [None] * len(lines)
    chain: list[int] = []
    for p, token in enumerate(tokens):
        if token.type in CONTAINERS:
            chain.append(p)
        elif token.nesting == -1 and token.type.replace("_close", "_open") in CONTAINERS:
            chain.pop()
        elif token.type in ("paragraph_open", "heading_open") and token.map:
            content = tokens[p + 1].content
            texts = [content] if token.type == "heading_open" else content.split("\n")
            mapped = [j for j in range(*token.map) if not _structural(lines[j])]
            for j, text in zip(mapped, texts, strict=False):
                words = HARD_BREAK.sub("", text.strip()).rstrip()
                found[j] = _Line(p, words, [], tuple(chain))
        elif token.type == "tr_open" and token.map:
            cells = []
            q = p + 1
            while tokens[q].type != "tr_close":
                if tokens[q].type == "inline":
                    cells.append(tokens[q].content)
                q += 1
            found[token.map[0]] = _Line(p, "", cells, tuple(chain))
    return found


class _Plan:
    """What each line of the new text shows — kept, rewritten against an old line, or inserted —
    where each removed old line stands, and the lines holding no words whose change is a change of
    formatting: a callout's type, a callout made or unmade, a table's alignment."""

    def __init__(
        self, old: list[str], new: list[str], was: list[_Line | None], now: list[_Line | None]
    ) -> None:
        self.old, self.new, self.was, self.now = old, new, was, now
        self.rewritten: dict[int, int] = {}
        self.inserted: set[int] = set()
        self.moved: dict[int, int] = {}
        self.removed: list[int] = []
        self.formatting: dict[int, list[str]] = {}
        self.unmarked: list[int] = []
        for tag, i1, i2, j1, j2 in opcodes(old, new):
            if tag == "equal":
                self.moved.update(zip(range(i1, i2), range(j1, j2), strict=True))
                continue
            pairs = min(i2 - i1, j2 - j1) if tag == "replace" else 0
            for k in range(pairs):
                self._pair(i1 + k, j1 + k)
            for i in range(i1 + pairs, i2):
                self._gone(i)
            for j in range(j1 + pairs, j2):
                self._came(j)
        self._index(was)

    def _index(self, was: list[_Line | None]) -> None:
        """The lookups the placement of removed lines makes, built once."""
        self.gone = set(self.removed)
        self.blocks: dict[int, list[int]] = {}
        for i, line in enumerate(was):
            if line is not None:
                self.blocks.setdefault(line.block, []).append(i)
        # The old lines holding words that stay, in order: where a removal finds its neighbours.
        self.staying = sorted(i for i in self.moved if was[i] is not None)

    def _gone(self, i: int) -> None:
        if self.was[i] is not None:
            self.removed.append(i)
        elif CALLOUT_MARKER.match(self.old[i]):
            self.unmarked.append(i)

    def _came(self, j: int) -> None:
        if self.now[j] is not None:
            self.inserted.add(j)
        elif CALLOUT_MARKER.match(self.new[j]):
            self.formatting.setdefault(j, []).append(escape(self.new[j].strip()))

    def _pair(self, i: int, j: int) -> None:
        was, now = self.was[i], self.now[j]
        if was is None and now is None:
            if self.old[i].strip() and self.new[j].strip():
                self.formatting.setdefault(j, []).append(escape(self.new[j].strip()))
            else:
                self._gone(i)
                self._came(j)
        elif was is None or now is None:
            self._gone(i)
            self._came(j)
        elif was.cells or now.cells:
            if was.cells and now.cells:
                self.rewritten[j] = i
                self.moved[i] = j
            else:
                self._gone(i)
                self._came(j)
        elif _alike(was.text, now.text):
            self.rewritten[j] = i
            self.moved[i] = j
        else:
            self._gone(i)
            self._came(j)

    def next_staying(self, i: int) -> int | None:
        """The first old line after `i` whose words stay."""
        at = bisect_right(self.staying, i)
        return self.staying[at] if at < len(self.staying) else None

    def last_staying(self, i: int) -> int | None:
        """The last old line before `i` whose words stay."""
        at = bisect_left(self.staying, i)
        return self.staying[at - 1] if at else None


def _segments(children: list[Token]) -> list[list[Token]]:
    """An inline token's children split at its line boundaries — a soft or hard break outside any
    open mark, a hard break kept with the line it ends — so each piece is one stored line, or
    several when a mark spans a boundary."""
    pieces: list[list[Token]] = [[]]
    depth = 0
    for child in children:
        if child.type == "softbreak" and depth == 0:
            pieces.append([])
            continue
        depth += child.nesting
        pieces[-1].append(child)
        if child.type == "hardbreak" and depth == 0:
            pieces.append([])
    return pieces


def _closes(tokens: list[Token]) -> dict[int, int]:
    """Each opening token's index to its closing token's."""
    found: dict[int, int] = {}
    stack: list[int] = []
    for p, token in enumerate(tokens):
        if token.nesting == 1:
            stack.append(p)
        elif token.nesting == -1 and stack:
            found[stack.pop()] = p
    return found


def render_changes(old: bytes, new: bytes, *, authors: Mapping[int, str] | None = None) -> str:
    """The whole of `new` as the reading view renders it, its differences from `old` marked in
    place. `authors` names the author of a line of `new` by its index from 0; a line it names
    carries that author, a line it does not — or a removed one — none."""
    spending = _BUDGET.set([ALIGN_BUDGET])
    try:
        return _render_changes(old, new, authors)
    finally:
        _BUDGET.reset(spending)


def _render_changes(old: bytes, new: bytes, authors: Mapping[int, str] | None) -> str:
    old_text, new_text = old.decode("utf-8"), new.decode("utf-8")
    old_lines, new_lines = old_text.split("\n"), new_text.split("\n")
    old_tokens = RENDERER.parse(old_text)
    tokens = labelled(new_text)
    was, now = _read(old_tokens, old_lines), _read(tokens, new_lines)
    plan = _Plan(old_lines, new_lines, was, now)
    before, after, blocks = _placed(plan, old_tokens)
    by_block: dict[int, list[int]] = {}
    for j, line in enumerate(now):
        if line is not None:
            by_block.setdefault(line.block, []).append(j)

    def by(lines: list[int], pieces: list[Token]) -> list[Token]:
        names = {authors.get(j) for j in lines} if authors else {None}
        if len(names) != 1 or None in names:
            return pieces
        name = escape(str(names.pop()))
        return [
            _html(f'<span class="by" data-author="{name}" title="{name}">'),
            *pieces,
            _html("</span>"),
        ]

    def struck(texts: list[str]) -> str:
        return " ".join(f"<del>{_inline(text)}</del>" for text in texts)

    def old_side(j: int) -> list[str]:
        """The old words standing at new line `j`: removed ones before it, its own old form,
        removed ones after it."""
        own = []
        if j in plan.rewritten:
            own = [plan.was[plan.rewritten[j]].text]  # type: ignore[union-attr]
        elif j not in plan.inserted:
            own = [now[j].text]  # type: ignore[union-attr]
        return before.get(j, []) + own + after.get(j, [])

    def one(j: int, piece: list[Token]) -> list[Token]:
        out: list[Token] = []
        if before.get(j):
            out.append(_html(struck(before[j]) + " "))
        if j in plan.rewritten:
            earlier = plan.was[plan.rewritten[j]].text  # type: ignore[union-attr]
            out.extend(by([j], [_html(_changed_text(earlier, now[j].text))]))  # type: ignore[union-attr]
        elif j in plan.inserted:
            out.extend(by([j], [_html("<ins>"), *piece, _html("</ins>")]))
        else:
            out.extend(by([j], piece))
        if after.get(j):
            out.append(_html(" " + struck(after[j])))
        return out

    def several(span: list[int], piece: list[Token]) -> list[Token]:
        """Lines a mark spans: compared as one text, the old words against the new."""
        if not any(
            j in plan.rewritten or j in plan.inserted or j in before or j in after for j in span
        ):
            return by(span, piece)
        earlier = "\n".join(text for j in span for text in old_side(j))
        now_text = "\n".join(now[j].text for j in span)  # type: ignore[union-attr]
        if not earlier:
            return by(span, [_html("<ins>"), *piece, _html("</ins>")])
        return by(span, [_html(_changed_text(earlier, now_text))])

    for position, token in enumerate(tokens):
        if token.type == "tr_open" and position in by_block:
            _row(tokens, position, by_block[position][0], plan, by)
        elif (
            token.type == "inline"
            and position - 1 in by_block
            and tokens[position - 1].type != "tr_open"
        ):
            lines = by_block[position - 1]
            children = token.children or []
            label = [c for c in children[:1] if (c.meta or {}).get("num")]
            pieces = _segments(children[len(label) :])
            counts = [1 + sum(c.type == "softbreak" for c in piece) for piece in pieces]
            if sum(counts) != len(lines):
                pieces, counts = [children[len(label) :]], [len(lines)]
            out: list[Token] = list(label)
            at = 0
            for n, (piece, count) in enumerate(zip(pieces, counts, strict=True)):
                if n and not (pieces[n - 1] and pieces[n - 1][-1].type == "hardbreak"):
                    out.append(Token("softbreak", "br", 0))
                span = lines[at : at + count]
                at += count
                out.extend(one(span[0], piece) if count == 1 else several(span, piece))
            token.children = out
    return render_tokens(_with_blocks(tokens, plan, blocks, now))


def _placed(
    plan: _Plan, old_tokens: list[Token]
) -> tuple[dict[int, list[str]], dict[int, list[str]], list[tuple[str, int, str]]]:
    """Where each removed old line stands in the new text. Lines of a block that keeps other lines
    are spliced into it: before the next of its lines that stays, or after the last one before
    them. A block removed whole is placed between blocks, as `(where, new line, html)`: `before`
    or `after` the block of a line that stays, inside the containers the two shared."""
    before: dict[int, list[str]] = {}
    after: dict[int, list[str]] = {}
    blocks: list[tuple[str, int, str]] = []
    done: set[int] = set()
    for i in plan.removed:
        line = plan.was[i]
        if line is None or line.block in done:
            continue
        own = plan.blocks[line.block]
        gone = [k for k in own if k in plan.gone]
        stays = [k for k in own if k in plan.moved]
        done.add(line.block)
        if stays:
            for k in gone:
                at = bisect_right(stays, k)
                text = plan.was[k].text  # type: ignore[union-attr]
                if at < len(stays):
                    before.setdefault(plan.moved[stays[at]], []).append(text)
                else:
                    after.setdefault(plan.moved[stays[at - 1]], []).append(text)
            continue
        later = plan.next_staying(own[-1])
        anchor = later if later is not None else plan.last_staying(own[0])
        shared = 0
        if anchor is not None:
            a_chain = plan.was[anchor].chain  # type: ignore[union-attr]
            while (
                shared < min(len(line.chain), len(a_chain))
                and line.chain[shared] == a_chain[shared]
            ):
                shared += 1
        html = _removed_block(old_tokens, line, gone, plan, shared)
        if anchor is None:
            blocks.append(("end", -1, html))
        else:
            blocks.append(("before" if later is not None else "after", plan.moved[anchor], html))
    for i in plan.unmarked:
        following = plan.next_staying(i)
        if following is not None:
            plan.formatting.setdefault(plan.moved[following], []).append(
                f"<del>{escape(plan.old[i].strip())}</del>"
            )
    return before, after, blocks


def _removed_block(
    old_tokens: list[Token], line: _Line, gone: list[int], plan: _Plan, shared: int
) -> str:
    """A block removed whole, struck, in the element its kind and its containers make, beginning
    below the containers it shared with the text that stays."""
    opening = old_tokens[line.block]
    if opening.type == "tr_open":
        inner = "".join(f"<td><del>{_inline(cell)}</del></td>" for cell in line.cells)
        html = f'<tr class="removed">{inner}</tr>'
    else:
        words = " ".join(f"<del>{_inline(plan.was[k].text)}</del>" for k in gone)  # type: ignore[union-attr]
        if opening.type == "heading_open":
            html = f"<{opening.tag}>{words}</{opening.tag}>"
        elif opening.hidden:
            html = words
        else:
            html = f"<p>{words}</p>"
    for p in reversed(line.chain[shared:]):
        container = old_tokens[p]
        kind = container.type.removesuffix("_open")
        if kind == "list_item":
            html = f'<li class="removed">{html}</li>'
        elif kind == "callout":
            html = f'<div class="callout callout-{escape(container.info)}">{html}</div>'
        elif kind in ("bullet_list", "ordered_list", "blockquote", "table", "thead", "tbody"):
            tag = {"bullet_list": "ul", "ordered_list": "ol"}.get(kind, kind)
            html = f"<{tag}>{html}</{tag}>"
    return html + "\n"


def _row(tokens: list[Token], position: int, j: int, plan: _Plan, by: Any) -> None:
    """A table row's cells, marked cell by cell against the old row; cells the row lost struck
    in its last cell."""
    cells = []
    q = position + 1
    while tokens[q].type != "tr_close":
        if tokens[q].type == "inline":
            cells.append(tokens[q])
        q += 1
    if j not in plan.rewritten and j not in plan.inserted:
        for cell in cells:
            cell.children = by([j], cell.children or [])
        return
    old_cells = plan.was[plan.rewritten[j]].cells if j in plan.rewritten else []  # type: ignore[union-attr]
    for n, cell in enumerate(cells):
        earlier = old_cells[n] if n < len(old_cells) else None
        if earlier is None:
            pieces = [_html("<ins>"), *(cell.children or []), _html("</ins>")]
        elif earlier != cell.content:
            pieces = [_html(_changed_text(earlier, cell.content))]
        else:
            pieces = cell.children or []
        cell.children = by([j], pieces)
    lost = old_cells[len(cells) :]
    if lost and cells:
        cells[-1].children = [
            *(cells[-1].children or []),
            _html(" " + " ".join(f"<del>{_inline(text)}</del>" for text in lost)),
        ]


def _with_blocks(
    tokens: list[Token], plan: _Plan, blocks: list[tuple[str, int, str]], now: list[_Line | None]
) -> list[Token]:
    """The tokens with what stands between blocks spliced in: a formatting change's marker line
    before the block it formats, and each block removed whole beside the block it stood by."""
    closes = _closes(tokens)
    inserts: dict[int, list[Token]] = {}
    # The top-level blocks, by their first line: a marker line belongs to the one holding it, or
    # stands before the first that starts after it.
    tops = [
        (t.map[0], t.map[1], p)
        for p, t in enumerate(tokens)
        if t.level == 0 and t.nesting == 1 and t.map
    ]
    starts = [top[0] for top in tops]

    def outermost(j: int) -> int:
        at = bisect_right(starts, j) - 1
        if at >= 0 and tops[at][0] <= j < tops[at][1]:
            return tops[at][2]
        return tops[at + 1][2] if at + 1 < len(tops) else len(tokens)

    for j, marks in sorted(plan.formatting.items()):
        for marked in marks:
            html = f'<p class="marker"><span class="format-changed">{marked}</span></p>\n'
            inserts.setdefault(outermost(j), []).append(_html(html, block=True))
    for where, j, html in blocks:
        token = _html(html, block=True)
        if where == "end":
            inserts.setdefault(len(tokens), []).append(token)
            continue
        line = now[j]
        assert line is not None
        shared = _shared_depth(tokens, line, html)
        target = line.chain[shared] if shared < len(line.chain) else line.block
        at = target if where == "before" else closes.get(target, target) + 1
        inserts.setdefault(at, []).append(token)
    out: list[Token] = []
    for position, token in enumerate(tokens):
        out.extend(inserts.get(position, []))
        out.append(token)
    out.extend(inserts.get(len(tokens), []))
    return out


def _shared_depth(tokens: list[Token], line: _Line, html: str) -> int:
    """How deep in the anchor's containers a removed block goes: a removed row inside its table's
    body, a removed item inside its list, anything else beside the anchor's own block."""
    kinds = [tokens[p].type for p in line.chain]
    if html.startswith('<tr class="removed">'):
        return len(kinds)
    if html.startswith('<li class="removed">') and "list_item_open" in kinds:
        return len(kinds) - 1 - kinds[::-1].index("list_item_open")
    return len(kinds)

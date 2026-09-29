"""Changes shown word by word inside the rendered text (DL-0170, DL-0195): the whole document, the
changes in place. The line diff finds the changed sentences — a sentence is a stored line — and
only those are compared word by word; a change to formatting alone carries its own marker.

The caller passes normalised text: *my edits* the draft normalised against the head, *pending
edits* the head against the last accepted text, a comparison two committed versions. The rendering
is a plain one — a block per paragraph, heading, list item, quote or table row — and is the one
every diff of the product shows. A changed sentence is classified (`classify`): one whose words are
unchanged is a change of *style*, shown formatted and collapsed, its earlier form opened on click;
any other is a change of *sense*, shown with its new formatting, the inserted words marked inside it
and the removed words struck where they stood (DL-0331). A change to a line that holds no words, a
callout's type or a table's alignment, is shown as that line, marked as a change of formatting.
Given the authors of the new text's lines, each line carries its author (DL-0040).

The comparison is bounded: the lines, and the words of a changed line, are aligned on what occurs
once on each side (patience sorting), which is near-linear; only a stretch with no such anchor is
aligned by `SequenceMatcher`, and one too large for that is shown as removed and inserted whole —
so no text makes a diff cost more than a bounded amount.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from collections.abc import Mapping
from difflib import SequenceMatcher
from enum import StrEnum
from html import escape

from django.utils.translation import gettext
from markdown_it import MarkdownIt
from markdown_it.token import Token

from editing.markdown import load_spec
from editing.markdown.rules import attr_span

BLOCK_PREFIX = re.compile(r"^((?:[ \t]*>[ \t]?)*[ \t]*(?:[-+*][ \t]+|[0-9]+[.)][ \t]+)?)")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$")
# Possessive throughout, so a line that fails to match costs its length, never its square.
CALLOUT_MARKER = re.compile(r"^[ \t]*+>[ \t]*+\[![^\]]++\][ \t]*+$")
DELIMITER_ROW = re.compile(
    r"^\|?+[ \t]*+:?+-++:?+[ \t]*+(?:\|[ \t]*+:?+-++:?+[ \t]*+)*+\|?+[ \t]*+$"
)
WORD = re.compile(r"\S+|\s+")
# The most element comparisons an alignment may cost: `SequenceMatcher` is quadratic at worst.
ALIGN_MOST = 250_000
# Typographic characters folded to their plain forms, so a change of typography alone reads as a
# change of style.
TYPOGRAPHY = str.maketrans(
    {"«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "—": "-", "–": "-", "…": "..."}
)
# Below this share of words in common, two sentences at one place are shown as one removed and
# one inserted, never as one rewritten.
SAME_SENTENCE = 0.5
SPACING = re.compile(r"\s+")


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
        elif (ahi - alo) * (bhi - blo) <= ALIGN_MOST:
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


def _renderer() -> MarkdownIt:
    """markdown-it-py that renders stored text for reading: raw HTML escaped, links checked, spans
    as classed elements, a sentence boundary as a space."""
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    md.inline.ruler.before("link", "attr_span", attr_span)

    # markdown-it binds a render rule to the renderer: the renderer comes first.
    def span_open(_renderer: object, tokens: list[Token], i: int, *_: object) -> str:
        meta = tokens[i].meta or {}
        kind = meta.get("kind") or ""
        if tokens[i].type == "underline_open":
            return '<span class="underline">'
        return f'<span class="entity entity-{escape(kind)}">'

    def span_close(*_: object) -> str:
        return "</span>"

    md.add_render_rule("entity_open", span_open)
    md.add_render_rule("underline_open", span_open)
    md.add_render_rule("entity_close", span_close)
    md.add_render_rule("underline_close", span_close)
    md.add_render_rule("softbreak", lambda *_: " ")
    return md


RENDERER = _renderer()


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
    """A line that holds no words of its own: a blank line, a table's delimiter row, a callout's
    marker line."""
    return not line.strip() or bool(DELIMITER_ROW.match(line) or CALLOUT_MARKER.match(line))


def _inline(text: str) -> str:
    return str(RENDERER.renderInline(text)).strip()


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
    _, old_text = _content(old_sentence)
    _, new_text = _content(new_sentence)
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


def _changed(old_line: str, new_line: str) -> str:
    _, old_text = _content(old_line)
    _, new_text = _content(new_line)
    if classify(old_line, new_line) is Change.STYLE:
        # Collapsed: the sentence as it now reads; its earlier form shown when opened.
        label = escape(gettext("formatting only"))
        return (
            f'<span class="format-changed" tabindex="0" data-label="{label}">'
            f'{_inline(new_text)}<span class="format-old">{_inline(old_text)}</span></span>'
        )
    return _marked(new_text, old_text)


def _alike(old_line: str, new_line: str) -> bool:
    """Whether two sentences at one place share enough words to be shown as one rewritten; the
    measure is a multiset's, linear in the words."""
    a = _plain(_content(old_line)[1]).split()
    b = _plain(_content(new_line)[1]).split()
    return SequenceMatcher(None, a, b, autojunk=False).quick_ratio() >= SAME_SENTENCE


def render_changes(old: bytes, new: bytes, *, authors: Mapping[int, str] | None = None) -> str:
    """The whole of `new` as HTML, its differences from `old` marked in place. `authors` names the
    author of a line of `new` by its index from 0; a line it names carries that author, a line it
    does not — or a removed one — none."""
    old_lines = old.decode("utf-8").split("\n")
    new_lines = new.decode("utf-8").split("\n")
    rendered: list[tuple[str, str]] = []  # (block kind, the line's HTML)

    def by(j: int, html: str) -> str:
        author = authors.get(j) if authors else None
        if not author:
            return html
        name = escape(author)
        return f'<span class="by" data-author="{name}" title="{name}">{html}</span>'

    def keep(line: str, j: int) -> None:
        if _structural(line):
            rendered.append(("p", ""))
            return
        kind, text = _content(line)
        rendered.append((kind, by(j, _inline(text))))

    def whole(line: str, mark: str, j: int | None = None) -> None:
        if _structural(line):
            return
        kind, text = _content(line)
        html = f"<{mark}>{_inline(text)}</{mark}>"
        rendered.append((kind, html if j is None else by(j, html)))

    for tag, i1, i2, j1, j2 in opcodes(old_lines, new_lines):
        if tag == "equal":
            for j in range(j1, j2):
                keep(new_lines[j], j)
        elif tag == "replace":
            pairs = min(i2 - i1, j2 - j1)
            for k in range(pairs):
                old_line, new_line = old_lines[i1 + k], new_lines[j1 + k]
                both_markers = _structural(old_line) and _structural(new_line)
                if both_markers and old_line.strip() and new_line.strip():
                    # A callout's type or a table's alignment changed: the line, marked.
                    marked = escape(new_line.strip())
                    rendered.append(("marker", f'<span class="format-changed">{marked}</span>'))
                    continue
                if _structural(old_line) or _structural(new_line):
                    whole(old_line, "del")
                    if _structural(new_line):
                        keep(new_line, j1 + k)
                    else:
                        whole(new_line, "ins", j1 + k)
                    continue
                if not _alike(old_line, new_line):
                    whole(old_line, "del")
                    whole(new_line, "ins", j1 + k)
                    continue
                kind, _text = _content(new_line)
                rendered.append((kind, by(j1 + k, _changed(old_line, new_line))))
            for line in old_lines[i1 + pairs : i2]:
                whole(line, "del")
            for j in range(j1 + pairs, j2):
                whole(new_lines[j], "ins", j)
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                whole(line, "del")
        else:
            for j in range(j1, j2):
                whole(new_lines[j], "ins", j)
    return _blocks(rendered)


def _blocks(rendered: list[tuple[str, str]]) -> str:
    """The rendered lines grouped into blocks: consecutive sentence lines of one kind make one
    block, and each list item starts its own; a heading, a table row, a changed marker line and a
    blank line each stand alone."""
    html: list[str] = []
    group: list[str] = []
    group_kind = ""

    def close() -> None:
        nonlocal group, group_kind
        if group:
            css = "" if group_kind == "p" else f' class="{group_kind}"'
            html.append(f"<p{css}>{' '.join(group)}</p>")
        group, group_kind = [], ""

    for kind, line in rendered:
        if not line:
            close()
        elif kind.startswith("h"):
            close()
            html.append(f"<{kind}>{line}</{kind}>")
        elif kind in ("row", "marker"):
            close()
            html.append(f'<p class="{kind}">{line}</p>')
        elif kind == "item":
            # Each list item its own block; its later sentences, indented, join it.
            close()
            group_kind = kind
            group.append(line)
        else:
            if group and kind != group_kind and kind != "p":
                close()
            if not group:
                group_kind = kind
            group.append(line)
    close()
    return "\n".join(html)

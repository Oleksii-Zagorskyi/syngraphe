"""Changes shown word by word inside the rendered text (DL-0170, DL-0195): the whole document, the
changes in place. The line diff finds the changed sentences — a sentence is a stored line — and
only those are compared word by word; a change to formatting alone carries its own marker.

The caller passes normalised text: *my edits* the draft normalised against the head, a comparison
two committed versions. The rendering is a plain one — a block per paragraph, heading, list item,
quote or table row — and is the one every diff of the product shows. A changed sentence is shown
as its words, without its formatting; a change to a line that holds no words, a callout's type or
a table's alignment, is shown as that line, marked as a change of formatting.

The comparison is bounded: the lines, and the words of a changed line, are aligned on what occurs
once on each side (patience sorting), which is near-linear; only a stretch with no such anchor is
aligned by `SequenceMatcher`, and one too large for that is shown as removed and inserted whole —
so no text makes a diff cost more than a bounded amount.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from difflib import SequenceMatcher
from html import escape

from markdown_it import MarkdownIt
from markdown_it.token import Token

from editing.markdown.rules import attr_span

BLOCK_PREFIX = re.compile(r"^((?:[ \t]*>[ \t]?)*[ \t]*(?:[-+*][ \t]+|[0-9]+[.)][ \t]+)?)")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$")
CALLOUT_MARKER = re.compile(r"^[ \t]*>[ \t]*\[![^\]]+\][ \t]*$")
DELIMITER_ROW = re.compile(r"^\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
WORD = re.compile(r"\S+|\s+")
# The most element comparisons an alignment may cost: `SequenceMatcher` is quadratic at worst.
ALIGN_MOST = 250_000


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
        return f"h{min(len(heading.group(1)), 4)}", heading.group(2)
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


def _words(old: str, new: str) -> str:
    """`new` against `old`, word by word: inserted words marked, deleted words struck."""
    a, b = WORD.findall(old), WORD.findall(new)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in opcodes(a, b):
        if tag == "equal":
            out.append(escape("".join(a[i1:i2])))
            continue
        if i2 > i1:
            out.append(f"<del>{escape(''.join(a[i1:i2]))}</del>")
        if j2 > j1:
            out.append(f"<ins>{escape(''.join(b[j1:j2]))}</ins>")
    return "".join(out)


def _changed(old_line: str, new_line: str) -> str:
    _, old_text = _content(old_line)
    _, new_text = _content(new_line)
    old_plain, new_plain = _plain(old_text), _plain(new_text)
    if old_plain == new_plain:
        return f'<span class="format-changed">{_inline(new_text)}</span>'
    return _words(old_plain, new_plain)


def render_changes(old: bytes, new: bytes) -> str:
    """The whole of `new` as HTML, its differences from `old` marked in place."""
    old_lines = old.decode("utf-8").split("\n")
    new_lines = new.decode("utf-8").split("\n")
    rendered: list[tuple[str, str]] = []  # (block kind, the line's HTML)

    def keep(line: str) -> None:
        if _structural(line):
            rendered.append(("p", ""))
            return
        kind, text = _content(line)
        rendered.append((kind, _inline(text)))

    def whole(line: str, mark: str) -> None:
        if _structural(line):
            return
        kind, text = _content(line)
        rendered.append((kind, f"<{mark}>{escape(_plain(text))}</{mark}>"))

    for tag, i1, i2, j1, j2 in opcodes(old_lines, new_lines):
        if tag == "equal":
            for line in new_lines[j1:j2]:
                keep(line)
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
                    keep(new_line) if _structural(new_line) else whole(new_line, "ins")
                    continue
                kind, _ = _content(new_line)
                rendered.append((kind, _changed(old_line, new_line)))
            for line in old_lines[i1 + pairs : i2]:
                whole(line, "del")
            for line in new_lines[j1 + pairs : j2]:
                whole(line, "ins")
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                whole(line, "del")
        else:
            for line in new_lines[j1:j2]:
                whole(line, "ins")
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

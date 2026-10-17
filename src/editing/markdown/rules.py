"""The rules written in both languages (ADR-0010): the attributed span, the callout, the `- 1.`
respelling, the tidying of inline text, and the validator's walk. `src/editing/js/rules.js` is this
module's twin — the same functions in the same order, each named by its language's convention —
and the conformance suite holds the two in step. A change here is a change there, in the same
commit.

Patterns use explicit ASCII classes only: Python's `\\w` and `\\s` match Unicode letters and spaces,
JavaScript's do not. `\\Z` here is JavaScript's `$`: Python's `$` also matches before a final line
break.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from markdown_it.helpers import parseLinkLabel

if TYPE_CHECKING:
    from markdown_it.rules_core import StateCore
    from markdown_it.rules_inline import StateInline
    from markdown_it.token import Token

    from editing.markdown import Spec

# `.type` or `.type #id`, the only attribute blocks a span may carry.
ATTRS = re.compile(r"^[ \t]*\.([A-Za-z][A-Za-z0-9_-]*)(?:[ \t]+#([A-Za-z0-9_-]+))?[ \t]*\Z")
# Matched where the label ends, never on a copy of the rest of the text, and bounded, so a long run
# of labels costs linear time.
BLOCK = re.compile(r"\{([^}\n]{0,128})\}")
MARKER = re.compile(r"^\[!([^\]\t\n ]+)\][ \t]*\n?")
FOOTNOTE = re.compile(r"(^|[^\\])\[\^")
TASK = re.compile(r"^\[[ xX]\](?:[ \t]|\Z)")
DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
LINE_BREAK = re.compile(r"\r\n?|\n")
NEWLINE = re.compile(r"[\r\n]")
# C0 and C1 controls but the tab and the line breaks, the Unicode line and paragraph separators,
# and the byte-order mark: invisible, and trimmed differently by the two languages.
CONTROL = re.compile(
    "["
    + "".join(
        re.escape(chr(c))
        for c in [*range(0x00, 0x09), 0x0B, 0x0C, *range(0x0E, 0x20), 0x7F, 0x85]
        + [0x2028, 0x2029, 0xFEFF]
    )
    + "]"
)
# JavaScript's `\s`, spelled out.
SPACE = "".join(
    chr(c)
    for c in [0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0xA0, 0x1680, *range(0x2000, 0x200B)]
    + [0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF]
)
INLINE_CODES = {"code_inline": "inline-code", "html_inline": "html", "hardbreak": "hard-break"}
# The blocks whose lines a link reference definition cannot share.
TEXT_BLOCKS = frozenset({"paragraph_open", "heading_open", "code_block", "fence", "html_block"})

# Every token a document inside the whitelist produces; anything else is refused by name.
KNOWN = frozenset(
    {
        "paragraph_open", "paragraph_close", "heading_open", "heading_close", "inline", "text",
        "softbreak", "bullet_list_open", "bullet_list_close", "ordered_list_open",
        "ordered_list_close", "list_item_open", "list_item_close", "blockquote_open",
        "blockquote_close", "callout_open", "callout_close", "table_open", "table_close",
        "thead_open", "thead_close", "tbody_open", "tbody_close", "tr_open", "tr_close",
        "th_open", "th_close", "td_open", "td_close", "em_open", "em_close", "strong_open",
        "strong_close", "link_open", "link_close", "image", "entity_open", "entity_close",
        "underline_open", "underline_close",
    }
)  # fmt: skip


def lines_of(text: str) -> list[str]:
    """The source lines as markdown-it counts them: `\\r\\n`, `\\r` and `\\n` each end one."""
    return LINE_BREAK.split(text)


def attr_span(state: StateInline, silent: bool) -> bool:
    """`[text]{.type #id}`: an entity span, or `[text]{.underline}`; any other attribute block is
    still a span, with no kind, so the validator names it rather than letting it pass as text."""
    if silent or state.pos >= state.posMax or state.src[state.pos] != "[":
        return False  # never consume silently: a link label's scan would read it as a link
    end = parseLinkLabel(state, state.pos, False)
    if end < 0:
        return False
    m = BLOCK.match(state.src, end + 1)
    if not m:
        return False
    a = ATTRS.match(m.group(1))
    kind = a.group(1) if a else None
    kind_type = "underline" if kind == "underline" else "entity"
    token = state.push(kind_type + "_open", "span", 1)
    token.meta = {"kind": kind, "id": (a.group(2) if a else None) or None, "raw": m.group(1)}
    pos, maximum = state.pos, state.posMax
    state.pos = pos + 1
    state.posMax = end
    state.md.inline.tokenize(state)
    state.pos = pos
    state.posMax = maximum
    # The close token says what it closes, so a rule rendering it alone — a mention's close — can.
    close = state.push(kind_type + "_close", "span", -1)
    close.meta = {"kind": token.meta["kind"], "id": token.meta["id"]}
    state.pos = m.end()
    return True


def callout(state: StateCore) -> None:
    """A quote whose first line starts `[!type]` becomes a callout; text after the marker stays as
    its first paragraph (DL-0238)."""
    tokens = state.tokens
    i = 0
    while i < len(tokens):
        if (
            tokens[i].type != "blockquote_open"
            or i + 2 >= len(tokens)
            or tokens[i + 1].type != "paragraph_open"
            or tokens[i + 2].type != "inline"
        ):
            i += 1
            continue
        m = MARKER.match(tokens[i + 2].content)
        if not m:
            i += 1
            continue
        tokens[i].type = "callout_open"
        tokens[i].info = m.group(1).lower()
        for j in range(i + 1, len(tokens)):
            if tokens[j].type == "blockquote_close" and tokens[j].level == tokens[i].level:
                tokens[j].type = "callout_close"
                break
        tokens[i + 2].content = tokens[i + 2].content[len(m.group(0)) :]
        if not tokens[i + 2].content:
            del tokens[i + 1 : i + 4]
        i += 1


def _trim(children: list[Token], index: int, step: int, strip: Callable[[str], str]) -> None:
    """Strip spaces from the text at one edge of a line of inline content, passing over the marks
    that open or close there, and drop what the stripping empties."""
    edge = "_open" if step == 1 else "_close"
    while 0 <= index < len(children):
        child = children[index]
        if child.type.endswith(edge):
            index += step
        elif child.type == "text":
            child.content = strip(child.content)
            if child.content:
                return
            del children[index]
            if step == -1:
                index -= 1
        else:
            return


def _closing(tokens: list[Token], at: int) -> int:
    """The index of the token closing the one opening at `at`."""
    depth = 0
    for index in range(at, len(tokens)):
        depth += tokens[index].nesting
        if depth == 0:
            return index
    return len(tokens) - 1


def _numbered_items(tokens: list[Token], at: int) -> list[tuple[int, int]] | None:
    """For the bullet list opening at `at`, each item's one numbered item — its open and close —
    when every item holds one numbered list of one item and nothing else; `None` otherwise."""
    close = _closing(tokens, at)
    found: list[tuple[int, int]] = []
    item = at + 1
    while item < close:
        item_close = _closing(tokens, item)
        inner = item + 1
        if (
            tokens[item].type != "list_item_open"
            or tokens[inner].type != "ordered_list_open"
            or _closing(tokens, inner) != item_close - 1
        ):
            return None
        numbered = inner + 1
        numbered_close = _closing(tokens, numbered)
        if numbered_close != item_close - 2:
            return None
        found.append((numbered, numbered_close))
        item = item_close + 1
    return found or None


def numbered_bullets(state: StateCore) -> None:
    """`- 1. Text`: a bullet list each item of which holds one numbered item and nothing else is the
    numbered list its author meant (DL-0441) — one ordered list of those items, in order. Any other
    shape is left for the validator to refuse."""
    # A pass moves each such list it meets whole, and one nested in a moved list is met by the
    # next: as many passes as these lists nest deep, each about the text's length.
    while _numbered_pass(state):
        pass


def _numbered_pass(state: StateCore) -> bool:
    """One pass of `numbered_bullets`, over the text in order; whether it moved any list."""
    tokens = state.tokens
    out: list[Token] = []
    moved_any = False
    at = 0
    while at < len(tokens):
        items = _numbered_items(tokens, at) if tokens[at].type == "bullet_list_open" else None
        if items is None:
            out.append(tokens[at])
            at += 1
            continue
        close = _closing(tokens, at)
        first = items[0][0] - 1
        opening, closing = tokens[first], tokens[_closing(tokens, first)]
        opening.level, closing.level = tokens[at].level, tokens[close].level
        moved: list[Token] = []
        for start, end in items:
            for index in range(start, end + 1):
                tokens[index].level -= 2
                moved.append(tokens[index])
        # One list is loose when any of its items is, as the stored form will read; a list
        # nested in an item keeps its own.
        own = [t for t in moved if t.level == opening.level + 2 and t.type.startswith("paragraph")]
        if any(not t.hidden for t in own):
            for token in own:
                token.hidden = False
        out.append(opening)
        out.extend(moved)
        out.append(closing)
        moved_any = True
        at = close + 1
    state.tokens = out
    return moved_any


def tidy(state: StateCore) -> None:
    """What both sides store the same way whatever the text arrived as: a line break inside text
    (from a character reference) becomes a space; a line of inline content — the start and end of
    a block, the sentences either side of a boundary — neither starts nor ends in a space; a
    heading's lines join into one; and two lists of one kind that follow each other are one."""
    tokens = state.tokens
    for position, token in enumerate(tokens):
        if token.type != "inline" or token.children is None:
            continue
        children = token.children
        heading = position > 0 and tokens[position - 1].type == "heading_open"
        for child in children:
            if child.type == "text":
                child.content = NEWLINE.sub(" ", child.content)
            elif child.type == "softbreak" and heading:
                child.type = "text"
                child.content = " "
        starts = [0] + [i + 1 for i, c in enumerate(children) if c.type == "softbreak"]
        for start in reversed(starts):
            end = start
            while end < len(children) and children[end].type != "softbreak":
                end += 1
            _trim(children, end - 1, -1, lambda text: text.rstrip(SPACE))
            _trim(children, start, 1, lambda text: text.lstrip(SPACE))
        token.children = [c for c in children if c.type != "text" or c.content]
    i = 0
    while i + 1 < len(tokens):
        closing, opening = tokens[i], tokens[i + 1]
        if (
            closing.type in ("bullet_list_close", "ordered_list_close")
            and opening.type == closing.type.replace("_close", "_open")
            and opening.level == closing.level
        ):
            del tokens[i : i + 2]
        else:
            i += 1


def cell_count(line: str) -> int:
    """The cells of one table row as markdown-it splits it: a pipe after a backslash is escaped,
    an empty first or last cell is the edge."""
    cells = [""]
    escaped = False
    for character in line.strip(SPACE):
        if character == "|" and not escaped:
            cells.append("")
        else:
            cells[-1] += character
        escaped = character == "\\"
    if cells and cells[0] == "":
        cells.pop(0)
    if cells and cells[-1] == "":
        cells.pop()
    return len(cells)


def definition_lines(lines: Sequence[str], tokens: Sequence[Token]) -> list[int]:
    """The lines, from 1, that define a link reference: shaped like one, outside fenced code, and
    outside every block that holds text."""
    covered: set[int] = set()
    for token in tokens:
        if token.type in TEXT_BLOCKS and token.map is not None:
            covered.update(range(token.map[0], token.map[1]))
    found: list[int] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        m = FENCE.match(line)
        if m:
            marker = m.group(1)[0]
            fence = None if fence == marker else (fence or marker)
            continue
        if fence is None and index not in covered and DEFINITION.match(line):
            found.append(index + 1)
    return found


def walk(
    tokens: Sequence[Token], lines: Sequence[str], env: dict[str, Any], spec: Spec
) -> list[tuple[str, int]]:
    """Every refusal in a parsed text: `(code, line)`, sorted, each once. A line is the first line
    of the block that holds the construct."""
    found: set[tuple[str, int]] = set()
    line = 1
    lists = quotes = 0
    header_cells = 0
    in_head = False
    item_start = False

    def refuse(code: str, at: int | None = None) -> None:
        found.add((code, line if at is None else at))

    for index, text in enumerate(lines):
        if CONTROL.search(text):
            refuse("control-character", index + 1)
    if env.get("references"):
        for number in definition_lines(lines, tokens) or [1]:
            refuse("link-reference", number)

    for index, token in enumerate(tokens):
        if token.type != "inline" and token.map is not None:
            line = token.map[0] + 1
        kind = token.type
        if kind not in KNOWN and kind not in ("code_block", "fence", "html_block", "hr"):
            refuse("unsupported")
        if kind == "heading_open":
            if int(token.tag[1:]) > spec.heading_max_depth:
                refuse("heading-depth")
            if spec.headings_top_level_only and (lists or quotes):
                refuse("heading-nested")
        elif kind in ("code_block", "fence"):
            refuse("code")
        elif kind == "html_block":
            refuse("html")
        elif kind == "hr":
            refuse("hr")
        elif kind in ("blockquote_open", "callout_open"):
            if quotes or lists:
                refuse("nested-quote")
            if kind == "callout_open" and token.info not in spec.callout_types:
                refuse("callout-type")
            quotes += 1
        elif kind in ("blockquote_close", "callout_close"):
            quotes -= 1
        elif kind in ("bullet_list_open", "ordered_list_open"):
            lists += 1
            if lists > spec.list_max_depth:
                refuse("list-depth")
        elif kind in ("bullet_list_close", "ordered_list_close"):
            lists -= 1
        elif kind == "list_item_open":
            following = tokens[index + 1].type if index + 1 < len(tokens) else ""
            if following == "list_item_close" or following.endswith("_list_open"):
                refuse("list-item-empty")
            item_start = True
            continue
        elif kind == "table_open":
            if spec.tables_top_level_only and (lists or quotes):
                refuse("table-nested")
        elif kind == "thead_open":
            in_head = True
        elif kind == "thead_close":
            in_head = False
        elif kind == "tr_open" and token.map is not None:
            cells = cell_count(lines[token.map[0]])
            if in_head:
                header_cells = cells
            elif cells > header_cells:
                refuse("table-row-cells")
        elif kind == "inline":
            if FOOTNOTE.search(token.content):
                refuse("footnote")
            if item_start and TASK.match(token.content):
                refuse("task-list")
            _inline(token.children or [], tokens[index - 1].type, spec, refuse)
        if kind != "paragraph_open":
            item_start = False
    return sorted(found, key=lambda refusal: (refusal[1], refusal[0]))


def _inline(
    children: Sequence[Token], block: str, spec: Spec, refuse: Callable[[str], None]
) -> None:
    """The refusals inside one block's inline content, an image's description included."""
    entities = 0
    if spec.image_alone and block == "paragraph_open" and len(children) > 1:
        if any(child.type == "image" for child in children):
            refuse("image-inline")
    for position, child in enumerate(children):
        kind = child.type
        following = children[position + 1].type if position + 1 < len(children) else None
        if kind not in KNOWN:
            refuse(INLINE_CODES.get(kind, "unsupported"))
        if kind == "image":
            if not spec.image_src.match(str(child.attrGet("src") or "")):
                refuse("image-src")
            if child.attrGet("title"):
                refuse("title")
            _inline(child.children or [], "image", spec, refuse)
        elif kind == "link_open":
            if not spec.link_schemes.match(str(child.attrGet("href") or "")):
                refuse("link-scheme")
            if child.attrGet("title"):
                refuse("title")
            if following == "link_close":
                refuse("link-empty")
        elif kind in ("entity_open", "underline_open"):
            span = child.meta.get("kind")
            if span is None:
                refuse("span-attrs")
            elif span not in spec.spans:
                refuse("span-type")
            elif child.meta.get("id") and not spec.spans[span]:
                refuse("span-id")
            elif span == "document" and not spec.mention_id.match(child.meta.get("id") or ""):
                refuse("mention-id")
            if following == kind.replace("_open", "_close"):
                refuse("span-empty")
            if kind == "entity_open":
                if entities:
                    refuse("span-nested")
                entities += 1
        elif kind == "entity_close":
            entities -= 1

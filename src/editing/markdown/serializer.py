"""The stored form of a text inside the whitelist: parse with the platform's markdown-it-py, build
the editor's document tree, and write it back as the editor's serialiser does (DL-0240).

`src/editing/js/serializer.js` is the editor's serialiser — prosemirror-markdown's state with the
platform's writers. This module ports the part of that state the whitelist uses, and the same
writers, so that a text reaches the same bytes whichever side writes it. The conformance suite's
re-spelling cases hold the two in step. `\\s` in the JavaScript regular expressions is spelled out
here as `SPACE`, since the two languages' classes differ.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from markdown_it.token import Token

from editing.markdown.parser import parser

# JavaScript's `\s`, the characters its `trim` removes as well: listed, and as a class.
SPACE_CHARACTERS = (
    "\t\n\x0b\x0c\r \xa0 " + "".join(chr(c) for c in range(0x2000, 0x200B)) + "    　﻿"
)
SPACE = "".join(re.escape(c) for c in SPACE_CHARACTERS)
# The order marks nest in on disk, outermost first (DL-0240); the editor's schema declares them so.
MARK_RANK = {"entity": 0, "link": 1, "underline": 2, "strong": 3, "em": 4}
ESCAPE = re.compile(r"[`*\\~\[\]_|]")
WORD = re.compile(r"[A-Za-z0-9_]")
EXTRA = re.compile(r"<|&(?=#?[A-Za-z0-9]+;)")
LINE_START = re.compile(r"^[+\-*>]")
HEADING_START = re.compile(rf"^([{SPACE}]*)(#{{1,6}})([{SPACE}]|\Z)")
NUMBER_START = re.compile(rf"^([{SPACE}]*[0-9]+)([.)])([{SPACE}]|\Z)")
LEADING = re.compile(rf"^([{SPACE}]*)(.*)\Z", re.DOTALL)
TRAILING = re.compile(rf"^(.*?)([{SPACE}]*)\Z", re.DOTALL)
TRIM_END = re.compile(rf"[{SPACE}]+\Z")
HEADING_END = re.compile(r"#+\Z")
LEADING_SPACE = re.compile(r"^[ \t]+")
TRAILING_SPACE = re.compile(r"[ \t]+\Z")
ONE_LINE = frozenset({"heading", "table_cell", "table_header"})
PLAIN_URL = re.compile(r"^[A-Za-z0-9_]+:")
ALIGN = re.compile(r"text-align:([A-Za-z0-9_]+)")


@dataclass(frozen=True)
class Mark:
    type: str
    attrs: tuple[tuple[str, Any], ...] = ()

    def attr(self, name: str) -> Any:
        return dict(self.attrs).get(name)


@dataclass
class Node:
    type: str
    attrs: dict[str, Any] = field(default_factory=dict)
    content: list[Node] = field(default_factory=list)
    text: str = ""
    marks: tuple[Mark, ...] = ()

    @property
    def is_text(self) -> bool:
        return self.type == "text"


def add_mark(mark: Mark, marks: tuple[Mark, ...]) -> tuple[Mark, ...]:
    """ProseMirror's `addToSet`: a mark replaces one of its own type, and the set stays in rank
    order."""
    kept = [m for m in marks if m.type != mark.type]
    kept.append(mark)
    return tuple(sorted(kept, key=lambda m: MARK_RANK[m.type]))


def _align(token: Token) -> str | None:
    m = ALIGN.search(str(token.attrGet("style") or ""))
    return m.group(1) if m else None


def _mark(token: Token, name: str) -> Mark:
    if name == "link":
        return Mark("link", (("href", token.attrGet("href")),))
    if name == "entity":
        return Mark("entity", (("kind", token.meta["kind"]), ("id", token.meta["id"])))
    return Mark(name)


BLOCKS = {
    "paragraph": "paragraph",
    "heading": "heading",
    "blockquote": "quote",
    "callout": "callout",
    "bullet_list": "bullet_list",
    "ordered_list": "ordered_list",
    "list_item": "list_item",
    "table": "table",
    "tr": "table_row",
    "th": "table_header",
    "td": "table_cell",
}
MARKS = {
    "em": "em",
    "strong": "strong",
    "link": "link",
    "underline": "underline",
    "entity": "entity",
}


class _ParseState:
    """prosemirror-markdown's `MarkdownParseState`, for the whitelist's tokens."""

    def __init__(self) -> None:
        self.stack: list[Node] = [Node("doc")]
        self.active: list[tuple[Mark, ...]] = [()]

    def add_text(self, text: str) -> None:
        if not text:
            return
        content, marks = self.stack[-1].content, self.active[-1]
        if content and content[-1].is_text and content[-1].marks == marks:
            content[-1].text += text
        else:
            content.append(Node("text", text=text, marks=marks))

    def open_node(self, kind: str, attrs: dict[str, Any]) -> None:
        self.stack.append(Node(kind, attrs))
        self.active.append(())

    def close_node(self) -> Node:
        node = self.stack.pop()
        self.active.pop()
        # What ProseMirror's `createAndFill` adds to satisfy the schema: a list item starts with a
        # paragraph, and a quote or callout holds at least one block.
        if node.type == "list_item" and (not node.content or node.content[0].type != "paragraph"):
            node.content.insert(0, Node("paragraph"))
        elif node.type in ("quote", "callout") and not node.content:
            node.content.append(Node("paragraph"))
        if self.stack:
            self.stack[-1].content.append(node)
        return node

    def parse(self, tokens: Sequence[Token]) -> None:
        for token in tokens:
            kind = token.type
            if kind == "inline":
                self.parse(token.children or [])
            elif kind == "text":
                self.add_text(token.content)
            elif kind == "softbreak":
                self.stack[-1].content.append(Node("sb", marks=self.active[-1]))
            elif kind == "image":
                alt = "".join(
                    " " if child.type == "softbreak" else child.content
                    for child in token.children or []
                )
                self.stack[-1].content.append(
                    Node("image", {"src": token.attrGet("src"), "alt": alt}, marks=self.active[-1])
                )
            elif kind in ("thead_open", "thead_close", "tbody_open", "tbody_close"):
                continue
            else:
                base, _, end = kind.rpartition("_")
                if base in BLOCKS and end == "open":
                    self.open_node(BLOCKS[base], self._attrs(base, token))
                elif base in BLOCKS and end == "close":
                    self.close_node()
                elif base in MARKS and end == "open":
                    self.active[-1] = add_mark(_mark(token, MARKS[base]), self.active[-1])
                elif base in MARKS and end == "close":
                    self.active[-1] = tuple(m for m in self.active[-1] if m.type != MARKS[base])
                else:
                    raise ValueError(f"token {kind} is outside the whitelist")

    @staticmethod
    def _attrs(base: str, token: Token) -> dict[str, Any]:
        if base == "heading":
            return {"level": int(token.tag[1:])}
        if base == "callout":
            return {"type": token.info}
        if base == "ordered_list":
            start = token.attrGet("start")
            return {"order": 1 if start is None else int(start)}
        if base in ("th", "td"):
            return {"align": _align(token)}
        return {}


def to_tree(text: str) -> Node:
    """The editor's document for a text the validator accepted."""
    state = _ParseState()
    state.parse(parser().parse(text))
    return state.stack[0]


def esc(text: str, start_of_line: bool) -> str:
    """Escape literal text so it never reads as markup: prosemirror-markdown's `esc`, then the
    platform's additions at a line start — `1)` as well as `1.`, and a leading `=`."""

    def one(m: re.Match[str]) -> str:
        i, character = m.start(), m.group(0)
        if (
            character == "_"
            and 0 < i < len(text) - 1
            and WORD.match(text[i - 1])
            and WORD.match(text[i + 1])
        ):
            return character
        return "\\" + character

    text = ESCAPE.sub(one, text)
    if start_of_line:
        text = escape_line_start(text)
    return EXTRA.sub(lambda m: "\\" + m.group(0), text)


def escape_line_start(text: str) -> str:
    """The escapes `esc` adds only at a line's start, for text already escaped otherwise: a
    sentence that moves to a line's start is written as the editor would write it there."""
    text = LINE_START.sub(lambda m: "\\" + m.group(0), text, count=1)
    text = HEADING_START.sub(lambda m: m.group(1) + "\\" + m.group(2) + m.group(3), text, 1)
    text = NUMBER_START.sub(lambda m: m.group(1) + "\\" + m.group(2) + m.group(3), text, 1)
    if text.startswith("="):
        text = "\\" + text
    return text


class _State:
    """prosemirror-markdown's `MarkdownSerializerState`, for the whitelist's nodes and marks, with
    `tightLists` on."""

    def __init__(self) -> None:
        self.delim = ""
        self.out = ""
        self.closed: Node | None = None
        self.in_autolink: bool | None = None
        self.at_block_start = False
        self.in_tight_list = False

    def flush_close(self, size: int = 2) -> None:
        if self.closed is not None:
            if not self.at_blank():
                self.out += "\n"
            if size > 1:
                delim_min = TRIM_END.sub("", self.delim)
                for _ in range(1, size):
                    self.out += delim_min + "\n"
            self.closed = None

    def wrap_block(self, delim: str, first: str | None, node: Node, f: Callable[[], None]) -> None:
        old = self.delim
        self.write(first if first is not None else delim)
        self.delim += delim
        f()
        self.delim = old
        self.close_block(node)

    def at_blank(self) -> bool:
        return self.out == "" or self.out.endswith("\n")

    def ensure_new_line(self) -> None:
        if not self.at_blank():
            self.out += "\n"

    def write(self, content: str = "") -> None:
        self.flush_close()
        if self.delim and self.at_blank():
            self.out += self.delim
        if content:
            self.out += content

    def close_block(self, node: Node) -> None:
        self.closed = node

    def text(self, text: str, escape: bool = True) -> None:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            self.write()
            if not escape and line[:1] == "[" and re.search(r"(^|[^\\])!\Z", self.out):
                self.out = self.out[:-1] + "\\!"
            self.out += esc(line, self.at_block_start) if escape else line
            if i != len(lines) - 1:
                self.out += "\n"

    def render(self, node: Node, parent: Node, index: int) -> None:
        WRITERS[node.type](self, node, parent, index)

    def render_content(self, parent: Node) -> None:
        for index, node in enumerate(parent.content):
            self.render(node, parent, index)

    def render_inline(self, parent: Node, from_block_start: bool = True) -> None:
        self.at_block_start = from_block_start
        active: list[Mark] = []
        trailing = ""

        def progress(node: Node | None, index: int) -> None:
            nonlocal active, trailing
            marks: list[Mark] = list(node.marks) if node is not None else []
            length = len(marks)
            # Reorder mixable marks — all of the whitelist's are — to match the order in `active`.
            i = 0
            while i < length:
                mark = marks[i]
                for j, other in enumerate(active):
                    if mark == other:
                        if i > j:
                            marks = marks[:j] + [mark] + marks[j:i] + marks[i + 1 : length]
                        elif j > i:
                            marks = marks[:i] + marks[i + 1 : j] + [mark] + marks[j:length]
                        break
                i += 1
            keep = 0
            while keep < min(len(active), length) and marks[keep] == active[keep]:
                keep += 1
            leading = trailing
            trailing = ""
            if (
                node is not None
                and node.is_text
                and any(
                    EXPEL.get(mark.type, False) and not any(m == mark for m in active[:keep])
                    for mark in marks
                )
            ):
                m = LEADING.match(node.text.split("\n")[0])
                assert m is not None
                lead, rest = m.group(1), m.group(2)
                if lead:
                    leading += lead
                    node = Node("text", text=rest, marks=node.marks) if rest else None
                    if node is None:
                        marks = list(active)
            if (
                node is not None
                and node.is_text
                and any(
                    EXPEL.get(mark.type, False)
                    and not self.is_mark_ahead(parent, index + 1, marks[: k + 1])
                    for k, mark in enumerate(marks)
                )
            ):
                m = TRAILING.match(node.text.split("\n")[0])
                assert m is not None
                rest, trail = m.group(1), m.group(2)
                if trail:
                    trailing = trail
                    node = Node("text", text=rest, marks=node.marks) if rest else None
                    if node is None:
                        marks = list(active)
            if node is not None or index == len(parent.content):
                while keep < len(active):
                    self.text(self.mark_string(active.pop(), False, parent, index), False)
            if leading:
                self.text(leading)
            if node is not None:
                while len(active) < length:
                    add = marks[len(active)]
                    active.append(add)
                    self.text(self.mark_string(add, True, parent, index), False)
                    self.at_block_start = False
                self.render(node, parent, index)
                self.at_block_start = False

        for index, node in enumerate(parent.content):
            progress(node, index)
        progress(None, len(parent.content))
        self.at_block_start = False

    def is_mark_ahead(self, parent: Node, index: int, marks: list[Mark]) -> bool:
        if index >= len(parent.content):
            return False
        following = parent.content[index].marks
        return len(following) >= len(marks) and list(following[: len(marks)]) == marks

    def mark_string(self, mark: Mark, opening: bool, parent: Node, index: int) -> str:
        return MARK_WRITERS[mark.type](self, mark, opening, parent, index)


def _is_plain_url(link: Mark, parent: Node, index: int) -> bool:
    href = str(link.attr("href"))
    if not PLAIN_URL.match(href):
        return False
    content = parent.content[index]
    if not content.is_text or content.text != href or content.marks[-1] != link:
        return False
    return index == len(parent.content) - 1 or link not in parent.content[index + 1].marks


def _link(state: _State, mark: Mark, opening: bool, parent: Node, index: int) -> str:
    if opening:
        state.in_autolink = _is_plain_url(mark, parent, index)
        return "<" if state.in_autolink else "["
    autolink, state.in_autolink = state.in_autolink, None
    href = str(mark.attr("href"))
    return ">" if autolink else "](" + re.sub(r'[()"]', lambda m: "\\" + m.group(0), href) + ")"


def _span(state: _State, mark: Mark, opening: bool, parent: Node, index: int) -> str:
    if opening:
        return "["
    if mark.type == "underline":
        return "]{.underline}"
    identifier = mark.attr("id")
    return "]{." + str(mark.attr("kind")) + (" #" + identifier if identifier else "") + "}"


def _fixed(opening_text: str, closing_text: str) -> Callable[..., str]:
    return lambda state, mark, opening, parent, index: opening_text if opening else closing_text


MARK_WRITERS: dict[str, Callable[[_State, Mark, bool, Node, int], str]] = {
    "entity": _span,
    "link": _link,
    "underline": _span,
    "strong": _fixed("**", "**"),
    "em": _fixed("*", "*"),
}
EXPEL = {"entity": True, "underline": True, "strong": True, "em": True, "link": False}


def _paragraph(state: _State, node: Node, parent: Node, index: int) -> None:
    state.render_inline(node)
    state.close_block(node)


def _heading(state: _State, node: Node, parent: Node, index: int) -> None:
    state.write("#" * node.attrs["level"] + " ")
    state.render_inline(node, False)
    state.close_block(node)


def _quote(state: _State, node: Node, parent: Node, index: int) -> None:
    state.wrap_block("> ", None, node, lambda: state.render_content(node))


def _callout(state: _State, node: Node, parent: Node, index: int) -> None:
    def body() -> None:
        state.write(f"[!{node.attrs['type']}]")
        state.ensure_new_line()
        state.render_content(node)

    state.wrap_block("> ", None, node, body)


def _list(state: _State, node: Node, marker: Callable[[int], str]) -> None:
    """prosemirror-markdown's `renderList`, tight, each item indented by its own marker's width
    (DL-0240)."""
    if state.closed is not None and state.closed.type == node.type:
        state.flush_close(3)
    elif state.in_tight_list:
        state.flush_close(1)
    previous = state.in_tight_list
    state.in_tight_list = True
    # An item with no text is not written: it would be refused.
    items = [c for c in node.content if len(c.content) > 1 or (c.content and c.content[0].content)]
    for i, child in enumerate(items):
        if i:
            state.flush_close(1)
        first = marker(i)

        def item(child: Node = child, i: int = i) -> None:
            state.render(child, node, i)

        state.wrap_block(" " * len(first), first, node, item)
    state.in_tight_list = previous


def _bullet_list(state: _State, node: Node, parent: Node, index: int) -> None:
    _list(state, node, lambda i: "- ")


def _ordered_list(state: _State, node: Node, parent: Node, index: int) -> None:
    start = node.attrs["order"]
    _list(state, node, lambda i: f"{start + i}. ")


def _list_item(state: _State, node: Node, parent: Node, index: int) -> None:
    state.render_content(node)


def _cell_text(state: _State, cell: Node) -> str:
    at = len(state.out)
    state.render_inline(cell)
    text = state.out[at:]
    state.out = state.out[:at]
    return re.sub(r"(?<!\\)\|", r"\\|", text.strip(SPACE_CHARACTERS))


def _table(state: _State, node: Node, parent: Node, index: int) -> None:
    state.flush_close(2)
    for r, row in enumerate(node.content):
        cells = [_cell_text(state, cell) for cell in row.content]
        state.write("| " + " | ".join(cells) + " |")
        state.ensure_new_line()
        if r == 0:
            delimiters = [DELIMITER.get(cell.attrs.get("align"), "---") for cell in row.content]
            state.write("| " + " | ".join(delimiters) + " |")
            state.ensure_new_line()
    state.close_block(node)


DELIMITER = {None: "---", "left": ":---", "right": "---:", "center": ":---:"}


def _image(state: _State, node: Node, parent: Node, index: int) -> None:
    src = re.sub(r"[()]", lambda m: "\\" + m.group(0), str(node.attrs["src"]))
    state.write("![" + esc(node.attrs["alt"] or "", False) + "](" + src + ")")


def _sb(state: _State, node: Node, parent: Node, index: int) -> None:
    """A sentence boundary is written only between two pieces of text: never first or last in
    its block, never twice in a row."""
    later = any(child.type != "sb" for child in parent.content[index + 1 :])
    if index > 0 and later and parent.content[index - 1].type != "sb":
        # A heading and a table cell hold one line: their sentences are joined by a space.
        state.write(" " if parent.type in ONE_LINE else "\n")


def _text(state: _State, node: Node, parent: Node, index: int) -> None:
    after_boundary = index > 0 and parent.content[index - 1].type == "sb" and state.at_blank()
    if state.in_autolink:
        state.text(node.text, False)
        return
    line_start = state.at_block_start or after_boundary
    following = parent.content[index + 1] if index + 1 < len(parent.content) else None
    # Spaces at either end of a sentence's line would read as an indent or a line break.
    raw = LEADING_SPACE.sub("", node.text) if line_start else node.text
    if following is None or following.type == "sb":
        raw = TRAILING_SPACE.sub("", raw)
    if not raw:
        return
    text = esc(raw, line_start)
    if parent.type == "heading" and index == len(parent.content) - 1:
        # A heading's closing `#`s would be read as its optional closing sequence.
        text = HEADING_END.sub(lambda m: "\\" + m.group(0), text)
    state.write()
    state.text(text, False)


WRITERS: dict[str, Callable[[_State, Node, Node, int], None]] = {
    "paragraph": _paragraph,
    "heading": _heading,
    "quote": _quote,
    "callout": _callout,
    "bullet_list": _bullet_list,
    "ordered_list": _ordered_list,
    "list_item": _list_item,
    "table": _table,
    "image": _image,
    "sb": _sb,
    "text": _text,
}


def serialize_tree(doc: Node) -> str:
    state = _State()
    state.render_content(doc)
    state.flush_close(1)
    return state.out


def serialize(text: str) -> str:
    """The stored form of `text`, which the validator must already have accepted."""
    return serialize_tree(to_tree(text))

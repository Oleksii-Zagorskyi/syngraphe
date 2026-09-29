"""*check* — normalisation preserves the parse (DL-0112, ADR-0012). A boundary is safe when the
block's HTML, soft breaks read as spaces, is identical before and after the line break. A break
inside a link destination, an attribute block or an image, or before a line that would open a
list or a heading, changes it; one inside bold, a span's text or a link's text does not.

The HTML is the platform's markdown-it-py configuration with renderer rules for spans, callouts and
soft breaks (ADR-0013) — enough that a span's kind and id take part in the comparison. It is the
check's rendering, not the reading view's.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from html import escape
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from editing.markdown.parser import make_parser

# A block's container markers: quote markers, indentation and list markers, in any nesting.
PREFIX = re.compile(r"^(?:>[ ]?|[ ]+|-[ ]|[0-9]+\.[ ])*")
LIST_MARKER = re.compile(r"-[ ]|[0-9]+\.[ ]")
SPACE = " \t"


def _entity_open(renderer: Any, tokens: Sequence[Token], index: int, options: Any, env: Any) -> str:
    meta = tokens[index].meta
    identifier = f' data-id="{escape(str(meta["id"]))}"' if meta.get("id") else ""
    kind = escape(str(meta.get("kind") or meta.get("raw")))
    return f'<span class="entity entity-{kind}"{identifier}>'


def _callout_open(
    renderer: Any, tokens: Sequence[Token], index: int, options: Any, env: Any
) -> str:
    return f'<div class="callout callout-{escape(tokens[index].info)}">'


def _renderer() -> MarkdownIt:
    md = make_parser()
    rules = md.add_render_rule
    rules("softbreak", lambda *args: " ")
    rules("entity_open", _entity_open)
    rules("entity_close", lambda *args: "</span>")
    rules("underline_open", lambda *args: '<span class="underline">')
    rules("underline_close", lambda *args: "</span>")
    rules("callout_open", _callout_open)
    rules("callout_close", lambda *args: "</div>")
    return md


_MD = _renderer()


def html(markdown: str) -> str:
    """The HTML the check compares."""
    rendered: str = _MD.render(markdown)
    return rendered


def continuation(block: str) -> str:
    """The prefix a continuation line of `block` carries: its quote markers kept, its list
    markers read as indentation of the same width."""
    first = PREFIX.match(block)
    prefix = first.group(0) if first else ""
    return LIST_MARKER.sub(lambda m: " " * len(m.group(0)), prefix)


def broken(block: str, boundary: int) -> str:
    """`block` with a line break at `boundary`, the whitespace around it consumed and the block's
    continuation prefix written after it."""
    left, right = block[:boundary].rstrip(SPACE), block[boundary:].lstrip(SPACE)
    return left + "\n" + continuation(block) + right


def same_parse(before: str, after: str) -> bool:
    """Whether two spellings of one block render to the same HTML."""
    return html(before) == html(after)


def preserves_parse(block: str, boundary: int) -> bool:
    """Whether a line break at `boundary` leaves the block's parse unchanged."""
    return same_parse(block, broken(block, boundary))

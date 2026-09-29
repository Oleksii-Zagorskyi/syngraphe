"""The reading view's HTML: one markdown-it-py parse of the stored text, rendered with raw HTML
escaped, spans and callouts as classed elements, a sentence boundary as a space, and each heading
and paragraph led by its clause number (ADR-0013, DL-0065).

Built apart from the editor's recogniser, which passes raw HTML and every link through so that
the validator can name them.
"""

from __future__ import annotations

from html import escape
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from editing.markdown.rules import attr_span, callout, tidy
from rendering.numbering import labels


def _span_open(_renderer: Any, tokens: list[Token], i: int, *_: Any) -> str:
    token = tokens[i]
    if token.type == "underline_open":
        return '<span class="underline">'
    meta = token.meta or {}
    kind = escape(meta.get("kind") or "")
    identifier = meta.get("id")
    data = f' data-id="{escape(identifier)}"' if identifier else ""
    return f'<span class="entity entity-{kind}"{data}>'


def _callout_open(_renderer: Any, tokens: list[Token], i: int, *_: Any) -> str:
    return f'<div class="callout callout-{escape(tokens[i].info)}">\n'


def _image(renderer: Any, tokens: list[Token], i: int, options: Any, env: Any) -> str:
    # Images arrive with Epic 11; until then a reader sees the description, and nothing is fetched.
    return escape(renderer.renderInlineAsText(tokens[i].children or [], options, env))


def _link_open(renderer: Any, tokens: list[Token], i: int, options: Any, env: Any) -> str:
    tokens[i].attrSet("rel", "noopener noreferrer")
    return str(renderer.renderToken(tokens, i, options, env))


def make_renderer() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    md.inline.ruler.before("link", "attr_span", attr_span)
    md.core.ruler.after("block", "callout", callout)
    md.core.ruler.after("text_join", "tidy", tidy)
    md.add_render_rule("entity_open", _span_open)
    md.add_render_rule("underline_open", _span_open)
    md.add_render_rule("entity_close", lambda *_: "</span>")
    md.add_render_rule("underline_close", lambda *_: "</span>")
    md.add_render_rule("callout_open", _callout_open)
    md.add_render_rule("callout_close", lambda *_: "</div>\n")
    md.add_render_rule("softbreak", lambda *_: " ")
    md.add_render_rule("image", _image)
    md.add_render_rule("link_open", _link_open)
    return md


RENDERER = make_renderer()


def render(body: str) -> str:
    """The body's HTML, each labelled block led by `<span class="num">LABEL</span> `."""
    tokens = RENDERER.parse(body)
    for i, label in labels(tokens).items():
        inline = tokens[i + 1]
        number = Token("html_inline", "", 0)
        number.content = f'<span class="num">{escape(label)}</span> '
        inline.children = [number, *(inline.children or [])]
    return str(RENDERER.renderer.render(tokens, RENDERER.options, {}))

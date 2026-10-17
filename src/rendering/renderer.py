"""The document's HTML, for the reading view, the diff views and the help pages: one markdown-it-py
parse of the stored text, rendered with raw HTML escaped, spans and callouts as classed elements, a
sentence boundary as a space, and each heading and paragraph led by its clause number (ADR-0013,
DL-0065).

Built apart from the editor's recogniser, which passes raw HTML and every link through so that
the validator can name them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.rules_core import StateCore
from markdown_it.token import Token

from documents.images import is_image_path
from editing.markdown import load_spec
from editing.markdown.rules import attr_span, callout, numbered_bullets, tidy
from rendering.numbering import labels

# The span that names another document (DL-0436): a link where the reader may follow it, its words
# alone everywhere else.
MENTION = "document"


@dataclass(frozen=True)
class RenderContext:
    """What a page renders text for: the documents a mention may link to, the address an image is
    shown from, the names of a change's two sides, and whether a pair of images may be opened at
    full size. With none, the output is the safe one — an image its description, a mention its
    words."""

    reachable: frozenset[int] = frozenset()
    image_url: Callable[[str], str] | None = None
    sides: tuple[str, str] = ("", "")
    full_size: bool = True


def context_of(env: Any) -> RenderContext | None:
    """The context a render was given, carried in markdown-it's `env`."""
    found = env.get("context") if isinstance(env, dict) else None
    return found if isinstance(found, RenderContext) else None


def _followed(meta: dict[str, Any], env: Any) -> int | None:
    """The document a mention links to: its number, when the reader's context reaches it and the
    mention stands inside no link of its own — no anchor inside another; else `None`, its words
    alone (DL-0084, ASR-16)."""
    context = context_of(env)
    identifier = str(meta.get("id") or "")
    # The whitelist's own rule, held here too for text that reached the store another way.
    if context is None or meta.get("inside") or not load_spec().mention_id.match(identifier):
        return None
    return int(identifier) if int(identifier) in context.reachable else None


def env_of(rest: tuple[Any, ...]) -> Any:
    """The `env` among a render rule's trailing arguments, `(options, env)`."""
    return rest[1] if len(rest) > 1 else None


def _span_open(_renderer: Any, tokens: list[Token], i: int, *rest: Any) -> str:
    token = tokens[i]
    if token.type == "underline_open":
        return '<span class="underline">'
    meta = token.meta or {}
    if meta.get("kind") == MENTION:
        followed = _followed(meta, env_of(rest))
        return f'<a class="mention" href="/document/{followed}/">' if followed else ""
    kind = escape(meta.get("kind") or "")
    identifier = meta.get("id")
    data = f' data-id="{escape(identifier)}"' if identifier else ""
    return f'<span class="entity entity-{kind}"{data}>'


def _span_close(_renderer: Any, tokens: list[Token], i: int, *rest: Any) -> str:
    """What `_span_open` opened, read from the close token's own `meta`, so a close rendered alone
    — a diff's token by token — still matches its open: a followed mention's `</a>`, nothing for
    one that drew its words alone."""
    meta = tokens[i].meta or {}
    if meta.get("kind") == MENTION:
        return "</a>" if _followed(meta, env_of(rest)) else ""
    return "</span>"


def _callout_open(_renderer: Any, tokens: list[Token], i: int, *_: Any) -> str:
    return f'<div class="callout callout-{escape(tokens[i].info)}">\n'


def _image(renderer: Any, tokens: list[Token], i: int, options: Any, env: Any) -> str:
    """An image the platform names, shown from the context's address; any other image — and every
    image rendered with no context — its description alone, nothing fetched."""
    description = renderer.renderInlineAsText(tokens[i].children or [], options, env)
    context = context_of(env)
    src = str(tokens[i].attrGet("src") or "")
    if context is None or context.image_url is None or not is_image_path(src):
        return escape(description)
    return f'<img src="{escape(context.image_url(src))}" alt="{escape(description)}">'


def _link_open(renderer: Any, tokens: list[Token], i: int, options: Any, env: Any) -> str:
    """A link, unless it stands inside a mention that links: then its words alone, so no anchor
    stands inside another."""
    if _followed({"kind": MENTION, "id": (tokens[i].meta or {}).get("mention")}, env):
        return ""
    tokens[i].attrSet("rel", "noopener noreferrer")
    return str(renderer.renderToken(tokens, i, options, env))


def _link_close(renderer: Any, tokens: list[Token], i: int, options: Any, env: Any) -> str:
    if _followed({"kind": MENTION, "id": (tokens[i].meta or {}).get("mention")}, env):
        return ""
    return str(renderer.renderToken(tokens, i, options, env))


def _mention_nesting(state: StateCore) -> None:
    """Each link and mention told, on its own tokens, what it stands inside — a diff renders tokens
    one by one, so the render rules decide from that alone: a mention inside a link or another span
    is marked `inside` and never links; a link inside a mention carries the outermost mention's
    number, and reads as its words where that mention links. No anchor stands inside another."""
    for token in state.tokens:
        spans: list[str | None] = []
        links = 0
        for child in token.children or []:
            meta = child.meta or {}
            if child.type in ("entity_open", "entity_close"):
                mention = meta.get("kind") == MENTION
                if child.type == "entity_close" and spans:
                    spans.pop()
                if mention and (links or spans):
                    child.meta = {**meta, "inside": True}
                if child.type == "entity_open":
                    spans.append(str(meta.get("id") or "") if mention else None)
            elif child.type in ("link_open", "link_close"):
                if child.type == "link_close":
                    links -= 1
                if spans and spans[0]:
                    child.meta = {**meta, "mention": spans[0]}
                if child.type == "link_open":
                    links += 1


def _whitelisted_links(state: StateCore) -> None:
    """A link whose scheme the whitelist does not allow reads as its words: the validator refuses
    it on every way in, and the page holds the rule itself for text that reached the store
    another way."""
    schemes = load_spec().link_schemes
    for token in state.tokens:
        children = token.children or []
        refused: list[int] = []
        depth: list[bool] = []
        for i, child in enumerate(children):
            if child.type == "link_open":
                bad = not schemes.match(str(child.attrs.get("href", "")))
                depth.append(bad)
                if bad:
                    refused.append(i)
            elif child.type == "link_close" and depth and depth.pop():
                refused.append(i)
        if refused:
            dropped = set(refused)
            token.children = [c for i, c in enumerate(children) if i not in dropped]


def make_renderer() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    md.inline.ruler.before("link", "attr_span", attr_span)
    md.core.ruler.after("block", "callout", callout)
    md.core.ruler.after("callout", "numbered_bullets", numbered_bullets)
    md.core.ruler.after("text_join", "tidy", tidy)
    md.core.ruler.after("tidy", "whitelisted_links", _whitelisted_links)
    md.core.ruler.after("whitelisted_links", "mention_nesting", _mention_nesting)
    if md.options["html"]:
        raise RuntimeError("raw HTML stays text: every html token is the platform's own")
    md.add_render_rule("entity_open", _span_open)
    md.add_render_rule("underline_open", _span_open)
    md.add_render_rule("entity_close", _span_close)
    md.add_render_rule("underline_close", lambda *_: "</span>")
    md.add_render_rule("callout_open", _callout_open)
    md.add_render_rule("callout_close", lambda *_: "</div>\n")
    md.add_render_rule("softbreak", lambda *_: " ")
    md.add_render_rule("image", _image)
    md.add_render_rule("link_open", _link_open)
    md.add_render_rule("link_close", _link_close)
    return md


RENDERER = make_renderer()


def labelled(body: str) -> list[Token]:
    """The body's tokens, each labelled block's inline children led by its number: an
    `html_inline` token marked `meta["num"]` and carrying `meta["label"]`, so a caller splicing the
    children can pass over it."""
    tokens = RENDERER.parse(body)
    for i, label in labels(tokens).items():
        inline = tokens[i + 1]
        number = Token("html_inline", "", 0)
        number.content = f'<span class="num">{escape(label)}</span> '
        number.meta = {"num": True, "label": label}
        inline.children = [number, *(inline.children or [])]
    return tokens


def render_tokens(tokens: list[Token], *, context: RenderContext | None = None) -> str:
    """Tokens from `labelled`, as HTML for the reader `context` describes; tokens a caller spliced
    in render as they are."""
    return str(RENDERER.renderer.render(tokens, RENDERER.options, {"context": context}))


def render_inline(text: str, *, context: RenderContext | None = None) -> str:
    """One line of inline text, rendered by the same rules and unlabelled."""
    return str(RENDERER.renderInline(text, {"context": context})).strip()


def render(body: str, *, context: RenderContext | None = None) -> str:
    """The body's HTML, each labelled block led by `<span class="num">LABEL</span> `."""
    return render_tokens(labelled(body), context=context)

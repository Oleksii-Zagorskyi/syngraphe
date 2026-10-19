"""The organisation's stylesheet (DL-0464, DL-0465, DL-0477; T-23): what it may contain, checked
against an allowlist with each refusal named by its line; how it is served to a reader's browser —
every selector confined to the document's text — and handed to the exports; and the platform's own
sheet applied after it, which keeps the marks of a change and the approval line as the platform
draws them.

Every reader of the stored text goes through `applied`, so a row written before a rule tightened
reaches no page, no PDF and no Word file.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import tinycss2
from tinycss2 import ast
from tinycss2.color3 import RGBA, parse_color

logger = logging.getLogger(__name__)

MAX_BYTES = 100_000

ELEMENTS = frozenset(
    "body article section div h1 h2 h3 h4 p ul ol li blockquote table thead tbody tr th td a "
    "strong em span img".split()
)
# The classes the platform puts on document text that a stylesheet may name.
CLASSES = frozenset(
    "document-text num entity entity-role entity-action entity-term underline mention callout "
    "callout-note callout-warning callout-example attachment-list appendix title-page "
    "document-title document-number document-type document-edition approver approval-date "
    "title-page-text".split()
)
# The platform's own on the same text, never named: the marks of a change, the approval line, the
# title page's alignment (DL-0360, DL-0363).
EXCLUDED = frozenset(
    "ins del format-changed format-old marker removed by imgpair image-description image-changed "
    "before after full-size approval align-left align-centre".split()
)
FONTS = (
    "DejaVu Sans",
    "DejaVu Sans Mono",
    "DejaVu Serif",
    "DejaVu Sans Condensed",
    "DejaVu Serif Condensed",
)
GENERICS = ("serif", "sans-serif", "monospace")

SIDES = ("top", "right", "bottom", "left")
_SPACING = ("margin", "padding")
PROPERTIES = frozenset(
    [
        "font-family",
        "font-size",
        "font-weight",
        "font-style",
        "font-variant",
        "line-height",
        "letter-spacing",
        "word-spacing",
        "text-decoration",
        "text-transform",
        "text-indent",
        "text-align",
        "vertical-align",
        "color",
        "background-color",
        "background",
        "border",
        "border-width",
        "border-style",
        "border-color",
        "border-radius",
        "border-collapse",
        "size",
        *_SPACING,
        *(f"{box}-{side}" for box in _SPACING for side in SIDES),
        *(f"border-{side}" for side in SIDES),
        *(f"border-{side}-{part}" for side in SIDES for part in ("width", "style", "color")),
    ]
)
PAGE_PROPERTIES = frozenset(["size", "margin", *(f"margin-{side}" for side in SIDES)])
PAGE_SIZES = frozenset(["a3", "a4", "a5", "letter", "legal"])
COLOUR_FUNCTIONS = frozenset(["rgb", "rgba", "hsl", "hsla"])
BORDER_STYLES = frozenset(["none", "solid", "dashed", "dotted", "double"])

# Millimetres per unit; `em` is bounded on its own scale.
MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "px": 0.75 * 25.4 / 72}
PT_MM = MM["pt"]

KEYWORDS = {
    "font-style": frozenset(["normal", "italic"]),
    "font-variant": frozenset(["normal", "small-caps"]),
    "text-decoration": frozenset(["none", "underline"]),
    "text-transform": frozenset(["none", "uppercase", "lowercase", "capitalize"]),
    "text-align": frozenset(["left", "right", "center", "justify"]),
    "vertical-align": frozenset(["baseline", "top", "middle", "bottom", "sub", "super"]),
    "border-collapse": frozenset(["collapse", "separate"]),
}


@dataclass(frozen=True, order=True)
class StyleRefusal:
    """One thing the stylesheet may not hold: its line, from 1, its code and what it names."""

    line: int
    code: str
    subject: str


def check(text: str) -> list[StyleRefusal]:
    """Every refusal of `text`, by line, then code; empty when it may be applied."""
    # A lone surrogate is counted, not raised on: `check` answers any text.
    if len(text.encode("utf-8", "surrogatepass")) > MAX_BYTES:
        return [StyleRefusal(1, "too-large", "")]
    found: list[StyleRefusal] = []
    for node in tinycss2.parse_stylesheet(text, skip_comments=True, skip_whitespace=True):
        _top(node, found, in_media=False)
    return sorted(found)


def applied(text: str) -> str:
    """`text` when it passes `check`, else nothing: the one way the stored row reaches a reader."""
    if text and not _passes(text):
        logger.warning("the organisation's stylesheet no longer passes the check; not applied")
        return ""
    return text


# Remembered per stored text: every page and every export asks, and the text rarely changes.
@functools.lru_cache(maxsize=8)
def _passes(text: str) -> bool:
    return not check(text)


# --- the check ---------------------------------------------------------------------------------


def _top(node: Any, found: list[StyleRefusal], *, in_media: bool) -> None:
    if isinstance(node, ast.ParseError):
        found.append(StyleRefusal(node.source_line, "syntax", node.kind))
    elif isinstance(node, ast.AtRule):
        _at_rule(node, found, in_media=in_media)
    elif isinstance(node, ast.QualifiedRule):
        _qualified(node, found)


def _significant(tokens: Iterable[Any]) -> list[Any]:
    return [t for t in tokens if not isinstance(t, ast.WhitespaceToken | ast.Comment)]


def _at_rule(node: ast.AtRule, found: list[StyleRefusal], *, in_media: bool) -> None:
    name = node.lower_at_keyword
    prelude = _significant(node.prelude)
    if name == "page" and not in_media and not prelude:
        _page(node, found)
        return
    is_print = len(prelude) == 1 and _ident(prelude[0]) == "print"
    if name == "media" and not in_media and is_print and node.content is not None:
        for inner in tinycss2.parse_rule_list(
            node.content, skip_comments=True, skip_whitespace=True
        ):
            _top(inner, found, in_media=True)
        return
    found.append(StyleRefusal(node.source_line, "at-rule", name))


def _page(node: ast.AtRule, found: list[StyleRefusal]) -> None:
    for item in tinycss2.parse_blocks_contents(
        node.content or [], skip_comments=True, skip_whitespace=True
    ):
        if isinstance(item, ast.ParseError):
            found.append(StyleRefusal(item.source_line, "syntax", item.kind))
        elif isinstance(item, ast.AtRule):
            found.append(StyleRefusal(item.source_line, "at-rule", item.lower_at_keyword))
        elif isinstance(item, ast.QualifiedRule):
            found.append(StyleRefusal(item.source_line, "selector", "nested"))
        elif isinstance(item, ast.Declaration):
            name = item.lower_name
            if name not in PAGE_PROPERTIES:
                found.append(StyleRefusal(item.source_line, "property", name))
            elif not _declaration_value(item, found, _page_value(name)):
                found.append(StyleRefusal(item.source_line, "value", name))


def _qualified(node: ast.QualifiedRule, found: list[StyleRefusal]) -> None:
    items = _selectors(node.prelude)
    if items is None:
        found.append(StyleRefusal(node.source_line, "selector", _quoted(node.prelude)))
        gutter = number = False
    else:
        gutter = any(_in_gutter(item[-1][1]) for item in items)
        # A clause number set large or spread would lie over the text beside it (DL-0363).
        number = any("num" in item[-1][1][1] for item in items)
    for item in tinycss2.parse_blocks_contents(
        node.content, skip_comments=True, skip_whitespace=True
    ):
        if isinstance(item, ast.ParseError):
            found.append(StyleRefusal(item.source_line, "syntax", item.kind))
        elif isinstance(item, ast.AtRule):
            found.append(StyleRefusal(item.source_line, "at-rule", item.lower_at_keyword))
        elif isinstance(item, ast.QualifiedRule):
            found.append(StyleRefusal(item.source_line, "selector", "nested"))
        elif isinstance(item, ast.Declaration):
            _declaration(item, found, gutter=gutter, number=number)


def _quoted(prelude: Sequence[Any]) -> str:
    """A refused selector as written; its blocks elided where the walk stopped short or they nest
    past the allowlist's depth, since serialising them recurses."""
    fetches, depth = _nested(prelude)
    if not fetches and depth <= DEPTH_MOST:
        return str(tinycss2.serialize(prelude)).strip()
    shallow = []
    for token in prelude:
        if isinstance(token, ast.FunctionBlock):
            shallow.append(f"{token.name}(…)")
        elif isinstance(token, ast.ParenthesesBlock | ast.SquareBracketsBlock):
            shallow.append("(…)" if isinstance(token, ast.ParenthesesBlock) else "[…]")
        elif isinstance(token, ast.CurlyBracketsBlock):
            shallow.append("{…}")
        else:
            shallow.append(tinycss2.serialize([token]))
    return "".join(shallow).strip()


def _declaration(
    item: ast.Declaration, found: list[StyleRefusal], *, gutter: bool, number: bool
) -> None:
    name = item.lower_name
    if name not in PROPERTIES or name == "size":
        found.append(StyleRefusal(item.source_line, "property", name))
        return
    in_gutter = (gutter and (name.startswith(_SPACING) or name == "text-indent")) or (
        number and name in ("font-size", "letter-spacing", "word-spacing")
    )
    rule = VALUES[name]
    if not _declaration_value(item, found, rule) or in_gutter:
        found.append(StyleRefusal(item.source_line, "value", name))


def _declaration_value(
    item: ast.Declaration, found: list[StyleRefusal], rule: Callable[[list[Any]], bool]
) -> bool:
    """Whether the value passes `rule`; a value that fetches is refused `fetches` here, and
    counts as passing so it is not refused twice."""
    fetches, depth = _nested(item.value)
    if fetches:
        found.append(StyleRefusal(item.source_line, "fetches", item.lower_name))
        return True
    if depth > DEPTH_MOST:
        return False
    if item.important:
        return False
    tokens = _significant(item.value)
    if any(
        isinstance(t, ast.FunctionBlock) and t.lower_name not in COLOUR_FUNCTIONS for t in tokens
    ):
        return False
    if item.lower_name == "font-family":
        return _families(item, tokens, found)
    return bool(tokens) and rule(tokens)


# No value the allowlist admits nests deeper than a colour function's arguments.
DEPTH_MOST = 8


def _nested(tokens: Sequence[Any]) -> tuple[bool, int]:
    """Whether any token fetches, and how deep the blocks nest — walked with a stack, so a value
    nested past the interpreter's own depth is measured, never raised on."""
    deepest = 0
    stack: list[tuple[Sequence[Any], int]] = [(tokens, 0)]
    while stack:
        level, depth = stack.pop()
        deepest = max(deepest, depth)
        for token in level:
            if isinstance(token, ast.URLToken):
                return True, deepest
            if isinstance(token, ast.FunctionBlock):
                if token.lower_name == "url":
                    return True, deepest
                stack.append((token.arguments, depth + 1))
            elif isinstance(
                token, ast.ParenthesesBlock | ast.SquareBracketsBlock | ast.CurlyBracketsBlock
            ):
                stack.append((token.content, depth + 1))
    return False, deepest


# --- selectors ---------------------------------------------------------------------------------

# A selector item: its compounds, each with the combinator that joins it to the one before.
Compound = tuple[str | None, tuple[str, ...]]
Item = list[tuple[str, Compound]]


def _selectors(prelude: Sequence[Any]) -> list[Item] | None:
    """The prelude's selector items, or `None` when any falls outside the grammar."""
    items: list[Item] = []
    current: Item = []
    element: str | None = None
    classes: list[str] = []
    started = False
    # A `>` read since the last compound closed, waiting for the compound it joins.
    child = False
    tokens = list(prelude)
    i = 0

    def close() -> None:
        nonlocal element, classes, started, child
        if started:
            current.append(((">" if child else " ") if current else "", (element, tuple(classes))))
            element, classes, started, child = None, [], False, False

    while i < len(tokens):
        token = tokens[i]
        if isinstance(token, ast.WhitespaceToken | ast.Comment):
            close()
            i += 1
            continue
        if isinstance(token, ast.LiteralToken) and token.value in (",", ">"):
            close()
            if not current or child:
                return None
            if token.value == ",":
                items.append(current)
                current = []
            else:
                child = True
            i += 1
            continue
        if isinstance(token, ast.IdentToken) and not started:
            name = token.lower_value
            if name not in ELEMENTS:
                return None
            element, started = name, True
            i += 1
            continue
        if isinstance(token, ast.LiteralToken) and token.value == ".":
            following = tokens[i + 1] if i + 1 < len(tokens) else None
            if not isinstance(following, ast.IdentToken):
                return None
            name = following.lower_value
            if name not in CLASSES:
                return None
            classes.append(name)
            started = True
            i += 2
            continue
        return None
    close()
    if not current or child:
        return None
    items.append(current)
    return items


def _in_gutter(compound: Compound) -> bool:
    element, classes = compound
    return element == "body" or "document-text" in classes or "num" in classes


def _compound_text(compound: Compound) -> str:
    element, classes = compound
    return (element or "") + "".join(f".{name}" for name in classes)


def _item_text(item: Item, *, skip_first: bool = False) -> str:
    parts: list[str] = []
    for n, (combinator, compound) in enumerate(item):
        if skip_first and n == 0:
            continue
        if parts:
            parts.append(" > " if combinator == ">" else " ")
        parts.append(_compound_text(compound))
    return "".join(parts)


# --- values ------------------------------------------------------------------------------------


def _ident(token: Any) -> str | None:
    return token.lower_value if isinstance(token, ast.IdentToken) else None


def _length(
    token: Any, *, most_mm: float, most_em: float | None, units: Iterable[str] = MM
) -> bool:
    if isinstance(token, ast.NumberToken):
        return bool(token.value == 0)
    if not isinstance(token, ast.DimensionToken) or token.value < 0:
        return False
    unit = token.lower_unit
    if unit == "em":
        return most_em is not None and token.value <= most_em
    return unit in units and token.value * MM[unit] <= most_mm + 1e-9


def _colour(token: Any, *, opaque: bool = False) -> bool:
    if isinstance(token, ast.IdentToken) and token.lower_value in ("currentcolor", "inherit"):
        return False
    colour = parse_color(token)
    if not isinstance(colour, RGBA):
        return False
    return not opaque or colour.alpha >= 1


def _one(rule: Callable[[Any], bool]) -> Callable[[list[Any]], bool]:
    return lambda tokens: len(tokens) == 1 and rule(tokens[0])


def _one_to_four(rule: Callable[[Any], bool]) -> Callable[[list[Any]], bool]:
    return lambda tokens: 1 <= len(tokens) <= 4 and all(rule(t) for t in tokens)


def _keyword(name: str) -> Callable[[list[Any]], bool]:
    return _one(lambda t: _ident(t) in KEYWORDS[name])


def _font_size(token: Any) -> bool:
    if not isinstance(token, ast.DimensionToken):
        return False
    if token.lower_unit == "pt":
        return bool(6 <= token.value <= 72)
    if token.lower_unit == "px":
        return bool(8 <= token.value <= 96)
    return False


def _font_weight(token: Any) -> bool:
    if _ident(token) in ("normal", "bold"):
        return True
    return (
        isinstance(token, ast.NumberToken)
        and token.is_integer
        and 100 <= token.int_value <= 900
        and token.int_value % 100 == 0
    )


def _spacing_word(token: Any) -> bool:
    return _ident(token) == "normal" or _length(token, most_mm=5 * PT_MM, most_em=0.5)


def _box(token: Any, *, auto: bool) -> bool:
    return (auto and _ident(token) == "auto") or _length(token, most_mm=50, most_em=4)


def _border_width(token: Any) -> bool:
    return _ident(token) in ("thin", "medium", "thick") or _length(token, most_mm=3, most_em=None)


def _border(tokens: list[Any]) -> bool:
    if not 1 <= len(tokens) <= 3:
        return False
    kinds: list[str] = []
    for token in tokens:
        if _ident(token) in BORDER_STYLES:
            kinds.append("style")
        elif _border_width(token):
            kinds.append("width")
        elif _colour(token):
            kinds.append("colour")
        else:
            return False
    return len(set(kinds)) == len(kinds)


def _families(item: ast.Declaration, tokens: list[Any], found: list[StyleRefusal]) -> bool:
    """`font-family`: each comma-separated family installed, or a generic; an unknown family
    is refused `font` and the value counts as passing."""
    known = {name.lower() for name in FONTS} | set(GENERICS)
    families: list[list[Any]] = [[]]
    for token in tokens:
        if isinstance(token, ast.LiteralToken) and token.value == ",":
            families.append([])
        else:
            families[-1].append(token)
    for family in families:
        if not family:
            return False
        if len(family) == 1 and isinstance(family[0], ast.StringToken):
            name = family[0].value.lower()
        elif all(isinstance(t, ast.IdentToken) for t in family):
            name = " ".join(t.lower_value for t in family)
        else:
            return False
        if name not in known:
            found.append(StyleRefusal(item.source_line, "font", name))
    return True


def _page_value(name: str) -> Callable[[list[Any]], bool]:
    if name == "size":
        return lambda tokens: (
            1 <= len(tokens) <= 2
            and _ident(tokens[0]) in PAGE_SIZES
            and (len(tokens) == 1 or _ident(tokens[1]) in ("portrait", "landscape"))
        )
    page_units = ("mm", "cm", "in", "pt")

    def margin(token: Any) -> bool:
        if not isinstance(token, ast.DimensionToken) or token.lower_unit not in page_units:
            return False
        return bool(12 - 1e-9 <= token.value * MM[token.lower_unit] <= 50 + 1e-9)

    return _one(margin) if name != "margin" else _one_to_four(margin)


def _value_rules() -> dict[str, Callable[[list[Any]], bool]]:
    rules: dict[str, Callable[[list[Any]], bool]] = {
        "font-family": lambda tokens: True,
        "font-size": _one(_font_size),
        "font-weight": _one(_font_weight),
        "line-height": _one(lambda t: isinstance(t, ast.NumberToken) and 1 <= t.value <= 3),
        "letter-spacing": _one(_spacing_word),
        "word-spacing": _one(_spacing_word),
        "text-indent": _one(lambda t: _length(t, most_mm=50, most_em=4)),
        "color": _one(lambda t: _colour(t, opaque=True)),
        "background-color": _one(_colour),
        "background": _one(_colour),
        "margin": _one_to_four(lambda t: _box(t, auto=True)),
        "padding": _one_to_four(lambda t: _box(t, auto=False)),
        "border": _border,
        "border-width": _one_to_four(_border_width),
        "border-style": _one_to_four(lambda t: _ident(t) in BORDER_STYLES),
        "border-color": _one_to_four(_colour),
        "border-radius": _one_to_four(lambda t: _length(t, most_mm=5, most_em=None)),
    }
    for name in KEYWORDS:
        rules[name] = _keyword(name)
    for side in SIDES:
        rules[f"margin-{side}"] = _one(lambda t: _box(t, auto=True))
        rules[f"padding-{side}"] = _one(lambda t: _box(t, auto=False))
        rules[f"border-{side}"] = _border
        rules[f"border-{side}-width"] = _one(_border_width)
        rules[f"border-{side}-style"] = _one(lambda t: _ident(t) in BORDER_STYLES)
        rules[f"border-{side}-color"] = _one(_colour)
    return rules


VALUES = _value_rules()


# --- what is served and exported --------------------------------------------------------------


def _rewritten(text: str, selector: Callable[[Item], list[str]], *, keep_page: bool) -> str:
    """The rules of a checked `text` with each selector item rewritten by `selector`, declarations
    as written; `@page` kept or dropped, `@media print` kept with its rules rewritten."""
    out: list[str] = []

    def rule(node: ast.QualifiedRule) -> str:
        items = _selectors(node.prelude) or []
        written = ", ".join(s for item in items for s in selector(item))
        return f"{written} {{{tinycss2.serialize(node.content).strip()}}}"

    for node in tinycss2.parse_stylesheet(text, skip_comments=True, skip_whitespace=True):
        if isinstance(node, ast.QualifiedRule):
            out.append(rule(node))
        elif isinstance(node, ast.AtRule) and node.lower_at_keyword == "page":
            if keep_page:
                out.append(f"@page {{{tinycss2.serialize(node.content or []).strip()}}}")
        elif isinstance(node, ast.AtRule) and node.lower_at_keyword == "media":
            inner = [
                rule(n)
                for n in tinycss2.parse_rule_list(
                    node.content or [], skip_comments=True, skip_whitespace=True
                )
                if isinstance(n, ast.QualifiedRule)
            ]
            out.append("@media print { " + " ".join(inner) + " }")
    return "\n".join(out) + ("\n" if out else "")


def _leads_with_text(item: Item) -> bool:
    return _compound_text(item[0][1]) in ("body", ".document-text")


def scoped_for_browser(text: str) -> str:
    """The checked rules for a reader's browser: each selector confined to the document's text —
    a leading `body` or `.document-text` read as `.document-text`, any other under it — and no
    `@page`."""

    def confined(item: Item) -> list[str]:
        if _leads_with_text(item):
            rest = _item_text(item, skip_first=True)
            joiner = " > " if len(item) > 1 and item[1][0] == ">" else " "
            return [".document-text" + (joiner + rest if rest else "")]
        return [".document-text " + _item_text(item)]

    return _rewritten(text, confined, keep_page=False)


def for_export(text: str) -> str:
    """The checked rules for the exports, as written: each selector under `:root`, so it weighs
    as much as the default's and, coming later, wins; a leading `body` or `.document-text` as
    both, since the default sets the text's font on `.document-text` itself."""

    def rooted(item: Item) -> list[str]:
        if _leads_with_text(item):
            rest = _item_text(item, skip_first=True)
            joiner = " > " if len(item) > 1 and item[1][0] == ">" else " "
            tail = joiner + rest if rest else ""
            return [f":root body{tail}", f":root .document-text{tail}"]
        return [":root " + _item_text(item)]

    return _rewritten(text, rooted, keep_page=True)


def guard(scope: str) -> str:
    """The platform's sheet after the organisation's, under `scope`: the approval line at fixed
    values for every property a stylesheet may set, and the marks of a change in their own
    colours and lines (DL-0360, DL-0363, DL-0477). Every declaration `!important`, which the
    organisation may not write, so no rule of theirs outweighs it."""

    def block(selectors: str, declarations: dict[str, str]) -> str:
        body = " ".join(f"{name}: {value} !important;" for name, value in declarations.items())
        return f"{selectors} {{ {body} }}"

    approval = {
        "font-family": '"DejaVu Sans", sans-serif',
        "font-size": "11pt",
        "font-weight": "normal",
        "font-style": "normal",
        "font-variant": "normal",
        "line-height": "1.4",
        "letter-spacing": "normal",
        "word-spacing": "normal",
        "text-decoration": "none",
        "text-transform": "none",
        "text-indent": "0",
        "vertical-align": "baseline",
        "text-align": "inherit",
        "color": "#000",
        # Its own white box: nothing painted behind it may hide its words.
        "background": "#fff",
        "border": "none",
        "border-radius": "0",
        "margin": "6pt 0 0 0",
        "padding": "0",
    }
    # A mark's words in the platform's ink, whatever colour the text around them takes: text set
    # to a mark's own background would otherwise vanish inside the mark.
    inherited = {
        "color": "#222",
        "font-size": "inherit",
        "letter-spacing": "inherit",
        "vertical-align": "inherit",
    }
    marks = {
        "ins": {"background-color": "#dff0d8", "text-decoration": "none"},
        "del": {"background-color": "#f6d6d6", "text-decoration": "line-through"},
        ".format-changed": {"background-color": "#fff3c4", "text-decoration": "none"},
        # The earlier formatting, revealed on focus, in the platform's grey (`document.css`).
        ".format-old": {
            "background-color": "transparent",
            "text-decoration": "line-through",
            "color": "#777",
        },
        ".imgpair": {"background-color": "transparent", "text-decoration": "none"},
    }
    rules = [block(f"{scope} .title-page .approval, {scope} .title-page .approval *", approval)]
    rules += [block(f"{scope} {mark}", {**inherited, **own}) for mark, own in marks.items()]
    # Formatting inside a mark — an `em`, a `strong`, an entity's span — takes the mark's ink and
    # paints nothing over its background; a mark nested in another keeps its own.
    words = ("ins", "del", ".format-changed", ".format-old")
    others = "".join(f":not({mark})" for mark in words)
    inside = ", ".join(f"{scope} {mark} *{others}" for mark in words)
    rules.append(block(inside, {"color": "inherit", "background-color": "transparent"}))
    return "\n".join(rules) + "\n"


GUARD = guard(".document-text")
EXPORT_GUARD = guard(":root")


def export_stylesheets(text: str) -> list[str]:
    """The sheets a PDF is rendered with, in order: the default, the furniture, the
    organisation's as written — after the furniture, so its page size and margins win within the
    checker's bounds — and the guard last."""
    from rendering.export import furniture
    from rendering.export.job import STYLESHEET

    return [
        STYLESHEET.read_text(encoding="utf-8"),
        furniture.pdf_css(),
        for_export(applied(text)),
        EXPORT_GUARD,
    ]


def served(text: str) -> str:
    """The stylesheet a reader's browser is given: the organisation's checked rules confined to
    the document's text, then the guard; the guard alone when no rule applies."""
    return _served(text, GUARD)


@functools.lru_cache(maxsize=8)
def _served(text: str, guard_text: str) -> str:
    return scoped_for_browser(applied(text)) + guard_text


def digest(css: str) -> str:
    """The served bytes' address: a release that changes the checker or the guard changes it."""
    import hashlib

    return hashlib.sha256(css.encode("utf-8")).hexdigest()[:16]

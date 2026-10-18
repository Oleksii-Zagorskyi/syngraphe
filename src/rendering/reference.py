"""The Word reference document's styles, derived from the organisation's stylesheet (DL-0465,
ADR-0013): a fixed mapping of selectors to Word's named styles and of properties to their OOXML
form, and the page from `@page`. What the mapping cannot carry is listed, never guessed.

Only computed values reach the XML — six hex digits, integers in OOXML's units, a font name from
`rendering.stylesheet.FONTS` — so no character of the stylesheet's text is ever copied into a
Word file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import tinycss2
from tinycss2 import ast
from tinycss2.color3 import RGBA, parse_color

from rendering.stylesheet import FONTS, MM, _item_text, _selectors, applied

# A selector, its leading `body`, `.document-text` or `:root` stripped, to the styles it sets.
# *Title Page Approval* is in no row: the approval line's look is the platform's alone.
MAPPING: dict[str, tuple[str, ...]] = {
    "": ("Normal", "BodyText"),
    "p": ("Normal", "BodyText"),
    "h1": ("Heading1",),
    "h2": ("Heading2",),
    "h3": ("Heading3",),
    "h4": ("Heading4",),
    ".entity": ("EntityRole", "EntityAction", "EntityTerm"),
    ".entity-role": ("EntityRole",),
    ".entity-action": ("EntityAction",),
    ".entity-term": ("EntityTerm",),
    ".underline": ("Underline",),
    ".num": ("ClauseNumber",),
    ".callout": ("CalloutNote", "CalloutWarning", "CalloutExample"),
    ".callout-note": ("CalloutNote",),
    ".callout-warning": ("CalloutWarning",),
    ".callout-example": ("CalloutExample",),
    "blockquote": ("BlockText",),
    "a": ("Hyperlink",),
    ".title-page": ("TitlePageTitle", "TitlePageDetail"),
    ".document-title": ("TitlePageTitle",),
    **{
        f".{name}": ("TitlePageDetail",)
        for name in (
            "document-number",
            "document-type",
            "document-edition",
            "approver",
            "approval-date",
            "title-page-text",
        )
    },
}
# Character styles take their shading in the run; every other style is a paragraph's.
CHARACTER = frozenset(
    ["EntityRole", "EntityAction", "EntityTerm", "Underline", "ClauseNumber", "Hyperlink"]
)
GENERIC_FONTS = {
    "serif": "DejaVu Serif",
    "sans-serif": "DejaVu Sans",
    "monospace": "DejaVu Sans Mono",
}
# A page's size in twentieths of a point, portrait.
PAGE_SIZES = {
    "a3": (16838, 23811),
    "a4": (11906, 16838),
    "a5": (8391, 11906),
    "letter": (12240, 15840),
    "legal": (12240, 20160),
}
BASE_PT = 11.0
TWIPS_PER_MM = 1440 / 25.4


@dataclass
class Look:
    """A style's properties as OOXML elements by their tag: the paragraph's and the run's."""

    paragraph: dict[str, str] = field(default_factory=dict)
    run: dict[str, str] = field(default_factory=dict)
    # The attributes of `w:spacing`, which three properties share.
    spacing: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Unmapped:
    line: int
    selector: str
    prop: str


@dataclass
class Derived:
    styles: dict[str, Look]
    section: Look | None
    unmapped: list[Unmapped]


def derive(text: str) -> Derived:
    """The styles `text` sets — read through `applied`, never the raw row — in source order, the
    later declaration winning; the page; and what is not carried."""
    styles: dict[str, Look] = {}
    section: Look | None = None
    unmapped: list[Unmapped] = []
    for node in tinycss2.parse_stylesheet(applied(text), skip_comments=True, skip_whitespace=True):
        if isinstance(node, ast.AtRule) and node.lower_at_keyword == "page":
            section = section or Look()
            for item in _declarations(node.content or []):
                if not _page(section, item):
                    unmapped.append(Unmapped(item.source_line, "@page", item.lower_name))
        elif isinstance(node, ast.AtRule) and node.lower_at_keyword == "media":
            # Print rules are the PDF's; a Word file has no media of its own to read them for.
            for inner in tinycss2.parse_rule_list(
                node.content or [], skip_comments=True, skip_whitespace=True
            ):
                if isinstance(inner, ast.QualifiedRule):
                    _rule(inner, styles, unmapped, "@media print ")
        elif isinstance(node, ast.QualifiedRule):
            _rule(node, styles, unmapped, "")
    return Derived(styles, section, unmapped)


def _declarations(content: Any) -> list[ast.Declaration]:
    return [
        item
        for item in tinycss2.parse_blocks_contents(
            content, skip_comments=True, skip_whitespace=True
        )
        if isinstance(item, ast.Declaration)
    ]


def _rule(
    node: ast.QualifiedRule, styles: dict[str, Look], unmapped: list[Unmapped], media: str
) -> None:
    items = _selectors(node.prelude) or []
    for item in items:
        written = _item_text(item)
        key = _stripped(item)
        targets = MAPPING.get(key) if key is not None and not media else None
        for declaration in _declarations(node.content):
            if targets is None:
                unmapped.append(
                    Unmapped(declaration.source_line, media + written, declaration.lower_name)
                )
                continue
            carried = False
            for target in targets:
                carried = _carry(styles.setdefault(target, Look()), target, declaration) or carried
            if not carried:
                unmapped.append(Unmapped(declaration.source_line, written, declaration.lower_name))


def _stripped(item: Any) -> str | None:
    """The selector's one compound once a leading `body` or `.document-text` is set aside; `None`
    for a selector of several compounds, which no Word style can stand for."""
    compounds = [compound for _combinator, compound in item]
    if len(compounds) > 1 and _text_of(compounds[0]) in ("body", ".document-text"):
        compounds = compounds[1:]
    if len(compounds) != 1:
        return None
    written = _text_of(compounds[0])
    return "" if written in ("body", ".document-text") else written


def _text_of(compound: Any) -> str:
    element, classes = compound
    return (element or "") + "".join(f".{name}" for name in classes)


# --- values to OOXML ---------------------------------------------------------------------------


def _tokens(declaration: ast.Declaration) -> list[Any]:
    return [t for t in declaration.value if not isinstance(t, ast.WhitespaceToken | ast.Comment)]


def _hex(token: Any) -> str | None:
    colour = parse_color(token)
    if not isinstance(colour, RGBA):
        return None
    return "".join(f"{round(part * 255):02X}" for part in (colour.red, colour.green, colour.blue))


def _points(token: Any) -> float | None:
    if isinstance(token, ast.NumberToken) and token.value == 0:
        return 0.0
    if not isinstance(token, ast.DimensionToken):
        return None
    if token.lower_unit == "em":
        return float(token.value) * BASE_PT
    if token.lower_unit in MM:
        return float(token.value) * MM[token.lower_unit] * 72 / 25.4
    return None


def _font(tokens: list[Any]) -> str | None:
    known = {name.lower(): name for name in FONTS}
    first: list[Any] = []
    for token in tokens:
        if isinstance(token, ast.LiteralToken) and token.value == ",":
            break
        first.append(token)
    if len(first) == 1 and isinstance(first[0], ast.StringToken):
        name = first[0].value.lower()
    elif first and all(isinstance(t, ast.IdentToken) for t in first):
        name = " ".join(t.lower_value for t in first)
    else:
        return None
    return known.get(name) or GENERIC_FONTS.get(name)


def _carry(look: Look, style: str, declaration: ast.Declaration) -> bool:
    """`declaration` set on `look` as OOXML; whether it could be."""
    name = declaration.lower_name
    tokens = _tokens(declaration)
    one = tokens[0] if len(tokens) == 1 else None
    if name == "font-family":
        font = _font(tokens)
        if font is None:
            return False
        look.run["rFonts"] = (
            f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:eastAsia="{font}" w:cs="{font}"/>'
        )
        return True
    if name == "font-size" and one is not None:
        points = _points(one)
        if points is None:
            return False
        half = round(points * 2)
        look.run["sz"] = f'<w:sz w:val="{half}"/>'
        look.run["szCs"] = f'<w:szCs w:val="{half}"/>'
        return True
    if name == "font-weight" and one is not None:
        bold = (isinstance(one, ast.IdentToken) and one.lower_value == "bold") or (
            isinstance(one, ast.NumberToken) and one.value >= 600
        )
        look.run["b"] = "<w:b/>" if bold else '<w:b w:val="0"/>'
        return True
    if name == "font-style" and isinstance(one, ast.IdentToken):
        look.run["i"] = "<w:i/>" if one.lower_value == "italic" else '<w:i w:val="0"/>'
        return True
    if name == "color" and one is not None:
        colour = _hex(one)
        if colour is None:
            return False
        look.run["color"] = f'<w:color w:val="{colour}"/>'
        return True
    if name in ("background-color", "background") and one is not None:
        colour = _hex(one)
        if colour is None:
            return False
        shading = f'<w:shd w:val="clear" w:color="auto" w:fill="{colour}"/>'
        (look.run if style in CHARACTER else look.paragraph)["shd"] = shading
        return True
    if name == "text-decoration" and isinstance(one, ast.IdentToken):
        look.run["u"] = (
            '<w:u w:val="single"/>' if one.lower_value == "underline" else '<w:u w:val="none"/>'
        )
        return True
    if style in CHARACTER:
        # The rest are a paragraph's.
        return False
    if name == "text-align" and isinstance(one, ast.IdentToken):
        value = {"left": "left", "right": "right", "center": "center", "justify": "both"}
        look.paragraph["jc"] = f'<w:jc w:val="{value[one.lower_value]}"/>'
        return True
    if name in ("margin-top", "margin-bottom", "margin") and tokens:
        sides = _sides(tokens)
        if sides is None:
            return False
        top, _right, bottom, _left = sides
        # A vertical `auto` margin computes to nothing in CSS.
        if name in ("margin", "margin-top"):
            look.spacing["w:before"] = str(round((top or 0) * 20))
        if name in ("margin", "margin-bottom"):
            look.spacing["w:after"] = str(round((bottom or 0) * 20))
        return True
    if name == "line-height" and isinstance(one, ast.NumberToken):
        look.spacing["w:line"] = str(round(float(one.value) * 240))
        look.spacing["w:lineRule"] = "auto"
        return True
    if name == "border-left" and tokens:
        border = _border(tokens)
        if border is None:
            return False
        look.paragraph["pBdr"] = f"<w:pBdr>{border}</w:pBdr>"
        return True
    return False


def _sides(
    tokens: list[Any],
) -> tuple[float | None, float | None, float | None, float | None] | None:
    values: list[float | None] = []
    for token in tokens:
        if isinstance(token, ast.IdentToken) and token.lower_value == "auto":
            # A vertical `auto` margin is nothing, as CSS computes it; a side's is `None`.
            values.append(None)
            continue
        points = _points(token)
        if points is None:
            return None
        values.append(points)
    if not 1 <= len(values) <= 4:
        return None
    top = values[0]
    right = values[1] if len(values) > 1 else top
    bottom = values[2] if len(values) > 2 else top
    left = values[3] if len(values) > 3 else right
    return top, right, bottom, left


def _border(tokens: list[Any]) -> str | None:
    width, style, colour = 0.75, "single", "auto"
    for token in tokens:
        if isinstance(token, ast.IdentToken) and token.lower_value in (
            "none",
            "solid",
            "dashed",
            "dotted",
            "double",
        ):
            style = {"none": "none", "solid": "single", "dashed": "dashed", "dotted": "dotted",
                     "double": "double"}[token.lower_value]  # fmt: skip
        elif isinstance(token, ast.IdentToken) and token.lower_value in ("thin", "medium", "thick"):
            width = {"thin": 0.5, "medium": 1.5, "thick": 3.0}[token.lower_value]
        elif (points := _points(token)) is not None:
            width = points
        elif (found := _hex(token)) is not None:
            colour = found
        else:
            return None
    eighths = max(2, min(96, round(width * 8)))
    return f'<w:left w:val="{style}" w:sz="{eighths}" w:space="4" w:color="{colour}"/>'


def _page(section: Look, declaration: ast.Declaration) -> bool:
    name = declaration.lower_name
    tokens = _tokens(declaration)
    if name == "size":
        size = (
            PAGE_SIZES.get(tokens[0].lower_value) if isinstance(tokens[0], ast.IdentToken) else None
        )
        if size is None:
            return False
        width, height = size
        landscape = len(tokens) > 1 and getattr(tokens[1], "lower_value", "") == "landscape"
        if landscape:
            width, height = height, width
            section.paragraph["pgSz"] = (
                f'<w:pgSz w:w="{width}" w:h="{height}" w:orient="landscape"/>'
            )
        else:
            section.paragraph["pgSz"] = f'<w:pgSz w:w="{width}" w:h="{height}"/>'
        return True
    if name == "margin" or name.startswith("margin-"):
        sides = _sides(tokens) if name == "margin" else None
        margins = dict(section.spacing)
        if name == "margin":
            if sides is None:
                return False
            for side, value in zip(("top", "right", "bottom", "left"), sides, strict=True):
                margins[side] = str(round((value or 0) * 20))
        else:
            points = _points(tokens[0]) if len(tokens) == 1 else None
            if points is None:
                return False
            margins[name.removeprefix("margin-")] = str(round(points * 20))
        section.spacing = margins
        attributes = " ".join(
            f'w:{side}="{margins.get(side, "1440")}"' for side in ("top", "right", "bottom", "left")
        )
        section.paragraph["pgMar"] = (
            f'<w:pgMar {attributes} w:header="709" w:footer="709" w:gutter="0"/>'
        )
        return True
    return False


# --- the overlay on Pandoc's reference document ------------------------------------------------

# The order OOXML's schema gives the children of a paragraph's and a run's properties.
PARAGRAPH_ORDER = (
    "pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr "
    "shd tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE "
    "autoSpaceDN bidi adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents "
    "suppressOverlap jc textDirection textAlignment textboxTightWrap outlineLvl divId cnfStyle "
    "rPr sectPr pPrChange"
).split()
RUN_ORDER = (
    "rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof "
    "snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd "
    "fitText vertAlign rtl cs em lang eastAsianLayout specVanish oMath"
).split()
SECTION_ORDER = (
    "headerReference footerReference footnotePr endnotePr type pgSz pgMar paperSrc pgBorders "
    "lnNumType pgNumType cols formProt vAlign noEndnote titlePg textDirection bidi rtlGutter "
    "docGrid printerSettings sectPrChange"
).split()


def _children(body: str) -> list[tuple[str, str]]:
    """The top-level elements of an element's body as `(tag, text)`, its white space dropped."""
    found: list[tuple[str, str]] = []
    at = 0
    pattern = re.compile(r"<w:(\w+)\b[^>]*?(/>|>)", re.DOTALL)
    while (match := pattern.search(body, at)) is not None:
        tag = match.group(1)
        if match.group(2) == "/>":
            end = match.end()
        else:
            close = body.find(f"</w:{tag}>", match.end())
            end = close + len(f"</w:{tag}>")
        found.append((tag, body[match.start() : end]))
        at = end
    return found


def _merged(body: str, wanted: dict[str, str], order: list[str]) -> str:
    """`body`'s children with `wanted`'s by tag in their place, in the schema's order."""
    kept = [(tag, text) for tag, text in _children(body) if tag not in wanted]
    every = kept + list(wanted.items())
    rank = {tag: n for n, tag in enumerate(order)}
    every.sort(key=lambda child: rank.get(child[0], len(order)))
    return "".join(text for _tag, text in every)


def _with_part(style: str, part: str, wanted: dict[str, str], order: list[str]) -> str:
    """The style element with its `w:pPr` or `w:rPr` holding `wanted`."""
    if not wanted:
        return style
    found = re.search(rf"<w:{part}\s*/>|<w:{part}>(.*?)</w:{part}>", style, re.DOTALL)
    if found is not None:
        merged = _merged(found.group(1) or "", wanted, order)
        return style[: found.start()] + f"<w:{part}>{merged}</w:{part}>" + style[found.end() :]
    block = f"<w:{part}>{_merged('', wanted, order)}</w:{part}>"
    if part == "pPr" and "<w:rPr" in style:
        at = style.index("<w:rPr")
        return style[:at] + block + style[at:]
    return style.replace("</w:style>", block + "</w:style>")


def overlay(styles_xml: str, document_xml: str, derived: Derived) -> tuple[str, str]:
    """Pandoc's `styles.xml` with each derived style's properties set, its others kept; and its
    `document.xml` with the derived page."""
    for identifier, look in derived.styles.items():
        found = re.search(
            rf'<w:style\b[^>]*w:styleId="{identifier}"[^>]*>.*?</w:style>', styles_xml, re.DOTALL
        )
        if found is None:
            continue
        paragraph = dict(look.paragraph)
        if look.spacing:
            # The paragraph's own spacing, never a run's character spacing.
            ppr = re.search(r"<w:pPr>(.*?)</w:pPr>", found.group(0), re.DOTALL)
            current = re.search(r"<w:spacing\b([^>]*?)/>", ppr.group(1)) if ppr else None
            attributes = dict(re.findall(r'(w:\w+)="([^"]*)"', current.group(1))) if current else {}
            attributes.update(look.spacing)
            paragraph["spacing"] = (
                "<w:spacing " + " ".join(f'{k}="{v}"' for k, v in attributes.items()) + "/>"
            )
        style = _with_part(found.group(0), "pPr", paragraph, PARAGRAPH_ORDER)
        style = _with_part(style, "rPr", look.run, RUN_ORDER)
        styles_xml = styles_xml[: found.start()] + style + styles_xml[found.end() :]
    if derived.section is not None and derived.section.paragraph:
        section = re.search(r"<w:sectPr>(.*?)</w:sectPr>", document_xml, re.DOTALL)
        if section is not None:
            merged = _merged(section.group(1), derived.section.paragraph, SECTION_ORDER)
            document_xml = (
                document_xml[: section.start()]
                + f"<w:sectPr>{merged}</w:sectPr>"
                + document_xml[section.end() :]
            )
    return styles_xml, document_xml

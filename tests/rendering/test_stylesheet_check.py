"""The stylesheet checker admits only the allowlist and names each refusal with its line (DL-0464,
DL-0477, T-23, ASR-19).

Every stylesheet here is invented. Each refused construct stands on a line other than the first,
so a refusal reported at the wrong line fails. Twenty-six sheets, a refusal of each kind and one
valid sheet, open the file; the groups after them walk every code, every bound at its edge
and one step past, every keyword a property admits, every unit a row refuses, and the two cases
DL-0477 accepts on purpose.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from rendering.stylesheet import (
    CLASSES,
    ELEMENTS,
    EXCLUDED,
    FONTS,
    MAX_BYTES,
    PROPERTIES,
    StyleRefusal,
    applied,
    check,
)

pytestmark = pytest.mark.fast


def sheet(*lines: str) -> str:
    """A stylesheet whose first line is a comment, so `lines` start at line 2."""
    return "/* an invented organisation's stylesheet */\n" + "\n".join(lines) + "\n"


def rule(selector: str, *declarations: str) -> str:
    """A rule with its prelude on line 2 and its first declaration on line 3."""
    return sheet(selector + " {", *(f"  {d};" for d in declarations), "}")


def page(*declarations: str) -> str:
    """An `@page` rule with its keyword on line 2 and its first declaration on line 3."""
    return sheet("@page {", *(f"  {d};" for d in declarations), "}")


def refused(text: str) -> list[tuple[int, str]]:
    return [(r.line, r.code) for r in check(text)]


def named(text: str) -> list[tuple[int, str, str]]:
    return [(r.line, r.code, r.subject) for r in check(text)]


# --- Twenty-six sheets: a refusal of each kind, and one that passes ------------------------------

ROW_ONE = [
    pytest.param(sheet('@import "x.css";'), [(2, "at-rule")], id="import"),
    pytest.param(rule("h1", "background: url(x.png)"), [(3, "fetches")], id="url-in-background"),
    pytest.param(
        sheet("@font-face {", '  font-family: "DejaVu Serif";', "}"),
        [(2, "at-rule")],
        id="font-face",
    ),
    # a refused selector's declarations are still checked, so `content` is also named.
    pytest.param(
        rule("p::before", 'content: "x"'),
        [(2, "selector"), (3, "property")],
        id="pseudo-element-with-content",
    ),
    # `.clause` is outside CLASSES, so the selector is refused beside `display`.
    pytest.param(
        rule(".clause", "display: none"),
        [(2, "selector"), (3, "property")],
        id="unknown-class-with-display",
    ),
    pytest.param(sheet("#id {}"), [(2, "selector")], id="id-selector"),
    pytest.param(sheet("a[href] {}"), [(2, "selector")], id="attribute-selector"),
    pytest.param(rule("h1", 'font-family: "Source Serif"'), [(3, "font")], id="unknown-font"),
    pytest.param(rule("p", "font-size: 2pt"), [(3, "value")], id="tiny-font-size"),
    pytest.param(rule("p", "margin-top: -4mm"), [(3, "value")], id="negative-margin"),
    pytest.param(rule("h1", "color: red !important"), [(3, "value")], id="important"),
    pytest.param(rule("p", "margin-left: calc(0mm - 40mm)"), [(3, "value")], id="calc"),
    pytest.param(rule("p", "text-indent: 300mm"), [(3, "value")], id="indent-past-the-bound"),
    pytest.param(rule("span", "font-size: 0.5em"), [(3, "value")], id="relative-font-size"),
    pytest.param(rule("p", "line-height: 0.01"), [(3, "value")], id="line-height-below-one"),
    pytest.param(rule("p", "color: rgba(0,0,0,0)"), [(3, "value")], id="see-through-colour"),
    pytest.param(rule("p", "color: transparent"), [(3, "value")], id="transparent-colour"),
    pytest.param(rule("p", "text-decoration: line-through"), [(3, "value")], id="line-through"),
    pytest.param(page("margin: 0"), [(3, "value")], id="page-margin-zero"),
    pytest.param(page("size: 10mm"), [(3, "value")], id="page-size-in-mm"),
    # one declaration, one refusal — the gutter's rule and the bound both broken count once.
    pytest.param(rule(".num", "padding-left: 300mm"), [(3, "value")], id="padding-on-num"),
    pytest.param(
        rule(".document-text", "padding-left: 0"), [(3, "value")], id="padding-on-document-text"
    ),
    pytest.param(rule(".approval", "color: white"), [(2, "selector")], id="approval-line"),
    # `inherit` is not a colour, so the deletion mark's declaration is refused as well.
    pytest.param(
        rule("del", "color: inherit"), [(2, "selector"), (3, "value")], id="deletion-mark"
    ),
    pytest.param(sheet("@media screen {}"), [(2, "at-rule")], id="media-screen"),
    pytest.param(
        sheet(
            "h1 {",
            '  font-family: "DejaVu Serif", serif;',
            "  color: #123456;",
            "}",
            "@page {",
            "  margin: 20mm;",
            "}",
        ),
        [],
        id="valid-sheet",
    ),
]


@pytest.mark.parametrize(("text", "expected"), ROW_ONE)
def test_the_allowlist_refuses_by_line(text: str, expected: list[tuple[int, str]]) -> None:
    assert refused(text) == expected


# --- The vocabulary -----------------------------------------------------------------------------

EVERY_PROPERTY = {
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
    *(
        f"{box}{side}"
        for box in ("margin", "padding")
        for side in ("", "-top", "-right", "-bottom", "-left")
    ),
    *(
        f"border{side}{part}"
        for side in ("", "-top", "-right", "-bottom", "-left")
        for part in ("", "-width", "-style", "-color")
    ),
    "border-radius",
    "border-collapse",
    "size",
}


def test_the_vocabulary_is_the_allowlists() -> None:
    assert set(ELEMENTS) == set(
        "body article section div h1 h2 h3 h4 p ul ol li blockquote table thead tbody tr th td "
        "a strong em span img".split()
    )
    assert set(CLASSES) == set(
        "document-text num entity entity-role entity-action entity-term underline mention callout "
        "callout-note callout-warning callout-example attachment-list appendix title-page "
        "document-title document-number document-type document-edition approver approval-date "
        "title-page-text".split()
    )
    assert set(EXCLUDED) == set(
        "ins del format-changed format-old marker removed by imgpair image-description "
        "image-changed before after full-size approval align-left align-centre".split()
    )
    assert not set(CLASSES) & set(EXCLUDED)
    assert set(PROPERTIES) == EVERY_PROPERTY
    assert tuple(FONTS) == (
        "DejaVu Sans",
        "DejaVu Sans Mono",
        "DejaVu Serif",
        "DejaVu Sans Condensed",
        "DejaVu Serif Condensed",
    )
    assert MAX_BYTES == 100_000


def test_a_refusal_is_a_frozen_ordered_record() -> None:
    refusal = StyleRefusal(2, "at-rule", "import")
    assert dataclasses.is_dataclass(refusal)
    assert (refusal.line, refusal.code, refusal.subject) == (2, "at-rule", "import")
    with pytest.raises(dataclasses.FrozenInstanceError):
        refusal.line = 3  # type: ignore[misc]
    assert StyleRefusal(2, "value", "b") < StyleRefusal(3, "at-rule", "a")
    assert StyleRefusal(2, "at-rule", "b") < StyleRefusal(2, "value", "a")
    assert check(sheet('@import "x.css";')) == [refusal]


# --- A sheet using every property, and the two cases accepted on purpose -----------------------

EVERY_PROPERTY_SHEET = sheet(
    "p {",
    '  font-family: "DejaVu Serif", "DejaVu Sans Condensed", serif;',
    "  font-size: 11pt;",
    "  font-weight: normal;",
    "  font-style: italic;",
    "  font-variant: small-caps;",
    "  line-height: 1.4;",
    "  letter-spacing: 0.2pt;",
    "  word-spacing: normal;",
    "  text-decoration: none;",
    "  text-transform: none;",
    "  text-indent: 5mm;",
    "  text-align: justify;",
    "  color: #202020;",
    "  background-color: rgba(255, 255, 255, 0.5);",
    "  margin: 1mm 2mm;",
    "  margin-top: 2pt;",
    "  margin-right: 0;",
    "  margin-bottom: 4pt;",
    "  margin-left: auto;",
    "  padding: 0 1mm 2mm 3mm;",
    "  padding-top: 0;",
    "  padding-right: 1em;",
    "  padding-bottom: 0.5cm;",
    "  padding-left: 0.1in;",
    "}",
    "td {",
    "  vertical-align: middle;",
    "}",
    ".callout {",
    "  background: #f4f4f4;",
    "  border: 1pt solid #cccccc;",
    "  border-top: thin dotted;",
    "  border-right: #cccccc;",
    "  border-bottom: 0.5mm double #cccccc;",
    "  border-left: dashed;",
    "  border-width: 1pt 2pt;",
    "  border-top-width: thick;",
    "  border-right-width: 0;",
    "  border-bottom-width: 2mm;",
    "  border-left-width: medium;",
    "  border-style: solid;",
    "  border-top-style: dotted;",
    "  border-right-style: none;",
    "  border-bottom-style: dashed;",
    "  border-left-style: double;",
    "  border-color: red;",
    "  border-top-color: #abc;",
    "  border-right-color: hsl(120, 50%, 50%);",
    "  border-bottom-color: rgb(1, 2, 3);",
    "  border-left-color: #abcd;",
    "  border-radius: 2mm 3mm;",
    "}",
    "table {",
    "  border-collapse: collapse;",
    "}",
    "@page {",
    "  size: A4 portrait;",
    "  margin: 20mm 25mm;",
    "  margin-top: 12mm;",
    "  margin-right: 50mm;",
    "  margin-bottom: 1.5cm;",
    "  margin-left: 1in;",
    "}",
)


def test_a_sheet_using_every_property_passes() -> None:
    assert set(re.findall(r"^\s+([a-z-]+):", EVERY_PROPERTY_SHEET, re.MULTILINE)) == EVERY_PROPERTY
    assert check(EVERY_PROPERTY_SHEET) == []


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(rule("p", "color: #fff", "background: #fff"), id="colour-equal-to-background"),
        pytest.param(rule("span", "background: #dff0d8"), id="background-in-a-marks-colour"),
        pytest.param(
            rule(".callout span", "background-color: #fff3c4"), id="background-colour-of-a-mark"
        ),
    ],
)
def test_the_cases_accepted_on_purpose_pass(text: str) -> None:
    """DL-0477: the audit answers these, not the checker."""
    assert check(text) == []


# --- `applied` ---------------------------------------------------------------------------------


def test_applied_is_the_text_when_it_passes_and_empty_when_it_does_not() -> None:
    valid = rule("h1", "color: #123456")
    assert applied(valid) == valid
    assert applied(EVERY_PROPERTY_SHEET) == EVERY_PROPERTY_SHEET
    assert applied(rule("p", "display: none")) == ""
    assert applied(sheet('@import "x.css";')) == ""
    assert applied("") == ""


# --- Size, syntax, and never raising -----------------------------------------------------------


def padded_to(size: int) -> str:
    """A valid sheet of exactly `size` UTF-8 bytes; the padding is a comment of two-byte letters,
    so a count of characters would pass what a count of bytes refuses."""
    head = rule("p", "color: #000") + "/* "
    tail = " */\n"
    room = size - len(head.encode()) - len(tail.encode())
    text = head + "é" * (room // 2) + "x" * (room % 2) + tail
    assert len(text.encode()) == size
    return text


def test_a_sheet_over_the_size_is_refused_unread() -> None:
    assert check(padded_to(MAX_BYTES)) == []
    assert refused(padded_to(MAX_BYTES + 1)) == [(1, "too-large")]
    oversized = padded_to(MAX_BYTES) + sheet('@import "x.css";', "p { display: none }")
    assert refused(oversized) == [(1, "too-large")]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            sheet("p {", "  color red;", "  font-size: 11pt;", "}"),
            [(3, "syntax")],
            id="declaration-without-a-colon",
        ),
        pytest.param(
            sheet("p {", "  : red;", "}"),
            [(3, "syntax")],
            id="declaration-without-a-name",
        ),
        pytest.param(
            sheet("p { color: #000 }", "h1 color: red;"),
            [(3, "syntax")],
            id="rule-without-a-block",
        ),
        pytest.param(
            sheet("p {", "  color red;", "  display: none;", "}"),
            [(3, "syntax"), (4, "property")],
            id="the-rest-is-still-checked",
        ),
    ],
)
def test_what_the_parser_cannot_read_is_a_syntax_refusal(
    text: str, expected: list[tuple[int, str]]
) -> None:
    assert refused(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "\n\n",
        "}",
        "{",
        "@",
        ";",
        ":",
        "p {",
        "p { color: }",
        "p { : red }",
        "p { color: #ggg; font-size: pt }",
        "p { margin: 1mm 2mm 3mm 4mm 5mm 6mm }",
        "p { font-family: }",
        "p { font-family: , }",
        "@page",
        "@page { size: }",
        "@page :first",
        "@media print",
        "@media print { color: red; }",
        "@media print { p { color: red } @page { margin: 20mm } }",
        "p { h1 { color: red } }",
        "/* unclosed comment",
        '"unclosed string',
        "url(x.png)",
        "p { color: url( }",
        "\x00",
        "p { color: red }\x00",
        "\ud800",  # a lone surrogate is a `str` that UTF-8 cannot encode as it stands
        "p { font-size: 1e400pt }",
        "p { line-height: 99999999999999999999999999 }",
        "p { font-weight: NaN }",
        "p::before:hover#x[y] ~ * + p { content: counter(x) }",
    ],
)
def test_check_never_raises(text: str) -> None:
    result = check(text)
    assert isinstance(result, list)
    assert all(isinstance(r, StyleRefusal) for r in result)
    assert result == sorted(result)
    assert applied(text) in (text, "")


# --- Order: every refusal, by line then code --------------------------------------------------


def test_every_refusal_is_reported_in_line_then_code_order() -> None:
    text = sheet(
        "p {",
        "  display: none;",
        "  color: red !important;",
        "  font-size: 11pt;",
        "}",
        "#x {",
        "  color: red;",
        "}",
        '@import "x.css";',
        "h1 { color: #000 }",
    )
    assert refused(text) == [
        (3, "property"),
        (4, "value"),
        (7, "selector"),
        (10, "at-rule"),
    ]
    assert refused(sheet('p::before { content: "x" }')) == [(2, "property"), (2, "selector")]


def test_one_bad_declaration_among_good_ones_is_the_only_refusal() -> None:
    text = sheet(
        "h1 {",
        '  font-family: "DejaVu Sans";',
        "  font-size: 18pt;",
        "  position: absolute;",
        "  color: #333;",
        "}",
    )
    assert refused(text) == [(5, "property")]


# --- At-rules -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(sheet('@import "x.css";'), [(2, "at-rule", "import")], id="import"),
        pytest.param(sheet('@import url("x.css");'), [(2, "at-rule", "import")], id="import-url"),
        pytest.param(sheet("@font-face {}"), [(2, "at-rule", "font-face")], id="font-face"),
        pytest.param(
            sheet('@namespace svg url("http://example.test/svg");'),
            [(2, "at-rule", "namespace")],
            id="namespace",
        ),
        pytest.param(
            sheet("@supports (display: grid) {", "  p { color: red }", "}"),
            [(2, "at-rule", "supports")],
            id="supports",
        ),
        pytest.param(sheet("@layer base;"), [(2, "at-rule", "layer")], id="layer"),
        pytest.param(
            sheet("@keyframes fade {", "  from { color: red }", "}"),
            [(2, "at-rule", "keyframes")],
            id="keyframes",
        ),
        pytest.param(sheet("@media screen {}"), [(2, "at-rule", "media")], id="media-screen"),
        pytest.param(
            sheet("@media print and (color) {", "  p { color: red }", "}"),
            [(2, "at-rule", "media")],
            id="media-print-with-a-condition",
        ),
        pytest.param(sheet("@media all {}"), [(2, "at-rule", "media")], id="media-all"),
        pytest.param(sheet("@media {}"), [(2, "at-rule", "media")], id="media-without-a-query"),
        pytest.param(sheet('@charset "utf-8";'), [(2, "at-rule", "charset")], id="charset"),
        pytest.param(sheet('@IMPORT "x.css";'), [(2, "at-rule", "import")], id="uppercase-keyword"),
        pytest.param(
            sheet("@page :first {", "  margin: 20mm;", "}"),
            [(2, "at-rule", "page")],
            id="page-selector",
        ),
        pytest.param(
            sheet("@page {", "  margin: 20mm;", "  @top-center {", '    content: "x";', "  }", "}"),
            [(4, "at-rule", "top-center")],
            id="margin-box-in-page",
        ),
        pytest.param(
            sheet("@page {", "  @bottom-right { content: counter(page) }", "}"),
            [(3, "at-rule", "bottom-right")],
            id="margin-box-alone",
        ),
        # `@media print` holds qualified rules only (DL-0464), so an at-rule inside it is refused.
        pytest.param(
            sheet("@media print {", "  @page { margin: 20mm }", "}"),
            [(3, "at-rule", "page")],
            id="page-inside-media-print",
        ),
        pytest.param(
            sheet("p { color: #000 }", "", "", '@import "x.css";'),
            [(5, "at-rule", "import")],
            id="line-of-the-keyword",
        ),
    ],
)
def test_every_at_rule_but_page_and_media_print_is_refused(
    text: str, expected: list[tuple[int, str, str]]
) -> None:
    assert named(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(page("size: A4", "margin: 20mm"), id="page-size-and-margin"),
        pytest.param(page("margin-top: 12mm", "margin-bottom: 50mm"), id="page-margin-sides"),
        pytest.param(sheet("@page {}"), id="page-empty"),
        pytest.param(sheet("@media print {", "  p { font-size: 11pt }", "}"), id="media-print"),
        pytest.param(sheet("@media print {}"), id="media-print-empty"),
        pytest.param(
            sheet(
                "@media print {", "  h1, h2 { color: #000 }", "  .callout { border: solid }", "}"
            ),
            id="media-print-two-rules",
        ),
        pytest.param(
            sheet("@MEDIA PRINT {", "  p { color: #000 }", "}"), id="media-print-uppercase"
        ),
    ],
)
def test_page_and_media_print_pass(text: str) -> None:
    assert check(text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            sheet("@media print {", "  p { display: none }", "}"),
            [(3, "property")],
            id="property-inside-media-print",
        ),
        pytest.param(
            sheet("@media print {", "  #x { color: red }", "}"),
            [(3, "selector")],
            id="selector-inside-media-print",
        ),
        pytest.param(
            sheet("@media print {", "  body { margin: 0 }", "}"),
            [(3, "value")],
            id="gutter-inside-media-print",
        ),
        pytest.param(
            sheet("@media print {", "  h1 {", "    background: url(x.png);", "  }", "}"),
            [(4, "fetches")],
            id="url-inside-media-print",
        ),
        pytest.param(
            sheet("@media print {", "  h1 { font-family: Arial }", "}"),
            [(3, "font")],
            id="font-inside-media-print",
        ),
        pytest.param(
            sheet("@page {", "  p { color: red }", "}"),
            [(3, "selector")],
            id="rule-nested-in-page",
        ),
        pytest.param(
            sheet("p {", "  h1 { color: red }", "}"),
            [(3, "selector")],
            id="rule-nested-in-a-rule",
        ),
    ],
)
def test_rules_inside_media_print_are_checked_as_at_the_top(
    text: str, expected: list[tuple[int, str]]
) -> None:
    assert refused(text) == expected


# --- Selectors ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "selector",
    [
        "p",
        "body",
        "img",
        "h1, h2, h3, h4",
        ".callout",
        ".callout.callout-note",
        "div.callout.callout-note",
        ".document-text h1",
        ".document-text > h1",
        "ul > li",
        "ul>li",
        "table thead th",
        "section.appendix p",
        "a.mention",
        ".title-page .document-title",
        "p .entity.entity-role",
        "article section div p span strong em",
        "P.CALLOUT",
        "DIV > LI",
        "blockquote,\n.attachment-list li",
    ],
)
def test_a_selector_in_the_grammar_passes(selector: str) -> None:
    assert check(rule(selector, "color: #000")) == []


@pytest.mark.parametrize(
    "selector",
    [
        "#id",
        "p#id",
        "a[href]",
        "a[href^='http']",
        "p:hover",
        "p:first-child",
        "p:not(.callout)",
        "p::before",
        "p::after",
        "p:before",
        "*",
        "* p",
        "p + p",
        "p ~ p",
        "script",
        "iframe",
        "h5",
        "html body",
        "p.clause",
        ".clause",
        ".approval",
        ".title-page .approval",
        "del",
        "ins",
        ".format-changed",
        ".format-old",
        ".marker",
        ".removed",
        ".by",
        ".imgpair",
        ".image-description",
        ".image-changed",
        ".before",
        ".after",
        ".full-size",
        ".align-left",
        ".align-centre",
        "h1, #x",
        ".callout, .approval",
        "p > ",
        "> p",
        "p, ",
        ".",
        "p.",
        "svg|p",
        "p:nth-child(2n)",
        "h1::first-line",
    ],
)
def test_a_selector_outside_the_grammar_is_refused(selector: str) -> None:
    assert refused(rule(selector, "color: #000")) == [(2, "selector")]


def test_a_refused_selectors_declarations_are_still_checked() -> None:
    assert refused(rule("#id", "display: none")) == [(2, "selector"), (3, "property")]
    assert refused(rule(".approval", "color: #000", "visibility: hidden")) == [
        (2, "selector"),
        (4, "property"),
    ]


def test_a_selectors_line_is_where_its_prelude_starts() -> None:
    text = sheet("p { color: #000 }", "", "h1,", "#x", "{", "  color: #000;", "}")
    assert refused(text) == [(4, "selector")]


# --- Properties ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("declaration", "subject"),
    [
        ('content: "x"', "content"),
        ("display: none", "display"),
        ("visibility: hidden", "visibility"),
        ("position: absolute", "position"),
        ("opacity: 0", "opacity"),
        ("float: left", "float"),
        ("width: 0", "width"),
        ("height: 0", "height"),
        ("overflow: hidden", "overflow"),
        ("transform: scale(0)", "transform"),
        ("clip-path: inset(100%)", "clip-path"),
        ("font: 11pt serif", "font"),
        ("text-shadow: 0 0 0 #000", "text-shadow"),
        ("list-style: none", "list-style"),
        ("page-break-after: always", "page-break-after"),
        ("break-after: page", "break-after"),
        ("z-index: 1", "z-index"),
        ("-webkit-text-fill-color: #fff", "-webkit-text-fill-color"),
        ("size: A4", "size"),
        ("DISPLAY: none", "display"),
        ("Color-Scheme: dark", "color-scheme"),
    ],
)
def test_a_property_outside_the_allowlist_is_refused_by_name(
    declaration: str, subject: str
) -> None:
    assert named(rule("p", declaration)) == [(3, "property", subject)]


def test_a_refused_property_is_not_checked_for_its_value() -> None:
    assert refused(rule("p", "display: calc(1px)")) == [(3, "property")]
    assert refused(rule("p", "opacity: 0 !important")) == [(3, "property")]
    # the property check comes first, so a `url(` under an unlisted property is `property`.
    assert refused(rule("p", "list-style: url(x.png)")) == [(3, "property")]


def test_property_names_are_compared_lowercased() -> None:
    assert check(rule("p", "COLOR: #000", "Font-Size: 11pt")) == []


@pytest.mark.parametrize(
    ("declaration", "subject"),
    [
        ("color: #000", "color"),
        ("padding: 20mm", "padding"),
        ("font-size: 11pt", "font-size"),
        ("background: #fff", "background"),
        ("border: solid", "border"),
        ("display: none", "display"),
        ("SIZE-ADJUST: 100%", "size-adjust"),
    ],
)
def test_only_size_and_the_margins_are_properties_of_page(declaration: str, subject: str) -> None:
    assert named(page("size: A4", declaration)) == [(4, "property", subject)]


@pytest.mark.parametrize(
    "declaration",
    [
        "size: A4",
        "margin: 20mm",
        "margin-top: 20mm",
        "margin-right: 20mm",
        "margin-bottom: 20mm",
        "margin-left: 20mm",
        "MARGIN: 20mm",
        "Size: letter",
    ],
)
def test_size_and_the_margins_pass_in_page(declaration: str) -> None:
    assert check(page(declaration)) == []


# --- Values: the general rules -----------------------------------------------------------------


@pytest.mark.parametrize(
    "declaration",
    [
        "color: #000 !important",
        "color: #000 ! important",
        "color: #000 !IMPORTANT",
        "font-size: 11pt !important",
        "margin: 0 !important",
        'font-family: "DejaVu Sans" !important',
        "text-decoration: none !important",
    ],
)
def test_important_is_refused_everywhere(declaration: str) -> None:
    assert refused(rule("p", declaration)) == [(3, "value")]


def test_important_is_refused_in_page() -> None:
    assert refused(page("margin: 20mm !important")) == [(3, "value")]


@pytest.mark.parametrize(
    "declaration",
    [
        "margin-left: calc(1mm)",
        "margin: calc(0mm - 40mm)",
        "color: var(--x)",
        "color: VAR(--x)",
        "font-size: calc(1pt)",
        "font-size: min(10pt, 12pt)",
        "font-size: max(10pt, 12pt)",
        "font-size: clamp(6pt, 11pt, 72pt)",
        "margin-left: env(safe-area-inset-left)",
        "text-indent: attr(data-indent)",
        "line-height: calc(1)",
        "font-weight: calc(400)",
        "color: color-mix(in srgb, red, blue)",
        "background-color: linear-gradient(red, blue)",
    ],
)
def test_every_function_but_the_colour_functions_is_refused(declaration: str) -> None:
    assert refused(rule("p", declaration)) == [(3, "value")]


@pytest.mark.parametrize(
    "declaration",
    [
        "color: rgb(0, 0, 0)",
        "color: rgba(0, 0, 0, 1)",
        "color: hsl(0, 0%, 0%)",
        "color: hsla(0, 0%, 0%, 1)",
        "background-color: rgba(0, 0, 0, 0.5)",
        "background-color: hsla(0, 0%, 0%, 0.5)",
        "border-color: rgb(1, 2, 3)",
    ],
)
def test_the_colour_functions_pass(declaration: str) -> None:
    assert check(rule("p", declaration)) == []


@pytest.mark.parametrize(
    "declaration",
    [
        "background: url(x.png)",
        "background: url('x.png')",
        'background: url("x.png")',
        "background: URL(x.png)",
        "background: Url(x.png)",
        "background-color: url(x.png)",
        "background: #fff url(x.png)",
        "color: url(x.png)",
        "border: url(x.png)",
        "border-color: url(x.png)",
        "border-style: url(x.png)",
        "border-width: url(x.png)",
        "border-radius: url(x.png)",
        "font-family: url(x.woff)",
        "font-size: url(x)",
        "margin: url(x)",
        "text-decoration: url(x)",
        "background: url(data:image/png;base64,AAAA)",
        "background: url(https://example.test/x.png)",
        "background: url( x.png )",
        "background: url()",
    ],
)
def test_any_url_is_a_fetch_whatever_the_property(declaration: str) -> None:
    assert refused(rule("p", declaration)) == [(3, "fetches")]


def test_a_url_in_page_and_in_media_print_is_a_fetch() -> None:
    assert refused(page("margin: url(x)")) == [(3, "fetches")]
    assert refused(sheet("@media print {", "  p { color: url(x) }", "}")) == [(3, "fetches")]


@pytest.mark.parametrize(
    "declaration",
    [
        "margin: -1mm",
        "margin-top: -0.1pt",
        "padding: 1mm -1mm",
        "text-indent: -1mm",
        "letter-spacing: -1pt",
        "word-spacing: -0.1em",
        "font-size: -11pt",
        "line-height: -1",
        "border-width: -1mm",
        "border-radius: -1mm",
        "border: -1mm solid",
        "font-weight: -400",
    ],
)
def test_a_negative_number_is_refused(declaration: str) -> None:
    assert refused(rule("p", declaration)) == [(3, "value")]


@pytest.mark.parametrize(
    "declaration",
    [
        "margin: 5",
        "margin: 1mm 2",
        "padding: 10",
        "text-indent: 10",
        "letter-spacing: 1",
        "border-width: 1",
        "border-radius: 1",
        "font-size: 11",
        "margin: 10%",
        "padding: 10%",
        "text-indent: 10%",
        "font-size: 100%",
        "letter-spacing: 1%",
        "border-width: 1%",
        "margin: 1rem",
        "margin: 1vh",
        "margin: 1vw",
        "margin: 1ch",
        "margin: 1ex",
        "margin: 1Q",
        "margin: 1pc",
        "font-size: 1rem",
        "font-size: 1vw",
        "letter-spacing: 1rem",
        "border-width: 1rem",
        "border-radius: 1vw",
        "text-indent: 1ex",
    ],
)
def test_a_length_needs_an_allowed_unit(declaration: str) -> None:
    """A bare number other than zero, a percentage and every unit outside the six are refused."""
    assert refused(rule("p", declaration)) == [(3, "value")]


@pytest.mark.parametrize(
    "declaration",
    [
        "margin: 0",
        "margin: 0 0 0 0",
        "padding: 0",
        "text-indent: 0",
        "letter-spacing: 0",
        "word-spacing: 0",
        "border-width: 0",
        "border-radius: 0",
        "margin: 0mm",
        "margin: 0pt",
        "margin: 0px",
        "margin: 0cm",
        "margin: 0in",
        "margin: 0em",
        "margin: 0.0mm",
        "margin: .5mm",
        "margin: +1mm",
        "margin: 1.0mm",
    ],
)
def test_zero_needs_no_unit(declaration: str) -> None:
    assert check(rule("p", declaration)) == []


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(rule("p", "margin: 1MM"), id="unit-uppercase"),
        pytest.param(rule("p", "margin: 1Pt"), id="unit-mixed-case"),
        pytest.param(rule("p", "font-weight: BOLD"), id="keyword-uppercase"),
        pytest.param(rule("p", "text-decoration: Underline"), id="keyword-capitalised"),
        pytest.param(rule("p", "color: RGB(0, 0, 0)"), id="colour-function-uppercase"),
        pytest.param(page("size: A4 LANDSCAPE"), id="page-keyword-uppercase"),
        pytest.param(page("size: a4"), id="page-size-lowercase"),
    ],
)
def test_units_and_keywords_are_read_whatever_their_case(text: str) -> None:
    # CSS reads units and keywords case-insensitively.
    assert check(text) == []


# --- Values: `font-family` and `font` -----------------------------------------------------------


@pytest.mark.parametrize(
    "declaration",
    [
        'font-family: "DejaVu Sans"',
        'font-family: "DejaVu Sans Mono"',
        'font-family: "DejaVu Serif"',
        'font-family: "DejaVu Sans Condensed"',
        'font-family: "DejaVu Serif Condensed"',
        "font-family: 'DejaVu Serif'",
        "font-family: DejaVu Serif",
        "font-family: DejaVu Sans Condensed",
        'font-family: "dejavu serif"',
        'font-family: "DEJAVU SANS"',
        "font-family: dejavu sans mono",
        "font-family: serif",
        "font-family: sans-serif",
        "font-family: monospace",
        "font-family: SERIF",
        'font-family: "DejaVu Serif", serif',
        'font-family: "DejaVu Sans", "DejaVu Sans Condensed", sans-serif',
        'font-family: "DejaVu Sans Mono",monospace',
        'font-family:"DejaVu Sans"',
        "font-family: \n    DejaVu Sans,\n    serif",
    ],
)
def test_a_font_family_from_the_installed_families_passes(declaration: str) -> None:
    assert check(rule("p", declaration)) == []


@pytest.mark.parametrize(
    ("declaration", "subject"),
    [
        ('font-family: "Source Serif"', "source serif"),
        ("font-family: Arial", "arial"),
        ("font-family: Times New Roman", "times new roman"),
        ('font-family: "Times New Roman", serif', "times new roman"),
        ('font-family: "DejaVu Sans", Arial', "arial"),
        ('font-family: serif, "Helvetica Neue"', "helvetica neue"),
        ("font-family: cursive", "cursive"),
        ("font-family: fantasy", "fantasy"),
        ("font-family: system-ui", "system-ui"),
        ("font-family: ui-serif", "ui-serif"),
        ("font-family: emoji", "emoji"),
        ("font-family: math", "math"),
        ("font-family: inherit", "inherit"),
        ("font-family: initial", "initial"),
        ("font-family: DejaVu", "dejavu"),
        ("font-family: DejaVu Sans Light", "dejavu sans light"),
    ],
)
def test_a_family_outside_the_installed_ones_is_refused(declaration: str, subject: str) -> None:
    assert named(rule("p", declaration)) == [(3, "font", subject)]


def test_two_unknown_families_are_two_refusals() -> None:
    text = rule("p", "font-family: Arial, Helvetica, serif")
    assert named(text) == [(3, "font", "arial"), (3, "font", "helvetica")]


@pytest.mark.parametrize(
    "declaration",
    [
        "font-family: 12pt",
        'font-family: "DejaVu Sans",',
        'font-family: "DejaVu Sans" serif',
        'font-family: "DejaVu Sans", , serif',
        'font-family: "DejaVu Sans" !important',
    ],
)
def test_a_font_family_outside_the_list_shape_is_a_value_refusal(declaration: str) -> None:
    # a family list that is not a comma list of names is `value`, not `font`.
    assert refused(rule("p", declaration)) == [(3, "value")]


# --- Values: type -------------------------------------------------------------------------------

PASSES_AT_THE_EDGE = [
    # font-size: 6–72 pt, 8–96 px
    "font-size: 6pt",
    "font-size: 72pt",
    "font-size: 8px",
    "font-size: 96px",
    "font-size: 11.5pt",
    "font-size: 6.0pt",
    # font-weight
    "font-weight: normal",
    "font-weight: bold",
    "font-weight: 100",
    "font-weight: 200",
    "font-weight: 300",
    "font-weight: 400",
    "font-weight: 500",
    "font-weight: 600",
    "font-weight: 700",
    "font-weight: 800",
    "font-weight: 900",
    # font-style, font-variant
    "font-style: normal",
    "font-style: italic",
    "font-variant: normal",
    "font-variant: small-caps",
    # line-height: 1–3 unitless
    "line-height: 1",
    "line-height: 3",
    "line-height: 1.0",
    "line-height: 2.5",
    "line-height: 3.0",
    # letter-spacing, word-spacing: normal, 0–5 pt, 0–0.5 em
    "letter-spacing: normal",
    "letter-spacing: 0",
    "letter-spacing: 5pt",
    "letter-spacing: 0.5em",
    "letter-spacing: 6px",
    "letter-spacing: 1.7mm",
    "letter-spacing: 0.17cm",
    "letter-spacing: 0.06in",
    "word-spacing: normal",
    "word-spacing: 5pt",
    "word-spacing: 0.5em",
    "word-spacing: 1.7mm",
    # text-decoration, text-transform
    "text-decoration: none",
    "text-decoration: underline",
    "text-transform: none",
    "text-transform: uppercase",
    "text-transform: lowercase",
    "text-transform: capitalize",
    # text-indent: 0–50 mm, 0–4 em
    "text-indent: 0",
    "text-indent: 50mm",
    "text-indent: 4em",
    "text-indent: 5cm",
    "text-indent: 1.9in",
    "text-indent: 141pt",
    "text-indent: 188px",
    # text-align, vertical-align
    "text-align: left",
    "text-align: right",
    "text-align: center",
    "text-align: justify",
    "vertical-align: baseline",
    "vertical-align: top",
    "vertical-align: middle",
    "vertical-align: bottom",
    "vertical-align: sub",
    "vertical-align: super",
    # color: opaque colours
    "color: #000",
    "color: #000000",
    "color: #000f",
    "color: #000000ff",
    "color: #ABCDEF",
    "color: red",
    "color: WHITE",
    "color: rgb(0, 0, 0)",
    "color: rgba(0, 0, 0, 1)",
    "color: rgba(0, 0, 0, 1.0)",
    "color: hsl(0, 0%, 0%)",
    "color: hsla(0, 0%, 0%, 1)",
    # background-color, background: a colour, alpha allowed
    "background-color: #fff",
    "background-color: #0008",
    "background-color: #00000080",
    "background-color: transparent",
    "background-color: rgba(0, 0, 0, 0)",
    "background-color: rgba(0, 0, 0, 0.5)",
    "background: #fff",
    "background: transparent",
    "background: rgba(255, 255, 255, 0.5)",
    "background: hsl(60, 100%, 90%)",
    "background: yellow",
    # margin, padding: one to four lengths, 0–50 mm or 0–4 em, auto for margin
    "margin: 50mm",
    "margin: 4em",
    "margin: 5cm",
    "margin: 1.9in",
    "margin: 141pt",
    "margin: 188px",
    "margin: 1mm 2mm",
    "margin: 1mm 2mm 3mm",
    "margin: 1mm 2mm 3mm 4mm",
    "margin: 1pt 1px 1mm 1cm",
    "margin: 1in 1em",
    "margin: auto",
    "margin: 0 auto",
    "margin: auto auto auto auto",
    "margin: 1mm auto 2mm",
    "margin-top: 50mm",
    "margin-right: 4em",
    "margin-bottom: auto",
    "margin-left: 0",
    "padding: 50mm",
    "padding: 4em",
    "padding: 1mm 2mm 3mm 4mm",
    "padding-top: 50mm",
    "padding-right: 4em",
    "padding-bottom: 5cm",
    "padding-left: 1.9in",
    # border: a width, a style and a colour, each at most once, any order
    "border: 1mm solid #000",
    "border: solid 1mm #000",
    "border: #000 solid 1mm",
    "border: solid",
    "border: none",
    "border: #000",
    "border: thin",
    "border: 0",
    "border: 3mm",
    "border: 1mm solid",
    "border: solid red",
    "border: thick dotted rgba(0, 0, 0, 0.5)",
    "border-top: 1pt solid red",
    "border-right: dashed",
    "border-bottom: 3mm double",
    "border-left: 8pt",
    # border-width: one to four widths, 0–3 mm, thin, medium, thick
    "border-width: 3mm",
    "border-width: 0",
    "border-width: thin",
    "border-width: medium",
    "border-width: thick",
    "border-width: 8pt",
    "border-width: 0.3cm",
    "border-width: 0.11in",
    "border-width: 11px",
    "border-width: 1mm 2mm",
    "border-width: 1mm 2mm 3mm",
    "border-width: 1mm 2mm 3mm 0",
    "border-width: thin medium thick 1mm",
    "border-top-width: 3mm",
    "border-right-width: thick",
    "border-bottom-width: 0",
    "border-left-width: 8pt",
    # border-style
    "border-style: none",
    "border-style: solid",
    "border-style: dashed",
    "border-style: dotted",
    "border-style: double",
    "border-style: solid dashed",
    "border-style: solid dashed dotted double",
    "border-top-style: solid",
    "border-right-style: none",
    "border-bottom-style: dotted",
    "border-left-style: double",
    # border-color
    "border-color: red",
    "border-color: #000 #111",
    "border-color: #000 #111 #222 #333",
    "border-color: rgba(0, 0, 0, 0.5)",
    "border-color: transparent",
    "border-top-color: red",
    "border-right-color: #abc",
    "border-bottom-color: hsl(0, 0%, 0%)",
    "border-left-color: #abcd",
    # border-radius: one to four lengths, 0–5 mm
    "border-radius: 5mm",
    "border-radius: 0",
    "border-radius: 14pt",
    "border-radius: 0.5cm",
    "border-radius: 0.19in",
    "border-radius: 18px",
    "border-radius: 1mm 2mm",
    "border-radius: 1mm 2mm 3mm 4mm",
    # border-collapse
    "border-collapse: collapse",
    "border-collapse: separate",
]


@pytest.mark.parametrize("declaration", PASSES_AT_THE_EDGE)
def test_a_value_within_its_rule_passes(declaration: str) -> None:
    assert check(rule("p", declaration)) == []


REFUSED_ONE_STEP_PAST = [
    # font-size
    "font-size: 5.9pt",
    "font-size: 72.1pt",
    "font-size: 7.9px",
    "font-size: 96.1px",
    "font-size: 0",
    "font-size: 0pt",
    "font-size: 1em",
    "font-size: 12mm",
    "font-size: 1cm",
    "font-size: 0.5in",
    "font-size: medium",
    "font-size: large",
    "font-size: smaller",
    "font-size: inherit",
    # font-weight
    "font-weight: 0",
    "font-weight: 50",
    "font-weight: 99",
    "font-weight: 150",
    "font-weight: 450",
    "font-weight: 901",
    "font-weight: 1000",
    "font-weight: bolder",
    "font-weight: lighter",
    "font-weight: 400.5",
    "font-weight: 400pt",
    # font-style, font-variant
    "font-style: oblique",
    "font-style: inherit",
    "font-variant: all-small-caps",
    "font-variant: petite-caps",
    # line-height
    "line-height: 0.99",
    "line-height: 3.01",
    "line-height: 0",
    "line-height: 1.5em",
    "line-height: 15pt",
    "line-height: 150%",
    "line-height: normal",
    "line-height: 1 2",
    # letter-spacing, word-spacing
    "letter-spacing: 5.1pt",
    "letter-spacing: 0.51em",
    "letter-spacing: 7px",
    "letter-spacing: 1.8mm",
    "letter-spacing: 0.18cm",
    "letter-spacing: 0.07in",
    "letter-spacing: 1pt 1pt",
    "letter-spacing: inherit",
    "word-spacing: 5.1pt",
    "word-spacing: 0.51em",
    "word-spacing: 1.8mm",
    "word-spacing: 7px",
    # text-decoration, text-transform
    "text-decoration: line-through",
    "text-decoration: overline",
    "text-decoration: underline red",
    "text-decoration: underline dotted",
    "text-decoration: none underline",
    "text-decoration: blink",
    "text-transform: full-width",
    "text-transform: uppercase lowercase",
    # text-indent
    "text-indent: 50.1mm",
    "text-indent: 4.1em",
    "text-indent: 5.1cm",
    "text-indent: 2in",
    "text-indent: 142pt",
    "text-indent: 190px",
    "text-indent: 1mm 2mm",
    "text-indent: 1mm hanging",
    # text-align, vertical-align
    "text-align: start",
    "text-align: end",
    "text-align: left right",
    "vertical-align: text-top",
    "vertical-align: text-bottom",
    "vertical-align: 2pt",
    "vertical-align: 10%",
    "vertical-align: 0",
    # color: fully opaque colours only
    "color: rgba(0, 0, 0, 0.99)",
    "color: rgba(0, 0, 0, 0)",
    "color: hsla(0, 0%, 0%, 0.5)",
    "color: #0008",
    "color: #00000080",
    "color: #000000fe",
    "color: transparent",
    "color: inherit",
    "color: initial",
    # `currentColor` is a keyword `parse_color` reads, not a colour; on `color` it is refused.
    "color: currentColor",
    "color: red blue",
    "color: #ggg",
    "color: #12345",
    "color: rgb(0 0 0)",
    "color: notacolour",
    "color: 123456",
    # background-color, background
    "background-color: red blue",
    "background-color: none",
    "background-color: inherit",
    "background: #fff none",
    "background: #fff #000",
    "background: none",
    "background: #fff no-repeat",
    "background: #fff center",
    "background: inherit",
    # margin, padding
    "margin: 50.1mm",
    "margin: 4.1em",
    "margin: 5.1cm",
    "margin: 2in",
    "margin: 142pt",
    "margin: 190px",
    "margin: 1mm 2mm 3mm 4mm 5mm",
    "margin: 1mm 51mm",
    "margin: 1mm 1mm 1mm 51mm",
    "margin: inherit",
    "margin: none",
    "margin-top: 50.1mm",
    "margin-right: 4.1em",
    "margin-bottom: 1mm 2mm",
    "margin-left: 2in",
    "padding: 50.1mm",
    "padding: 4.1em",
    "padding: auto",
    "padding: 0 auto",
    "padding: 1mm 2mm 3mm 4mm 5mm",
    "padding-top: 50.1mm",
    "padding-right: auto",
    "padding-bottom: 5.1cm",
    "padding-left: 2in",
    # border
    "border: 1mm 2mm",
    "border: 1mm 2mm solid",
    "border: solid dashed",
    "border: red blue",
    "border: 1mm solid #000 #fff",
    "border: 3.1mm solid",
    "border: 9pt",
    "border: 1mm groove",
    "border: 1mm inset",
    "border: 1mm ridge",
    "border: 1mm outset",
    "border: 1mm hidden",
    "border: 1em solid",
    "border: 1mm solid #000 solid",
    "border: inherit",
    "border-top: 3.1mm",
    "border-right: solid solid",
    "border-bottom: red red",
    "border-left: 1mm groove",
    # border-width
    "border-width: 3.1mm",
    "border-width: 9pt",
    "border-width: 0.31cm",
    "border-width: 0.12in",
    "border-width: 12px",
    "border-width: 1mm 2mm 3mm 4mm 1mm",
    "border-width: 1mm 3.1mm",
    "border-width: thin thin thin thin thin",
    "border-width: thinner",
    "border-width: none",
    "border-width: inherit",
    "border-top-width: 3.1mm",
    "border-right-width: 9pt",
    "border-bottom-width: 1mm 2mm",
    "border-left-width: 12px",
    # border-style
    "border-style: groove",
    "border-style: ridge",
    "border-style: inset",
    "border-style: outset",
    "border-style: hidden",
    "border-style: solid solid solid solid solid",
    "border-style: solid groove",
    "border-style: inherit",
    "border-top-style: groove",
    "border-right-style: solid solid",
    "border-bottom-style: 1mm",
    "border-left-style: ridge",
    # border-color
    "border-color: red #000 #111 #222 #333",
    "border-color: notacolour",
    "border-color: inherit",
    "border-color: #ggg",
    "border-top-color: red blue",
    "border-right-color: none",
    "border-bottom-color: 1mm",
    "border-left-color: solid",
    # border-radius
    "border-radius: 5.1mm",
    "border-radius: 15pt",
    "border-radius: 0.51cm",
    "border-radius: 0.2in",
    "border-radius: 19px",
    "border-radius: 1mm 2mm 3mm 4mm 5mm",
    "border-radius: 1mm 5.1mm",
    "border-radius: 1mm / 2mm",
    "border-radius: 50%",
    # border-collapse
    "border-collapse: inherit",
    "border-collapse: collapse separate",
    "border-collapse: none",
]


@pytest.mark.parametrize("declaration", REFUSED_ONE_STEP_PAST)
def test_a_value_outside_its_rule_is_refused(declaration: str) -> None:
    assert refused(rule("p", declaration)) == [(3, "value")]


@pytest.mark.parametrize(
    "declaration",
    [
        # `em` is not convertible to the row's millimetres, and the row names no em bound.
        "border-width: 1em",
        "border-width: 0.1em",
        "border-top-width: 1em",
        "border-radius: 1em",
        "border-radius: 0.1em",
        "border: 0.1em solid",
    ],
)
def test_em_is_refused_where_the_row_gives_a_bound_in_millimetres_only(declaration: str) -> None:
    assert refused(rule("p", declaration)) == [(3, "value")]


# --- Values: `@page` ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "declaration",
    [
        "size: A3",
        "size: A4",
        "size: A5",
        "size: letter",
        "size: legal",
        "size: A4 portrait",
        "size: A4 landscape",
        "size: letter landscape",
        "size: legal portrait",
        "margin: 12mm",
        "margin: 50mm",
        "margin: 1.2cm",
        "margin: 5cm",
        "margin: 0.48in",
        "margin: 1.9in",
        "margin: 35pt",
        "margin: 141pt",
        "margin: 12mm 50mm",
        "margin: 12mm 20mm 30mm",
        "margin: 12mm 20mm 30mm 50mm",
        "margin: 1.2cm 35pt 0.48in 12mm",
        "margin-top: 12mm",
        "margin-right: 50mm",
        "margin-bottom: 12mm",
        "margin-left: 1.9in",
        "SIZE: A4",
    ],
)
def test_a_page_value_within_its_rule_passes(declaration: str) -> None:
    assert check(page(declaration)) == []


@pytest.mark.parametrize(
    "declaration",
    [
        "size: B5",
        "size: A6",
        "size: 10mm",
        "size: 210mm 297mm",
        "size: A4 A4",
        "size: A4 portrait landscape",
        "size: landscape",
        "size: portrait",
        "size: auto",
        "size: A4 auto",
        "size: landscape A4",
        "margin: 11.9mm",
        "margin: 50.1mm",
        "margin: 0",
        "margin: 1.19cm",
        "margin: 5.1cm",
        "margin: 0.47in",
        "margin: 2in",
        "margin: 34pt",
        "margin: 142pt",
        "margin: 12mm 11.9mm",
        "margin: 12mm 12mm 12mm 50.1mm",
        "margin: 12mm 12mm 12mm 12mm 12mm",
        "margin: 12px",
        "margin: 46px",
        "margin: 1em",
        "margin: 4em",
        "margin: 10%",
        "margin: -20mm",
        "margin: 20",
        # a page margin is a length from 12 mm to 50 mm; `auto` is not one of them.
        "margin: auto",
        "margin: 12mm auto",
        "margin-top: 11.9mm",
        "margin-right: 50.1mm",
        "margin-bottom: 0",
        "margin-left: 12px",
        "margin-left: auto",
        "margin-bottom: 11mm",
    ],
)
def test_a_page_value_outside_its_rule_is_refused(declaration: str) -> None:
    assert refused(page(declaration)) == [(3, "value")]


def test_a_page_margin_at_the_general_bound_is_still_refused() -> None:
    """Zero passes for a paragraph's margin and fails for the page's."""
    assert check(rule("p", "margin: 0")) == []
    assert refused(page("margin: 0")) == [(3, "value")]
    assert check(rule("p", "margin: 4em")) == []
    assert refused(page("margin: 4em")) == [(3, "value")]


# --- The gutter is the platform's (DL-0363) ---------------------------------------------------


@pytest.mark.parametrize(
    "selector",
    [
        "body",
        "BODY",
        ".document-text",
        "div.document-text",
        ".num",
        "p.num",
        "span.num.entity",
        "h1, .num",
        "section .document-text",
        "body > .num",
        ".document-text p, body",
    ],
)
@pytest.mark.parametrize(
    "declaration",
    [
        "margin: 1mm",
        "margin: 0",
        "margin-top: 0",
        "margin-bottom: auto",
        "padding: 0",
        "padding-left: 1mm",
        "text-indent: 1mm",
        "text-indent: 0",
    ],
)
def test_spacing_on_the_gutters_elements_is_refused(selector: str, declaration: str) -> None:
    assert refused(rule(selector, declaration)) == [(3, "value")]


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(rule(".document-text p", "margin: 1mm"), id="descendant-of-document-text"),
        pytest.param(rule("body h1", "padding: 1mm"), id="descendant-of-body"),
        pytest.param(rule(".num span", "text-indent: 1mm"), id="descendant-of-num"),
        pytest.param(rule(".document-text > h1", "margin-left: 1mm"), id="child-of-document-text"),
        pytest.param(rule("body", "color: #000", "font-size: 11pt"), id="body-without-spacing"),
        # A clause number's size and spacing are the platform's (DL-0363); its colour is not.
        pytest.param(rule(".num", "color: #999"), id="num-without-spacing"),
        pytest.param(rule(".document-text", "line-height: 1.5"), id="document-text-line-height"),
        pytest.param(rule(".entity", "padding: 0 1mm"), id="another-class"),
    ],
)
def test_spacing_elsewhere_passes(text: str) -> None:
    assert check(text) == []


def test_spacing_on_the_gutter_is_refused_once_per_declaration() -> None:
    assert refused(rule("body", "margin: 1mm", "color: #000", "padding: 0")) == [
        (3, "value"),
        (5, "value"),
    ]


# --- The lines of a long sheet ------------------------------------------------------------------


def test_lines_are_counted_through_comments_and_blank_lines() -> None:
    text = (
        "/* a comment\n"
        "   over three lines\n"
        "*/\n"
        "\n"
        "p {\n"
        "  /* a comment before the declaration */\n"
        "\n"
        "  display: none;\n"
        "}\n"
        "\n"
        "\n"
        '@import "x.css";\n'
        "h1\n"
        "{\n"
        "  color: red !important;\n"
        "  font-family: Arial;\n"
        "  background: url(x.png);\n"
        "}\n"
    )
    assert refused(text) == [
        (8, "property"),
        (12, "at-rule"),
        (15, "value"),
        (16, "font"),
        (17, "fetches"),
    ]
    assert [(r.line, r.subject) for r in check(text) if r.code != "value"] == [
        (8, "display"),
        (12, "import"),
        (16, "arial"),
        (17, "background"),
    ]


def test_windows_line_ends_count_as_lines() -> None:
    assert refused("p {\r\n  color: #000;\r\n  display: none;\r\n}\r\n") == [(3, "property")]


SOURCES = ("rendering/renderer.py", "editing/diffview.py", "rendering/title_page.py",
           "rendering/export/compose.py")  # fmt: skip
# The values a class built from a placeholder can take, as the code fills it.
FILLED = {
    "entity-": ("entity-role", "entity-action", "entity-term"),
    "callout-": ("callout-note", "callout-warning", "callout-example"),
    "align-": ("align-left", "align-centre"),
}


def test_every_class_of_the_text_is_placed() -> None:
    """Every class the renderer, the diff, the title page and the export put on document text is
    one a stylesheet may name or one that stays the platform's: a class a later change adds fails
    here until it is placed."""
    import re
    from pathlib import Path

    from rendering.stylesheet import CLASSES, EXCLUDED

    source = Path(__file__).resolve().parents[2] / "src"
    found: set[str] = set()
    for name in SOURCES:
        text = (source / name).read_text(encoding="utf-8")
        for value in re.findall(r'class=\\?"([^"\\]*)', text):
            for word in value.split():
                if "{" not in word:
                    found.add(word)
                    continue
                prefix = word.split("{", 1)[0]
                if prefix:
                    found.update(FILLED.get(prefix, (word,)))
        # A class wholly from a placeholder is named where its helper is called: the title
        # page's details, the image pair's sides.
        found.update(re.findall(r'_detail\(\s*"([a-z-]+)"', text))
        found.update(re.findall(r'figure\(\w+, "([a-z-]+)"', text))

    assert found - CLASSES - EXCLUDED == set()
    assert {"num", "mention", "appendix", "imgpair", "approval", "title-page-text"} <= found


@pytest.mark.parametrize(
    "text",
    [
        "ul>li{color:#123}",
        "ul > li{color:#123}",
        "body > p, h1 { color: #123 }",
        "ul > li,\nh1 { color: #123 }",
        "@media print { ul>li{color:#123} }",
        "h1,ul>li{color:#123}",
    ],
)
def test_a_child_compound_against_a_comma_or_the_block_passes(text: str) -> None:
    """The prelude as written, with no white space before `,` or `{`: a child-joined compound is
    complete there, not a combinator left dangling."""
    from rendering.stylesheet import check

    assert check(text) == []


@pytest.mark.parametrize("text", ["ul > { color: #123 }", "ul >, h1 { color: #123 }", "> p {}"])
def test_a_dangling_child_combinator_is_refused(text: str) -> None:
    from rendering.stylesheet import check

    assert [r.code for r in check(text)] == ["selector"]


@pytest.mark.parametrize("opening", ["(", "rgb(", "[", "{"])
def test_a_value_nested_past_any_depth_is_refused_not_raised(opening: str) -> None:
    """Blocks nested a thousand deep are a refusal with their line, never an error."""
    from rendering.stylesheet import check

    found = check("h1 { color: #123 }\np { color: " + opening * 1_000 + " }\n")

    assert found and {r.line for r in found} == {2}


@pytest.mark.parametrize(
    "text",
    [
        ".num { font-size: 72pt }",
        ".document-text .num { letter-spacing: 2pt }",
        "span.num { word-spacing: 1pt }",
    ],
)
def test_the_clause_numbers_size_and_spacing_are_the_platforms(text: str) -> None:
    """The gutter is the platform's (DL-0363): a clause number set large or spread would lie over
    the text beside it."""
    from rendering.stylesheet import check

    assert [r.code for r in check(text)] == ["value"]

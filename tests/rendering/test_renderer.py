"""The reading view's renderer (ADR-0013) against its oracle: the golden HTML for every accept case
of the whitelist conformance list, byte for byte; the constructs of the conformance sample; and
what a text may never make of the page — raw HTML, a `javascript:` link, an image fetched, an
attribute value unescaped.

The golden files are written from the renderer's contract, never from its output
(`tests/fixtures/whitelist/golden/README.md`). Every text is invented; the roles named are
synthetic examples.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rendering.renderer import render

pytestmark = pytest.mark.fast

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CASES = FIXTURES / "whitelist" / "cases.json"
GOLDEN = FIXTURES / "whitelist" / "golden"
CONFORMANCE = FIXTURES / "render" / "conformance.md"

ACCEPT = {
    case["id"]: case["input"]
    for case in json.loads(CASES.read_text(encoding="utf-8"))
    if case["kind"] == "accept"
}


def body(text: str) -> str:
    """The text after its frontmatter, if it has one."""
    match = re.match(r"---\n.*?\n---\n", text, re.DOTALL)
    return text[match.end() :] if match else text


@pytest.mark.parametrize("case_id", sorted(ACCEPT))
def test_golden_html_for_every_accept_case(case_id: str) -> None:
    expected = (GOLDEN / f"{case_id}.html").read_bytes().decode("utf-8")

    assert render(ACCEPT[case_id]) == expected


def test_every_accept_case_has_a_golden_file_and_every_file_a_case() -> None:
    files = {path.stem for path in GOLDEN.glob("*.html")}

    assert sorted(set(ACCEPT) - files) == [], "accept cases without a golden file"
    assert sorted(files - set(ACCEPT)) == [], "golden files without an accept case"


def test_conformance_sample_constructs() -> None:
    source = body(CONFORMANCE.read_text(encoding="utf-8"))
    html = render(source)

    roles_with_id = re.findall(r"\]\{\.role #([A-Za-z0-9_-]+)\}", source)
    assert roles_with_id
    rendered_roles = re.findall(r'<span class="entity entity-role" data-id="([^"]*)">', html)
    assert rendered_roles == roles_with_id
    assert '<div class="callout callout-note">' in html
    for alignment in ("left", "center", "right"):
        assert f'<td style="text-align:{alignment}">' in html
        assert f'<th style="text-align:{alignment}">' in html
    assert "<br" not in html
    assert not re.search(r"\[[^\]]*\]\{\.", html)


def test_text_is_escaped() -> None:
    html = render("Сума a < b & c.\n")

    assert "a &lt; b &amp; c." in html


def test_raw_html_is_escaped_not_rendered() -> None:
    html = render(
        'Текст з <b>тегом</b> і <script>alert(1)</script>.\n\n<div onclick="alert(2)">Блок</div>\n'
    )

    assert "<b>" not in html and "<script" not in html and "<div onclick" not in html
    assert "&lt;b&gt;тегом&lt;/b&gt;" in html
    assert "&lt;script&gt;" in html
    assert "&lt;div onclick=&quot;alert(2)&quot;&gt;" in html


def test_javascript_link_is_not_a_link() -> None:
    html = render("[Натисніть тут](javascript:alert(1)) для синтетичного прикладу.\n")

    assert "<a" not in html
    assert "href" not in html


def test_a_link_opens_without_the_opener() -> None:
    html = render("Див. [синтетичний порядок](https://example.test/poriadok).\n")

    tags = re.findall(r"<a\b[^>]*>", html)
    assert tags == ['<a href="https://example.test/poriadok" rel="noopener noreferrer">']


def test_image_is_its_alt_text() -> None:
    html = render(
        "# План\n\n![План поверху](images/plan.png)\n\n![Схема & <b>](https://example.test/a.png)\n"
    )

    assert "<img" not in html
    assert "images/plan.png" not in html and "https://example.test/a.png" not in html
    assert "src" not in html
    assert "<p>План поверху</p>" in html
    assert "<p>Схема &amp; &lt;b&gt;</p>" in html


def test_attribute_values_are_escaped() -> None:
    # A callout type outside the whitelist still reaches the class attribute; it must not end it.
    html = render('> [!x"onmouseover="alert(1)]\n> Текст примітки.\n')

    assert 'onmouseover="' not in html
    assert '"onmouseover' not in html
    assert 'class="callout callout-x&quot;onmouseover=&quot;alert(1)"' in html
    for opening in re.findall(r"<[a-z]+\b[^>]*>", html):
        # Every tag is its name and quoted values alone: the text added no attribute.
        assert re.fullmatch(r'<[a-z0-9]+(?: [a-z-]+="[^"<>]*")*>', opening), opening


def test_span_attribute_values_are_escaped() -> None:
    # The recogniser admits only `[A-Za-z0-9_-]` in a span's type and id; a quote cannot reach
    # the attribute, so an attempt stays text or renders as a span without a kind of its own.
    html = render('Текст [слово]{.role #a"b} далі.\n')

    for opening in re.findall(r"<[a-z]+\b[^>]*>", html):
        assert re.fullmatch(r'<[a-z0-9]+(?: [a-z-]+="[^"<>]*")*>', opening), opening


def test_a_link_outside_the_whitelist_is_its_text() -> None:
    """The renderer holds the whitelist's link schemes itself, for text that reached the store
    another way: such a link reads as its words."""
    html = render(
        "Див. [схему](data:image/png;base64,AAAA) і [пошук](search-ms:query=x) та "
        "[правила](https://example.org/pravyla).\n"
    )

    assert "data:" not in html and "search-ms" not in html
    assert "схему" in html and "пошук" in html
    assert 'href="https://example.org/pravyla"' in html

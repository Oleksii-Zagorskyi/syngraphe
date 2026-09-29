"""The reading view's renderer (ADR-0013): a handful of golden cases — headings and
paragraphs numbered, a soft break read as a space, a list, a table, the entity and underline
spans, a callout — and what a text may never make of the page: raw HTML, a `javascript:` link, an
image fetched, an attribute value unescaped.

Newlines between tags are not part of the contract and are ignored in the comparison. Every text
is invented; the role *Бухгалтер* is a synthetic example.
"""

from __future__ import annotations

import re

import pytest

from rendering.renderer import render

pytestmark = pytest.mark.fast


def flat(html: str) -> str:
    """The HTML without the line breaks markdown-it writes between tags."""
    return re.sub(r">\n+<", "><", html.strip())


def num(label: str) -> str:
    return f'<span class="num">{label}</span> '


GOLDEN = [
    pytest.param(
        "# Загальні положення\n\n## Строки\n\nЗаяву розглядають за три дні.\n",
        f"<h1>{num('1')}Загальні положення</h1>"
        f"<h2>{num('1.1')}Строки</h2>"
        f"<p>{num('1.1-1')}Заяву розглядають за три дні.</p>",
        id="headings",
    ),
    pytest.param(
        "# Порядок\n\nПерше речення абзацу.\nДруге речення абзацу.\n",
        f"<h1>{num('1')}Порядок</h1><p>{num('1-1')}Перше речення абзацу. Друге речення абзацу.</p>",
        id="softbreak",
    ),
    pytest.param(
        "Вступне речення.\n\n- перший пункт;\n- другий пункт.\n",
        f"<p>{num('1')}Вступне речення.</p>"
        f"<ul><li>{num('2')}перший пункт;</li><li>{num('3')}другий пункт.</li></ul>",
        id="list",
    ),
    pytest.param(
        "# Строки\n\n| Вид заявки | Строк |\n|---|---|\n| Звичайна | три дні |\n",
        f"<h1>{num('1')}Строки</h1>"
        "<table><thead><tr><th>Вид заявки</th><th>Строк</th></tr></thead>"
        "<tbody><tr><td>Звичайна</td><td>три дні</td></tr></tbody></table>",
        id="table",
    ),
    pytest.param(
        "Заяву погоджує [Бухгалтер]{.role #r1}, а [строк]{.term} рахують [щодня]{.underline}.\n",
        f"<p>{num('1')}Заяву погоджує "
        '<span class="entity entity-role" data-id="r1">Бухгалтер</span>, а '
        '<span class="entity entity-term">строк</span> рахують '
        '<span class="underline">щодня</span>.</p>',
        id="spans",
    ),
    pytest.param(
        "> [!note]\n> Примітка до порядку.\n",
        f'<div class="callout callout-note"><p>{num("1")}Примітка до порядку.</p></div>',
        id="callout",
    ),
]


@pytest.mark.parametrize(("source", "expected"), GOLDEN)
def test_golden(source: str, expected: str) -> None:
    assert flat(render(source)) == expected


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


def test_javascript_link_is_not_a_link() -> None:
    html = render("[Натисніть тут](javascript:alert(1)) для синтетичного прикладу.\n")

    assert "<a" not in html
    assert "href" not in html


def test_a_link_opens_without_the_opener() -> None:
    html = render("Див. [синтетичний порядок](https://example.test/poriadok).\n")

    tags = re.findall(r"<a\b[^>]*>", html)
    assert len(tags) == 1
    assert 'href="https://example.test/poriadok"' in tags[0]
    assert 'rel="noopener noreferrer"' in tags[0]


def test_image_is_its_alt_text() -> None:
    html = render(
        "# План\n\n![План поверху](images/plan.png)\n\n![Схема & <b>](https://example.test/a.png)\n"
    )

    assert "<img" not in html
    assert "images/plan.png" not in html and "https://example.test/a.png" not in html
    assert "План поверху" in html
    assert "Схема &amp; &lt;b&gt;" in html


def test_attribute_values_are_escaped() -> None:
    # A callout type outside the whitelist still reaches the class attribute; it must not end it.
    html = render('> [!x"onmouseover="alert(1)]\n> Текст примітки.\n')

    assert 'onmouseover="' not in html
    assert '"onmouseover' not in html
    for opening in re.findall(r"<[a-z]+\b[^>]*>", html):
        # Every tag is its name and quoted values alone: the text added no attribute.
        assert re.fullmatch(r'<[a-z0-9]+(?: [a-z-]+="[^"<>]*")*>', opening), opening

"""The files of a document's bundle: `document.md`'s frontmatter, the passport's header and the
initial tree (ADR-0005)."""

from __future__ import annotations

import pytest

from documents import bundle
from documents.bundle import Frontmatter

pytestmark = pytest.mark.fast

TWO_APPENDICES = """---
title: "Порядок ведення реєстру (синтетичний приклад)"
language: "uk"
title_page: true
appendices:
  - number: 1
    title: "Форма запиту"
  - number: 3
    title: "Перелік \\"умов\\""
attachments:
  - number: 1
    title: "Схема"
    file_name: "scheme.pdf"
    sha256: "0000000000000000000000000000000000000000000000000000000000000000"
    bytes: 2048
---

# Загальні положення

Текст.
"""


def test_frontmatter_round_trips() -> None:
    frontmatter, body = bundle.parse(TWO_APPENDICES)

    assert frontmatter.title == "Порядок ведення реєстру (синтетичний приклад)"
    assert [a["number"] for a in frontmatter.appendices] == [1, 3]
    assert frontmatter.attachments[0]["bytes"] == 2048
    assert bundle.render(frontmatter, body) == TWO_APPENDICES


def test_empty_lists_round_trip() -> None:
    text = bundle.render(Frontmatter(title="T", language="en"), "# A\n")

    assert text == (
        '---\ntitle: "T"\nlanguage: "en"\ntitle_page: false\nappendices: []\n'
        "attachments: []\n---\n\n# A\n"
    )
    assert bundle.render(*bundle.parse(text)) == text


@pytest.mark.parametrize(
    "text",
    [
        "no frontmatter\n",
        "---\ntitle: T\n",
        "---\n- a list\n---\n",
        '---\ntitle: "T"\nlanguage: "uk"\nextra: 1\n---\n',
        "---\n!!python/object:os.system {}\n---\n",
    ],
)
def test_parse_refuses_what_is_not_a_frontmatter(text: str) -> None:
    with pytest.raises(ValueError):
        bundle.parse(text)


def test_passport_header_carries_numbers_only() -> None:
    assert bundle.passport_header(tenant=3, document=12) == "---\ndocument: 12\ntenant: 3\n---\n"


def test_initial_tree() -> None:
    tree = bundle.initial_tree(
        tenant=3,
        document=12,
        title="Синтетичний приклад",
        language="uk",
        title_page=False,
        outline="# Загальні положення\n",
    )

    assert set(tree) == {"document.md", "passport.md", "entities.yaml"}
    frontmatter, body = bundle.parse(tree["document.md"].decode("utf-8"))
    assert frontmatter == Frontmatter(title="Синтетичний приклад", language="uk")
    assert body == "# Загальні положення\n"
    assert tree["passport.md"].decode() == bundle.passport_header(tenant=3, document=12)
    assert tree["entities.yaml"] == b"[]\n"


@pytest.mark.parametrize("name", ["two-sections-ukr", "two-sections-eng", "with-parts-ukr"])
def test_the_flow_documents_round_trip(name: str) -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "fixtures" / "documents" / name / "document.md"
    text = path.read_text(encoding="utf-8")

    assert bundle.render(*bundle.parse(text)) == text


@pytest.mark.parametrize(
    "title",
    ["a\x7fb", "a\x85b", "a\x9fb", "a￾b", "a b", "a b", 'а "б" \\ в', "yes", "1.0"],
)
def test_any_title_the_form_takes_or_yaml_fears_round_trips(title: str) -> None:
    text = bundle.render(Frontmatter(title=title, language="uk"), "# A\n")

    try:
        frontmatter, body = bundle.parse(text)
    except ValueError:
        # Refused as a title, never misread: the form refuses the same titles.
        assert not bundle.valid_title(title)
        return
    assert frontmatter.title == title
    assert bundle.render(frontmatter, body) == text


def test_every_code_point_is_written_so_it_reads_back() -> None:
    for code in range(0x20, 0x3000):
        if 0xD800 <= code <= 0xDFFF:
            continue
        title = f"a{chr(code)}b"
        text = bundle.render(Frontmatter(title="T", language="uk", appendices=[]), "")
        text = text.replace('"T"', bundle._string(title))
        if bundle.valid_title(title):
            assert bundle.parse(text)[0].title == title, hex(code)


@pytest.mark.parametrize(
    "attachment",
    [
        {"number": 1, "title": "A", "file_name": None, "sha256": "0" * 64, "bytes": 1},
        {"number": 1, "title": "A", "file_name": "a", "sha256": "0012", "bytes": 1},
        {"number": 1, "title": "A", "file_name": "a", "sha256": "0" * 64, "bytes": -5},
        {"number": 2**31, "title": "A", "file_name": "a", "sha256": "0" * 64, "bytes": 1},
    ],
)
def test_parse_refuses_a_malformed_attachment(attachment: dict[str, object]) -> None:
    lines = "\n".join(
        f"    {k}: {v!r}" if k != "number" else f"  - number: {v}" for k, v in attachment.items()
    )
    text = f'---\ntitle: "T"\nlanguage: "uk"\nattachments:\n{lines}\n---\n'
    text = text.replace("'", '"').replace("None", "null")

    with pytest.raises(ValueError):
        bundle.parse(text)


def test_parse_refuses_a_repeated_key_and_an_empty_language() -> None:
    with pytest.raises(ValueError):
        bundle.parse('---\ntitle: "T"\ntitle: "U"\nlanguage: "uk"\n---\n')
    with pytest.raises(ValueError):
        bundle.parse('---\ntitle: "T"\nlanguage: ""\n---\n')

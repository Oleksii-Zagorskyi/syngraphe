"""Clause numbers for the reading view (DL-0065, DL-0327, DL-0330). The sequences are the shared
oracle in `tests/fixtures/render/numbering-cases.json`, which the editor's gutter meets too
(`tests/editing/browser/test_gutter_matches_renderer.py`); the tests below it check what a
sequence cannot show — which token a label sits on and which text it names.

Every text is invented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from editing.markdown.parser import parser
from rendering.numbering import labels

pytestmark = pytest.mark.fast

CASES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "render" / "numbering-cases.json"
CASES: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))


def sequence(text: str) -> list[str]:
    """The labels of `text` in ascending token index: its document-order sequence."""
    found = labels(parser().parse(text))
    return [found[index] for index in sorted(found)]


def numbered(text: str) -> list[tuple[str, str]]:
    """`(label, text)` for every labelled token in document order: the text is the inline
    content the heading or paragraph opens on. Asserts that only headings and paragraphs are
    labelled, each keyed by its opening token's index."""
    tokens = parser().parse(text)
    found = labels(tokens)
    for index in found:
        assert tokens[index].type in ("heading_open", "paragraph_open"), tokens[index].type
    return [(found[index], tokens[index + 1].content) for index in sorted(found)]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_labels(case: dict[str, Any]) -> None:
    assert sequence(case["input"]) == case["labels"]


def test_every_case_is_labelled_on_headings_and_paragraphs() -> None:
    for case in CASES:
        numbered(case["input"])


def test_headings_carry_their_path() -> None:
    text = (
        "# Загальні положення\n\n"
        "## Сфера застосування\n\n"
        "## Терміни\n\n"
        "### Основні терміни\n\n"
        "# Відповідальність\n\n"
        "## Керівник\n"
    )

    assert numbered(text) == [
        ("1", "Загальні положення"),
        ("1.1", "Сфера застосування"),
        ("1.2", "Терміни"),
        ("1.2.1", "Основні терміни"),
        ("2", "Відповідальність"),
        ("2.1", "Керівник"),
    ]


def test_skipped_level_is_filled_with_one() -> None:
    text = "# Порядок\n\n### Строки\n\nЗаяву розглядають за три дні.\n\n## Винятки\n"

    assert numbered(text) == [
        ("1", "Порядок"),
        ("1.1.1", "Строки"),
        ("1.1.1-1", "Заяву розглядають за три дні."),
        # The filled `1` counts as the second level's first heading, so no number repeats.
        ("1.2", "Винятки"),
    ]


def test_before_the_first_heading_the_index_alone() -> None:
    text = "Вступне речення.\n\nЩе одне вступне речення.\n\n# Розділ\n\nТекст розділу.\n"

    assert numbered(text) == [
        ("1", "Вступне речення."),
        ("2", "Ще одне вступне речення."),
        ("1", "Розділ"),
        ("1-1", "Текст розділу."),
    ]


def test_list_quote_and_callout_paragraphs_carry_their_own_text() -> None:
    text = (
        "# Порядок\n\n"
        "- перший пункт;\n  - підпункт першого пункту;\n\n"
        "> Цитата з синтетичного наказу.\n\n"
        "> [!note]\n> Примітка до порядку.\n"
    )

    assert numbered(text) == [
        ("1", "Порядок"),
        ("1-1", "перший пункт;"),
        ("1-2", "підпункт першого пункту;"),
        ("1-3", "Цитата з синтетичного наказу."),
        ("1-4", "Примітка до порядку."),
    ]


def test_table_cells_and_image_paragraphs_are_not_labelled() -> None:
    text = (
        "# Строки\n\n"
        "Строки наведено в таблиці.\n\n"
        "| Вид заявки | Строк |\n| --- | --- |\n| звичайна | десять днів |\n\n"
        "![Схема](images/skhema.png)\n\n"
        "Строк рахують від дня надходження.\n"
    )

    assert numbered(text) == [
        ("1", "Строки"),
        ("1-1", "Строки наведено в таблиці."),
        ("1-2", "Строк рахують від дня надходження."),
    ]


def test_nothing_to_number() -> None:
    assert labels(parser().parse("")) == {}

"""Clause numbers for the reading view, the twin of the editor's gutter (DL-0065;
`src/editing/js/gutter.js::clauseNumbers`): a heading carries its path, a skipped level filled
with `1`; every paragraph outside a table — in lists, tight or loose, in quotes and callouts —
takes the next index of its section, `PATH-INDEX`, or `INDEX` alone before the first heading.

Every text is invented.
"""

from __future__ import annotations

import pytest

from editing.markdown.parser import parser
from rendering.numbering import labels

pytestmark = pytest.mark.fast


def numbered(text: str) -> list[tuple[str, str]]:
    """`(label, text)` for every labelled token in document order: the text is the inline
    content the heading or paragraph opens on. Asserts that only headings and paragraphs are
    labelled, each keyed by its opening token's index."""
    tokens = parser().parse(text)
    found = labels(tokens)
    for index in found:
        assert tokens[index].type in ("heading_open", "paragraph_open"), tokens[index].type
    return [(found[index], tokens[index + 1].content) for index in sorted(found)]


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
        # The filled `1` counts as the second level's first heading, as the gutter counts it.
        ("1.2", "Винятки"),
    ]


def test_a_first_heading_below_the_top_level() -> None:
    assert numbered("### Примітка\n\nТекст примітки.\n") == [
        ("1.1.1", "Примітка"),
        ("1.1.1-1", "Текст примітки."),
    ]


def test_paragraphs_count_within_their_section() -> None:
    text = (
        "# Загальні положення\n\n"
        "Перше речення розділу.\n\n"
        "Друге речення розділу.\n\n"
        "## Строки\n\n"
        "Строк становить десять днів.\n\n"
        "# Відповідальність\n\n"
        "Керівник погоджує заявку.\n"
    )

    assert numbered(text) == [
        ("1", "Загальні положення"),
        ("1-1", "Перше речення розділу."),
        ("1-2", "Друге речення розділу."),
        # The index resets after every heading, whatever its level.
        ("1.1", "Строки"),
        ("1.1-1", "Строк становить десять днів."),
        ("2", "Відповідальність"),
        ("2-1", "Керівник погоджує заявку."),
    ]


def test_before_the_first_heading_the_index_alone() -> None:
    text = "Вступне речення.\n\nЩе одне вступне речення.\n\n# Розділ\n\nТекст розділу.\n"

    assert numbered(text) == [
        ("1", "Вступне речення."),
        ("2", "Ще одне вступне речення."),
        ("1", "Розділ"),
        ("1-1", "Текст розділу."),
    ]


def test_tight_list_items_are_counted() -> None:
    text = "# Порядок\n\nЗаява містить:\n\n- прізвище заявника;\n- підрозділ заявника.\n"

    assert numbered(text) == [
        ("1", "Порядок"),
        ("1-1", "Заява містить:"),
        ("1-2", "прізвище заявника;"),
        ("1-3", "підрозділ заявника."),
    ]


def test_loose_and_ordered_list_items_are_counted() -> None:
    text = (
        "# Порядок\n\n"
        "1. Заявник подає заяву.\n\n"
        "2. Керівник погоджує заяву.\n\n"
        "   Погодження фіксують у реєстрі.\n\n"
        "Після погодження заяву передають далі.\n"
    )

    assert numbered(text) == [
        ("1", "Порядок"),
        ("1-1", "Заявник подає заяву."),
        ("1-2", "Керівник погоджує заяву."),
        ("1-3", "Погодження фіксують у реєстрі."),
        ("1-4", "Після погодження заяву передають далі."),
    ]


def test_nested_list_items_are_counted() -> None:
    text = "# Порядок\n\n- перший пункт;\n  - підпункт першого пункту;\n- другий пункт.\n"

    assert [label for label, _ in numbered(text)] == ["1", "1-1", "1-2", "1-3"]


def test_quote_and_callout_paragraphs_are_counted() -> None:
    text = (
        "# Порядок\n\n"
        "> Цитата з синтетичного наказу.\n>\n> Друге речення цитати.\n\n"
        "> [!note]\n> Примітка до порядку.\n\n"
        "Текст після примітки.\n"
    )

    assert numbered(text) == [
        ("1", "Порядок"),
        ("1-1", "Цитата з синтетичного наказу."),
        ("1-2", "Друге речення цитати."),
        ("1-3", "Примітка до порядку."),
        ("1-4", "Текст після примітки."),
    ]


def test_table_cells_are_not_clauses() -> None:
    text = (
        "# Строки\n\n"
        "Строки наведено в таблиці.\n\n"
        "| Вид заявки | Строк |\n|---|---|\n| Звичайна | десять днів |\n\n"
        "Строк рахують від дня надходження.\n"
    )

    assert numbered(text) == [
        ("1", "Строки"),
        ("1-1", "Строки наведено в таблиці."),
        ("1-2", "Строк рахують від дня надходження."),
    ]


def test_nothing_to_number() -> None:
    assert labels(parser().parse("")) == {}

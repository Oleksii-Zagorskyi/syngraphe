"""The validator names each construct outside the whitelist and its line (ADR-0010, DL-0171)."""

from __future__ import annotations

import time

import pytest

from editing.markdown import load_spec
from editing.markdown.validator import Refusal, validate

pytestmark = pytest.mark.fast


def codes(text: str) -> list[tuple[str, int]]:
    return [(r.code, r.line) for r in validate(text)]


def test_refusals_name_construct_and_line() -> None:
    text = (
        "# Порядок погодження\n"
        "\n"
        "<script>alert(1)</script>\n"
        "\n"
        "![схема](https://example.test/схема.png)\n"
        "\n"
        "[посилання](javascript:alert(1))\n"
        "\n"
        "##### Надто глибоко\n"
        "\n"
        "- пункт\n"
        "\n"
        "  | a | b |\n"
        "  | --- | --- |\n"
        "  | 1 | 2 |\n"
        "\n"
        "Речення перед зображенням. ![схема](images/schema.png)\n"
    )
    assert codes(text) == [
        ("html", 3),
        ("image-src", 5),
        ("link-scheme", 7),
        ("heading-depth", 9),
        ("table-nested", 13),
        ("image-inline", 17),
    ]


def test_constructs_easily_misread() -> None:
    assert validate("[[Відповідальний]{.role}](https://example.test/r)\n") == []
    assert validate("0. нульовий\n1. перший\n") == []
    assert codes('[посилання](https://example.test "підказка")\n') == [("title", 1)]
    assert codes("[[вкладена]{.role}]{.term}\n") == [("span-nested", 1)]
    assert codes("[]{.term}\n") == [("span-empty", 1)]
    assert codes("| a | b |\n| --- | --- |\n| 1 | 2 | 3 |\n") == [("table-row-cells", 3)]


def test_refusals_sort_by_line_then_code() -> None:
    assert validate("##### Глибоко `код`\n") == [
        Refusal(1, "heading-depth"),
        Refusal(1, "inline-code"),
    ]


@pytest.mark.budget
def test_a_long_run_of_labels_costs_linear_time() -> None:
    """A text of a hundred thousand characters that opens a span label at every fourth is checked
    in seconds at most, not in the minute and more a scan of the rest of the text at each takes."""
    started = time.perf_counter()
    validate("[a]{" * 25000)
    assert time.perf_counter() - started < 5.0


def test_a_text_over_the_size_is_refused_unread() -> None:
    limit = load_spec().max_bytes
    assert validate("а" * (limit // 2)) == []
    assert validate("а" * (limit // 2 + 1)) == [Refusal(1, "too-large")]

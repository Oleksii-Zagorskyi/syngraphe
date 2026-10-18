"""The validator names each construct outside the whitelist and its line (ADR-0010, DL-0171)."""

from __future__ import annotations

from typing import Any

import pytest

from editing.markdown import load_spec
from editing.markdown.validator import Refusal, validate

pytestmark = pytest.mark.fast


def codes(text: str) -> list[tuple[str, int]]:
    return [(r.code, r.line) for r in validate(text)]


def test_refusals_name_construct_and_line() -> None:
    text = (
        "# Approval procedure\n"
        "\n"
        "<script>alert(1)</script>\n"
        "\n"
        "![scheme](https://example.test/scheme.png)\n"
        "\n"
        "[link](javascript:alert(1))\n"
        "\n"
        "##### Too deep\n"
        "\n"
        "- item\n"
        "\n"
        "  | a | b |\n"
        "  | --- | --- |\n"
        "  | 1 | 2 |\n"
        "\n"
        "A sentence before an image. ![scheme](images/schema.png)\n"
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
    assert validate("[[Responsible]{.role}](https://example.test/r)\n") == []
    assert validate("0. zeroth\n1. first\n") == []
    assert codes('[link](https://example.test "hint")\n') == [("title", 1)]
    assert codes("[[nested]{.role}]{.term}\n") == [("span-nested", 1)]
    assert codes("[]{.term}\n") == [("span-empty", 1)]
    assert codes("| a | b |\n| --- | --- |\n| 1 | 2 | 3 |\n") == [("table-row-cells", 3)]


def test_refusals_sort_by_line_then_code() -> None:
    assert validate("##### Deep `code`\n") == [
        Refusal(1, "heading-depth"),
        Refusal(1, "inline-code"),
    ]


@pytest.mark.budget
def test_a_long_run_of_labels_costs_linear_time(grows_linearly: Any) -> None:
    """A text that opens a span label at every fourth character: each label read where it stands,
    never by a scan of the rest of the text."""
    # Up to 50,000 characters: past them the parser's own inline pass grows a little faster
    # than its input, which is the library's, not the validator's.
    grows_linearly(lambda n: "[a]{" * n, validate, 3_125)


def test_a_text_over_the_size_is_refused_unread() -> None:
    limit = load_spec().max_bytes
    assert validate("а" * (limit // 2)) == []
    assert validate("а" * (limit // 2 + 1)) == [Refusal(1, "too-large")]

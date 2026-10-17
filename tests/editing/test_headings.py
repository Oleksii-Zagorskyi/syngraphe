"""A heading's own number, written by its author or left by a Markdown export (DL-0363), is
stripped where it equals the number the outline gives the heading (DL-0441): the number is
derived, never stored. Any other heading and every other line are left. Invented text."""

from __future__ import annotations

import pytest

from editing.normalizer.headings import strip_own_numbers

pytestmark = pytest.mark.fast


def test_a_headings_own_number_is_stripped() -> None:
    text = (
        "# 1. Purpose\n\nA sentence 1 stays.\n\n# Two\n\n## 2.1 Scope\n\n"
        "## 2.2\tLimits\n\n# 4 Terms\n\n# 4\n"
    )

    assert strip_own_numbers(text) == (
        "# Purpose\n\nA sentence 1 stays.\n\n# Two\n\n## Scope\n\n## Limits\n\n# 4 Terms\n\n# 4\n"
    )


def test_a_heading_without_its_number_is_unchanged() -> None:
    text = "# Purpose\n\n## 1.1.1 Deeper than its label\n"

    assert strip_own_numbers(text) == text


def test_line_breaks_of_every_kind_keep_each_heading_its_own() -> None:
    """A lone carriage return breaks a line as markdown-it reads it: each heading keeps its own
    line, and every break comes back as it was."""
    text = "Intro.\r\r# 1 Alpha\r\n\r\n# 2 Beta\n\n#  3 Gamma\n"

    assert strip_own_numbers(text) == "Intro.\r\r# Alpha\r\n\r\n# Beta\n\n#  Gamma\n"

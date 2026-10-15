"""The heading reader behind the heading cache: ATX headings, four levels, outside the frontmatter
and fenced code, lines counted as git counts them."""

from __future__ import annotations

import pytest

from documents.caches import headings

pytestmark = pytest.mark.fast


def test_headings_and_their_lines() -> None:
    text = "---\ntitle: T\n---\n\n# One\n\ntext\n\n## Two ##\n\n#### Four\n\n##### Five\n"

    assert headings(text) == [(1, "One", 5), (2, "Two", 9), (4, "Four", 11)]


def test_fences_close_only_on_their_own_kind() -> None:
    text = "```\n~~~\n# inside\n```\n# after\n"

    assert headings(text) == [(1, "after", 5)]


def test_empty_headings_are_not_headings() -> None:
    assert headings("# #\n### ###\n#\n") == []


def test_lines_are_counted_at_line_feeds_only() -> None:
    assert headings("﻿# First\r\nLine more\n# H\n") == [(1, "First", 1), (1, "H", 3)]


def test_a_heading_reads_as_its_reader_reads_it() -> None:
    """Marks and spans leave their words, never their syntax (the role is a synthetic example)."""
    text = "## The [Accountant]{.role #b} report for **Q1**\n\n### Time limits\n"

    assert headings(text) == [(2, "The Accountant report for Q1", 1), (3, "Time limits", 3)]

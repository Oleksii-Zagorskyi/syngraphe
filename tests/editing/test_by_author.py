"""Each line of a past version named by its edit author (DL-0040, DL-0489): a block whose lines
share one author carries the name; a paragraph whose sentences have several carries it on each
sentence. The names and the text are invented."""

from __future__ import annotations

import re

import pytest

from editing.past_authors import by_author
from rendering.renderer import labelled, render_tokens

pytestmark = pytest.mark.fast


def named(html: str) -> list[tuple[str, str]]:
    return re.findall(r'data-author="([^"]+)"[^>]*>(.*?)</', html)


def test_one_author_names_the_block() -> None:
    tokens = labelled("First sentence.\nSecond sentence.\n")
    by_author(tokens, {0: "Author A", 1: "Author A"})

    html = render_tokens(tokens)

    assert html.startswith('<p data-author="Author A" title="Author A" class="by">')
    assert html.count("data-author") == 1


def test_two_authors_in_one_paragraph_name_each_sentence() -> None:
    tokens = labelled("First sentence.\nSecond *sentence*.\n")
    by_author(tokens, {0: "Author A", 1: "Author B"})

    html = render_tokens(tokens)

    assert named(html) == [("Author A", "First sentence."), ("Author B", "Second <em>sentence")]
    # The clause's number stays first, outside every name, and the paragraph keeps its anchor.
    assert re.match(r'<p[^>]*><span class="num">1</span> <span data-author="Author A"', html)


def test_an_unnamed_line_beside_named_ones_is_left_bare() -> None:
    tokens = labelled("First sentence.\nSecond sentence.\nThird sentence.\n")
    by_author(tokens, {0: "Author A", 2: "Author B"})

    html = render_tokens(tokens)

    assert [name for name, _ in named(html)] == ["Author A", "Author B"]
    assert " Second sentence. " in html


def test_a_mark_across_two_lines_keeps_the_text_whole() -> None:
    """Emphasis running from one sentence into the next cannot be divided by line: the paragraph
    is drawn without names rather than with broken markup."""
    tokens = labelled("First *sentence.\nSecond* sentence.\n")
    by_author(tokens, {0: "Author A", 1: "Author B"})

    html = render_tokens(tokens)

    assert "data-author" not in html
    assert "<em>sentence. Second</em>" in html


def test_only_a_changed_block_is_named() -> None:
    """Against the version before, a paragraph none of whose lines changed names nobody: no
    change, no change author (DL-0504)."""
    tokens = labelled("First sentence.\n\nSecond paragraph.\nIts second sentence.\n")
    authors = {0: "Author A", 2: "Author B", 3: "Author B"}
    by_author(tokens, authors, changed={3})

    html = render_tokens(tokens)

    assert [n for n, _ in named(html)] == ["Author B"]
    assert 'data-author="Author A"' not in html
    assert html.count('class="by"') == 1


def test_the_first_version_names_every_block() -> None:
    """With nothing before it within the reader's reach, every block is named."""
    tokens = labelled("First sentence.\n\nSecond paragraph.\n")
    by_author(tokens, {0: "Author A", 2: "Author B"}, changed=None)

    html = render_tokens(tokens)

    assert [n for n, _ in named(html)] == ["Author A", "Author B"]

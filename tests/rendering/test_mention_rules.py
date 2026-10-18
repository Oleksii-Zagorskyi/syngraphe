"""The mention's own rules, with no database: the words and line `targets` reads, and the
renderer holding the whitelist's mention rules itself for text that reached the store another way
— a number the pattern refuses never links, nor a mention inside another (DL-0436). Text is
invented."""

from __future__ import annotations

from typing import Any

import pytest

from rendering import mentions
from rendering.renderer import RenderContext, render

pytestmark = pytest.mark.fast

READER = RenderContext(reachable=frozenset({2, 12}))


def test_words_read_as_a_reader_reads_them() -> None:
    body = (
        "First line.\nSee [the payment\nrules]{.document #2} and "
        "[the `form` rules]{.document #12}.\n"
    )

    found = mentions.targets(body)

    assert [(m.number, m.words) for m in found] == [
        (2, "the payment rules"),
        (12, "the form rules"),
    ]
    # The line every refusal names: the first of the block holding it.
    assert {m.line for m in found} == {1}


def test_a_number_the_pattern_refuses_never_links() -> None:
    for refused in ("012", "00000000000000000002", "12a"):
        html = render(f"See [the rules]{{.document #{refused}}}.\n", context=READER)
        assert 'class="mention"' not in html, refused
        assert "See the rules." in html, refused


def test_a_mention_inside_a_mention_never_nests_an_anchor() -> None:
    html = render("[[inner]{.document #2} outer]{.document #12}\n", context=READER)

    assert html.count("<a ") == 1 and html.count("</a>") == 1
    assert '<a class="mention" href="/document/12/">inner outer</a>' in html


@pytest.mark.budget
def test_targets_reads_a_paragraph_of_mentions_in_linear_time(grows_linearly: Any) -> None:
    """A paragraph up to the size limit holding mentions alone costs about its length, not its
    square."""

    def body(n: int) -> str:
        return " ".join(f"[w]{{.document #{k % 9 + 1}}}" for k in range(n)) + "\n"

    counted: list[int] = []
    grows_linearly(body, lambda text: counted.append(len(mentions.targets(text))), 5_000)
    assert counted[-1] == 20_000


def test_mentions_are_listed_where_they_open() -> None:
    """The order of first mention is where each opens, nested ones included."""
    found = mentions.targets("A [outer [inner]{.document #3}]{.document #2}.\n")

    assert [m.number for m in found] == [2, 3]

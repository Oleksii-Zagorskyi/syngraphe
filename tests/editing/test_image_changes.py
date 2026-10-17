"""An image changed, drawn before and after (ST-0034, DL-0059, DL-0439, DL-11-002): a replaced
image is its paragraph flagged *image changed* above the pair; one added is inserted whole, one
removed struck whole; the same image with a new description a change of words. With no reader's
context every image is its description. Image names are placeholders; text invented."""

from __future__ import annotations

import re

import pytest

from editing.diffview import render_changes
from rendering.renderer import RenderContext

pytestmark = pytest.mark.fast

OLD = "images/" + "a" * 64 + ".png"
NEW = "images/" + "b" * 64 + ".png"
CONTEXT = RenderContext(image_url=lambda src: f"/shown/{src[7:]}/", sides=("0.1", "0.1-1"))
TEXT = "A first sentence.\n"


def changes(old: str, new: str, context: RenderContext | None = CONTEXT) -> str:
    from django.utils import translation

    with translation.override("en"):
        return render_changes(old.encode(), new.encode(), context=context)


def test_a_replaced_image_is_a_pair() -> None:
    html = changes(TEXT + f"\n![The old plan]({OLD})\n", TEXT + f"\n![The new plan]({NEW})\n")

    assert html.count('<div class="imgpair">') == 1
    pair = html[html.index('<div class="imgpair">') :]
    assert f'<img src="/shown/{OLD[7:]}/" alt="The old plan">' in pair
    assert f'<img src="/shown/{NEW[7:]}/" alt="The new plan">' in pair
    assert '<figure class="before">' in pair and '<figure class="after">' in pair
    assert "<figcaption>before · 0.1 — The old plan</figcaption>" in pair
    assert "<figcaption>after · 0.1-1 — The new plan</figcaption>" in pair
    assert "<details" in pair and "open both full size" in pair
    # The flag stands alone on the row, no number, and the pair stands outside the paragraph.
    assert re.search(
        r'<p><span class="image-changed">image changed</span></p>\s*<div class="imgpair">', html
    )
    assert "<del>" not in html and "<ins>" not in html


def test_an_image_added_or_removed_is_whole() -> None:
    added = changes(TEXT, TEXT + f"\n![A plan]({NEW})\n")
    removed = changes(TEXT + f"\n![A plan]({OLD})\n", TEXT)

    assert f'<ins><img src="/shown/{NEW[7:]}/" alt="A plan"></ins>' in added
    assert f'<del><img src="/shown/{OLD[7:]}/" alt="A plan"></del>' in removed
    assert "imgpair" not in added + removed


def test_a_new_description_is_a_change_of_words() -> None:
    html = changes(TEXT + f"\n![The old plan]({OLD})\n", TEXT + f"\n![The new plan]({OLD})\n")

    assert "imgpair" not in html
    assert html.count("<img") == 1
    assert "<del>The old plan</del>" in html and "<ins>The new plan</ins>" in html


def test_an_export_draws_no_full_size_copy() -> None:
    export = RenderContext(image_url=str, sides=("0.1", "0.1-1"), full_size=False)
    html = changes(
        TEXT + f"\n![The old plan]({OLD})\n", TEXT + f"\n![The new plan]({NEW})\n", export
    )

    assert html.count("<img") == 2 and "<details" not in html


def test_no_context_draws_descriptions() -> None:
    html = changes(TEXT + f"\n![The old plan]({OLD})\n", TEXT + f"\n![The new plan]({NEW})\n", None)

    assert "<img" not in html and "imgpair" not in html


def test_a_replaced_image_beside_new_words_is_still_a_pair() -> None:
    """Image lines are paired with each other before the rest of a rewritten stretch is paired
    by position, so words added or removed beside a replaced image leave its pair intact."""
    added = changes(
        f"Intro.\n\n![The old plan]({OLD})\n\nEnd.\n",
        f"Intro.\n\nA new paragraph.\n\n![The new plan]({NEW})\n\nEnd.\n",
    )
    removed = changes(
        f"Intro.\n\nA paragraph to go.\n\n![The old plan]({OLD})\n\nEnd.\n",
        f"Intro.\n\n![The new plan]({NEW})\n\nEnd.\n",
    )
    for html in (added, removed):
        assert html.count('<div class="imgpair">') == 1, html
        assert "<ins><img" not in html and "<del><img" not in html


def test_the_same_image_moved_is_formatting_only() -> None:
    html = changes(TEXT + f"\n![A plan]({OLD})\n", TEXT + f"\n> ![A plan]({OLD})\n")

    assert "image-description" not in html and "imgpair" not in html
    assert "format-changed" in html


def test_an_image_in_a_table_cell_keeps_both_rules() -> None:
    """A cell's image replaced is flagged with its pair in the cell; the same image with a new
    description is its words changed, drawn once."""
    table = "| Plan |\n| --- |\n| ![{words}]({src}) |\n"
    replaced = changes(
        table.format(words="The old plan", src=OLD), table.format(words="The new plan", src=NEW)
    )
    described = changes(
        table.format(words="The old plan", src=OLD), table.format(words="The new plan", src=OLD)
    )

    assert re.search(
        r'<td><span class="image-changed">image changed</span><div class="imgpair">', replaced
    )
    assert described.count("<img") == 1
    assert "<del>The old plan</del>" in described and "<ins>The new plan</ins>" in described


def test_a_description_reformatted_is_formatting_only() -> None:
    """A draft's source keeps a description's emphasis, which the rendered description drops: the
    same image and the same words, reformatted, are a change of formatting — never the picture
    struck and inserted again."""
    old, new = TEXT + f"\n![A plan]({OLD})\n", TEXT + f"\n![*A plan*]({OLD})\n"

    for html in (changes(old, new), changes(old, new, None)):
        assert "<del>" not in html and "<ins>" not in html, html
        assert "format-changed" in html

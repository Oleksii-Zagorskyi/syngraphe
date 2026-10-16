"""What a text references: every image token's `src` and the line the source view shows it on.
Invented English; the names are placeholders."""

from __future__ import annotations

import pytest

from documents import images
from documents.images import Reference

pytestmark = pytest.mark.fast

PLAN = "images/" + "a" * 64 + ".png"
CHART = "images/" + "b" * 64 + ".gif"


def test_each_reference_carries_the_line_it_stands_on() -> None:
    body = (
        "A first sentence.\n\n"
        f"![A plan]({PLAN})\n\n"
        "> [!note]\n"
        f"> ![A chart]({CHART})\n\n"
        "> [!warning]\n"
        "> A warning sentence.\n"
        f"> ![A plan again]({PLAN})\n"
    )
    appendix = f"- An item.\n\n  ![A chart]({CHART})\n"

    assert images.referenced({"document.md": body, "appendices/1.md": appendix}) == [
        Reference(PLAN, "document.md", 3),
        Reference(CHART, "document.md", 6),
        Reference(PLAN, "document.md", 10),
        Reference(CHART, "appendices/1.md", 3),
    ]


def test_only_the_platforms_names_are_image_paths() -> None:
    assert images.is_image_path(PLAN)
    for src in ("images/plan.png", "images/" + "a" * 64 + ".svg", PLAN + "\n", "media/" + PLAN[7:]):
        assert not images.is_image_path(src)


def test_a_bracketed_destination_carries_its_own_line() -> None:
    body = f"> [!note]\n> ![A plan](<{PLAN}>)\n"

    assert images.referenced({"document.md": body}) == [Reference(PLAN, "document.md", 2)]

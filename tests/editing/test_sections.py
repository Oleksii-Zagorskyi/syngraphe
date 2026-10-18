"""A body's sections as ranges of its lines: found by the platform's own Markdown parser, read,
spliced, and the shift a splice gives the ordinals of the other open editors. Every text is an
invented synthetic example."""

from __future__ import annotations

from typing import Any

import pytest

from editing.sections import (
    WHOLE,
    Range,
    ordinal_of,
    ranges,
    section_text,
    shift,
    splice,
)

pytestmark = pytest.mark.fast

# Lines: 0 preamble, 2 `# First section`, 6 `## First subsection`, 10 `# Second section`, 12 last.
NESTED = (
    "An introductory paragraph.\n"
    "\n"
    "# First section\n"
    "\n"
    "Section text.\n"
    "\n"
    "## First subsection\n"
    "\n"
    "Subsection text.\n"
    "\n"
    "# Second section\n"
    "\n"
    "The last paragraph.\n"
)

FIRST_LINE = "# Heading\n\nText.\n"

NO_HEADING = "The first paragraph.\n\nThe second paragraph.\n"

DEPTHS = "## A\n\n### A.1\n\n# B\n\n#### B.1\n\n## C\n\nText.\n"

NOT_HEADINGS = (
    "> # not a heading\n"
    "\n"
    "- # not a heading\n"
    "\n"
    "#hashtag\n"
    "\n"
    "A line with # in the middle.\n"
    "\n"
    "```\n"
    "# code\n"
    "```\n"
    "\n"
    "# A real heading\n"
    "\n"
    "Text.\n"
)

SHORT = "# First\n# Second\n# Last"

FLAT = (
    "Introduction.\n"
    "\n"
    "# First\n"
    "\n"
    "Text of the first.\n"
    "\n"
    "# Second\n"
    "\n"
    "Text of the second.\n"
    "\n"
    "# Third\n"
    "\n"
    "Text of the third.\n"
)

BODIES = [NESTED, FIRST_LINE, "", NO_HEADING, DEPTHS, NOT_HEADINGS, SHORT, FLAT]


def test_ranges() -> None:
    assert ranges(NESTED) == [Range(2, 10, 1), Range(6, 10, 2), Range(10, 13, 1)]
    assert section_text(NESTED, ranges(NESTED)[1]).startswith("## First subsection\n")


def test_a_heading_on_the_first_line() -> None:
    assert ranges(FIRST_LINE) == [Range(0, 3, 1)]


def test_no_sections() -> None:
    assert ranges("") == []
    assert ranges(NO_HEADING) == []


def test_nested_depths() -> None:
    assert ranges(DEPTHS) == [
        Range(0, 4, 2),
        Range(2, 4, 3),
        Range(4, 11, 1),
        Range(6, 8, 4),
        Range(8, 11, 2),
    ]


def test_only_top_level_headings() -> None:
    assert ranges(NOT_HEADINGS) == [Range(12, 15, 1)]


def test_short_sections() -> None:
    found = ranges(SHORT)
    assert found == [Range(0, 1, 1), Range(1, 2, 1), Range(2, 3, 1)]
    assert section_text(SHORT, found[0]) == "# First\n"
    assert section_text(SHORT, found[1]) == "# Second\n"
    assert section_text(SHORT, found[2]) == "# Last"


def test_text_and_splice_round_trip() -> None:
    lines = FLAT.splitlines(keepends=True)
    found = ranges(FLAT)
    preamble = "".join(lines[: found[0].start])
    assert preamble + "".join(section_text(FLAT, r) for r in found) == FLAT
    for body in BODIES:
        for r in ranges(body):
            assert splice(body, r, section_text(body, r)) == body


def test_splice_replaces_only_its_lines() -> None:
    last = ranges(NESTED)[2]
    before = "".join(NESTED.splitlines(keepends=True)[: last.start])
    text = "# Second section\n\nA new paragraph.\n"
    spliced = splice(NESTED, last, text)
    assert spliced == before + text
    assert spliced[: len(before)] == NESTED[: len(before)]


def test_splice_keeps_lines_apart() -> None:
    first, second, third = ranges(FLAT)
    spliced = splice(FLAT, second, "# Second\n\nChanged text.")
    assert "Changed text.\n# Third\n" in spliced
    assert ranges(spliced)[2] == Range(9, 12, 1)
    emptied = splice(FLAT, second, "")
    assert emptied == FLAT.replace("# Second\n\nText of the second.\n\n", "")
    assert [r.start for r in ranges(emptied)] == [first.start, first.end]
    # Nothing follows the last section, so nothing is added after its text.
    assert splice(FLAT, third, "# Third\n\nThe end.").endswith("The end.")


def test_shift_after_a_heading_is_added() -> None:
    old = FLAT
    second = ranges(old)[1]
    new = splice(old, second, section_text(old, second) + "# New\n\nA new paragraph.\n\n")
    assert shift(old, new, 1) == 1
    assert section_text(new, ranges(new)[3]) == section_text(old, ranges(old)[2])


def test_shift_after_a_heading_is_removed_or_none() -> None:
    old = "# First\n\nText.\n\n## Subsection\n\nIts text.\n\n# Second\n\nText of the second.\n"
    first = ranges(old)[0]
    text = section_text(old, first)
    removed = splice(old, first, text.replace("## Subsection\n\n", ""))
    assert shift(old, removed, 0) == -1
    reworded = splice(old, first, text.replace("Text.", "Other text."))
    assert reworded != old
    assert shift(old, reworded, 0) == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("section:0", 0),
        ("section:1", 1),
        ("section:12", 12),
        (WHOLE, None),
        ("whole", None),
        ("section:-1", None),
        ("section:+1", None),
        ("section:01", None),
        ("section:", None),
        ("section:٣", None),
        (" section:1", None),
        ("section:1 ", None),
        ("section:1\n", None),
        ("", None),
    ],
)
def test_ordinal_of(value: str, expected: int | None) -> None:
    assert ordinal_of(value) == expected


def test_lines_are_counted_as_splitlines_counts_them() -> None:
    # A line separator inside a paragraph is a line to `splitlines`
    # and none to the parser, and the indices must still be `splitlines`' own.
    body = "Intro\u2028with a separator.\n\n# First\n\nText.\n"
    assert ranges(body) == [Range(3, 6, 1)]
    assert section_text(body, ranges(body)[0]) == "# First\n\nText.\n"


def test_a_span_holds_its_subsections_and_typed_headings() -> None:
    """An editor's span runs through every heading its own text holds, so a heading typed into
    it does not cut it short (DL-0167)."""
    from editing import sections

    body = "# A\n\nA sentence.\n\n## A.1\n\nA sentence.\n\n# B\n\nA sentence.\n"
    first = sections.ranges(body)[0]
    text = sections.section_text(body, first)
    assert sections.headings_in(text) == 2
    assert sections.extent(body, 0, 2) == first
    grown = sections.splice(body, first, text + "# New\n\nA sentence.\n\n")
    assert sections.section_text(grown, sections.extent(grown, 0, 3)).endswith(
        "# New\n\nA sentence.\n\n"
    )
    assert sections.extent(grown, 3, 1) == sections.ranges(grown)[3]
    assert sections.extent(grown, 3, 2) is None
    assert sections.span_of("section:4") == (4, 1)
    assert sections.span_of("section:4:3") == (4, 3)
    assert sections.span_of("section:4:1") is None
    assert sections.span_of("whole") is None
    assert sections.span_name(4, 1) == "section:4" and sections.span_name(4, 3) == "section:4:3"


def _ends_by_scanning(levels: list[int]) -> list[int]:
    """Each section's end as the rule states it: the next heading of the same or a higher level."""
    return [
        next((j for j in range(i + 1, len(levels)) if levels[j] <= level), len(levels))
        for i, level in enumerate(levels)
    ]


def test_ends_follow_the_rule_for_any_sequence_of_levels() -> None:
    """Every sequence of heading levels, deep and shallow mixed, ends each section where the rule
    says; one heading per line, so a section's end is the line of the heading that ends it."""
    import random

    chance = random.Random(9)
    for _ in range(300):
        levels = [chance.randint(1, 6) for _ in range(chance.randint(1, 40))]
        body = "".join("#" * level + " Section\n" for level in levels)
        assert [r.end for r in ranges(body)] == _ends_by_scanning(levels)
        assert [r.level for r in ranges(body)] == levels


@pytest.mark.budget
def test_ranges_cost_about_what_the_parse_costs(grows_linearly: Any) -> None:
    """Up to the size allowed, a body of nothing but headings — the case that costs most — is
    divided in time that grows with its length."""
    counted: list[int] = []
    grows_linearly(lambda n: "# aa\n" * n, lambda body: counted.append(len(ranges(body))), 15_000)
    assert counted[-1] == 60_000

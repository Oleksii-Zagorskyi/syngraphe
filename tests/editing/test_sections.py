"""A body's sections as ranges of its lines: found by the platform's own Markdown parser, read,
spliced, and the shift a splice gives the ordinals of the other open editors. Every text is an
invented synthetic example."""

from __future__ import annotations

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

# Lines: 0 preamble, 2 `# Перший розділ`, 6 `## Перший підрозділ`, 10 `# Другий розділ`, 12 last.
NESTED = (
    "Вступний абзац.\n"
    "\n"
    "# Перший розділ\n"
    "\n"
    "Текст розділу.\n"
    "\n"
    "## Перший підрозділ\n"
    "\n"
    "Текст підрозділу.\n"
    "\n"
    "# Другий розділ\n"
    "\n"
    "Останній абзац.\n"
)

FIRST_LINE = "# Заголовок\n\nТекст.\n"

NO_HEADING = "Перший абзац.\n\nДругий абзац.\n"

DEPTHS = "## А\n\n### А.1\n\n# Б\n\n#### Б.1\n\n## В\n\nТекст.\n"

NOT_HEADINGS = (
    "> # не заголовок\n"
    "\n"
    "- # не заголовок\n"
    "\n"
    "#хештег\n"
    "\n"
    "Рядок із # посередині.\n"
    "\n"
    "```\n"
    "# код\n"
    "```\n"
    "\n"
    "# Справжній заголовок\n"
    "\n"
    "Текст.\n"
)

SHORT = "# Перший\n# Другий\n# Останній"

FLAT = (
    "Вступ.\n"
    "\n"
    "# Перший\n"
    "\n"
    "Текст першого.\n"
    "\n"
    "# Другий\n"
    "\n"
    "Текст другого.\n"
    "\n"
    "# Третій\n"
    "\n"
    "Текст третього.\n"
)

BODIES = [NESTED, FIRST_LINE, "", NO_HEADING, DEPTHS, NOT_HEADINGS, SHORT, FLAT]


def test_ranges() -> None:
    assert ranges(NESTED) == [Range(2, 10, 1), Range(6, 10, 2), Range(10, 13, 1)]
    assert section_text(NESTED, ranges(NESTED)[1]).startswith("## Перший підрозділ\n")


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
    assert section_text(SHORT, found[0]) == "# Перший\n"
    assert section_text(SHORT, found[1]) == "# Другий\n"
    assert section_text(SHORT, found[2]) == "# Останній"


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
    text = "# Другий розділ\n\nНовий абзац.\n"
    spliced = splice(NESTED, last, text)
    assert spliced == before + text
    assert spliced[: len(before)] == NESTED[: len(before)]


def test_splice_keeps_lines_apart() -> None:
    first, second, third = ranges(FLAT)
    spliced = splice(FLAT, second, "# Другий\n\nЗмінений текст.")
    assert "Змінений текст.\n# Третій\n" in spliced
    assert ranges(spliced)[2] == Range(9, 12, 1)
    emptied = splice(FLAT, second, "")
    assert emptied == FLAT.replace("# Другий\n\nТекст другого.\n\n", "")
    assert [r.start for r in ranges(emptied)] == [first.start, first.end]
    # Nothing follows the last section, so nothing is added after its text.
    assert splice(FLAT, third, "# Третій\n\nКінець.").endswith("Кінець.")


def test_shift_after_a_heading_is_added() -> None:
    old = FLAT
    second = ranges(old)[1]
    new = splice(old, second, section_text(old, second) + "# Новий\n\nНовий абзац.\n\n")
    assert shift(old, new, 1) == 1
    assert section_text(new, ranges(new)[3]) == section_text(old, ranges(old)[2])


def test_shift_after_a_heading_is_removed_or_none() -> None:
    old = "# Перший\n\nТекст.\n\n## Підрозділ\n\nТекст підрозділу.\n\n# Другий\n\nТекст другого.\n"
    first = ranges(old)[0]
    text = section_text(old, first)
    removed = splice(old, first, text.replace("## Підрозділ\n\n", ""))
    assert shift(old, removed, 0) == -1
    reworded = splice(old, first, text.replace("Текст.", "Інший текст."))
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
    body = "Вступ\u2028з розділювачем.\n\n# Перший\n\nТекст.\n"
    assert ranges(body) == [Range(3, 6, 1)]
    assert section_text(body, ranges(body)[0]) == "# Перший\n\nТекст.\n"


def test_a_span_holds_its_subsections_and_typed_headings() -> None:
    """An editor's span runs through every heading its own text holds, so a heading typed into
    it does not cut it short (DL-0167)."""
    from editing import sections

    body = "# А\n\nРечення.\n\n## А.1\n\nРечення.\n\n# Б\n\nРечення.\n"
    first = sections.ranges(body)[0]
    text = sections.section_text(body, first)
    assert sections.headings_in(text) == 2
    assert sections.extent(body, 0, 2) == first
    grown = sections.splice(body, first, text + "# Нове\n\nРечення.\n\n")
    assert sections.section_text(grown, sections.extent(grown, 0, 3)).endswith(
        "# Нове\n\nРечення.\n\n"
    )
    assert sections.extent(grown, 3, 1) == sections.ranges(grown)[3]
    assert sections.extent(grown, 3, 2) is None
    assert sections.span_of("section:4") == (4, 1)
    assert sections.span_of("section:4:3") == (4, 3)
    assert sections.span_of("section:4:1") is None
    assert sections.span_of("whole") is None
    assert sections.span_name(4, 1) == "section:4" and sections.span_name(4, 3) == "section:4:3"

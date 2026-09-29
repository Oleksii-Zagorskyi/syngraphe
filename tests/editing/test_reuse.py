"""Moved text keeps its stored lines on every path (DL-0244, V-15). Invented Ukrainian text."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from editing.normalizer import normalize
from editing.normalizer.splitter import Lists

LANGUAGES = Path(__file__).resolve().parents[2] / "src" / "identity" / "fixtures" / "languages"

pytestmark = pytest.mark.fast


def lists_for(code: str) -> Lists:
    data = json.loads((LANGUAGES / f"{code}.json").read_text(encoding="utf-8"))
    return Lists(data["code"], tuple(data["never_final"]), tuple(data["may_be_final"]))


# The stored document, a paragraph per entry, as an older normalizer might have left it: P1's
# first line holds two sentences — the stored newline is the authority, so the splitter would
# place a boundary there that the stored text does not have.
H1 = "# Порядок погодження документів"
S1 = "## Загальні положення"
S2 = "## Відповідальність"
P1 = [
    "Цей порядок визначає строки погодження. Він застосовується до всіх підрозділів.",
    "Керівник підрозділу відповідає за його виконання.",
]
P2 = [
    "Погодження здійснює комісія з перевірки.",
    'Документ позначають відміткою "погоджено".',
    "Строк погодження становить 10 робочих днів.",
    "Комісія може продовжити строк один раз.",
]
P3 = [
    "Заявник подає заяву в паперовій формі.",
    "Копію заяви передають секретарю комісії.",
]
P4 = [
    "Порушення строку фіксують у журналі.",
    "Журнал веде секретар комісії.",
]
P5 = [
    "Керівник напряму розглядає скарги щомісяця.",
    "Відповідь надають письмово.",
    "Журнал веде секретар комісії.",
]


def document(*blocks: str | list[str], joined: bool = False) -> str:
    """Blocks separated by blank lines; a paragraph's lines kept, or joined into one line as the
    source view and an outside paste submit them."""
    parts = [b if isinstance(b, str) else (" " if joined else "\n").join(b) for b in blocks]
    return "\n\n".join(parts) + "\n"


STORED = document(H1, S1, P1, P2, P3, S2, P4, P5)
P2_REWORDED = [P2[0], P2[1], "Строк погодження становить 15 робочих днів.", P2[3]]


def paths() -> dict[str, tuple[str, str]]:
    """Each V-15 path: the submitted text and the text that must be stored."""
    moved_between = document(H1, S1, P1, P3, S2, P4, P5, P2)
    pasted = document(H1, S1, P1, P3, S2, P2, P4, P5).replace("\n".join(P2), "   ".join(P2) + " \t")
    return {
        "moved within a section": (
            document(H1, S1, P1, P3, P2, S2, P4, P5),
            document(H1, S1, P1, P3, P2, S2, P4, P5),
        ),
        "moved between sections": (moved_between, moved_between),
        "through the source view": (
            document(H1, S1, P1, P2, S2, P3, P4, P5, joined=True),
            document(H1, S1, P1, P2, S2, P3, P4, P5),
        ),
        "pasted back from outside": (pasted, document(H1, S1, P1, P3, S2, P2, P4, P5)),
        "moved with one sentence reworded": (
            document(H1, S1, P1, P3, S2, P4, " ".join(P2_REWORDED), P5),
            document(H1, S1, P1, P3, S2, P4, P2_REWORDED, P5),
        ),
        "two identical sentences, one moved": (
            document(H1, S1, P1, P2, [*P3, P5[2]], S2, P4, P5[:2], joined=True),
            document(H1, S1, P1, P2, [*P3, P5[2]], S2, P4, P5[:2]),
        ),
    }


def test_v15_every_path() -> None:
    uk = lists_for("uk")
    failed = {}
    for name, (submitted, expected) in paths().items():
        stored = normalize(STORED.encode(), submitted, uk)
        if stored != expected.encode():
            failed[name] = stored.decode()
    assert failed == {}


def test_reworded_sentence_is_the_only_new_line() -> None:
    submitted, _ = paths()["moved with one sentence reworded"]
    stored_lines = set(STORED.split("\n"))
    out = normalize(STORED.encode(), submitted, lists_for("uk")).decode().split("\n")
    assert [line for line in out if line not in stored_lines] == [P2_REWORDED[2]]


def test_edited_paragraph_keeps_its_other_lines_in_place() -> None:
    """Alignment in place: a sentence added to P1 leaves its two stored lines — the older
    two-sentence line included — as they were."""
    added = "Контроль здійснює заступник керівника."
    submitted = document(H1, S1, " ".join([*P1, added]), P2, P3, S2, P4, P5)
    expected = document(H1, S1, [*P1, added], P2, P3, S2, P4, P5)
    assert normalize(STORED.encode(), submitted, lists_for("uk")) == expected.encode()


def test_new_document_is_split() -> None:
    submitted = "Перше речення. Друге речення! Третє?\n"
    out = normalize(b"", submitted, lists_for("uk"))
    assert out == "Перше речення.\nДруге речення!\nТретє?\n".encode()


def test_a_stored_line_inside_a_new_sentence_is_not_reused() -> None:
    """A stored line is carried only where it stands as a sentence (DL-0323): a new sentence that
    contains a list item's words, or a clause that repeats a stored sentence, is split as new
    text."""
    uk = lists_for("uk")
    stored = "Умови такі.\n\n- перша умова\n- друга умова\n\nКінець розділу.\n"
    added = "Кінець розділу. Виконується перша умова договору."
    submitted = stored.replace("Кінець розділу.", added)
    out = normalize(stored.encode(), submitted, uk).decode()
    assert out.endswith("Кінець розділу.\nВиконується перша умова договору.\n")

    stored = "Комісія погодила.\nГолова підписав акт.\n"
    submitted = "Комісія погодила, бо Голова підписав акт. Голова підписав акт.\n"
    out = normalize(stored.encode(), submitted, uk).decode()
    assert out == "Комісія погодила, бо Голова підписав акт.\nГолова підписав акт.\n"


def test_a_sentence_moved_to_a_lines_start_keeps_its_bytes() -> None:
    """A new line is written as the serialiser writes a sentence at a line's start, so the same
    sentence arriving there later matches it."""
    uk = lists_for("uk")
    first = normalize(b"", "Температура впала. -5 градусів тримається тиждень.\n", uk)
    assert first.decode() == "Температура впала.\n\\-5 градусів тримається тиждень.\n"
    moved = "\\-5 градусів тримається тиждень. Температура впала.\n"
    assert normalize(first, moved, uk).decode() == (
        "\\-5 градусів тримається тиждень.\nТемпература впала.\n"
    )


def test_a_no_break_space_separates_sentences() -> None:
    """A paste from a word processor puts a no-break space between sentences; the stored lines
    are found and kept."""
    submitted = document(H1, S1, P1, P3, S2, P2, P4, P5).replace("\n".join(P2), "\xa0".join(P2))
    expected = document(H1, S1, P1, P3, S2, P2, P4, P5)
    assert normalize(STORED.encode(), submitted, lists_for("uk")) == expected.encode()


def test_moved_into_a_list_and_a_quote_keeps_the_bytes_after_the_prefix() -> None:
    uk = lists_for("uk")
    listed = document(H1, S1, P1, P3, S2, P4, P5, "- " + "\n  ".join(P2))
    out = normalize(STORED.encode(), listed, uk).decode()
    assert out == listed
    quoted = document(H1, S1, P1, P3, S2, P4, P5, "> " + "\n> ".join(P2))
    out = normalize(STORED.encode(), quoted, uk).decode()
    assert out == quoted


def test_renumbered_items_are_touched() -> None:
    """Deleting the first item renumbers the rest; each renumbered line is touched (DL-0324)."""
    from editing.normalizer import run

    stored = "1. Перший пункт.\n2. Другий пункт.\n3. Третій пункт.\n"
    submitted = "1. Другий пункт.\n2. Третій пункт.\n"
    result = run(stored.encode(), submitted, lists_for("uk"))
    assert result.text == submitted
    assert result.touched == frozenset({0, 1})


RICH = (
    "# Розділ\n\n"
    "Вступне речення. Друге речення з [посиланням](https://example.org/a--b).\n\n"
    "- Пункт один. Ще речення.\n"
    "  - Вкладений пункт.\n"
    "    - Третій рівень.\n\n"
    "> [!note]\n"
    "> Примітка тут. Ще одна.\n"
    "> - Пункт у примітці.\n\n"
    "> Цитата. Друга.\n\n"
    "| А | Б |\n| --- | :---: |\n| 1 | 2 |\n\n"
    "![схема](images/scheme.png)\n\n"
    "Див. https://example.org/a--b...c тут. [Відповідальний]{.role #vidp} погоджує.\n"
)


def test_the_output_is_accepted_and_a_fixed_point() -> None:
    from editing.markdown.serializer import serialize
    from editing.markdown.validator import validate

    uk = lists_for("uk")
    out = normalize(b"", RICH, uk)
    text = out.decode()
    assert validate(text) == []
    assert serialize(text) == text
    assert normalize(out, text, uk) == out
    assert "a--b...c" in text  # a web address written as text is never typeset


def test_a_boundary_that_would_change_the_parse_is_joined() -> None:
    out = normalize(b"", "Кінець розділу. # Не заголовок.\n", lists_for("uk")).decode()
    assert out == "Кінець розділу. # Не заголовок.\n"


def test_unbalanced_quotes_stay_straight() -> None:
    out = normalize(b"", 'Він сказав "так. Потім "ні".\n', lists_for("uk")).decode()
    assert "«" not in out and "»" not in out

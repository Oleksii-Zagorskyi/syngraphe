"""The names an export's files carry (DL-0275, DL-0357): one file is
`<title>_—_<version>_—_<stance>.<ext>`, a marked one ends its stance in `-<marks>`, and a part
inside a zip is `<word>-<number>_—_<name>`. Every space becomes `_`, every character filesystems
refuse becomes `-`, and nothing else changes.

Every title is invented; the stances and fixed words are the glossary's Ukrainian terms.
"""

from __future__ import annotations

import pytest

from rendering.export.names import file_name, part_name

pytestmark = pytest.mark.fast

CANONICAL = "канонічна версія"
FORBIDDEN = ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]


def test_spaces_and_forbidden_characters() -> None:
    """A space becomes `_`; a colon and a slash become `-`."""
    name = file_name("Відпустки та лікарняні: правила/2026", "2.0", CANONICAL, "pdf")

    assert name == "Відпустки_та_лікарняні-_правила-2026_—_2.0_—_канонічна_версія.pdf"


@pytest.mark.parametrize("character", FORBIDDEN)
def test_each_forbidden_character_becomes_a_hyphen(character: str) -> None:
    name = file_name(f"Порядок{character}погодження", "1.0", CANONICAL, "pdf")

    assert name == "Порядок-погодження_—_1.0_—_канонічна_версія.pdf"


def test_a_run_of_forbidden_characters_keeps_one_hyphen_each() -> None:
    name = file_name('Порядок <"чернетка"> ?', "0.1", "погоджені правки", "docx")

    assert name == "Порядок_--чернетка--_-_—_0.1_—_погоджені_правки.docx"


def test_a_long_title_is_cut_at_eighty_characters() -> None:
    title = (
        "Положення про порядок надання щорічних основних і додаткових відпусток "
        "працівникам структурних підрозділів: редакція 2026/27"
    )

    name = file_name(title, "1.0", CANONICAL, "pdf")

    kept = "Положення_про_порядок_надання_щорічних_основних_і_додаткових_відпусток_працівник"
    assert len(kept) == 80
    assert name == f"{kept}_—_1.0_—_канонічна_версія.pdf"


def test_a_title_of_eighty_characters_is_not_cut() -> None:
    title = "Правила" + "а" * 73

    assert file_name(title, "1.0", CANONICAL, "md") == f"{title}_—_1.0_—_канонічна_версія.md"


def test_the_marks_suffix_follows_the_stance() -> None:
    name = file_name("Порядок погодження", "0.3", "всі неприйняті правки", "pdf", marks="правки")

    assert name == "Порядок_погодження_—_0.3_—_всі_неприйняті_правки-правки.pdf"


def test_a_clean_export_has_no_suffix() -> None:
    marked = file_name("Порядок погодження", "0.3", "погоджені правки", "zip", marks="правки")
    clean = file_name("Порядок погодження", "0.3", "погоджені правки", "zip")

    assert clean == "Порядок_погодження_—_0.3_—_погоджені_правки.zip"
    assert marked != clean


def test_the_marks_take_the_same_replacements() -> None:
    name = file_name("Порядок", "0.3", "мої правки", "pdf", marks="мої правки/чернетка")

    assert name == "Порядок_—_0.3_—_мої_правки-мої_правки-чернетка.pdf"


def test_the_stance_takes_the_same_replacements() -> None:
    name = file_name("Порядок", "1.0", "канонічна: версія", "pdf")

    assert name == "Порядок_—_1.0_—_канонічна-_версія.pdf"


def test_a_title_already_safe_is_unchanged() -> None:
    name = file_name("Положення_про_відпустки.v2", "1.0", CANONICAL, "docx")

    assert name == "Положення_про_відпустки.v2_—_1.0_—_канонічна_версія.docx"


def test_cyrillic_digits_dots_and_other_punctuation_stay() -> None:
    name = file_name("Правила №3, «нова» (ст. 5.1) — огляд!", "2.0", CANONICAL, "pdf")

    assert name == "Правила_№3,_«нова»_(ст._5.1)_—_огляд!_—_2.0_—_канонічна_версія.pdf"


def test_part_name() -> None:
    assert part_name("вкладений файл", 2, "схема.xlsx") == "вкладений_файл-2_—_схема.xlsx"


def test_part_name_of_an_appendix() -> None:
    assert part_name("додаток", 1, "Форма заяви.pdf") == "додаток-1_—_Форма_заяви.pdf"


def test_part_name_replaces_in_the_word_and_the_name() -> None:
    name = part_name("вкладений файл", 3, 'звіт "квартал: 1".xlsx')

    assert name == "вкладений_файл-3_—_звіт_-квартал-_1-.xlsx"


def test_part_name_does_not_cut_the_name() -> None:
    original = "Таблиця розрахунку " + "щорічних відпусток " * 6 + "2026.xlsx"
    assert len(original) > 80

    name = part_name("вкладений файл", 1, original)

    assert name == "вкладений_файл-1_—_" + original.replace(" ", "_")


def test_control_characters_never_reach_a_name() -> None:
    """A title holding a control character — a NUL, a line break — is cleaned, never passed on
    to a file system or a zip entry."""
    name = file_name("Порядок\x00 з\nрозривом\x7f", "1.0", "канонічна версія", "pdf")

    assert not any(ord(c) < 0x20 or ord(c) == 0x7F for c in name)
    assert name.startswith("Порядок")

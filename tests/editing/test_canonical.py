"""Canonical form and typography: a prettifier's padding is no edit, and typography reaches only
the lines an edit touched (ASR-20, DL-0273). Invented text."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from editing.normalizer import normalize, run
from editing.normalizer.canonical import canonicalise
from editing.normalizer.splitter import Lists
from editing.normalizer.typography import typeset

LANGUAGES = Path(__file__).resolve().parents[2] / "src" / "identity" / "fixtures" / "languages"

pytestmark = pytest.mark.fast


def lists_for(code: str) -> Lists:
    data = json.loads((LANGUAGES / f"{code}.json").read_text(encoding="utf-8"))
    return Lists(data["code"], tuple(data["never_final"]), tuple(data["may_be_final"]))


STORED_TABLE = (
    "Перед таблицею одне речення.\n"
    "\n"
    "| Посада | Строк | Примітка |\n"
    "| --- | :---: | --- |\n"
    '| директор | 5 днів | "термін" - умовний |\n'
    "| секретар | 2 дні | без змін |\n"
)


def test_padded_row_is_untouched() -> None:
    padded = (
        "Перед таблицею одне речення.   \n"
        "\n"
        "| Посада   |  Строк  | Примітка             |\n"
        "|----------|:-------:|----------------------|\n"
        '| директор | 5 днів  | "термін" - умовний   |\n'
        "| секретар | 2 дні   | без змін             |\n"
    )
    result = run(STORED_TABLE.encode(), padded, lists_for("uk"))
    assert result.text.encode() == STORED_TABLE.encode()
    assert result.touched == frozenset()


def test_touched_row_is_typeset_untouched_row_is_not() -> None:
    edited = STORED_TABLE.replace("2 дні", '3 дні "робочих"')
    out = normalize(STORED_TABLE.encode(), edited, lists_for("uk")).decode()
    assert '| директор | 5 днів | "термін" - умовний |' in out
    assert "| секретар | 3 дні «робочих» | без змін |" in out


def test_canonical_form() -> None:
    decomposed = unicodedata.normalize("NFD", "Її строк — п’ять днів.")
    assert canonicalise(decomposed + "  \n") == "Її строк — п’ять днів.\n"
    assert canonicalise("* пункт\n") == "- пункт\n"


def test_typography_on_touched_lines_only() -> None:
    uk = lists_for("uk")
    line = 'Він написав "текст", слово - слово, слово--слово і далі...'
    stored = f"Перше речення абзацу.\n{line}\n\nДругий абзац без змін.\n"
    typed = line.replace("Він написав", "Вона написала")
    submitted = f"Перше речення абзацу, змінене.\n{line}\n\nДругий абзац без змін.\n{typed}\n"
    out = normalize(stored.encode(), submitted, uk).decode().split("\n")
    assert out[0] == "Перше речення абзацу, змінене."
    assert out[1] == line
    assert out[3] == "Другий абзац без змін."
    assert out[4] == "Вона написала «текст», слово — слово, слово—слово і далі…"


def test_typography_rules_and_masking() -> None:
    assert typeset('"цитата" і "друга"', "uk") == "«цитата» і «друга»"
    assert typeset('"quoted" words', "en") == "“quoted” words"
    assert typeset('лише одна " лапка', "uk") == 'лише одна " лапка'
    assert typeset("обов'язок - п'ять", "uk") == "обов'язок — п'ять"
    masked = '[форма "А"](https://example.org/a--b...c) і [строк]{.term #a--b} - "так"...'
    assert typeset(masked, "uk") == (
        "[форма «А»](https://example.org/a--b...c) і [строк]{.term #a--b} — «так»…"
    )
    assert typeset("![Схема -- етап...](images/a--b.png)", "uk") == (
        "![Схема -- етап...](images/a--b.png)"
    )

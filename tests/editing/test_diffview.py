"""Changes shown word by word inside the rendered text (DL-0170): only the changed sentences are
compared word by word, a change of formatting alone has its own marker. Invented text."""

from __future__ import annotations

import pytest

from editing.diffview import render_changes

pytestmark = pytest.mark.fast

OLD = (
    "# Строки\n\n"
    "Заяву подають за десять днів.\n"
    "Відповідь надсилають **поштою**.\n"
    "Копію зберігають у справі.\n"
)


def test_word_level_marks_inside_rendered_text() -> None:
    new = OLD.replace("за десять днів", "не пізніше ніж за п'ять днів").replace(
        "**поштою**", "*поштою*"
    )
    html = render_changes(OLD.encode(), new.encode())
    assert "<del>десять</del>" in html
    assert "<ins>не пізніше ніж </ins>за" in html
    assert "<ins>п&#x27;ять</ins>" in html
    assert '<span class="format-changed">Відповідь надсилають <em>поштою</em>.</span>' in html
    assert "Копію зберігають у справі." in html and "<h1>Строки</h1>" in html


def test_markup_in_the_text_is_never_markup_in_the_page() -> None:
    old = "Текст.\n"
    new = "Текст \\<script>alert(1)\\</script>.\n"
    html = render_changes(old.encode(), new.encode())
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_each_list_item_is_its_own_block() -> None:
    old = "- Перший пункт.\n- Другий пункт.\n  Його друге речення.\n\n1. Один.\n2. Два.\n"
    new = old.replace("Другий пункт.", "Другий змінений пункт.")
    html = render_changes(old.encode(), new.encode())
    assert '<p class="item">Перший пункт.</p>' in html
    assert "Його друге речення.</p>" in html and html.count('<p class="item">') == 4


def test_a_change_to_a_line_without_words_is_shown() -> None:
    """A callout's type, a table's alignment: shown as the line, marked as formatting."""
    callout = "> [!note]\n> Примітка.\n"
    html = render_changes(callout.encode(), callout.replace("note", "warning").encode())
    assert '<span class="format-changed">&gt; [!warning]</span>' in html
    table = "| А | Б |\n| --- | --- |\n| 1 | 2 |\n"
    html = render_changes(table.encode(), table.replace("| --- | --- |", "| :-: | --- |").encode())
    assert '<span class="format-changed">| :-: | --- |</span>' in html


def test_a_diff_costs_a_bounded_amount() -> None:
    """A sentence of 110 KB with one word changed, and a text of repeated lines rewritten, render
    in well under a second each, not the minutes an unbounded alignment takes."""
    import time

    sentence = " ".join(f"слово{n % 97}" for n in range(15000)) + ".\n"
    changed = sentence.replace("слово5 ", "інше ", 1)
    repeated = "Той самий абзац.\n\n" * 2000
    rewritten = "Інший абзац.\n\n" * 2000
    for old, new in ((sentence, changed), (repeated, rewritten), (repeated, sentence)):
        started = time.perf_counter()
        render_changes(old.encode(), new.encode())
        assert time.perf_counter() - started < 2.0


def test_the_alignment_rebuilds_the_new_text() -> None:
    """Whatever the input, the opcodes cover both sides in order and `equal` means equal."""
    import random

    from editing.diffview import opcodes

    chance = random.Random(4)
    for _ in range(300):
        a = [chance.choice("абвгде") for _ in range(chance.randrange(0, 40))]
        b = [chance.choice("абвгде") for _ in range(chance.randrange(0, 40))]
        rebuilt: list[str] = []
        i_at = j_at = 0
        for tag, i1, i2, j1, j2 in opcodes(a, b):
            assert (i1, j1) == (i_at, j_at)
            if tag == "equal":
                assert a[i1:i2] == b[j1:j2]
            rebuilt.extend(b[j1:j2])
            i_at, j_at = i2, j2
        assert (i_at, j_at) == (len(a), len(b)) and rebuilt == b


def test_edits_far_apart_in_a_long_text_are_shown_word_by_word() -> None:
    """The first and the last sentence of three thousand changed: each marked in place."""
    old = "".join(f"Речення номер {n} про порядок.\n" for n in range(3000))
    new = old.replace("номер 0 ", "номер нуль ").replace("номер 2999 ", "номер останнє ")
    html = render_changes(old.encode(), new.encode())
    assert "<del>0</del><ins>нуль</ins>" in html
    assert "<del>2999</del><ins>останнє</ins>" in html
    assert html.count("<del>") == 2

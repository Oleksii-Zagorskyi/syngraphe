"""Changes shown word by word inside the rendered text (DL-0170): only the changed sentences are
compared word by word, a change of formatting alone has its own marker. People are synthetic
examples; the texts are invented."""

from __future__ import annotations

import pytest

from editing.diffview import Change, classify, render_changes

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
    assert '<span class="format-changed" tabindex="0"' in html
    assert 'Відповідь надсилають <em>поштою</em>.<span class="format-old">' in html
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


def test_sense_and_style() -> None:
    """A change of formatting marks or typography alone is style; a changed word is sense."""
    assert classify("Строк — **десять** днів.", "Строк — десять днів.") is Change.STYLE
    assert classify('Він сказав "так".', "Він сказав «так».") is Change.STYLE
    assert classify("- Строк - десять днів.", "- Строк — десять днів.") is Change.STYLE
    assert classify("Строк — десять днів.", "Строк — п'ять днів.") is Change.SENSE
    assert classify("Строк — десять днів.", "Строк — десять робочих днів.") is Change.SENSE
    # What a sentence points at is its sense too.
    assert classify("[Договір](https://a.test/1).", "[Договір](https://a.test/2).") is Change.SENSE
    assert classify("![Схема](images/a.png)", "![Схема](images/b.png)") is Change.SENSE
    assert classify("![Схема](images/a.png)", "![План](images/a.png)") is Change.SENSE
    assert classify("[Особа]{.role #r1} звітує.", "[Особа]{.role #r2} звітує.") is Change.SENSE
    assert classify("[Особа]{.role} звітує.", "[Особа]{.term} звітує.") is Change.SENSE
    assert classify("[Особа]{.underline} звітує.", "Особа звітує.") is Change.STYLE


def test_a_sense_change_keeps_its_formatting() -> None:
    """The new wording as it reads, the inserted words marked inside their formatting, the removed
    ones struck in plain text (DL-0331)."""
    old = "Заяву подають **керівнику** за десять днів.\n"
    new = "Заяву подають **керівнику відділу** за [п'ять](https://example.test/) днів.\n"
    html = render_changes(old.encode(), new.encode())
    assert "<strong>керівнику <ins>відділу</ins></strong>" in html
    assert '<del>десять</del><a href="https://example.test/"><ins>п&#x27;ять</ins></a>' in html


def test_each_line_carries_its_author() -> None:
    old = "Перше речення.\nДруге речення.\n"
    new = "Перше речення.\nДруге змінене речення.\nТретє речення.\n"
    html = render_changes(old.encode(), new.encode(), authors={0: "Автор А", 2: "Автор Б"})
    assert '<span class="by" data-author="Автор А" title="Автор А">Перше речення.</span>' in html
    assert (
        '<span class="by" data-author="Автор Б" title="Автор Б"><ins>Третє речення.</ins>' in html
    )
    # A line the mapping does not name carries no author.
    assert html.count('class="by"') == 2


def test_an_image_inserted_or_removed_shows() -> None:
    html = render_changes("Текст.\n".encode(), "Текст.\n\n![Схема](images/a.png)\n".encode())
    assert '<ins><img src="images/a.png" alt="Схема"' in html
    html = render_changes("Текст.\n\n![Схема](images/a.png)\n".encode(), "Текст.\n".encode())
    assert '<del><img src="images/a.png" alt="Схема"' in html
    html = render_changes(
        "Див. ![схему](images/a.png) нижче.\n".encode(),
        "Див. ![схему](images/b.png) нижче.\n".encode(),
    )
    assert '<ins><img src="images/b.png"' in html and '<del><img src="images/a.png"' in html


def test_unrelated_sentences_are_not_diffed_word_by_word() -> None:
    old = "Заяву подають письмово.\n"
    new = "Строк розгляду становить п'ять днів.\n"
    html = render_changes(old.encode(), new.encode())
    assert "<del>Заяву подають письмово.</del>" in html
    assert "<ins>Строк розгляду становить п'ять днів.</ins>" in html


@pytest.mark.parametrize(
    "line",
    [":-" + " " * 399_990 + "x", "|" + " " * 399_990 + "x", "> " + " " * 399_990 + "[!x"],
)
def test_a_line_that_fails_a_pattern_costs_its_length(line: str) -> None:
    """The line patterns never backtrack over a long run of spaces (a line at the size ceiling)."""
    import time

    started = time.monotonic()
    render_changes(b"a\n", (line + "\n").encode())
    assert time.monotonic() - started < 2.0


def test_sentences_alike_by_their_words() -> None:
    """Half their words in common or more: one sentence rewritten; less: one removed, one
    inserted. Spaces are not words."""
    one_word = render_changes("Заяву подають письмово до п'ятниці.\n".encode(),
                              "Строк розгляду становить десять днів.\n".encode())  # fmt: skip
    assert "<del>" in one_word and "<ins>Строк розгляду становить десять днів.</ins>" in one_word
    most = render_changes(
        "Заяву подають письмово до п'ятниці.\n".encode(),
        "Заяву подають письмово до четверга.\n".encode(),
    )
    assert "<del>п&#x27;ятниці.</del><ins>четверга.</ins>" in most

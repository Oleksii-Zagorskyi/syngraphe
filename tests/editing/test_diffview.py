"""Changes shown word by word inside the rendered text (DL-0170): only the changed sentences are
compared word by word, a change of formatting alone has its own marker. The text is the reading
view's — the same renderer, its classes and clause numbers — with the marks spliced in. People are
synthetic examples; the texts are invented."""

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
    assert "Копію зберігають у справі." in html
    assert '<h1><span class="num">1</span> Строки</h1>' in html


def test_markup_in_the_text_is_never_markup_in_the_page() -> None:
    old = "Текст.\n"
    new = "Текст \\<script>alert(1)\\</script>.\n"
    html = render_changes(old.encode(), new.encode())
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_lists_read_as_lists() -> None:
    old = "- Перший пункт.\n- Другий пункт.\n  Його друге речення.\n\n1. Один.\n2. Два.\n"
    new = old.replace("Другий пункт.", "Другий змінений пункт.")
    html = render_changes(old.encode(), new.encode())
    assert '<li><span class="num">1</span> Перший пункт.</li>' in html
    assert "Його друге речення.</li>" in html and html.count("<li>") == 4
    assert "<ul>" in html and "<ol>" in html
    assert "Другий <ins>змінений </ins>пункт." in html


def test_the_changes_read_like_the_document() -> None:
    """Callouts, tables, entity spans and clause numbers as the reading view draws them."""
    old = (
        "# Порядок\n\n"
        "Заяву погоджує [Бухгалтер]{.role #r1}.\n\n"
        "> [!note]\n> Примітка до порядку.\n\n"
        "| Вид | Строк |\n| --- | --- |\n| Звичайна | три дні |\n"
    )
    new = old.replace("три дні", "два дні").replace("до порядку", "до всього порядку")
    html = render_changes(old.encode(), new.encode())
    assert '<span class="entity entity-role" data-id="r1">Бухгалтер</span>' in html
    assert '<div class="callout callout-note">' in html
    assert "до <ins>всього </ins>порядку" in html
    assert "<td>Звичайна</td>" in html and "<del>три</del><ins>два</ins> дні" in html
    assert '<span class="num">1-1</span>' in html and '<span class="num">1-2</span>' in html


def test_a_removed_sentence_stands_where_it_was() -> None:
    """Inside a paragraph that stays, a removed sentence is struck in place; a paragraph removed
    whole is a block of its own."""
    old = "# Строки\n\nПерше речення.\nДруге речення.\nТретє речення.\n\nОкремий абзац.\n"
    new = "# Строки\n\nПерше речення.\nТретє речення.\n"
    html = render_changes(old.encode(), new.encode())
    assert "Перше речення. <del>Друге речення.</del> Третє речення.</p>" in html
    assert "<p><del>Окремий абзац.</del></p>" in html


def test_a_change_to_a_line_without_words_is_shown() -> None:
    """A callout's type, a table's alignment: shown as the line, marked as formatting."""
    callout = "> [!note]\n> Примітка.\n"
    html = render_changes(callout.encode(), callout.replace("note", "warning").encode())
    assert '<span class="format-changed">&gt; [!warning]</span>' in html
    table = "| А | Б |\n| --- | --- |\n| 1 | 2 |\n"
    html = render_changes(table.encode(), table.replace("| --- | --- |", "| :-: | --- |").encode())
    assert '<span class="format-changed">| :-: | --- |</span>' in html
    assert html.index("format-changed") < html.index("<table>")


@pytest.mark.budget
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
    assert (
        '<del>десять</del><a href="https://example.test/" rel="noopener noreferrer">'
        "<ins>п&#x27;ять</ins></a>" in html
    )


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
    """While images reach a reader as their descriptions, a change to an image is marked on its
    description, inserted or struck; nothing is fetched."""
    html = render_changes("Текст.\n".encode(), "Текст.\n\n![Схема](images/a.png)\n".encode())
    assert "<ins>Схема</ins>" in html and "<img" not in html
    html = render_changes("Текст.\n\n![Схема](images/a.png)\n".encode(), "Текст.\n".encode())
    assert "<del>Схема</del>" in html and "<img" not in html
    html = render_changes(
        "Див. ![схему](images/a.png) нижче.\n".encode(),
        "Див. ![схему](images/b.png) нижче.\n".encode(),
    )
    # The words stand and the file changed: the sentence struck and inserted whole.
    assert "<del>Див. схему нижче.</del><ins>Див. схему нижче.</ins>" in html
    assert "images/" not in html


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
@pytest.mark.budget
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


# --- where a removal stands, and what a line's text is ---------------


def _once(html: str, text: str) -> None:
    assert html.count(text) == 1, html


def test_a_removed_list_item_is_struck_once_as_an_item() -> None:
    old = "- Перший пункт.\n- Другий пункт.\n- Третій пункт.\n"
    html = render_changes(old.encode(), old.replace("- Другий пункт.\n", "").encode())
    _once(html, "Другий пункт.")
    assert '<li class="removed"><del>Другий пункт.</del></li>' in html
    loose = "- Перший пункт.\n\n- Другий пункт.\n\n- Третій пункт.\n"
    html = render_changes(loose.encode(), loose.replace("- Другий пункт.\n\n", "").encode())
    assert '<li class="removed"><p><del>Другий пункт.</del></p></li>' in html


def test_the_last_item_removed_is_its_own_item() -> None:
    old = "- Перший пункт.\n- Другий пункт.\n"
    html = render_changes(old.encode(), "- Перший пункт.\n".encode())
    assert '<li class="removed"><del>Другий пункт.</del></li>' in html


def test_table_rows_removed_or_rewritten_stay_rows() -> None:
    table = "| А | Б |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n"
    html = render_changes(table.encode(), table.replace("| 3 | 4 |\n", "").encode())
    assert '<tr class="removed"><td><del>3</del></td><td><del>4</del></td></tr>' in html
    assert "<p" not in html
    rows = "| Вид | Строк |\n| --- | --- |\n| Звичайна | три дні |\n"
    changed = rows.replace("| Звичайна | три дні |", "| Термінова | один день |")
    html = render_changes(rows.encode(), changed.encode())
    assert "<p" not in html and "<del>Звичайна</del>" in html and "Термінова" in html


def test_cells_removed_from_a_row_are_struck() -> None:
    old = "| А | Б | В |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n"
    new = "| А | Б |\n| --- | --- |\n| 1 | 2 |\n"
    html = render_changes(old.encode(), new.encode())
    assert "<del>В</del>" in html and "<del>3</del>" in html


def test_a_continuation_line_keeps_its_leading_number() -> None:
    old = "Абзац починається тут.\n2024. Року зміни.\n"
    new = "Абзац починається тут.\n2024. Року великі зміни.\n"
    html = render_changes(old.encode(), new.encode())
    assert "2024. Року <ins>великі </ins>зміни." in html


def test_a_callout_title_reads_without_its_marker() -> None:
    old = "> [!note] Назва примітки тут.\n> Текст примітки.\n"
    html = render_changes(old.encode(), old.replace("тут.", "там.").encode())
    assert "[!note]" not in html and "<del>тут.</del><ins>там.</ins>" in html


def test_removals_stay_in_their_own_block() -> None:
    old = "Перше речення.\nДруге речення.\n\nОкремий абзац.\n"
    html = render_changes(old.encode(), "Перше речення.\n".encode())
    assert "Перше речення. <del>Друге речення.</del></p>" in html
    assert "<p><del>Окремий абзац.</del></p>" in html
    callout = "> [!note]\n> Перший абзац.\n>\n> Другий абзац.\n"
    html = render_changes(callout.encode(), "> [!note]\n> Перший абзац.\n".encode())
    assert "<del></del>" not in html
    assert html.index("<del>Другий абзац.</del>") < html.index("</div>")


def test_a_hard_break_keeps_the_lines_apart() -> None:
    old = "Перше речення.\\\nДруге речення.\nТретє речення.\n"
    new = old.replace("Третє", "Змінене третє")
    html = render_changes(old.encode(), new.encode())
    assert "<ins>Перше" not in html and "Змінене" in html


def test_a_mark_across_sentences_is_compared_whole() -> None:
    old = "**Перше речення.\nДруге речення.**\n"
    new = old.replace("Друге речення", "Друге змінене речення")
    html = render_changes(old.encode(), new.encode())
    assert "**" not in html and "<ins>змінене </ins>" in html
    assert "<ins><strong>" not in html


def test_an_escaped_pipe_is_a_cell_character() -> None:
    old = "| А | Б |\n| --- | --- |\n| x \\| y | 4 |\n"
    html = render_changes(old.encode(), old.replace("| 4 |", "| 5 |").encode())
    assert "format-changed" not in html and "x | y" in html and "\\" not in html


def test_a_quote_becoming_a_callout_is_marked() -> None:
    old = "Абзац.\n\n> Текст цитати.\n"
    new = "Абзац.\n\n> [!note]\n> Текст цитати.\n"
    html = render_changes(old.encode(), new.encode())
    assert "format-changed" in html
    html = render_changes(new.encode(), old.encode())
    assert "format-changed" in html


def test_a_changed_target_alone_is_shown() -> None:
    old = "[Особа]{.role #r1} звітує.\n"
    html = render_changes(old.encode(), old.replace("#r1", "#r2").encode())
    assert "<del>" in html and "<ins>" in html


# --- cost and escaping ------------------------------------------------


@pytest.mark.budget
def test_crafted_alignments_cost_a_bounded_amount() -> None:
    """Regions with no line met once on each side, each led by a unique line, and one long
    sentence of the same shape in words: the aligner's cost is budgeted per diff, so neither takes
    more than a second or two, whatever the shape."""
    import time

    old = "".join(f"U{k}\n" + "а\nб\n" * 250 for k in range(20))
    new = "".join(f"U{k}\n" + "б\nа\nа\n" * 166 for k in range(20))
    words_old = " ".join(f"U{k} " + "а б " * 60 for k in range(400)) + ".\n"
    words_new = " ".join(f"U{k} " + "б а а " * 40 for k in range(400)) + ".\n"
    for a, b in ((old, new), (words_old, words_new)):
        started = time.perf_counter()
        render_changes(a.encode(), b.encode())
        assert time.perf_counter() - started < 3.0


@pytest.mark.budget
def test_many_marker_changes_and_removed_blocks_cost_linearly() -> None:
    import time

    callouts = "".join(f"> [!note]\n> Примітка {k}.\n\n" for k in range(10_000))
    paragraphs = "".join(f"Абзац номер {k}.\n\n" for k in range(10_000))
    for a, b in (
        (callouts, callouts.replace("[!note]", "[!warning]")),
        (paragraphs + "Кінець.\n", "Кінець.\n"),
    ):
        started = time.perf_counter()
        render_changes(a.encode(), b.encode())
        assert time.perf_counter() - started < 3.0


def test_hostile_values_stay_text_in_a_diff() -> None:
    import re

    old = (
        '> [!note"onmouseover="a()]\n> Примітка.\n\n'
        "[Особа]{.role #a} звітує.\n\n"
        "| А | Б |\n| --- | --- |\n| 1 | 2 |\n\n"
        "Рядок \\<script>alert(1)\\</script>.\n"
    )
    new = old.replace("| --- | --- |", "| :-: | --- |").replace(
        "Рядок \\<script>alert(1)\\</script>.\n", ""
    )
    new = new.replace("| 1 | 2 |", "| \\<script> | 2 |")
    html = render_changes(old.encode(), new.encode(), authors={0: 'Ев"іл <b>'})
    tags = set(re.findall(r"<([a-z0-9]+)\b", html))
    assert tags <= {"a", "code", "del", "div", "em", "h1", "ins", "p", "span", "strong", "table",
                    "tbody", "td", "th", "thead", "tr", "ul", "ol", "li"}, tags  # fmt: skip
    for opening in re.findall(r"<[a-z]+\b[^>]*>", html):
        assert re.fullmatch(r'<[a-z0-9]+(?: [a-z-]+="[^"<>]*")*>', opening), opening

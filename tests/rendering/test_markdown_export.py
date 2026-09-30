"""The Markdown export is the source view saved (DL-0181, DL-0184): each paragraph's
stored lines, one sentence per line, joined into one line by a single space, with the block prefix
of a quote, a callout or a list item dropped from the lines it joins; everything else — headings,
table rows, blank lines, a quote's bare `>` line, a callout's marker, every mark and span — as
stored.

The expectations were written from that rule and checked against the editor's source view
(`serialize(doc, { oneLine: true })` in `src/editing/js/serializer.js`), which is the authority
where the two could differ. Every text is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rendering.export.markdown import join_paragraphs

pytestmark = pytest.mark.fast

RENDER = Path(__file__).resolve().parents[1] / "fixtures" / "render"
CONFORMANCE = RENDER / "conformance.md"
EXPORTED = RENDER / "conformance.export.md"


def test_markdown_is_the_source_view() -> None:
    body = CONFORMANCE.read_text(encoding="utf-8")

    assert join_paragraphs(body) == EXPORTED.read_text(encoding="utf-8")


CASES = [
    pytest.param(
        "Кожен працівник ознайомлюється з порядком.\n"
        "Ознайомлення підтверджується підписом.\n"
        "Копія зберігається у відділі кадрів.\n",
        "Кожен працівник ознайомлюється з порядком. Ознайомлення підтверджується підписом. "
        "Копія зберігається у відділі кадрів.\n",
        id="paragraph-of-three-sentences",
    ),
    pytest.param(
        "Перший абзац.\nЙого друге речення.\n\nДругий абзац.\nЙого друге речення.\n",
        "Перший абзац. Його друге речення.\n\nДругий абзац. Його друге речення.\n",
        id="two-paragraphs-keep-their-blank-line",
    ),
    pytest.param(
        "> Перше речення цитати.\n> Друге речення цитати.\n",
        "> Перше речення цитати. Друге речення цитати.\n",
        id="quote-of-two-sentences",
    ),
    pytest.param(
        "> Перший абзац цитати.\n> Його друге речення.\n>\n> Другий абзац цитати.\n",
        "> Перший абзац цитати. Його друге речення.\n>\n> Другий абзац цитати.\n",
        id="quote-keeps-its-bare-line",
    ),
    pytest.param(
        "> [!warning]\n"
        "> Перевірте такі умови.\n"
        "> Без них заяву не приймуть.\n"
        ">\n"
        "> 1. наявність підпису;\n"
        "> 2. дату реєстрації.\n"
        ">    Дата ставиться від руки.\n",
        "> [!warning]\n"
        "> Перевірте такі умови. Без них заяву не приймуть.\n"
        ">\n"
        "> 1. наявність підпису;\n"
        "> 2. дату реєстрації. Дата ставиться від руки.\n",
        id="callout-with-a-paragraph-and-a-list",
    ),
    pytest.param(
        "- Заява подається письмово.\n"
        "  Строк розгляду становить десять днів.\n"
        "\n"
        "  Відповідь надсилається поштою.\n"
        "  Копія лишається у справі.\n"
        "- Інший пункт.\n",
        "- Заява подається письмово. Строк розгляду становить десять днів.\n"
        "\n"
        "  Відповідь надсилається поштою. Копія лишається у справі.\n"
        "- Інший пункт.\n",
        id="loose-list-item-with-continuation-lines",
    ),
    pytest.param(
        "9. Пункт має два речення.\n"
        "   Друге речення пункту.\n"
        "   - Вкладений пункт.\n"
        "     Його друге речення.\n"
        "     1. Глибший пункт.\n"
        "        І його друге речення.\n"
        "10. Пункт із довшим маркером.\n"
        "    Його друге речення.\n",
        "9. Пункт має два речення. Друге речення пункту.\n"
        "   - Вкладений пункт. Його друге речення.\n"
        "     1. Глибший пункт. І його друге речення.\n"
        "10. Пункт із довшим маркером. Його друге речення.\n",
        id="nested-list-items-with-continuation-lines",
    ),
    pytest.param(
        "Строки наведено нижче.\n"
        "Вони обов'язкові.\n"
        "\n"
        "| Етап | Строк |\n"
        "| :--- | ---: |\n"
        "| **подання** | 1 день |\n"
        "| а \\| б |  |\n",
        "Строки наведено нижче. Вони обов'язкові.\n"
        "\n"
        "| Етап | Строк |\n"
        "| :--- | ---: |\n"
        "| **подання** | 1 день |\n"
        "| а \\| б |  |\n",
        id="table-untouched",
    ),
    pytest.param(
        "## Строк [погодження]{.term #strok-pohodzhennia}\n"
        "\n"
        "[Секретар]{.role #sekretar} **обов'язково** [реєструє]{.action} звернення.\n"
        "Слова, [підкреслені в тексті]{.underline}, мають *особливу вагу*.\n"
        "Правила наведено [тут](https://example.org/pravyla), знак \\* лишається.\n",
        "## Строк [погодження]{.term #strok-pohodzhennia}\n"
        "\n"
        "[Секретар]{.role #sekretar} **обов'язково** [реєструє]{.action} звернення. "
        "Слова, [підкреслені в тексті]{.underline}, мають *особливу вагу*. "
        "Правила наведено [тут](https://example.org/pravyla), знак \\* лишається.\n",
        id="marks-untouched",
    ),
    pytest.param(
        "Абзац, де **виділення\nперетинає** межу речення.\n",
        "Абзац, де **виділення перетинає** межу речення.\n",
        id="a-mark-across-a-sentence-boundary",
    ),
]


@pytest.mark.parametrize(("stored", "exported"), CASES)
def test_join_paragraphs(stored: str, exported: str) -> None:
    assert join_paragraphs(stored) == exported


def test_line_start_escapes_go_with_the_line_start() -> None:
    """A sentence stored at a line start is escaped where it would read as a list, a heading or a
    marker there (`serializer.js::esc`); joined into its paragraph it is mid-line, and the source
    view writes it without that escape. The paragraph's own first line keeps its escape.
    """
    stored = (
        "\\- Перше речення з дефіса.\n"
        "Друге речення.\n"
        "\\- Третє з дефіса.\n"
        "1\\. Четверте.\n"
        "\\# П'яте.\n"
    )

    exported = (
        "\\- Перше речення з дефіса. Друге речення. - Третє з дефіса. 1. Четверте. # П'яте.\n"
    )
    assert join_paragraphs(stored) == exported


def test_the_result_ends_with_one_newline() -> None:
    assert join_paragraphs("Одне речення.\nДруге речення.") == "Одне речення. Друге речення.\n"

"""What is read and what is stored are the same (DL-0486, DL-0487): the invisible format
characters are removed from the lines a person changes, the two joiners kept; the marks that
reorder text are refused, each named by its line; a line stored before keeps its bytes (ASR-20).

The text is invented; Ukrainian where the language is what the test is about."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from editing.markdown.validator import validate
from editing.normalizer import Emptied, normalize, run
from editing.normalizer.splitter import Lists
from tenancy.schemas import schema_context

LANGUAGES = Path(__file__).resolve().parents[2] / "src" / "identity" / "fixtures" / "languages"
SOFT_HYPHEN, ZERO_WIDTH_SPACE, WORD_JOINER = "­", "​", "⁠"
LEFT_TO_RIGHT_MARK, BYTE_ORDER_MARK, TAG = "‎", "﻿", "\U000e0041"
NON_JOINER, JOINER = "‌", "‍"
REORDERING = ["‪", "‫", "‬", "‭", "‮", "⁦", "⁧", "⁨", "⁩"]


def lists_for(code: str) -> Lists:
    data = json.loads((LANGUAGES / f"{code}.json").read_text(encoding="utf-8"))
    return Lists(data["code"], tuple(data["never_final"]), tuple(data["may_be_final"]))


@pytest.mark.fast
def test_harmless_invisibles_removed_joiners_kept() -> None:
    hidden = SOFT_HYPHEN + ZERO_WIDTH_SPACE + WORD_JOINER + LEFT_TO_RIGHT_MARK + BYTE_ORDER_MARK
    submitted = (
        f"# Пере{hidden}лік\n\n"
        f"Заява по{SOFT_HYPHEN}дається пись{ZERO_WIDTH_SPACE}мово{TAG}.\n\n"
        f"Текст із з{NON_JOINER}єднувачем і{JOINER} без змін.\n"
    )

    stored = normalize(b"", submitted, lists_for("uk")).decode("utf-8")

    assert stored == (
        "# Перелік\n\n"
        "Заява подається письмово.\n\n"
        f"Текст із з{NON_JOINER}єднувачем і{JOINER} без змін.\n"
    )


@pytest.mark.fast
def test_a_stored_line_keeps_its_bytes() -> None:
    """A line stored before the rule keeps its soft hyphen while it is left alone; the line
    edited beside it is cleaned."""
    previous = f"Перше ре{SOFT_HYPHEN}чення.\nДруге речення.\n".encode()
    submitted = f"Перше ре{SOFT_HYPHEN}чення.\nДруге ре{ZERO_WIDTH_SPACE}чення, змінене.\n"

    result = run(previous, submitted, lists_for("uk"))

    assert result.text.splitlines() == [f"Перше ре{SOFT_HYPHEN}чення.", "Друге речення, змінене."]
    assert 0 not in result.touched


@pytest.mark.fast
def test_a_stored_line_keeps_its_bytes_from_the_source_view() -> None:
    """The source view submits a paragraph as one line: its stored sentence is still found and
    kept, typography and all, while the sentence edited beside it is cleaned."""
    previous = f'Перше ре{SOFT_HYPHEN}чення "так".\nДруге речення.\n'.encode()

    unchanged = run(
        previous, f'Перше ре{SOFT_HYPHEN}чення "так". Друге речення.\n', lists_for("uk")
    )
    edited = run(
        previous,
        f'Перше ре{SOFT_HYPHEN}чення "так". Друге ре{ZERO_WIDTH_SPACE}чення, змінене.\n',
        lists_for("uk"),
    )

    assert unchanged.text == previous.decode() and not unchanged.touched
    assert edited.text.splitlines() == [
        f'Перше ре{SOFT_HYPHEN}чення "так".',
        "Друге речення, змінене.",
    ]
    assert edited.touched == {1}


EMPTIED = [
    (f"- {ZERO_WIDTH_SPACE}", "list-item-empty"),
    (f"[{ZERO_WIDTH_SPACE}]{{.action}}", "span-empty"),
    (f"**{ZERO_WIDTH_SPACE}**", "hr"),
]


@pytest.mark.fast
@pytest.mark.parametrize(("line", "code"), EMPTIED)
def test_a_construct_left_empty_is_refused_by_its_line(line: str, code: str) -> None:
    """A construct holding only an invisible character reads as empty, and is refused as what
    it reads as, by its submitted line — the source view submits a paragraph as one line, so the
    stored form's line numbers would differ."""
    submitted = f"Перше речення. Друге{SOFT_HYPHEN} речення.\n\n{line}\n"

    with pytest.raises(Emptied) as refused:
        normalize(b"", submitted, lists_for("uk"))

    assert [(r.code, r.line) for r in refused.value.refusals] == [(code, 3)]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_construct_left_empty_is_refused_at_finishing(
    migrated_tenant: Any, member_of: Any, new_document: Any, settings: Any
) -> None:
    from editing.models import Draft

    settings.LANGUAGE_CODE = "en"
    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        body = f"A synthetic paragraph.\n\n- {ZERO_WIDTH_SPACE}\n"
        draft.content = {**draft.content, "document.md": body}
        draft.save()

    finished = client.get(f"/document/{document.number}/edit/finish/")

    assert finished.status_code == 409
    assert "line 3: a list item that does not begin with text" in finished.content.decode()


@pytest.mark.fast
@pytest.mark.parametrize("mark", REORDERING)
def test_a_reordering_mark_is_refused_by_its_line(mark: str) -> None:
    refusals = validate(f"# Розділ\n\nПерше речення.\nДруге {mark}речення.\n")

    assert [(r.code, r.line) for r in refusals] == [("reordering-mark", 4)]


@pytest.mark.fast
def test_the_other_invisibles_are_not_refused() -> None:
    """The validator lets them through for the normaliser to remove; a control character and the
    line separators stay refused."""
    harmless = SOFT_HYPHEN + ZERO_WIDTH_SPACE + WORD_JOINER + BYTE_ORDER_MARK + JOINER
    assert validate(f"Текст{harmless} далі.\n") == []
    assert [r.code for r in validate("Текст далі.\n")] == ["control-character"]


@pytest.mark.integration
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_a_stored_reordering_mark_is_refused_at_load(
    migrated_tenant: Any, member_of: Any, new_document: Any
) -> None:
    from editing.models import Draft

    client, author, _ = member_of("the.author@example.test")
    document = new_document(author)
    client.post(f"/document/{document.number}/edit/take/")
    with schema_context(migrated_tenant.number):
        draft = Draft.objects.get(hold__document=document)
        body = "A synthetic paragraph.\n\nA line ‮with a mark.\n"
        draft.content = {**draft.content, "document.md": body}
        draft.save()

    loaded = client.post(f"/document/{document.number}/edit/load/").json()

    assert loaded["verdict"] == {
        "state": "refused",
        "refusals": [{"code": "reordering-mark", "line": 3}],
    }


@pytest.mark.integration
@pytest.mark.django_db
def test_the_refusal_in_ukrainian(settings: Any) -> None:
    from django.utils import translation

    from editing.messages import CONSTRUCTS

    with translation.override("uk"):
        named = str(CONSTRUCTS["reordering-mark"])
    with translation.override("en"):
        english = str(CONSTRUCTS["reordering-mark"])

    assert english == "a mark that reorders text"
    assert named != english and named.strip()


@pytest.mark.fast
@pytest.mark.parametrize(
    ("line", "stored"),
    [("# Мета", "\\# Мета"), ("- пункт", "\\- пункт"), ("> цитата", "\\> цитата")],
)
def test_a_removal_at_a_paragraphs_start_keeps_it_a_paragraph(line: str, stored: str) -> None:
    """An invisible character before a marker made the line paragraph text; removing it must not
    make the marker a heading, a list or a quote: the marker is escaped as the editor writes it."""
    submitted = f"Вступ.\n\n{ZERO_WIDTH_SPACE}{line}\n"

    assert normalize(b"", submitted, lists_for("uk")).decode() == f"Вступ.\n\n{stored}\n"

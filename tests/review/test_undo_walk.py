"""The reversal of versions of a run, computed over a repository (ADR-0015, DL-0243, DL-0380):
which lines of the undone versions revert cleanly, which a later version built on and are listed
for the reviewer, and the head's file with the clean reversal applied. Moves follow the platform's
rule (ADR-0011), the frontmatter is left, a line a later version deleted is not listed (DL-0422),
and `reverse` reads no git.

Every text here is an invented synthetic example; the authors are fixed strings.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pygit2
import pytest

from documents import bundle, gitstore
from editing import authorship
from review import undo
from review.undo import Classified, Listed

pytestmark = pytest.mark.integration

TITLE = "Синтетичний порядок погодження"
HEADING = "# Загальні положення\n\n"


def document(body: str, title: str = TITLE) -> str:
    """`document.md` with the fixed frontmatter."""
    return bundle.render(bundle.Frontmatter(title=title, language="uk"), body)


def history(tmp_path: Path, files: Sequence[tuple[str, str]]) -> tuple[Path, list[str]]:
    """A bare repository with one commit per `(author, document.md)`, oldest first, on `main`;
    its path and the commits' shas."""
    path = tmp_path / "document.git"
    repo = pygit2.init_repository(str(path), bare=True)
    shas = []
    for n, (author, text) in enumerate(files, 1):
        who = pygit2.Signature(author, f"{author}@example.invalid", 1_800_000_000 + n * 60, 0)
        shas.append(
            gitstore.commit(
                repo, {"document.md": text.encode()}, who, f"Версія {n}", gitstore.Kind.EDIT
            )
        )
    return path, shas


def line_of(text: str, sentence: str) -> int:
    """The number of the one line of `text` that is `sentence`."""
    lines = text.split("\n")
    assert lines.count(sentence) == 1
    return lines.index(sentence) + 1


def reversed_run(
    tmp_path: Path, files: Sequence[tuple[str, str]], undone: Sequence[int]
) -> tuple[undo.Reversal, list[str]]:
    """The first file is the base, the last the head; `undone` are indexes into `files`."""
    path, shas = history(tmp_path, files)
    prepared = undo.prepare(path, base=shas[0], head=shas[-1])
    return prepared.reverse({shas[n] for n in undone}), shas


def moved_texts(path: Path, base: str, head: str, commit: str) -> tuple[list[str], list[str]]:
    """The non-blank texts `commit` removed and added, as the run's `-U0` log has them."""
    (change,) = [
        change
        for change in authorship.changes(path, authorship.DOCUMENT_FILE, base, head)
        if change.commit == commit
    ]
    removed = [t.decode() for hunk in change.hunks for t in hunk.removed if t.strip()]
    added = [t.decode() for hunk in change.hunks for t in hunk.added if t.strip()]
    return removed, added


def test_an_insertion_reverts_cleanly(tmp_path: Path) -> None:
    base = document(
        HEADING + "Ранок починається з кави.\nВітер гойдає гілки.\n\nУчні повертаються додому.\n"
    )
    by_u = base.replace("кави.\n", "кави.\nНад містом пливуть хмари.\n")
    reversal, shas = reversed_run(tmp_path, [("a", base), ("a", by_u)], [1])
    assert reversal.head == shas[1]
    assert reversal.classified == (
        Classified(
            shas[1], "added", line_of(by_u, "Над містом пливуть хмари."),
            "Над містом пливуть хмари.", "clean", False,
        ),
    )  # fmt: skip
    assert reversal.body == base
    assert reversal.removed == frozenset({line_of(by_u, "Над містом пливуть хмари.")})
    assert reversal.inserted == {}
    assert reversal.listed == ()


def test_a_deletion_is_restored_between_its_neighbours(tmp_path: Path) -> None:
    sentence = "Сторож зачиняє ворота."
    base = document(
        HEADING
        + f"Сад відкривається о восьмій.\n{sentence}\nДоріжки посипані піском.\n\n"
        + "Фонтан працює влітку.\nЛавки пофарбовано торік.\n"
    )
    by_u = base.replace(f"{sentence}\n", "")
    by_v = by_u.replace("Лавки пофарбовано торік.", "Лавки пофарбовано навесні.")
    reversal, shas = reversed_run(tmp_path, [("a", base), ("a", by_u), ("b", by_v)], [1])
    assert reversal.classified == (
        Classified(shas[1], "removed", line_of(base, sentence), sentence, "clean", False),
    )
    assert reversal.body == by_v.replace("восьмій.\n", f"восьмій.\n{sentence}\n")
    assert reversal.inserted == {line_of(by_v, "Сад відкривається о восьмій."): (sentence,)}
    assert reversal.removed == frozenset()
    assert reversal.listed == ()


def test_a_rewrite_reverts(tmp_path: Path) -> None:
    s, s1 = "Міст фарбують щовесни.", "Міст фарбують щоосені."
    base = document(HEADING + f"Річка тече на південь.\n{s}\nЧовни стоять біля берега.\n")
    by_u = base.replace(s, s1)
    reversal, shas = reversed_run(tmp_path, [("a", base), ("a", by_u)], [1])
    assert set(reversal.classified) == {
        Classified(shas[1], "removed", line_of(base, s), s, "clean", False),
        Classified(shas[1], "added", line_of(by_u, s1), s1, "clean", False),
    }
    assert reversal.body == base
    assert reversal.listed == ()


def test_a_rewrite_built_on_is_listed_once(tmp_path: Path) -> None:
    s, s1, s2 = (
        "Бібліотека працює до сьомої.",
        "Бібліотека працює до восьмої.",
        "Бібліотека працює до дев'ятої.",
    )
    base = document(HEADING + f"Читальня на другому поверсі.\n{s}\nКаталог оновлено.\n")
    by_u = base.replace(s, s1)
    by_v = by_u.replace(s1, s2)
    reversal, shas = reversed_run(tmp_path, [("a", base), ("a", by_u), ("b", by_v)], [1])
    assert set(reversal.classified) == {
        Classified(shas[1], "removed", line_of(base, s), s, "built_on", True),
        Classified(shas[1], "added", line_of(by_u, s1), s1, "built_on", True),
    }
    assert reversal.listed == (Listed(where=line_of(by_v, s2), before=s, after=s2, wrote=s1),)
    assert reversal.body == by_v
    assert reversal.removed == frozenset()
    assert reversal.inserted == {}


def test_a_line_deleted_later_is_not_listed(tmp_path: Path) -> None:
    """DL-0422."""
    s = "Пором відходить щогодини."
    base = document(HEADING + "Порт відкрито цілий рік.\nМаяк світить уночі.\n")
    by_u = base.replace("рік.\n", f"рік.\n{s}\n")
    by_v = base
    reversal, shas = reversed_run(tmp_path, [("a", base), ("a", by_u), ("b", by_v)], [1])
    assert reversal.classified == (
        Classified(shas[1], "added", line_of(by_u, s), s, "built_on", False),
    )
    assert reversal.listed == ()
    assert reversal.body == by_v


def test_a_moved_paragraph_is_followed(tmp_path: Path) -> None:
    """The paragraph `u` added, moved by `v` within the section, is taken out with its blank
    line where it stands now."""
    paragraph = ["Вежу збудовано з цегли.", "Годинник б'є щогодини.", "Сходи ведуть на дах."]
    base_body = (
        HEADING
        + "Площа лежить у центрі.\nНа ній стоїть ратуша.\n\n"
        + "Ринок працює щосуботи.\n\n# Інші положення\n\nПарк зачиняють увечері.\n"
    )
    block = "\n".join(paragraph) + "\n\n"
    by_u_body = HEADING + block + base_body.removeprefix(HEADING)
    by_v_body = base_body.replace("щосуботи.\n\n", "щосуботи.\n\n" + block)
    base, by_u, by_v = document(base_body), document(by_u_body), document(by_v_body)
    path, shas = history(tmp_path, [("a", base), ("a", by_u), ("b", by_v)])
    # The log shows `v` moving the paragraph itself, not the text around it.
    removed, added = moved_texts(path, shas[0], shas[2], shas[2])
    assert sorted(removed) == sorted(added) == sorted(paragraph)
    reversal = undo.prepare(path, base=shas[0], head=shas[2]).reverse({shas[1]})
    assert set(reversal.classified) == {
        Classified(shas[1], "added", line_of(by_u, text), text, "clean", False)
        for text in paragraph
    }
    assert reversal.listed == ()
    assert "\n\n\n" not in reversal.body
    assert reversal.body == by_v.replace(block, "")
    assert reversal.body == base


def test_a_deletion_whose_place_changed_is_listed(tmp_path: Path) -> None:
    s, new = "Автобус приходить о дев'ятій.", "Таксі чекає біля входу."
    base = document(HEADING + f"Вокзал відкрито вдень.\n{s}\nКаса працює до обіду.\n")
    by_u = base.replace(f"{s}\n", "")
    by_v = by_u.replace("вдень.\n", f"вдень.\n{new}\n")
    reversal, shas = reversed_run(tmp_path, [("a", base), ("a", by_u), ("b", by_v)], [1])
    assert reversal.classified == (
        Classified(shas[1], "removed", line_of(base, s), s, "built_on", True),
    )
    assert reversal.listed == (Listed(where=line_of(by_v, new), before=s, after=new),)
    assert reversal.body == by_v


def test_an_ambiguous_move_is_not_guessed(tmp_path: Path) -> None:
    """The base holds one sentence twice; `u` moves one copy and rewrites another sentence.
    The move is not classified and stays; the rewrite reverts."""
    twice = "Двері відчиняються назовні."
    s, s1 = "Світло вмикається автоматично.", "Світло вмикається вручну."
    base = document(
        HEADING
        + f"{twice}\nКоридор має три виходи.\nЛіфт обслуговує всі поверхи.\n"
        + f"Сходи освітлено.\n{twice}\n\nПідвал зачинено.\n{s}\nГорище порожнє.\n"
    )
    by_u = document(
        HEADING
        + "Коридор має три виходи.\nЛіфт обслуговує всі поверхи.\nСходи освітлено.\n"
        + f"{twice}\n{twice}\n\nПідвал зачинено.\n{s1}\nГорище порожнє.\n"
    )
    path, shas = history(tmp_path, [("a", base), ("a", by_u)])
    # The log shows `u` removing and adding one copy of the repeated sentence.
    removed, added = moved_texts(path, shas[0], shas[1], shas[1])
    assert removed.count(twice) == added.count(twice) == 1
    reversal = undo.prepare(path, base=shas[0], head=shas[1]).reverse({shas[1]})
    assert all(entry.text != twice for entry in reversal.classified)
    assert set(reversal.classified) == {
        Classified(shas[1], "removed", line_of(base, s), s, "clean", False),
        Classified(shas[1], "added", line_of(by_u, s1), s1, "clean", False),
    }
    assert reversal.listed == ()
    assert reversal.body == by_u.replace(s1, s)


def test_an_authors_versions_are_undone_together(tmp_path: Path) -> None:
    """All of author A's versions undone together; what A wrote and A changed later is A's
    own business, never built on."""
    s, s1 = "Хор співає у неділю.", "Хор співає у суботу."
    base = document(
        HEADING + "Клуб відкрито для всіх.\nЗала вміщує сто людей.\n\n"
        "Оркестр репетирує щодня.\nКвитки продають у касі.\n"
    )
    by_u = base.replace("всіх.\n", f"всіх.\n{s}\n")
    by_v = by_u.replace("Оркестр репетирує щодня.", "Оркестр репетирує щовечора.")
    by_w = by_v.replace(s, s1)
    reversal, shas = reversed_run(
        tmp_path, [("base", base), ("A", by_u), ("B", by_v), ("A", by_w)], [1, 3]
    )
    assert set(reversal.classified) == {
        Classified(shas[1], "added", line_of(by_u, s), s, "clean", False),
        Classified(shas[3], "removed", line_of(by_v, s), s, "clean", False),
        Classified(shas[3], "added", line_of(by_w, s1), s1, "clean", False),
    }
    assert reversal.listed == ()
    assert reversal.inserted == {}
    assert reversal.removed == frozenset({line_of(by_w, s1)})
    assert reversal.body == by_w.replace(f"{s1}\n", "")
    assert reversal.body == base.replace("Оркестр репетирує щодня.", "Оркестр репетирує щовечора.")


def test_the_frontmatter_is_left(tmp_path: Path) -> None:
    s, s1 = "Вистава триває дві години.", "Вистава триває три години."
    body = HEADING + f"Театр має дві сцени.\n{s}\nАнтракт короткий.\n"
    base = document(body)
    by_u = document(body.replace(s, s1), title="Синтетичний порядок, нова назва")
    reversal, shas = reversed_run(tmp_path, [("a", base), ("a", by_u)], [1])
    assert set(reversal.classified) == {
        Classified(shas[1], "removed", line_of(base, s), s, "clean", False),
        Classified(shas[1], "added", line_of(by_u, s1), s1, "clean", False),
    }
    assert reversal.body == document(body, title="Синтетичний порядок, нова назва")
    assert reversal.listed == ()


def test_reverse_reads_no_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`prepare` reads the repository; `reverse` never does."""
    texts = [
        "Озеро замерзає взимку.",
        "Рибалки виходять на лід.",
        "Ковзанка відкрита щодня.",
        "Біля берега ростуть верби.",
        "Човни зберігають у сараї.",
    ]
    files = [("base", document(HEADING + "Село стоїть на пагорбі.\n"))]
    for n, text in enumerate(texts):
        files.append((f"author-{n % 2}", files[-1][1] + f"{text}\n"))
    path, shas = history(tmp_path, files)

    calls: list[tuple[str, ...]] = []
    real = authorship._git

    def counting(repository: Path, *args: str) -> bytes:
        calls.append(args)
        return real(repository, *args)

    monkeypatch.setattr(authorship, "_git", counting)
    prepared = undo.prepare(path, base=shas[0], head=shas[-1])
    assert calls

    def refused(*args: Any) -> bytes:
        raise AssertionError("reverse ran git")

    monkeypatch.setattr(authorship, "_git", refused)
    for sha, text in zip(shas[1:], texts, strict=True):
        reversal = prepared.reverse({sha})
        assert [(entry.version, entry.verdict) for entry in reversal.classified] == [(sha, "clean")]
        assert reversal.body == files[-1][1].replace(f"{text}\n", "")


def test_bad_arguments(tmp_path: Path) -> None:
    path, shas = history(
        tmp_path,
        [("a", document(HEADING + "Поле засіяно житом.\n")), ("a", document(HEADING + "Поле.\n"))],
    )
    with pytest.raises(ValueError):
        undo.prepare(path, base="abc", head=shas[-1])
    prepared = undo.prepare(path, base=shas[0], head=shas[-1])
    with pytest.raises(ValueError):
        prepared.reverse(set())
    with pytest.raises(ValueError):
        prepared.reverse({"0" * 40})


def test_a_built_on_place_shows_what_the_undone_edit_wrote(tmp_path: Path) -> None:
    """Both wordings of a place a later version built on: what the undone version wrote there, and
    what stands now — and, where it replaced text, what stood before it (ADR-0015)."""
    s = "Пором відходить щогодини."
    b_wording = "Пором відходить двічі на годину."
    base = document(HEADING + "Порт відкрито цілий рік.\nМаяк світить уночі.\n")
    by_u = base.replace("рік.\n", f"рік.\n{s}\n")
    by_v = by_u.replace(s, b_wording)
    reversal, _shas = reversed_run(tmp_path, [("a", base), ("a", by_u), ("b", by_v)], [1])
    assert reversal.listed == (
        Listed(where=line_of(by_v, b_wording), before="", after=b_wording, wrote=s),
    )


def test_a_line_rewritten_and_then_deleted_is_not_listed(tmp_path: Path) -> None:
    """DL-0422 applied to a chain: a later version rewrote the line, another deleted the rewrite;
    nothing of it stands, so nothing is left to edit."""
    s = "Пором відходить щогодини."
    rewritten = "Пором відходить двічі на годину."
    base = document(HEADING + "Порт відкрито цілий рік.\nМаяк світить уночі.\n")
    by_u = base.replace("рік.\n", f"рік.\n{s}\n")
    by_v = by_u.replace(s, rewritten)
    by_w = base
    reversal, _shas = reversed_run(
        tmp_path, [("a", base), ("a", by_u), ("b", by_v), ("c", by_w)], [1]
    )
    assert [(c.verdict, c.listed) for c in reversal.classified] == [("built_on", False)]
    assert reversal.listed == ()

"""The correction notice's core on small invented histories: the cases the move rule, the
frontmatter and the removal index decide, and its cost on a long run (ADR-0011, ADR-0014).

Authors are the numbers 1 to 3; the texts are invented."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from review import notices

pytestmark = pytest.mark.integration

DOMAIN = "users.noreply.syngraphe.local"
FRONT = (
    '---\ntitle: "Синтетичний порядок"\nlanguage: "uk"\ntitle_page: false\n'
    "appendices: []\nattachments: []\n---\n\n# Розділ\n\n"
)


def history(repo: Path, commits: list[tuple[int, str]]) -> list[str]:
    """A bare repository holding `document.md` at each `(author, text)`; the commits' shas."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(repo)], check=True, env=env)
    stream = bytearray()
    for mark, (author, text) in enumerate(commits, 1):
        who = f"{author} <{author}@{DOMAIN}> {1_800_000_000 + mark * 60} +0000"
        data = text.encode()
        stream += f"commit refs/heads/main\nmark :{mark}\nauthor {who}\ncommitter {who}\n".encode()
        stream += b"data 1\nx\n"
        if mark > 1:
            stream += f"from :{mark - 1}\n".encode()
        stream += f"M 100644 inline document.md\ndata {len(data)}\n".encode() + data + b"\n"
    marks = repo / "marks"
    subprocess.run(
        ["git", "-C", str(repo), "fast-import", "--quiet", f"--export-marks={marks}"],
        input=bytes(stream),
        check=True,
        env=env,
    )
    shas = dict(line.split(" ") for line in marks.read_text().splitlines())
    marks.unlink()
    return [shas[f":{n}"] for n in range(1, len(commits) + 1)]


def run_of(shas: list[str], authors: list[int]) -> list[notices.RunCommit]:
    """The run after the first commit, which is the base."""
    return [
        notices.RunCommit(sha=shas[n], parent=shas[n - 1], author=authors[n])
        for n in range(1, len(shas))
    ]


def found(tmp_path: Path, commits: list[tuple[int, str]], covered_by: int) -> list[notices.Entry]:
    repo = tmp_path / "doc.git"
    shas = history(repo, commits)
    authors = [author for author, _ in commits]
    covered = {shas[n] for n in range(1, len(shas)) if authors[n] == covered_by}
    return notices.entries(repo, base=shas[0], run=run_of(shas, authors), covered=covered)


def test_the_frontmatter_generates_nothing(tmp_path: Path) -> None:
    base = FRONT + "Перше.\n"
    by_a = base.replace("Синтетичний порядок", "Змінений автором") + "Друге.\n"
    by_r = by_a.replace("Змінений автором", "Змінений рецензентом")
    assert found(tmp_path, [(1, base), (2, by_a), (3, by_r)], covered_by=3) == []


def test_an_ambiguous_move_names_nobody(tmp_path: Path) -> None:
    """The base holds a sentence twice; author 2 moves one copy, author 3 replaces it: the text
    cannot say whose it was, so nothing is disclosed."""
    base = FRONT + "Спільне.\nПерше.\nДруге.\nСпільне.\n"
    moved = FRONT + "Спільне.\nСпільне.\nПерше.\nДруге.\n"
    replaced = FRONT + "Спільне.\nЗамінене.\nПерше.\nДруге.\n"
    assert found(tmp_path, [(1, base), (2, moved), (3, replaced)], covered_by=3) == []


def test_a_removal_undone_by_another_is_not_disclosed_again(tmp_path: Path) -> None:
    """Author 2 removes a line, author 1 puts it back, author 3 adds a second copy: author 3
    reversed nothing of author 2's."""
    base = FRONT + "Один.\n"
    written = base + "Два.\n"
    removed = base
    restored = base + "Два.\n"
    doubled = base + "Два.\nТри.\nДва.\n"
    commits = [(1, base), (2, written), (2, removed), (1, restored), (3, doubled)]
    assert [e for e in found(tmp_path, commits, covered_by=3) if e.kind == "restored"] == []


def test_an_undone_replacement_is_disclosed_once(tmp_path: Path) -> None:
    base = FRONT + "Один.\n"
    written = base + "Два.\n"
    replaced = base + "Два Б.\n"
    undone = base + "Два.\n"
    got = found(tmp_path, [(1, base), (1, written), (2, replaced), (3, undone)], covered_by=3)
    assert [(e.kind, e.author) for e in got] == [("line", 2)]


def test_a_restored_line_names_its_remover(tmp_path: Path) -> None:
    base = FRONT + "Один.\n"
    written = base + "Два.\n"
    removed = base
    restored = base + "Два.\n"
    got = found(tmp_path, [(1, base), (1, written), (2, removed), (3, restored)], covered_by=3)
    assert [(e.kind, e.author, e.range_before) for e in got] == [("restored", 2, "12")]


def test_a_long_run_costs_its_length(tmp_path: Path) -> None:
    """Two hundred versions of a four-hundred-line text, every other one covered, a move every
    fifth: seconds, never minutes."""
    lines = [f"Речення номер {n}." for n in range(400)]
    commits = [(1, FRONT + "\n".join(lines) + "\n")]
    for n in range(200):
        author = 3 if n % 2 else 2
        if n % 5 == 0:
            lines.insert(0, lines.pop(200 + n % 150))
        else:
            lines[(n * 7) % 400] = f"Правка {n} автора {author}."
        commits.append((author, FRONT + "\n".join(lines) + "\n"))
    started = time.monotonic()
    got = found(tmp_path, commits, covered_by=3)
    assert time.monotonic() - started < 20.0
    assert got and all(entry.changer == 3 and entry.author == 2 for entry in got)


def test_every_copy_of_an_ambiguous_text_names_nobody(tmp_path: Path) -> None:
    """The base holds a sentence twice; author 2 moves one copy; author 3 removes the copy the
    diff left in place: as the authorship rows say, nobody can be named (ADR-0011)."""
    base = FRONT + "Спільне.\nПерше.\nДруге.\nСпільне.\n"
    moved = FRONT + "Спільне.\nСпільне.\nПерше.\nДруге.\n"
    removed = FRONT + "Спільне.\nПерше.\nДруге.\n"
    assert found(tmp_path, [(1, base), (2, moved), (3, removed)], covered_by=3) == []

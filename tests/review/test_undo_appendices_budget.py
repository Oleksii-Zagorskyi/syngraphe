"""The undo over appendices within the undo's budget (DL-0135, DL-0447, V-17): at ASR-23's largest
document — a body of about 150 KB and five appendices of about 30 KB — and a run of 200 versions,
each changing the body and one appendix, *undo this edit* on the run's earliest version walks
every file the run touched and merges each file's reversal in under five seconds. What is timed is
what the act computes, without its database writes: the files the run touched, each file's walk and
reversal as `plan` takes them, and each file's merge into a draft that holds the head.

Judged alone: a run beside other test runs or the full suite measures the load, not the walk. The
document is generated here, invented English one sentence per line.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pygit2
import pytest

pytestmark = [pytest.mark.integration]

BUDGET_SECONDS = 5.0
VERSIONS = 200
WORDS = (
    "the applicant records each request in writing before the agreed date and keeps a copy for "
    "review by the office that answers it within the period this rule sets for every case"
).split()


def sentence(seed: int) -> str:
    """An invented English sentence of about sixty characters, distinct for each seed."""
    words = [WORDS[(seed * 7 + k * 3) % len(WORDS)] for k in range(9)]
    return f"Clause {seed}: " + " ".join(words) + "."


def text(heading: str, first: int, size: int) -> list[str]:
    """A heading, then paragraphs of four sentences, to about `size` bytes."""
    lines = [f"# {heading}", ""]
    n = first
    while sum(len(line) + 1 for line in lines) < size:
        lines += [sentence(n + k) for k in range(4)] + [""]
        n += 4
    return lines


def commit(repo: Any, files: dict[str, str], parent: str | None, n: int) -> str:
    builder = repo.TreeBuilder()
    folder = repo.TreeBuilder()
    for path, content in files.items():
        blob = repo.create_blob(content.encode("utf-8"))
        if path.startswith("appendices/"):
            folder.insert(path.removeprefix("appendices/"), blob, pygit2.GIT_FILEMODE_BLOB)
        else:
            builder.insert(path, blob, pygit2.GIT_FILEMODE_BLOB)
    builder.insert("appendices", folder.write(), pygit2.GIT_FILEMODE_TREE)
    who = pygit2.Signature(f"Author {n % 3}", f"author{n % 3}@example.test", 1_700_000_000 + n)
    parents = [pygit2.Oid(hex=parent)] if parent else []
    return str(repo.create_commit(None, who, who, f"Version {n}", builder.write(), parents))


@pytest.fixture(scope="module")
def envelope(tmp_path_factory: Any) -> dict[str, Any]:
    """The generated run: its repository, its base and head, and every commit oldest first."""
    from documents import bundle

    path: Path = tmp_path_factory.mktemp("undo-appendices") / "document.git"
    repo = pygit2.init_repository(str(path), bare=True)
    front = bundle.Frontmatter(title="Synthetic envelope", language="en")
    body = text("Purpose", 1, 150_000)
    appendices = [text(f"Appendix {a}", 100_000 * a, 30_000) for a in range(1, 6)]

    def files() -> dict[str, str]:
        out = {"document.md": bundle.render(front, "\n".join(body) + "\n")}
        for a, lines in enumerate(appendices, 1):
            out[f"appendices/{a}.md"] = "\n".join(lines) + "\n"
        return out

    shas = [commit(repo, files(), None, 0)]
    for n in range(1, VERSIONS + 1):
        # Each version rewrites one sentence of the body and one of an appendix, spread through
        # the files so a later version rarely builds on an earlier one's line.
        at = 2 + (n * 37) % (len(body) - 2)
        while not body[at] or body[at].startswith("#"):
            at += 1
        body[at] = sentence(1_000_000 + n)
        lines = appendices[n % 5]
        at = 2 + (n * 13) % (len(lines) - 2)
        while not lines[at] or lines[at].startswith("#"):
            at += 1
        lines[at] = sentence(2_000_000 + n)
        shas.append(commit(repo, files(), shas[-1], n))
    return {"path": path, "repo": repo, "commits": shas}


@pytest.mark.budget
def test_the_walk_over_appendices_meets_the_budget(envelope: dict[str, Any]) -> None:
    from review.notices import RunCommit, touched
    from review.undo import merge, prepare

    repo, path, commits = envelope["repo"], envelope["path"], envelope["commits"]
    base, head, undone = commits[0], commits[-1], {commits[1]}
    started = time.perf_counter()
    run = [RunCommit(sha, parent, "") for parent, sha in zip(commits, commits[1:], strict=False)]
    files = ["document.md", *touched(repo, run)]
    merged = 0
    for file in files:
        prepared = prepare(path, base=base, head=head, path=file)
        # As `plan` takes it: the file's own versions undone, classified, then reversed.
        new = undone & prepared.versions
        if not new or not prepared.reverse(new).classified:
            continue
        reversal = prepared.reverse(new)
        current = repo.revparse_single(f"{head}:{file}").data.decode("utf-8")
        draft = current if file != "document.md" else current.split("---\n", 2)[2]
        _text, _listed, applied = merge(current, reversal, draft, path=file)
        merged += applied["taken"] + applied["put"]
    elapsed = time.perf_counter() - started
    print(f"the undo over {len(files)} files: {elapsed:.3f} s over {VERSIONS} versions")
    size = sum(len(repo.revparse_single(f"{head}:{file}").data) for file in files)
    assert len(files) == 6 and merged and size > 290_000
    assert elapsed < BUDGET_SECONDS

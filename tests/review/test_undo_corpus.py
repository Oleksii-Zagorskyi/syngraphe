"""V-14 on the generated corpus: *undo this edit*, version by version, judged against the
generator's own record.

The corpus is invented, generated text: a Ukrainian document of about forty pages written by three
synthetic authors over three base commits and two hundred single edits (`tests/fixtures/corpus/`,
the V-05 corpus). Nothing in it comes from a real document.

The oracle here is written from the generator's record and the texts the repository holds, never
from the code it judges: for the version at commit `n`, every sentence `n` added and every sentence
it removed is classified as reverting cleanly or as built on by a later version, and listed for the
reviewer or not (ADR-0015, DL-0243, DL-0247; a sentence a later version deleted outright is built on
and not listed, DL-0422). The code's classification and its reversed text are compared
with it, every disagreement collected before the test fails.
"""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.integration

# The generator's three base commits come first; the edits follow.
BASE_COMMITS = 3
EDIT_KINDS = ("insert", "rewrite", "delete", "append", "move")
CATEGORIES = ("clean", "built_on listed", "built_on not listed")


# --- the texts -----------------------------------------------------------------------------------


def _documents(repo: Path, shas: list[str]) -> list[str]:
    """`document.md` at each commit, read from the repository in one batch."""
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    result = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input="".join(f"{sha}:document.md\n" for sha in shas).encode(),
        env=env,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    out, at, texts = result.stdout, 0, []
    for _ in shas:
        header_end = out.index(b"\n", at)
        size = int(out[at:header_end].split(b" ")[2])
        texts.append(out[header_end + 1 : header_end + 1 + size].decode("utf-8"))
        at = header_end + 1 + size + 1
    return texts


def _split(text: str) -> tuple[list[str], list[str]]:
    """The frontmatter's lines, fences included, and the body's lines."""
    lines = text.split("\n")
    if lines and lines[0] == "---":
        close = lines.index("---", 1)
        return lines[: close + 1], lines[close + 1 :]
    return [], lines


def _non_blank(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip()]


def _body(text: str) -> list[str]:
    """The body's non-blank lines, in order."""
    return _non_blank(_split(text)[1])


# --- the oracle ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Expected:
    side: str
    text: str
    verdict: str
    listed: bool
    # For a removed sentence: its neighbours in the parent, `None` at the body's edge.
    above: str | None = None
    below: str | None = None


@dataclass(frozen=True)
class Version:
    index: int
    n: int
    sha: str
    kind: str
    lines: dict[tuple[str, str], Expected]

    def label(self) -> str:
        return f"commit {self.n} ({self.kind})"


def _category(verdict: str, listed: bool) -> str:
    return "clean" if verdict == "clean" else f"built_on {'listed' if listed else 'not listed'}"


def _rewritten_later(sentences: dict[str, Any], sentence: dict[str, Any]) -> bool:
    """The record says a later version rewrote it and something of the rewriting still stands:
    the last successor along `replaced_by` is live. A chain rewritten and then deleted leaves
    nothing to edit, and is not listed (DL-0422)."""
    if sentence["status"] != "rewritten":
        return False
    last = sentence
    while last["replaced_by"] is not None:
        last = sentences[str(last["replaced_by"])]
    return bool(last["status"] == "live")


def _oracle(
    commits: list[dict[str, Any]], truth: dict[str, Any], texts: list[str]
) -> list[Version]:
    """What *undo this edit* must say for every commit after the base commits, from the record and
    the texts alone. Asserts first that the record and the texts agree on what each commit added
    and removed: if they do not, the corpus is wrong, not the code under test."""
    sentences = truth["sentences"]
    head = _body(texts[-1])
    assert len(set(head)) == len(head), "a non-blank body line repeats at the head"
    head_at = {line: i for i, line in enumerate(head)}
    versions = []
    for index in range(BASE_COMMITS, len(commits)):
        commit = commits[index]
        n, kind = commit["n"], commit["kind"]
        before, after = _body(texts[index - 1]), _body(texts[index])
        by_text_added = set(after) - set(before)
        by_text_removed = set(before) - set(after)
        added = {s["text"]: s for s in sentences.values() if s["created"] == n}
        removed = {s["text"]: s for s in sentences.values() if s["changed_at"] == n}
        assert set(added) == by_text_added, f"commit {n}: the record and the texts differ on adds"
        assert set(removed) == by_text_removed, (
            f"commit {n}: the record and the texts differ on removals"
        )
        if kind == "move":
            assert not added and not removed, f"commit {n}: a move adds or removes a sentence"
        lines: dict[tuple[str, str], Expected] = {}
        for text, sentence in added.items():
            at_head = text in head_at
            assert at_head == (sentence["status"] == "live"), f"commit {n}: {text!r} status"
            listed = not at_head and _rewritten_later(sentences, sentence)
            lines[("added", text)] = Expected(
                "added", text, "clean" if at_head else "built_on", listed
            )
        for text in removed:
            position = before.index(text)
            above = next(
                (line for line in reversed(before[:position]) if line not in removed), None
            )
            below = next((line for line in before[position + 1 :] if line not in removed), None)
            clean = (above is None or above in head_at) and (below is None or below in head_at)
            if clean:
                low = head_at[above] if above is not None else -1
                high = head_at[below] if below is not None else len(head)
                clean = low < high and all(line in added for line in head[low + 1 : high])
            lines[("removed", text)] = Expected(
                "removed", text, "clean" if clean else "built_on", not clean, above, below
            )
        versions.append(Version(index, n, commit["sha"], kind, lines))
    return versions


# --- fixtures ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def texts(platform_corpus: dict[str, Any]) -> list[str]:
    return _documents(platform_corpus["repo"], [c["sha"] for c in platform_corpus["commits"]])


@pytest.fixture(scope="module")
def oracle(platform_corpus: dict[str, Any], texts: list[str]) -> list[Version]:
    return _oracle(platform_corpus["commits"], platform_corpus["truth"], texts)


@pytest.fixture(scope="module")
def prepared(platform_corpus: dict[str, Any]) -> Any:
    from review.undo import prepare

    commits = platform_corpus["commits"]
    return prepare(platform_corpus["repo"], base=commits[0]["sha"], head=commits[-1]["sha"])


@pytest.fixture(scope="module")
def reversals(prepared: Any, oracle: list[Version]) -> dict[int, Any]:
    """Each version's reversal, or the exception `reverse` raised for it."""
    done: dict[int, Any] = {}
    for version in oracle:
        try:
            done[version.n] = prepared.reverse({version.sha})
        except Exception as error:  # noqa: BLE001 - a raise is one more disagreement to list
            done[version.n] = error
    return done


# --- the comparison ------------------------------------------------------------------------------


def _short(text: str | None) -> str:
    if text is None:
        return "<edge>"
    return repr(text if len(text) <= 70 else text[:67] + "...")


def _classification_disagreements(version: Version, classified: Any) -> list[str]:
    where, found = version.label(), []
    got: dict[tuple[str, str], list[Any]] = {}
    for item in classified:
        got.setdefault((item.side, item.text), []).append(item)
    for key, items in got.items():
        if key not in version.lines:
            found.append(
                f"{where}: classified a line the version did not change: {key[0]} {_short(key[1])}"
            )
        elif len(items) > 1:
            found.append(f"{where}: {key[0]} {_short(key[1])} classified {len(items)} times")
    for key, expected in version.lines.items():
        if key not in got:
            found.append(f"{where}: {key[0]} {_short(key[1])} not classified")
            continue
        item = got[key][0]
        if (item.verdict, item.listed) != (expected.verdict, expected.listed):
            found.append(
                f"{where}: {key[0]} {_short(key[1])} is {item.verdict}, listed={item.listed}; "
                f"the record says {expected.verdict}, listed={expected.listed}"
            )
    return found


def _body_disagreements(version: Version, body: Any, head_text: str) -> list[str]:
    where, found = version.label(), []
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    frontmatter, lines = _split(body)
    head_frontmatter, head_lines = _split(head_text)
    drafted, head = _non_blank(lines), _non_blank(head_lines)
    if frontmatter != head_frontmatter:
        found.append(f"{where}: the draft's frontmatter differs from the head's")
    for expected in version.lines.values():
        if expected.verdict != "clean":
            continue
        if expected.side == "added":
            if expected.text in drafted:
                found.append(f"{where}: clean added {_short(expected.text)} still in the draft")
            continue
        count = drafted.count(expected.text)
        if count != 1:
            found.append(
                f"{where}: clean removed {_short(expected.text)} {count} times in the draft"
            )
            continue
        at = drafted.index(expected.text)
        above = drafted[at - 1] if at > 0 else None
        below = drafted[at + 1] if at + 1 < len(drafted) else None
        if (above, below) != (expected.above, expected.below):
            found.append(
                f"{where}: clean removed {_short(expected.text)} back between {_short(above)} and "
                f"{_short(below)}; its neighbours were {_short(expected.above)} and "
                f"{_short(expected.below)}"
            )
    own = {expected.text for expected in version.lines.values()}
    if [line for line in drafted if line not in own] != [line for line in head if line not in own]:
        found.append(
            f"{where}: the draft's other lines differ from the head's, or their order does"
        )
    return found


# --- the tests -----------------------------------------------------------------------------------


def test_v14_per_version_reversal_matches_the_record(
    oracle: list[Version], reversals: dict[int, Any], texts: list[str]
) -> None:
    disagreements: list[str] = []
    for version in oracle:
        reversal = reversals[version.n]
        if isinstance(reversal, Exception):
            disagreements.append(f"{version.label()}: reverse raised {reversal!r}")
            continue
        disagreements += _classification_disagreements(version, reversal.classified)
        disagreements += _body_disagreements(version, reversal.body, texts[-1])
    if disagreements:
        pytest.fail(
            f"{len(disagreements)} disagreements with the record over {len(oracle)} versions:\n"
            + "\n".join(disagreements),
            pytrace=False,
        )


def _table(counts: Counter[tuple[str, str]]) -> str:
    rows = [f"{'kind':<8} " + " ".join(f"{c:>20}" for c in CATEGORIES)]
    for kind in EDIT_KINDS:
        rows.append(f"{kind:<8} " + " ".join(f"{counts[kind, c]:>20}" for c in CATEGORIES))
    rows.append(
        f"{'all':<8} "
        + " ".join(f"{sum(counts[k, c] for k in EDIT_KINDS):>20}" for c in CATEGORIES)
    )
    return "\n".join(rows)


def test_v14_the_corpus_exercises_every_verdict(
    oracle: list[Version], reversals: dict[int, Any]
) -> None:
    expected: Counter[tuple[str, str]] = Counter()
    returned: Counter[tuple[str, str]] = Counter()
    raised = 0
    for version in oracle:
        for line in version.lines.values():
            expected[version.kind, _category(line.verdict, line.listed)] += 1
        reversal = reversals[version.n]
        if isinstance(reversal, Exception):
            raised += 1
            continue
        for item in reversal.classified:
            returned[version.kind, _category(item.verdict, item.listed)] += 1
    print(f"\nV-14, the record's verdicts by edit kind over {len(oracle)} versions:")
    print(_table(expected))
    print(f"V-14, the verdicts `reverse` returned ({raised} versions raised):")
    print(_table(returned))
    total = {c: sum(expected[k, c] for k in EDIT_KINDS) for c in CATEGORIES}
    absent = [c for c in CATEGORIES if not total[c]]
    assert not absent, (
        f"the corpus does not exercise the claim: no {', '.join(absent)} in the record"
    )
    never = [c for c in CATEGORIES if not sum(returned[k, c] for k in EDIT_KINDS)]
    assert not never, f"`reverse` never returned {', '.join(never)}"


def test_v14_the_last_version_reverts_whole(
    platform_corpus: dict[str, Any], prepared: Any, texts: list[str], oracle: list[Version]
) -> None:
    last = platform_corpus["commits"][-1]
    assert oracle[-1].lines, "the corpus's last commit changes no line; the row needs another"
    reversal = prepared.reverse({last["sha"]})
    assert reversal.classified, "the last version's lines are not classified"
    not_clean = [
        (item.side, item.text, item.verdict)
        for item in reversal.classified
        if item.verdict != "clean"
    ]
    assert not not_clean, f"lines of the last version not clean: {not_clean}"
    body = reversal.body
    if isinstance(body, str):
        body = body.encode("utf-8")
    assert body == texts[-2].encode("utf-8")

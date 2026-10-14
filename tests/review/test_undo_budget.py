"""The undo's walk within the authorship budget (DL-0135, V-14): *undo this edit* on the earliest
version of the longest run — the generated corpus's 202 commits after its first — read from the
repository and reversed in under five seconds.

Judged alone: a run beside other test runs or the full suite measures the load, not the walk. The
corpus is the invented one of `tests/fixtures/corpus/`.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

pytestmark = [pytest.mark.integration]

BUDGET_SECONDS = 5.0


@pytest.mark.budget
def test_the_walk_meets_the_budget(platform_corpus: dict[str, Any]) -> None:
    from review.undo import prepare

    commits = platform_corpus["commits"]
    started = time.perf_counter()
    prepared = prepare(platform_corpus["repo"], base=commits[0]["sha"], head=commits[-1]["sha"])
    reversal = prepared.reverse({commits[1]["sha"]})
    elapsed = time.perf_counter() - started
    assert reversal.classified
    print(f"the walk: {elapsed:.3f} s over {len(commits) - 1} versions")
    assert elapsed < BUDGET_SECONDS


@pytest.mark.budget
def test_the_merge_into_the_draft_is_bounded() -> None:
    """The three-way merge after the walk, on the text that makes an unbounded alignment slowest:
    one short line repeated to the body's ceiling, the first and the last changed. It meets the
    walk's budget and still yields the reversal where the draft holds the base."""
    from documents import bundle
    from editing.markdown import load_spec
    from review.undo import Reversal, merge

    line = "# h\n"
    count = load_spec().max_bytes // len(line) - 2
    base_body = "# first\n" + line * count + "# last\n"
    wanted_body = line * (count + 2)
    front = bundle.Frontmatter(title="Synthetic repeated headings", language="en")
    reversal = Reversal(
        head="",
        body=bundle.render(front, wanted_body),
        removed=frozenset(),
        inserted={},
        listed=(),
        classified=(),
    )
    started = time.perf_counter()
    body, listed, _applied = merge(bundle.render(front, base_body), reversal, base_body)
    elapsed = time.perf_counter() - started
    print(f"the merge: {elapsed:.3f} s over {count + 2} lines")
    assert elapsed < BUDGET_SECONDS
    assert body == wanted_body and not listed

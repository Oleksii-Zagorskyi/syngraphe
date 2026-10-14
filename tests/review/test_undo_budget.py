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

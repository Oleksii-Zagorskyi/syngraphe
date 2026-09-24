---
tags:
  - testing
aliases:
  - Syngraphē test strategy
status: draft
date: 2026-09-23
---

# Test strategy

One shape of test for every epic, so twelve epics do not produce twelve. It says which levels exist, what CI runs, and what *tests done* means for a story.

> [!note] Target state — in force from Epic 2, Story 1
> This is the plan the code is tested against, written before the code. It takes effect with Epic 2's first story, which adds the first code and the package definition CI installs.

## What CI runs

The command a developer runs locally is the command CI runs — never a variant reconstructed per session:

```bash
ruff check . && ruff format --check . && mypy src && pytest -q
```

CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs it on every push and pull request, on Python 3.12, with PostgreSQL and Redis as real services. A red build is fixed before the next story starts.

## Levels

**Fast tests — no database, no repository.** The pure logic: the normalizer and its sentence splitter, the whitelist parser, the canonical table row, permission decisions computed from given rows, render rules such as paragraph numbering. They run as a group in about a second, so they can run constantly while working.

**Integration tests — a real PostgreSQL and real bare repositories.** Anything that crosses the two stores runs against both for real: tenant schemas created and migrated, repositories initialised in a temporary directory, commits made through the git service layer. Neither store is mocked, because the write protocol between them is the thing most likely to be wrong and a mock would agree with whatever the code assumes. Celery tasks are tested by calling them as functions against their rows; the broker is outside the test, since every task has a row behind it.

**Crash tests — the process dies between two steps.** Every multi-step write the design names is tested by stopping it at each step and proving the reconciler repairs the result: a row without its repository, a commit without its row, a draft whose hold was forced. These are integration tests with a deliberate interruption, and they exist because the design's safety depends on repair rather than on nothing failing.

**Invariant tests — one or more per ASR that can be broken by code.** Tenant isolation holds when a query forgets its filter (ASR-01); history is never rewritten (ASR-02); a stored line is never re-normalised (ASR-20); stored content never executes and the renderer never fetches (ASR-19); no notification carries document text. Each is named for the invariant, so a failure reads as the requirement it breaks.

**The conformance suite — one case list, two enforcement points.** Every whitelist case marked accept or reject, run against the server-side parser in CI and against the editor in the browser tests; a divergence fails both (`verification-plan.md` V-04).

**Browser tests — the editor and the review surface.** End-to-end flows through a real browser: take, edit, send for review, accept, freeze. The tool is chosen in Epic 4, where the editor exists to test. Browser tests are complemented, not replaced, by QA sessions — a person or a separate session using the running application and writing a log the developer works through.

**Performance** is not measured by the test suite. The numbers in `asr.md` are verified by measurement against the running system, and the design's unproven speed claims live in [`verification-plan.md`](verification-plan.md).

## What is not tested

The framework itself, third-party library behaviour, and exact markup. Test the use of a library, not the library; and markup belongs to browser tests and QA, where a cosmetic change does not fail a unit test.

## Test material

**Invented, always** — the data boundary in `CLAUDE.md` has no exception for tests. Realistic Ukrainian prose is written for the purpose; the synthetic policy sample from Epic 1 DD-3 may become the normalizer's fixture. Test data is fixed, never random or time-dependent, and datetimes are UTC.

Tests live in `tests/` at the repository root, one file per functional area, named for the area; test functions are named for the behaviour, so a failure says what broke.

## Tests done, for a story

A story's tests are done when all of these hold:

1. **Every behaviour the story adds has a test**, written in the story, not deferred to a later one. An epic's documentation or consolidation story fills gaps; it does not excuse a story from writing its own.
2. **Every refusal path is tested** — the unauthorised caller, the input outside the whitelist, the other tenant's object. A permission that is only tested for the permitted case is untested.
3. **Every ASR the story touches has its invariant test**, new or already existing and still green.
4. **Every multi-step write the story adds has its crash test.**
5. **The CI command passes locally**, in full, not only the new tests.
6. **What tests cannot see has been looked at** — the page opened, the row queried, the export read — and the completion note says so.

A failing test is fixed before the next story starts, and the completion note records the failure and its fix.

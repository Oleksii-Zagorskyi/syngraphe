---
tags:
  - testing
aliases:
  - Syngraphē test strategy
status: draft
date: 2026-09-23
last-updated: 2026-10-14
---

# Test strategy

One shape of test for every epic, so no epic invents its own. It says which levels exist, the command that runs each, what CI runs, where the fixtures come from, and what *tests done* means for a story. A plan for a piece of work cites this document instead of repeating it.

> [!note] Target state — in force from the first story that adds code
> This is the plan the code is tested against, written before the code. It takes effect with the story that adds the package definition CI installs.

## What CI runs

The commands a developer runs locally are the commands CI runs — never a variant reconstructed per session. The first prepares a fresh clone, and runs again whenever a lockfile changes: it installs the Python dependencies from `uv.lock` (DL-0270) and the editor's from `package-lock.json`, builds the editor's bundle with esbuild, and installs the Chromium the browser tests drive (DL-0274). The second is the check:

```bash
uv sync --locked && npm ci && npm run build && uv run playwright install chromium
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q -n auto -m "not budget" && uv run pytest -q -m budget --durations=0
```

The tests run on one worker per core (`pytest-xdist`), each worker with a test database of its own, and every run with a database name of its own, so two runs on one server never share one (DL-0428). The suite refuses a database server that archives its log: the stack's `db` sends every segment to the backup store, and a test run's would go with it (DL-0430). The timing budgets, marked `budget`, run afterwards in a process of their own: beside the workers they measure the load. Each one's time is printed, so its margin shows on a green run, not only on a red one — a shared CI runner is slower than a developer's machine, and a budget that passes there by a few milliseconds is visible before it fails. A single file or test runs without `-n`, in one process.

The check needs PostgreSQL and Redis running — on a developer's machine the developer override's `test-db`, at `POSTGRES_TEST_PORT`, and the stack's `redis`; services in CI — and GNU gettext on the path, whose `xgettext` the catalogue test runs through `makemessages`, with Pango and HarfBuzz, which weasyprint loads for the PDF export tests: the developer's package manager installs them, CI a step of its own. The browser and conformance levels start the application themselves, as a live server inside the test run, so nothing else has to be started first.

CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs both on every push and pull request, on Python 3.12, the timing budgets as a step of their own. A red build is fixed before the next story starts.

## Levels

Each level is a pytest marker, so it can run alone while working and CI runs them all. A test carries exactly one level marker; a test that asserts on elapsed time also carries `budget`. **A budget is one of two kinds.** A user-facing budget (ASR-21) promises a time on the reference machine and asserts it. A guard against cost that grows faster than its input asserts the **growth** — the time at one size against the time at four times that size, the median of a few runs — never a time on whatever machine runs it, which a slower runner breaks while the code is linear.

| Level | Marker | Runs against | Command |
|---|---|---|---|
| Fast | `fast` | nothing — pure functions | `pytest -m fast` |
| Integration | `integration` | a real PostgreSQL and real bare repositories | `pytest -m integration` |
| Crash | `crash` | the same, with the process stopped between two steps | `pytest -m crash` |
| Invariant | `invariant` | whichever store the requirement binds | `pytest -m invariant` |
| Conformance | `conformance` | the server-side parser and the renderer's output; and the editor, through the browser | `pytest -m conformance` |
| Browser | `browser` | the running application in Chromium | `pytest -m browser` |

**Fast tests — no database, no repository.** The pure logic: the normalizer and its sentence splitter, the whitelist parser and validator, the canonical table row, permission decisions computed from given rows, render rules such as clause numbering. They run as a group in about a second, so they can run constantly while working.

**Integration tests — a real PostgreSQL and real bare repositories.** Anything that crosses the two stores runs against both for real: tenant schemas created and migrated, repositories initialised in a temporary directory, commits made through the git service layer. Neither store is mocked, because the write protocol between them is the thing most likely to be wrong and a mock would agree with whatever the code assumes. Celery tasks are tested by calling them as functions against their rows; the broker is outside the test, since every task has a row behind it. An export test reads the produced file back — the PDF's text and outline, the DOCX's styles and runs — and asserts on what it finds, never on the renderer having returned.

**Crash tests — the process dies between two steps.** Every multi-step write the design names is tested by stopping it at each step and proving the reconciler repairs the result: a row without its repository, a commit without its row, a draft whose hold was forced. These are integration tests with a deliberate interruption, and they exist because the design's safety depends on repair rather than on nothing failing.

**Invariant tests — one or more per ASR that can be broken by code.** Tenant isolation holds when a query forgets its filter (ASR-01); history is never rewritten (ASR-02); a stored line is never re-normalised (ASR-20); stored content never executes and the renderer never fetches (ASR-19); a link grants no access (ASR-16); no notification carries document text. Each is named for the invariant, so a failure reads as the requirement it breaks.

**The conformance suite — one case list, two enforcement points.** Every whitelist case marked accept or reject, run against the server-side parser in CI and against the editor in the browser; a divergence fails both ([`verification-plan.md`](verification-plan.md) V-04). Its third subject is the server-side renderer: for every accept case the suite fixes the renderer's exact output, because the renderer's rules exist on the server alone and have no twin to be compared with ([`ADR-0013`](adr/ADR-0013-one-parse-for-every-render-target.md)). The case list is data.

**Browser tests — the editor and the review surface.** End-to-end flows through Chromium driven by Playwright, headless in CI and headed on a developer's machine: take, edit, paste, send for review, accept, freeze. They are the scripted sweep; they run beside, and never replace, a QA session — a person, or a separate session, using the running application in a real browser and writing a log the developer works through. A demonstration of a finished slice (DL-0122) is a QA session.

**Performance** is not measured by the test suite. The numbers in [`asr.md`](asr.md) are verified by measurement against the running system, and the design's unproven speed claims live in the verification plan.

## What is not tested

The framework itself, third-party library behaviour, and the exact markup of page templates. Test the use of a library, not the library; and a page's markup belongs to browser tests and QA, where a cosmetic change does not fail a unit test. The renderer's output is not page markup: the conformance suite fixes it.

## Fixtures

All in `tests/fixtures/`, all invented, all generated or written for the purpose — the data boundary in [`CLAUDE.md`](../CLAUDE.md) has no exception for tests.

| Fixture | Holds | Used by |
|---|---|---|
| `corpus/` | two synthetic document histories, Ukrainian and English — a policy of about forty pages, two hundred single-edit commits by three authors, twenty tags — and the record of who wrote every sentence and what happened to it; the generator that made them sits beside them | attribution, per-author undo, blame, repack |
| `splitter/` | the two corpora enriched with the hard cases — clause references, abbreviations, initials, amounts, quotations, lists, callouts, spans — every intended sentence boundary marked, and the counts per case; the six planted bad breaks as negative cases | the normalizer's splitter and its parse-preservation check |
| `whitelist/` | the conformance case list: every construct accepted, every refusal with its stable code and line, every re-spelling with its stored form; `golden/`, the reading view's HTML for every accept case, written from the renderer's rules, never from its output | the parser, the validator, the editor, the renderer |
| `render/` | the conformance sample carrying every whitelist construct in invented Ukrainian, its Markdown export before the headings are numbered, the negative sample with a remote image, and the clause-numbering cases both numbering twins run | the reading view, the gutter, PDF, DOCX and Markdown |
| `load/` | invented folders in the form `load_document` reads, each with its attachments | the loader |
| `documents/` | small invented documents for flows: a two-section policy, one with an appendix and an attachment, one in each language | integration and browser tests |

Fixed, never random or time-dependent; datetimes are UTC. A generated fixture — `corpus/`, `splitter/` — is regenerated by its script, never edited by hand.

## Layout

Tests live in `tests/` at the repository root, one directory per functional area, named for the app it tests, and one file per topic — `tests/documents/test_create.py`, `tests/editing/test_splitter.py` — so a test can be named, as `tests/{area}/test_{topic}.py::test_{behaviour}`, before the code it tests exists. Test functions are named for the behaviour, so a failure says what broke. Shared fixtures — a migrated tenant schema, a temporary repository root, a signed-in client per role — are in `tests/conftest.py`.

**A test reaches the tenant, the repositories and the files through these fixtures, never a fixed path or number.** `migrated_tenant` is one schema per worker, migrated once and put back to its migrated state before every test that takes it — its rows, and its sequences, so document numbers start again at 1. Its number is the same in every test of a worker, so each such test gets a repository root of its own. Another tenant comes from `make_tenant_schema`, which migrates a schema of its own. Everything a test writes goes under `tmp_path` or the roots the fixtures set.

## Tests done, for a story

A story's tests are done when all of these hold:

1. **Every behaviour the story adds has a test**, written in the story, not deferred to a later one. An epic's documentation or consolidation story fills gaps; it does not excuse a story from writing its own.
2. **Every refusal path is tested** — the unauthorised caller, the input outside the whitelist, the other tenant's object. A permission that is only tested for the permitted case is untested.
3. **Every ASR the story touches has its invariant test**, new or already existing and still green.
4. **Every multi-step write the story adds has its crash test.**
5. **The tests the change can reach pass**, selected from the change rather than listed by hand — by a coverage-based selector, or by the changed files: their app's tests and every test that imports a changed module. **The CI command passes locally in full** after a change to a shared core — the models and migrations, the settings, the renderer, the editor's parser and commit path, the templates, the message catalogue — at least every third story, and always before the work is committed.
6. **What tests cannot see has been looked at** — the page opened, the row queried, the export read — and the completion note says so.

A failing test is fixed before the next story starts, and the completion note records the failure and its fix.

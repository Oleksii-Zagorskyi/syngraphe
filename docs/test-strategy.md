---
tags:
  - testing
aliases:
  - Syngraphē test strategy
status: active
date: 2026-09-23
last-updated: 2026-11-12
---

# Test strategy

One shape of test for every epic, so no epic invents its own. It says which levels exist, the command that runs each, what CI runs, where the fixtures come from, and what *tests done* means for a story. A plan for a piece of work cites this document instead of repeating it.

## What CI runs

The commands a developer runs locally are the commands CI runs — never a variant reconstructed per session. The first prepares a fresh clone, and runs again whenever a lockfile changes: it installs the Python dependencies from `uv.lock` (DL-0270) and the editor's from `package-lock.json`, builds the editor's bundle with esbuild, and installs the Chromium the browser tests drive (DL-0274). The second is the check:

```bash
uv sync --locked && npm ci && npm run build && uv run playwright install chromium
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run python scripts/check_record.py && uv run pytest -q -n auto -m "not budget" && uv run pytest -q -m budget --durations=0
```

`scripts/check_record.py` checks what the record must keep true and a script can decide: every cited decision row, ADR, story, verification claim and backlog row exists, and no superseded row is cited as current; the coverage table is current; each page's stories are its regions'; the help index and the page list agree; every address of a document is in the technical design; the glossary's never-used words stay out of the interface; across the decision logs and the ADRs, every supersession is named on both rows, every status is one of the set and every id is unique. A glossary term on an English help page without its pair on the Ukrainian one is printed as advice and fails nothing.

The tests run on one worker per core (`pytest-xdist`), each worker with a test database of its own, and every run with a database name of its own, so two runs on one server never share one (DL-0428). The suite refuses a database server that archives its log: the stack's `db` sends every segment to the backup store, and a test run's would go with it (DL-0430). The timing budgets, marked `budget`, run afterwards in a process of their own: beside the workers they measure the load. Each one's time is printed, so its margin shows on a green run, not only on a red one — a shared CI runner is slower than a developer's machine, and a budget that passes there by a few milliseconds is visible before it fails. A single file or test runs without `-n`, in one process.

The check needs PostgreSQL and Redis running — on a developer's machine the developer override's `test-db`, at `POSTGRES_TEST_PORT`, and the stack's `redis`; services in CI — and GNU gettext on the path, whose `xgettext` the catalogue test runs through `makemessages`, with Pango and HarfBuzz, which weasyprint loads for the PDF export tests: the developer's package manager installs them, CI a step of its own. The browser and conformance levels start the application themselves, as a live server inside the test run, so nothing else has to be started first.

CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs both on every push to every branch, and so on the merge commit on `main` (DL-0431), on Python 3.12, the timing budgets as a step of their own. A red build is fixed before the next story starts.

From release 0.2 CI also checks that the prompt version each prompt loads has its committed, passing eval results, and calls no model to do it (§ Evals, DL-0563, DL-0576).

## Levels

Each level is a pytest marker, so it can run alone while working and CI runs them all. A test carries one level marker, with two exceptions: a crash test carries `crash` and `integration`, since it is an integration test; and a pure test inside an integration module carries `fast` beside the module's `integration`. The tests of the Compose files in `tests/foundation/` carry no level and run only in the full check. A test that asserts on elapsed time also carries `budget`. **A budget is one of two kinds.** A user-facing budget (ASR-21) promises a time on the reference machine and asserts it. A guard against cost that grows faster than its input asserts the **growth** — the time at one size against the time at four times that size, the median of a few runs — never a time on whatever machine runs it, which a slower runner breaks while the code is linear.

| Level | Marker | Runs against | Command |
|---|---|---|---|
| Fast | `fast` | nothing — pure functions | `pytest -m fast` |
| Integration | `integration` | a real PostgreSQL and real bare repositories | `pytest -m integration` |
| Crash | `crash` | the same, with the process stopped between two steps | `pytest -m crash` |
| Invariant | `invariant` | whichever store the requirement binds | `pytest -m invariant` |
| Conformance | `conformance` | the server-side parser and the renderer's output; and the editor, through the browser | `pytest -m conformance` |
| Browser | `browser` | the running application in Chromium | `pytest -m browser` |

**Fast tests — no database, no repository.** The pure logic: the normalizer and its sentence splitter, the whitelist parser and validator, the canonical table row, permission decisions computed from given rows, render rules such as clause numbering. They run as a group in about a second, so they can run constantly while working.

**Integration tests — a real PostgreSQL and real bare repositories.** Anything that crosses the two stores runs against both for real: tenant schemas created and migrated, repositories initialised in a temporary directory, commits made through the git service layer. Neither store is mocked, because the write protocol between them is the thing most likely to be wrong and a mock would agree with whatever the code assumes. Celery tasks are tested by calling them as functions against their rows; the broker is outside the test, since every task has a row behind it — but for one smoke test, which sends a task through Redis to a worker of the run's own, on a queue of the run's own. An export test reads the produced file back — the PDF's text and outline, the DOCX's styles and runs — and asserts on what it finds, never on the renderer having returned.

**Crash tests — the process dies between two steps.** Every multi-step write the design names is tested by stopping it at each step and proving the reconciler repairs the result: a row without its repository, a commit without its row, a draft whose hold was forced. These are integration tests with a deliberate interruption, and they exist because the design's safety depends on repair rather than on nothing failing.

**Invariant tests — one or more per ASR that can be broken by code.** Tenant isolation holds when a query forgets its filter (ASR-01); history is never rewritten (ASR-02); a stored line is never re-normalised (ASR-20); stored content never executes and the renderer never fetches (ASR-19); a link grants no access (ASR-16); no notification carries document text. Each is named for the invariant, so a failure reads as the requirement it breaks. The `invariant` marker is carried by the tests of tenant isolation (ASR-01), untouched lines (ASR-20), the one not-found answer and the email's content; the tests of ASR-02, ASR-16 and ASR-19 run at the level of the store they need — integration or fast — and `pytest -m invariant` does not select them.

**The route sweep — every route closed to a blocked organisation.** `tests/tenancy/test_blocked_sweep.py` walks the resolver: each route, its arguments filled, is first reached while the organisation is active, then must answer *Nothing to show here* to its member once blocked, by `GET` and `POST`, on the organisation's own domain and from the platform host (ST-0065). A route no fill reaches while active, and a route that reads no organisation's content, is listed with its reason; a new route is swept as it stands, or fails naming the keyword the filler lacks.

**The conformance suite — one case list, two enforcement points.** Every whitelist case marked accept or reject, run against the server-side parser in CI and against the editor in the browser; a divergence fails both ([`verification-plan.md`](verification-plan.md) V-04). Its third subject is the server-side renderer: for every accept case the suite fixes the renderer's exact output, because the renderer's rules exist on the server alone and have no twin to be compared with ([`ADR-0013`](adr/ADR-0013-one-parse-for-every-render-target.md)). The case list is data.

**Browser tests — the editor and the review surface.** End-to-end flows through Chromium driven by Playwright: take, edit, paste, send for review, accept, freeze. They run headless in CI and on a developer's machine alike; `--headed` shows the browser while working on one test. They are the scripted sweep; they run beside, and never replace, a QA session — a person, or a separate session, using the running application in a real browser and writing a log the developer works through. A demonstration of a finished slice (DL-0122) is a QA session.

**Performance** is not measured by the test suite. The numbers in [`asr.md`](asr.md) are verified by measurement against the running system, and the design's unproven speed claims live in the verification plan.

## Evals

From release 0.2, the AI reader (DL-0558), a prompt is measured beside the levels above and apart from them, on the AI workbench (DL-0557). **An eval is not a test, and CI never runs one** (DL-0563): a test costs nothing and answers the same on every run; an eval calls a model, which costs money on every run and answers differently each time.

**The eval command — `ai_eval`, a working name.** A management command of the product, on the code path production uses — prompt assembly, the provider call, the quote check, the sorting — run on the developer's machine through the development stack, against the provider's API (DL-0563). It runs a prompt's case set three times and writes the result, dated, into `evals/<id>-<slug>/` under the hash of the prompt version it measured — one hash over the base prompt, the prompt, the model and the effort (ADR-0024) — to be committed with the prompt change it measures (DL-0563, DL-0566). Every case is invented, as every fixture is. **The layout** (DL-0570): the invented documents are the evals' fixtures, in `evals/_cases/<case>/`, each with its key naming every heuristic's planted defects and traps, written once and shared by the heuristics they serve; the injection set is in `evals/_adversarial/`; `evals/<id>-<slug>/` names the documents of that prompt's set and holds its dated results; every prompt is in `prompts/<id>-<slug>/` with its settings — the heuristics it covers, model and effort — the shared base as `P01-base-read` and the judge as `P02-judge` (ADR-0026). On production only the command that loads the prompts runs; it reads the results and never writes them.

**What CI does.** It never calls a model and holds no provider key. On every push it checks, deterministically, that the version each prompt loads — named in its settings — has a committed, passing result under its hash in `evals/`, the rule the load command applies when it refuses a prompt version without one (DL-0563, ADR-0024, DL-0576). Passing means the heuristic at its target and a passing adversarial result under the same hash. The other versions in `prompts/` are history and need no passing result.

**The deterministic parts are ordinary tests**, at the levels above and in the check: the word-for-word verification of a finding's quotes; the sorting of a finding by where its verified quotes sit; the structural injection checks — a forged delimiter, a chat role marker, the run marker's format (ADR-0022); the load command's gate and the prompt version's hash (ADR-0024); and the provider interface, with a double in the provider's place. **A double agrees with whatever the code assumes** — the reason neither store is mocked — so it hides the wiring between the assembled request and the real client. One test therefore runs the real assembly — the base, the delimited document, the heuristic, the client's own request and the parse of its structured answer — against a recorded response of the provider, over an invented document.

**The numbers** — each heuristic's target, its false-positive budget, the size of its case set, the judge's threshold, the ceiling in production — are in [`evaluation-strategy.md`](evaluation-strategy.md) § The numbers (DL-0566), and are not repeated here.

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
| `documents/` | small invented documents for flows: a two-section policy, one with an appendix and an attachment, one in each language | the tests of the document's files and repository |

Fixed, never random or time-dependent; datetimes are UTC. `corpus/` is generated: it is regenerated by its script, never edited by hand. `splitter/` is written and marked by hand: a wrong mark is corrected as a change to the sample, with its reason.

## Layout

Tests live in `tests/` at the repository root, one directory per functional area, named for the app it tests — `tests/foundation/` for the project itself: its configuration, its image and its Compose files — and one file per topic — `tests/documents/test_create.py`, `tests/editing/test_splitter.py` — so a test can be named, as `tests/{area}/test_{topic}.py::test_{behaviour}`, before the code it tests exists. Test functions are named for the behaviour, so a failure says what broke. Shared fixtures — a migrated tenant schema, a temporary repository root, a signed-in client per role — are in `tests/conftest.py`.

**A test reaches the tenant, the repositories and the files through these fixtures, never a fixed path or number.** `migrated_tenant` is one schema per worker, migrated once and put back to its migrated state before every test that takes it — its rows, and its sequences, so document numbers start again at 1. Its number is the same in every test of a worker, so each such test gets a repository root of its own. Another tenant comes from `make_tenant_schema`, which migrates a schema of its own. Everything a test writes goes under `tmp_path` or the roots the fixtures set.

## Tests done, for a story

A story's tests are done when all of these hold:

1. **Every behaviour the story adds has a test**, written in the story, not deferred to a later one. An epic's documentation or consolidation story fills gaps; it does not excuse a story from writing its own.
2. **Every refusal path is tested** — the unauthorised caller, the input outside the whitelist, the other tenant's object. A permission that is only tested for the permitted case is untested.
3. **Every ASR the story touches has its invariant test**, new or already existing and still green.
4. **Every multi-step write the story adds has its crash test.**
5. **The tests the change can reach pass**, selected by coverage: `pytest-testmon` — `uv run pytest -q -n auto -m "not budget" --testmon-forceselect` — which reruns every test whose recorded lines the change touches. Coverage sees Python run inside a test and nothing else, so **the CI command passes locally in full** instead whenever the change reaches what it cannot see: a file that is not Python under `src/` or `tests/`, or any file the suite reads outside them; Python that runs only on import — migrations, models, URL configurations, settings, application configs, module-level code. Every memoised function is emptied before each test, so its body is traced by every test that reaches it. The full command passes as well at least every third story, and always before the work is committed.
6. **What tests cannot see has been looked at** — the page opened, the row queried, the export read — and the completion note says so.

A failing test is fixed before the next story starts, and the completion note records the failure and its fix.

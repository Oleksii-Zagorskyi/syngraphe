# Syngraphē — working instructions

Instructions for an agent working in this repository. Read before writing code.

## What this is

A platform for documents an organisation has to stand behind — written,
reviewed, approved, and answerable for afterwards. Django owns the workflow;
each document is a bare git repository the application owns; edits are a single
linear sequence with one editor at a time. Product reasoning is in `docs/`;
`docs/adr/` holds the decisions and `docs/design-record/` the account of how
they were reached. **Read the ADRs before changing anything they govern.**

## Repository layout

Every directory has one job. Put a file where its job says, or raise the gap
before inventing a new location.

| Path | Holds |
|---|---|
| `src/` | The Django project and its apps. All application code |
| `tests/` | The test suite. Top level, not per app — one place to look |
| `docs/` | Product-level documents: PRD, technical design, ASRs, data model, glossary, lifecycle, backlog |
| `docs/adr/` | Architecture decision records. Numbered, never rewritten once accepted |
| `docs/enhancements/` | Enhancement proposals — one initiative each — and the roadmap in its README |
| `docs/verification-plan.md` | Every claim the design has not yet proved, with its pass condition |
| `docs/design-record/` | The decision log and the architecture reviews — how the design was reached |
| `docs/interface/` | Page wireframes and interface vocabulary. Each region marked with the release it belongs to |
| `prompts/` | **Canonical** prompt and heuristic text, one directory per heuristic. Arrives with 0.2 |
| `evals/` | Labelled cases and results for the prompts. Pairs with `prompts/`, one directory per heuristic |
| `deploy/` | Dockerfile, entrypoint, Gunicorn configuration and Compose overrides |
| `scripts/` | Operational and documentation scripts. Idempotent, resumable, sanity-checked before any destructive step |
| `.github/workflows/` | CI |
| `compose.yaml` | At the root, so `docker compose up` runs from a checkout with `.env` filled |

**Do not create empty directories or placeholder files.** A directory appears
when its first real file does.

**`ai/` and `workspace/` are ignored mounts.** They are separate
working repositories that happen to sit in this checkout. Nothing the product
depends on may read from them, and no tracked file may reference them.

## Prompts are source

**`prompts/` is canonical; the database holds a copy loaded from it by a seed
command.** A heuristic is prompt text under version control, reviewed like code
and tested by its evals. The platform administrator may edit a row in place for
a hotfix, and that edit is a divergence from the source to be reconciled, not a
new source of truth. Tenant-level *selection* of which heuristics are enabled is
ordinary data and lives only in the database.

Prompts are plain Markdown loaded by path, never packaged as module data, so
they can be read and edited by someone who does not write Python.

## Stack

Django and Python 3.12 · PostgreSQL with one schema per tenant · Redis · Celery
· containers for web, database, cache and worker. A git library operating on
bare repositories the application owns — git is a library here, never a service,
and never a second authorisation surface.

## Commands

Copy `.env.example` to `.env` and fill every `???` first — the backup store's
only for the kind `BACKUP_TARGET` names; the application refuses to start while
one remains, naming every missing key at once — all but the mail key, read where
it is used. The stack needs an off-host
backup store, `sftp` or `s3`, before `db` and `backup` start: there is no local
kind (`docs/runbook.md § Backup`). Set
`SITE_HTTPS=false` unless a TLS proxy is in front: over plain HTTP the session
and CSRF cookies are never sent, and nobody can sign in.

```bash
# prepare a fresh clone; again whenever a lockfile changes: the Python
# dependencies, the editor's bundle, the browser the browser tests drive
uv sync --locked && npm ci && npm run build && uv run playwright install chromium

# run the stack: web, worker, render, PostgreSQL, Redis and the backup; every schema
# migrates on start
mkdir -p .repos
docker compose up

# the developer's shape: source bind-mounted, the development server, the
# database and Redis reachable from the host; it serves the bundle built on
# the host, so run `npm run build` after changing src/editing/js/ or the
# whitelist specification
docker compose -f compose.yaml -f deploy/compose.dev.yaml up

# the check; needs PostgreSQL and Redis, published by the developer override,
# GNU gettext on the path, and Pango and HarfBuzz for the PDF exports; the
# tests on one worker per core, then the timing budgets alone
uv run ruff check . && uv run ruff format --check . && uv run mypy src \
  && uv run pytest -q -n auto -m "not budget" && uv run pytest -q -m budget
```

The first line installs the Python dependencies from `uv.lock` and the
editor's from `package-lock.json`, builds the editor's bundle and installs the
Chromium the browser tests drive; it needs Node 22. The check is the line CI
runs, the one `docs/test-strategy.md § What CI runs` names, run the same way by
a developer and by CI. Every run gets a test database of its own, so a second
run beside it — a sub-agent's, a reviewer's — needs nothing set.

Run the suite after every unit of work. A failing test is fixed before the
next one starts, not after.

## Conventions

**English in every document.** The decision log, ADRs, product documents and
every other Markdown file in this repository are written in English. Material
that arrives in Ukrainian — an answer, a screenshot, an example — is translated
when it is recorded. Ukrainian appears only where it is the subject: the
glossary's Ukrainian terms, invented test prose where the language is what
the test is about, interface strings — or where a document's frontmatter lists
both languages, which marks it bilingual by design.

**Configuration, never code.** No hostname, domain, tenant name, display name,
mailbox or timezone appears as a literal in `src/`. The test: could this file be
copied to another organisation's installation and run unchanged? Defaults are
allowed; hardcoded values are not.

**Unsupplied configuration ships as `???`** and the reader treats `???` as
absent, reporting every missing key at once rather than the first.

**Tenant isolation is enforced by the database.** Crossing a schema boundary
requires a deliberate act, not a forgotten filter. Never reintroduce
application-layer tenant filtering as the primary control.

**Need to know by default.** Ask what this consumer needs to see, never whether
there is a reason to restrict it. A feature a user cannot access does not appear
in their navigation.

**Record before the fallible step.** Persist the payload, then attempt the call
that leaves the process, then record the outcome. Report success only on a
confirmed acceptance — never on the absence of an exception. An unimplemented
receiver returns a failure, never `{success: true}`.

**Datetimes are UTC in the database**, converted only at the output boundary.
Never convert in business logic.

**Comments carry the why; the code carries the what.** A comment restating its
line is deleted. Public interfaces get docstrings. Where a choice is
non-obvious, link the ADR or decision that made it.

**Scripts are idempotent.** Detect already-done state and no-op, resume from a
partial run, sanity-check before anything destructive, and abort rather than
half-write.

## Commit messages

**The 50/72 form.** A capitalised, imperative subject of about 50 characters,
never over 72; a blank line; a body wrapped at 72, written only when it tells a
reader something the subject does not. Plain ASCII text, no Markdown.

**Cite the identifier that governs the change** where one exists, on `Refs:`
lines at the end — `Refs: ST-0035`, `Refs: DL-0181 to DL-0191`. That makes the
history an index into the design record, which is most of what the record is
for.

No session numbers, no tracker references that resolve to nothing outside this
repository, and no tool or agent attribution of any kind.

## Git

**Commits are authored by the maintainer, after review.** Leave your work in the
working tree and say what changed; do not stage, commit, push, merge or rebase.
Read-only git — `status`, `log`, `diff`, `show`, `blame` — is yours to use
freely, as is `git mv` for a rename.

## The data boundary — the one rule with no exceptions

**No real document content ever enters this repository.** Not as a fixture, not
as a test sample, not in a docstring, not in an issue, not temporarily. The
organisation's policies, their text, their titles and anything identifying the
organisation itself live outside the tree entirely.

Test material is invented. Anything sourced from a real document does not enter
this repository at all.

**A test's sample text is invented English, unless the language is what the
test is about.** Invented Ukrainian stays where the behaviour depends on it:
the move rule, which git does not apply to Cyrillic (ADR-0011), and the
undo's walk, which follows moves by it; the sentence splitter and the
normalizer; the diff, rendering and export engines' own tests; the generated
corpus; the Ukrainian catalogue's coverage.

**An example is marked as one.** A group, a role holder, a department or a
document named to illustrate a rule — *Accountants*, *the CFO*, a finance
policy — is invented and marked as a synthetic example where it appears.

This is permanent: history cannot be unpublished.

## Stop and ask

- A task contradicts an ADR, the data model, or the decision log.
- A design choice arises that the recorded decisions do not cover.
- A test fails in a way that needs the specification changed rather than the code.
- You are about to create a directory or a file class the layout above does not name.

Do not stop for implementation details the specification already bounds —
variable names, helper structure, which of two equivalent idioms. Make the call
and note it when you report the work.

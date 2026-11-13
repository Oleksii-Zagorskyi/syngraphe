# Syngraphē

*A platform for the documents an organisation has to stand behind — written, reviewed, approved, and answerable for afterwards.*

[![CI](https://github.com/Oleksii-Zagorskyi/syngraphe/actions/workflows/ci.yml/badge.svg)](https://github.com/Oleksii-Zagorskyi/syngraphe/actions/workflows/ci.yml)

Policies, procedures and job descriptions are edited in Word, mailed around, and
approved in a meeting. Six months later nobody can say what the document said in
March, who changed the paragraph that matters, or who approved it. Syngraphē
keeps every change forever with its author and its date, runs the document
through a review cycle, and freezes an approved edition you can compare against
the one before it.

**Controlled documents** is the category — anything whose version, approval and
distribution have to be managed: policies, procedures and SOPs, job
descriptions, contracts and other legal instruments, official public statements.
Release 0.1 is built around policies, and the rest follow without structural
change.

I am building it for a company I co-own, to replace exactly that arrangement.

> **Status: release 0.1.** The editing, review and approval cycle runs in its
> first production installation. The AI reader — a
> companion that runs analyses for the editor as they work, and a reviewer
> that checks a document, or a whole corpus, against a configurable set of
> heuristics — is release 0.2, not yet started.

## What it does

- **An editor** for the formatting a policy actually needs — headings, lists,
  emphasis, callouts, plain tables, images. Nothing else, deliberately.
- **No save button.** Work is captured as you type.
- **A review cycle** where the reviewer sees what changed and who changed it,
  and can correct wording and accept in one step instead of returning the
  document.
- **A complete record.** Step through every change, compare any two points, see
  who wrote which sentence — or which row inside a table.
- **Editions.** Freeze the text, have it approved, and compare it directly
  against the edition before it.
- **Views drawn from a document** — starting with a role directory: who holds
  which rights and obligations, and which paragraphs say so. A view is derived
  and kept current by the platform, and a view can be promoted into an
  authoritative document of its own.
- **Export** to PDF, Word and Markdown, of a stated version.
- **Separate organisations** on one platform, isolated at the database.

The interface is Ukrainian or English, as each person chooses, and each
document is written in one language.

## How it works

Documents are Markdown. Each one is a bare git repository the application owns,
so history is real history rather than a table of diffs — but git is a library
here, not a service: Django owns the workflow and is the only authorisation
surface. Edits are a single linear sequence with one editor at a time, which is
the decision most of the design follows from ([ADR-0003](docs/adr/ADR-0003-linear-edit-history.md)).

Tenants are isolated by PostgreSQL schema, not by application-layer filtering.
Commits carry no personal data. Access rights are rows with a full change
history, answerable for any date in the past.

## The AI reader — release 0.2

Two actors, neither of them a role a person holds.

A **companion** runs analyses for whoever is editing, scoped to what that editor
can already see, and never reads a document they could not open themselves.

A **reviewer** checks a document — or a whole corpus — against a configurable
set of heuristics, and reports blind spots, contradictions and ambiguities as
recommendations. It does not decide anything. A human reviewer decides what
enters a document and what does not, and the record shows which of them did
which.

The heuristics are prompt text under version control with their own evaluation
cases, in `prompts/` and `evals/`. Neither directory
exists yet: they arrive with 0.2.

## The design record

The part of this repository I would read first.

`docs/design-record/` holds the reasoning: a decision log of every choice with
its alternatives and its consequences, including the ones that were reversed and
why; independent architecture reviews, each followed by a pass over the repairs;
and the analyses that settled the storage model and the edit model.

Worth opening on their own:

| Document | What it is |
|---|---|
| [ADR-0003 — linear edit history](docs/adr/ADR-0003-linear-edit-history.md) | Why branching was dropped, and where divergence re-enters anyway |
| [Technical design](docs/technical-design.md) | The write protocol between git and PostgreSQL, and the claims it has not yet proved |
| [Threat model](docs/threat-model.md) | Written before implementation, and it changed the design |
| [Architecturally significant requirements](docs/asr.md) | The constraints whose violation is a rebuild rather than a bug |

## About the name

From Ancient Greek συγγραφή (*syngraphē*) — a written composition, a document,
a written record — from *syn-* (together) and *graphō* (write). Not the act of
typing: the thing that results and is then stood behind. There is a modern
resonance in *graph* too, for the dependencies between documents, clauses,
revisions and reviewers, though that is not where the word comes from.

Interface and domain terms are carried in both English and Ukrainian, each
marked *fixed* or *proposed*. If you are contributing, translating, or naming
something new, [the glossary](docs/glossary.md) is the reference — including the
list of words this product does not use, and what to use instead.

## Running it

To run it you need Docker with Compose, and an off-host backup store — an SFTP
server or an S3 bucket; the database and the backup do not start without one,
and there is no local kind ([the runbook](docs/runbook.md#backup)). To run the
check you also need `uv`, Node 22, GNU gettext, and Pango and HarfBuzz with the
DejaVu fonts.

```bash
cp .env.example .env         # fill every ??? above "Compose only, the production override";
                             # of the backup store's keys, only those of the kind you chose.
                             # Set BACKUP_KEY_FILE to the store's SSH key, or to /dev/null for S3.
                             # The application refuses to start while a ??? remains;
                             # MAIL_PASSWORD_KEY alone may wait until mail is set up.
                             # set SITE_HTTPS=false unless a TLS proxy is in front: over plain
                             # HTTP the cookies are never sent and nobody can sign in
mkdir -p .repos              # the document repositories, written by the application's user, uid 1000
docker compose up            # web, worker, render, PostgreSQL, Redis and the backup; the schema migrates on start
curl http://127.0.0.1:8000/health/
```

The developer's shape — the source bind-mounted, the development server, the
database and Redis reachable from the host — is
`docker compose -f compose.yaml -f deploy/compose.dev.yaml up`, which serves the
editor's bundle built on the host. With it running,
`uv sync --locked && npm ci && npm run build && uv run playwright install chromium`
prepares the clone and
`uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run python scripts/check_record.py && uv run pytest -q -n auto -m "not budget" && uv run pytest -q -m budget --durations=0`
is the check, the same line CI runs. Layout and conventions are in
[`CLAUDE.md`](CLAUDE.md).

A production installation runs a release tag behind a reverse proxy, with the
production override, `deploy/compose.prod.yaml`. Its deploy, update, rollback
and restore are in [the runbook](docs/runbook.md#deploy).

## Licence

Apache License 2.0 — see [LICENSE](LICENSE). The documents the platform holds in
any installation belong to that organisation and are not part of this
repository.

## How this was built

I designed this and directed coding agents to build it, under a written
methodology I keep privately. Every change is one I reviewed and approved. The
design record in `docs/` is the account of that process.

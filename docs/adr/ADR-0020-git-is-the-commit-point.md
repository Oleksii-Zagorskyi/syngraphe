---
status: accepted
last-updated: 2026-11-12
supersedes: []
superseded_by: []
---

# ADR-0020: Git is the commit point — rows derived from commits, one writer lock per document, a reconciler that repairs from git

**Date:** 2026-11-12
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** None

## Context

Django performs every ref update and every row write (ADR-0002), so a document's record lives in two stores: a bare git repository per document, and rows in the tenant's PostgreSQL schema. ADR-0002 names the consequence without settling it: *the two stores need a stated write protocol* — the order, the authority and the repair path between git and PostgreSQL are the platform's to define. This ADR collects the write protocol of DL-0111, as DL-0455 changed it, and the consequence ADR-0002 left open, into one record.

No transaction spans the two stores. A process can stop between a commit and the rows that describe it, or between a row and the repository it announces. Without a rule, each of those states is undefined, and the comparison that T-07's tamper detection relies on has nothing to compare (DL-0111).

History is linear and append-only (ADR-0003, ASR-02), every document has its own repository at `tenant-N/document-M/` (ADR-0008), and no commit spans two documents. Two containers, `web` and `worker`, mount the same repository root and both write; an operator's shell can write too. The editor's hold serialises human editors of one document, but an acceptance, a return, an approval, the backup's bundle and the reconciler's own repairs are not made under that hold.

## Decision

Git is the commit point. The ref update is the moment a version, an acceptance, a return or an approval exists; every row about it is derived from the commit, idempotently and by one rule per kind, by the request that made it and again by whoever finds it without its row — the next writer, which settles the head before it writes, and a reconciler, which repairs the rows from git, never the reverse (DL-0111). A row is never the authority for something git holds: where a row and the passport disagree, the passport is believed. One writer lock per document covers every ref update, and the backup reads under the same lock (DL-0111, DL-0301). Document creation is the one write that begins in the database, with a row in the state `creating` that becomes `active` once the repository has its first commit and the rows derived from it. The reconciler never deletes a repository, deletes a row only when told to, trusts a repository only where its passport names it, and never finishes a stopped copy (DL-0455).

## Rationale

**One authority makes every crash state defined.** With git as the commit point, a stop leaves one of two shapes: a commit without its rows, which is derived, or a `creating` row without its commit, which is finished. Neither needs a judgement about which store is right. The same rule is what a comparison of the stores means: a disagreement is a finding about the row (DL-0111).

**The record that travels is the one believed.** Acceptances, returns and approvals are sections of the passport inside the repository (DL-0041), and the history that holds them is append-only (ASR-02). A row is a cache of them that makes pages fast; it can be rebuilt from the repository, and the repository cannot be rebuilt from it.

**The lock is almost never contended, and still has to exist.** The editor's hold already keeps two people from writing one document's text. Acceptance, return, approval, the backup's bundle and the reconciler's repairs are outside that hold, and a ref update that interleaved with any of them would break the linear history. A file lock beside the repository is one any process on the host can take, an operator's shell included, with no service to run.

**Two repair paths, because they meet different needs.** Settling the head at the next write keeps the invariant exactly where it is needed — before a number is computed or a commit is made — without waiting for a schedule. The reconciler reaches the documents nobody writes to, and the faults a writer does not look for: a repository without a row, a row without a repository, a passport and a row that disagree.

**Repair fails closed.** A repository whose row is recreated reaches nobody but administrators, the same instinct as an untagged finding (DL-0111). A repository is never deleted because a repository is the record. A row is deleted only by an operator who has read the report, because an absent commit can be a mount that is not there.

**One repository per document is what keeps the protocol small.** With no commit across documents, the lock is per document, a repair is per document, and the backup's superset property holds per document: each repository copied after the database's recovery point holds at least what the database knew about it (DL-0111).

**A copy is cheap to make again** (DL-0455). A copy's first commit holds its source's text, so finishing it from the organisation's template would make a different document. Leaving a stopped copy unfinished keeps the record of its source in one place, the audit trail, and adds no column to the document's row.

## Consequences

- Every act that updates a ref has the same shape: take the lock, settle the head, lock the row, commit, derive. A new kind of commit needs its derivation rule written once and called from three places — its own request, the settling of the head, and the reconciler. The three call the same derivation, so a row is the same whoever writes it.
- A reconciler is the second path from git to the rows (DL-0111). In report mode it lists what disagrees and writes nothing. In repair mode it derives what git implies: it replays the commits after the newest one the rows know and stops at the first it cannot derive; it finishes a creation that stopped, and an acceptance, a return or an approval that stopped after its commit; it recreates the row of a repository that has none. It runs every hour in repair mode, and an operator runs it by hand after a restore. One document's fault is reported and the run goes on.
- The nightly repack runs per repository under the same lock (DL-0313). In an append-only linear history the only unreachable objects are debris from failed writes, so pruning them does not touch ASR-02.
- After a restore git is level with the rows or ahead of them, which is the state the reconciler repairs.
- The interface reads rows, so between a commit and its derivation a page can be behind git. It is never ahead: a row for a commit that does not exist is a finding.
- An acceptance, a return or an approval is derivable only from a passport section that reads. A commit of those kinds whose section does not read is reported and stops the replay of everything after it, so a hole is never derived past.
- A document whose lock is held longer than the wait is refused to a person as busy and reported by the reconciler; a writer that never releases the lock stops that document's writes and its bundle, and the backup records the failure in its marker (ADR-0019).
- The lock is a file on the host's filesystem. Every writer must mount the same repository root; that is a constraint on the deployment.
- State that exists only in the database — holds, access rows, and above all drafts, which carry a whole editing session (ADR-0003) — is not recoverable from git. It is protected by the database's continuous archiving, not by this protocol (ADR-0018).
- A stopped copy stays as an invisible `creating` row until an operator removes it: the reconciler recognises a `creating` row that the audit trail names a copy, reports it, and leaves it invisible; an operator removes the row and its repository by a command, and the copier copies again (DL-0455). The runbook carries the command.
- Two things are given up, on the record: there is no commit that means *the corpus as of this moment*, which nothing needs; and a generated view across documents has no repository to live in, and needs a per-tenant derived store when B-003 is taken up (DL-0111).

## Alternatives Rejected

- **A repository per document *set***: One repository holds a group of documents. Rejected because a set is not a stable grouping — every reviewer assembles a different review scope — and with one repository per document an agent's mount list is its review scope, so a run simply does not have a confidential document on its filesystem (DL-0111).
- **A forge as the system of record**: A job reconciles the forge's permissions and the platform's. Rejected in ADR-0002 because it keeps two descriptions of one fact and the machinery that stops them diverging.
- **The writer lock held through the bundle's verification and its copy to the store**: The backup keeps the lock until the bundle is verified and stored. Rejected because the time to finish an edit would depend on the link to the store (ADR-0019, DL-0301).
- **A filesystem snapshot for the copy of the repositories**: Offered beside the lock in DL-0111. Not taken: the backup as built writes each bundle under the writer lock (ADR-0018, DL-0301); the record gives no further reason.
- **A stopped copy finished by the reconciler like any creation**: The copy's source is kept in two columns on the document's row. Rejected because a copy is cheap to make again and the record of its source stays in one place (DL-0455).
- **A stopped copy given a failed state, told to the copier**: The row stays, marked as failed. Rejected in DL-0455 with the same reason: a copy is cheap to make again.
- **Repositories named by the internal identifier**: The naming DL-0111 first set. Rejected because with `tenant-N/document-M/` an operator sees which tenant and document a directory holds without a lookup, and a repository restored without its row names its own document (DL-0200, ADR-0008).
- **Repositories named by title or slug**: The directory carries the document's title. Rejected because a title would reach filesystem listings, backup manifests and operator shells that the access table does not govern (DL-0111).

### Option attribution

| Option | Raised by | Outcome |
|---|---|---|
| Git is the commit point; rows derived by the request, by the next writer and by a reconciler (DL-0111) | the record | **accepted** |
| One writer lock per document, covering every ref update and the backup's bundle (DL-0111, DL-0301) | the record | **accepted** |
| Document creation begins in the database, in the state `creating` (DL-0111) | the record | **accepted** |
| The reconciler never deletes a repository; a repository without a row is recreated without access (DL-0111) | the record | **accepted** |
| A stopped copy is never finished (DL-0455) | owner | **accepted** |
| A repository per document *set* | the record | rejected |
| A forge as the system of record | the record | rejected |
| The writer lock held through the bundle's verification and its copy to the store | the record | rejected |
| A filesystem snapshot for the copy of the repositories | the record | rejected |
| A stopped copy finished by the reconciler like any creation | the record | rejected |
| A stopped copy given a failed state, told to the copier | the record | rejected |
| Repositories named by the internal identifier | the record | rejected |
| Repositories named by title or slug | the record | rejected |

## Guardrails / Conditions of validity

The protocol is safe only while these controls hold.

- **Rows are derived, never the source of truth** (DL-0111). A content version's row is derived from its commit. The rows of an acceptance, a return and an approval are derived from the section their commit appended to the passport, never from a commit's trailer alone.
- **The passport is believed over the row** (DL-0111). The reconciler rewrites an acceptance's or a return's row from its section, reports an edition's row or a tag that disagrees, and never changes the passport.
- **Every writer takes the same lock, before any row lock** (DL-0111). The lock is the file `tenant-N/document-M.lock` beside the repository, taken with `flock`, so `web`, `worker` and an operator's shell take the same lock. It is taken before any database row lock, always in that order. A thread that asks for a lock it already holds is refused rather than left waiting on itself.
- **A wait for the lock ends.** Taking a hold, an acceptance, a return, a freeze and an approval wait ten seconds for it and then answer that the document is busy; the reconciler waits thirty seconds and then reports the document as locked and goes on.
- **The next writer settles the head** (DL-0111). Under the lock, before it reads anything for a write, every writer derives the rows of each commit at the head that the rows do not know, oldest first — a version's row, an acceptance's rows and its correction notices (ADR-0014), a return's rows, an approval's rows, tag and the end of its freeze. If one cannot be derived, the write is refused. So nothing is written over a commit the rows do not know, and no version number is given twice.
- **Document creation keeps its order** (DL-0111). The row is committed first, in the state `creating`, with a number that is never given again; then, under the lock, the repository is initialised and receives its first commit; then the rows derived from that commit; then the row becomes `active`. A stop between any two steps leaves a state the reconciler recognises.
- **Every repair is made under the document's lock** and audited with numbers, never a title.
- **The reconciler never deletes a repository** (DL-0111). A repository without a row is reported and recreated from `document.md`'s frontmatter with no access rows at all — only administrators reach it — and the tenant's administrators are notified.
- **A changed history is reported, never agreed to.** A commit without a row before the newest known one means the history changed under the rows.
- **A row is deleted only when an operator tells the reconciler to.** The one deletion is a version row whose commit its repository no longer holds, with the rows derived from it; it happens only when an operator asks for it by its own option, never in the hourly run, and never when the repository or the tenant's directory is absent, which may be a missing mount (ADR-0018, DL-0276).
- **A repository is trusted only where its passport names it.** The reconciler acts on a repository only when the passport in its first commit names the tenant and the document number of the directory it sits in; any other is reported and left alone.
- **A copy's source is on the record before its repository exists** (DL-0455). The copy's source is written to the audit trail before the repository is touched, so the reconciler can tell a stopped copy from any other stopped creation.
- **The backup and the restore take the lock** (DL-0111, DL-0301). A repository's bundle is written under its writer lock; verification and the copy to the store follow after the lock is released (ADR-0019). A restore of one repository from its bundles is made under the lock too, and leaves alone a repository already there. A restore never takes the database past the repositories (ADR-0018).

## References

- Originating decision-log entries: DL-0111, DL-0200, DL-0455; DL-0041, DL-0276, DL-0301, DL-0313
- ADR-0002 — Django owns the workflow; ADR-0003 — linear edit history; ADR-0008 — identity and addressing; ADR-0014 — the correction notice at acceptance; ADR-0018 and ADR-0019 — backup and restore
- ASR-02; T-07; B-003
- `technical-design.md § The write protocol between git and PostgreSQL`, `§ Versions, holds and history`; `runbook.md § The reconciler`
- `src/documents/locks.py`, `src/documents/reconcile.py`, `src/documents/services.py`, `src/review/services.py`, `src/editions/services.py`, `src/documents/backup.py`

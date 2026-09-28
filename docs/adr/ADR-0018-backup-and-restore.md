---
tags:
  - adr
aliases:
  - ADR-0018 Backup and restore — the database continuously, the repositories as bundles, into one backup store
status: accepted
date: 2026-09-28
supersedes: []
superseded_by: []
---

# ADR-0018: Backup and restore — the database continuously, the repositories as bundles, into one backup store

**Date:** 2026-09-28
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** None — collects the backup half of DL-0111, DL-0118, DL-0271, DL-0276 and DL-0277 into one record

## Context

The platform keeps one record in two stores. Git holds every document's content and its passport — versions, acceptances, returns, approvals — in one bare repository per document; PostgreSQL holds everything else, and some of it exists nowhere else: holds, access rows and above all drafts, which ADR-0003 makes the only copy of an editing session's work. *Nothing is ever lost* is the scope agreement's promise, and it is true only with a copy off the host (DL-0118).

The recovery objectives are set: at most five minutes of database changes lost, fifteen of repository changes, and a running platform on a fresh host within four hours (ASR-25). Two hazards were named when the write protocol was designed (DL-0111): a repository copied while it is being written can yield a ref pointing at an object the copy missed; and a restore can leave the database ahead of git unless the database is taken first. The backup store receives every tenant's content together, off the host and possibly at a third party. The production host is not yet chosen (DL-0117); the development host is a machine whose Docker VM holds the containers.

## Decision

**The database is archived continuously with point-in-time recovery, by pgBackRest; every document repository is written as a `git bundle` under the document's writer lock every fifteen minutes — incremental, on a nightly full bundle — and verified; both are encrypted into one off-host backup store; a restore never puts the database past the repositories; and the restore is the runbook's procedure, rehearsed.**

- **Database.** pgBackRest runs in the database container's image. `archive_command` ships each completed segment of the write-ahead log to the backup store, and `archive_timeout`, at most 300 seconds, closes a segment that has not filled, so a quiet database still ships its changes within ASR-25's five minutes. A full base backup runs nightly; retention is two full backups and their archive. A restore replays the archive to a chosen point in time.
- **Repositories.** Every fifteen minutes a worker task bundles each document repository whose refs moved since its last bundle: it takes the writer lock, writes an incremental `git bundle` of what the refs gained since that bundle, runs `git bundle verify`, and copies the file to the backup store under `repos/tenant-N/document-M/`, named for the time it was taken. The task learns of a new base backup from pgBackRest's own record of its backups: the first run after one completes writes a full bundle — the whole repository, every commit, tag and ref — for every repository, and each full bundle starts that repository's next chain. A repository is restored by cloning from its full bundle and fetching each incremental after it, in order.
- **A complete set.** A run's bundles are a set. Only once every bundle of the run has verified and reached the store does the run record, in the store, the time it began; that time is what a full restore aims the database at. A bundle that fails verification is not copied and is logged as an error; its run records nothing, and the next run bundles that repository again from the refs last copied.
- **Order.** The database is never restored past the repositories (DL-0276). A restore of the whole host takes the database to the time the last complete set began, which every bundle of that set postdates; history is append-only and no commit spans two documents, so each repository then holds at least what the database knew about it, and the reconciler replays the difference. A failure of the database alone, with the repositories intact on the host, restores it to its latest archived point: the repositories on the host already hold every commit it names. Should a row still name a commit no copy holds, the reconciler reports it and deletes nothing on its own.
- **Encrypted before it leaves.** Both backups are encrypted on the host: pgBackRest's encryption for the archive and the base backups, `rclone crypt` for the bundles. The keys are per-installation values in `.env`, held by the operator and never written to the backup store, so only the platform operator can read it (DL-0277). Losing the keys loses the backups; the runbook tells the operator to keep a copy away from the platform.
- **One store.** The backup store is the off-host location the operator names — a directory on another machine, an object bucket, an SFTP host — reached by pgBackRest's own transport for the archive and by `rclone` for the bundles; both configured from the environment. Nothing about the database ever enters a git repository, and the word *repository* is kept for the documents' git repositories.
- **Restore is exercised, not described.** The runbook's cases — a fresh host, a point in time, one repository — are rehearsed on a copy before production opens and after any change to the tooling, with the duration recorded against ASR-25.

## Rationale

**Continuous archiving is the recovery-point decision, not a tooling preference.** Drafts, holds and access rows live only in the database; a nightly dump loses a day of them. Shipping each segment of the write-ahead log as it completes, with a timeout that closes a quiet one, is what makes five minutes achievable, and point-in-time recovery is what makes *a bad write at 14:07* recoverable to 14:06.

**pgBackRest gives the operator commands, not scripts.** Base backup, archive, verification, retention, encryption and `restore --type=time` are its commands, tested by many installations; WAL-G is one binary that does the archive well but leaves retention and verification to the operator's scripts; plain `pg_basebackup` with an `archive_command` leaves point-in-time recovery itself to be assembled by hand at the worst moment. A runbook an operator follows at three in the morning should name commands that exist.

**A bundle cannot be half a repository.** A plain copy of a live repository can capture a ref updated after the object it points at was skipped; a filesystem snapshot avoids that but depends on the filesystem under the volume, which production has not chosen. `git bundle` writes one self-contained file that git itself verifies as complete and clones back exactly, and it is written under the same lock every write to the repository takes, so it never catches a commit half-done. At the platform's sizes — tens of tenants, a repository of a few megabytes — a full bundle per document per night is small, an incremental one every fifteen minutes holds only what moved, and each chain restores on its own, which is what case C of the runbook needs.

**The database is never restored past the repositories.** A row naming a commit no copy holds is content lost from both stores: the version is gone from git, and the draft it used up is gone from the database. Restored no later than the bundles, the worst case is a repository ahead of its rows, which the reconciler was built to repair. The price is up to ten more minutes of database changes in the rare loss of the whole host; a failure of the database alone loses no more than five.

**The store is read by the operator alone.** It holds every organisation's documents together, often at a third party; without encryption, tenant isolation (ASR-01) and the confidentiality the threat model protects would end at the host. The store's own protection is someone else's promise, and a key kept beside the ciphertext protects nothing.

## Consequences

- The database image is the platform's own build on `postgres:16` with pgBackRest installed; a `backup` service on the same image runs the nightly base backup on a schedule, since the database image has no scheduler; `compose.yaml` carries `archive_mode`, `archive_command`, `archive_timeout`, the spool and socket volumes; the environment gains the backup store's credentials and the two encryption keys. pgBackRest reaches the store by its own storage types — a mounted path, SFTP, an object store — and `rclone` carries only the bundles.
- A worker task runs the fifteen-minute bundle run; operator scripts run the same from the shell, restore the database to a point in time, and restore the repositories from their chains — each idempotent and sanity-checking its target before writing.
- Bundle retention follows the database's: a repository's chains are kept back to the older of the two retained base backups, and a chain is deleted with the base backup it followed.
- The backup store is a production requirement the operator supplies; until then the development host's store may be a directory on another machine.
- A restore of the whole host loses up to fifteen minutes of changes to either store; a restore of the database alone loses whatever was only in the database after the recovery point. Drafts are the loss that matters, and the runbook tells the operator to name those documents' holders.
- The off-host store is a copy for losing the host, not T-07's off-site replication of the record: the operator writes to it and can alter it, so it detects nothing an operator does.
- Redis is not in the backup set: it holds nothing that is not also a row, and the reconciler re-enqueues from rows.
- Bundle size grows with attachment versions; ASR-23's envelope and the tenant's attachment cap bound it, and a chain starts again from a full bundle each night, so a restore applies at most a day of incrementals.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| pgBackRest for the database, `git bundle` under the lock for the repositories, one backup store, database first | agent, from the write protocol's hazards (DL-0111) and the recovery objectives (ASR-25) | **chosen** by the owner (DL-0271), with incremental bundles every fifteen minutes and the database restored no later than them (DL-0276), and both backups encrypted (DL-0277) |
| A nightly full bundle per document, and nothing between | this record's first draft | rejected — a day of commits could be lost; misses ASR-25's fifteen minutes (DL-0276) |
| The database restored to its latest point, the reconciler reporting versions whose commit is missing | agent | declined by the owner (DL-0276) — those versions and the drafts they used up would be lost from both stores |
| Every commit pushed to an off-host mirror | agent | declined by the owner (DL-0276) — the store types allowed have no git server |
| The store's own protection, recorded as an accepted risk | agent | declined by the owner (DL-0277) |
| WAL-G for the database | agent, as an alternative | rejected — one binary, but retention and verification would be the operator's scripts |
| `pg_basebackup` and an `archive_command` script, no tool | agent, as an alternative | rejected — point-in-time recovery assembled by hand during an incident |
| A filesystem snapshot of the repository root | the write protocol's first option (DL-0111) | not chosen for the product — it depends on the filesystem under the volume, which production has not chosen; it stays a valid operator choice on a host that has one |
| A plain copy of each repository | — | rejected — a live repository copied mid-write can hold a ref to a missing object; the hazard DL-0111 named |
| A nightly database dump | — | rejected — loses a day of drafts, holds and access rows; misses ASR-25's five minutes |

## Review triggers

- Production hosting is chosen (DL-0117): the backup store, the transport and the retention are set for it, and the restore is rehearsed there.
- A bundle run takes long enough that the last complete set falls more than fifteen minutes behind: the run is split or the interval revisited.
- A tenant asks for signing or off-site replication of the record (T-07's residual): a decision beyond this one.

## References

- Originating decision-log entries: DL-0111 (the write protocol and its two backup hazards), DL-0118, DL-0271, DL-0276, DL-0277
- ASR-01, ASR-02, ASR-23, ASR-25; T-07, T-20
- `technical-design.md § The write protocol between git and PostgreSQL`; `runbook.md §§ Backup, Restore`; `threat-model.md` T-20

---
tags:
  - adr
aliases:
  - ADR-0019 Backup when something fails — clean markers, chains kept by count, a store the host cannot empty
status: accepted
date: 2026-09-28
supersedes:
  - ADR-0018 (in part — the complete set, the interval, the lock's scope, how the run learns of a base backup, the restore target, retention, continuous archiving during a store outage, and who can delete from the store)
superseded_by:
  - DL-0545 (in part — that `pgbackrest verify` reports a gap in the archive)
---

# ADR-0019: Backup when something fails — clean markers, chains kept by count, a store the host cannot empty

**Date:** 2026-09-28
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** in ADR-0018 — the lead sentence of § Decision where it says *every fifteen minutes*; the points *Repositories*, *A complete set* and *Order* where they name the interval, the lock's scope, how the run learns of a new base backup, when a run records its set and where a whole-host restore aims the database; the first point's *continuously* during an outage of the store; the point *One store* where it offers a directory on another machine or an SFTP host as a production store, which DL-0298 rules out unless the store itself keeps what the host deletes; § Consequences, the *fifteen-minute* bundle run, the bullet on bundle retention and the bullet on the development host's store; § Review triggers, the second trigger. ADR-0018's tools, its encryption and its one store stand, and so does its rule that the database is never restored past the repositories, with one exception: the operator may choose, at the restore, a newer marker that names the repositories it gives up (DL-0294).

## Context

ADR-0018 describes the backup when everything works. A review of it found what happens when something does not, and every case ends in one of three losses: a recovery point that silently falls days behind, a chain of bundles deleted while it is still the only one, or a backup the host can destroy.

- **One repository stops every tenant's marker.** A run recorded its set only when every bundle verified and reached the store, so one repository failing on every run — damaged, a bundle that cannot be written, a lock never free — kept every tenant's whole-host recovery point where it was, with a log line as the only signal. A run with nothing to bundle recorded nothing either.
- **The interval is not the worst case.** A marker records when its run began and is written when it ends, so just before it lands the newest marker began the interval plus the run's duration earlier: fifteen-minute runs cannot keep ASR-25's fifteen minutes, and the review trigger fired before every marker.
- **Retention by age can delete the only chain.** A chain went with the base backup it followed; a repository whose full bundle failed kept adding to its old chain until that chain expired.
- **The worker could not read what it was told to read.** The run learns of a new base backup from pgBackRest's record, and pgBackRest, its configuration and the key to its encrypted record are in the database's image only.
- **The restore target could lie past the archive.** Bundles and the write-ahead log leave the host on separate clocks; when recovery reaches the end of the log before its target time, PostgreSQL stops with a fatal error.
- **The lock covered the network.** Read in order, a document's writer lock was held through the bundle's verification and its copy to the store.
- **An outage of the store fills the host's disk.** PostgreSQL keeps every segment it could not archive, and on a host whose data disk is shared with other workloads the archive's outage becomes theirs.
- **The host can empty the store.** The store's credentials are on the host and retention deletes from it; whoever takes the host — the loss the off-host copy exists for — can remove every backup. Encryption answers who can read the store, not who can empty it.

## Decision

**Every run writes a marker listing its failures, and a whole-host restore aims at the newest clean one, bounded by the end of the archive; runs start every ten minutes and hold the lock only to write; each repository keeps its newest two chains; the archive gives way before a shared disk fills; and in production nothing on the host can destroy a backup for thirty days.**

- **A marker per run** (DL-0294). Every run writes `repos/complete/<start, UTC>`, a run with nothing to bundle included, listing each repository whose bundle failed and when its consecutive failures began. A writer lock not taken within a timeout is a failure of that repository. A marker listing no failure is **clean**.
- **Every ten minutes** (DL-0296). ASR-25's fifteen minutes holds while a run takes less than five. A run does not start while another is running; the skipped start is logged.
- **The lock covers the write** (DL-0301). The run takes the writer lock, writes the bundle, releases the lock, then verifies the bundle and copies it; the refs recorded beside the repository are rewritten only once the copy is confirmed.
- **The `backup` service announces a base backup** (DL-0299). After `pgbackrest backup` succeeds, it writes the backup's label and stop time to a file on a small state volume, which `backup` and `worker` each write their own files to and `web` mounts read-only; the first run that finds a label newer than its last full bundles writes new ones. The worker holds neither pgBackRest nor the archive's key.
- **Chains kept by count** (DL-0303). Each repository keeps its newest two chains; when a new full bundle reaches the store, the oldest of three is deleted, whatever its age, and the newest is never deleted. A repository whose newest full bundle is older than the newest base backup gets a full bundle on every run until one lands.
- **The restore target** (DL-0300). A whole-host restore aims at the earliest of the newest clean marker's start, the last moment known to be good, and the end of the archive's continuous range after the base backup restored — a gap that DL-0297 left ends that range, and `pgbackrest verify` reports it; when the end of the range is the earliest, the database is restored to it rather than to a time. When a marker newer than the clean one lists failures, the operator may choose that marker instead, knowingly giving up the named repositories' commits since their last bundle (DL-0294): the one case in which the database is restored past some repositories, bounded to those the marker names and decided by the operator, never by the platform.
- **The archive gives way before the disk** (DL-0297). pgBackRest archives asynchronously through its spool; `archive-push-queue-max` caps what waits, and past it segments are acknowledged without being shipped. The live database loses nothing; the archive has a gap that point-in-time recovery cannot cross, closed by a full base backup once the store is back. Both the cap and the alert below it are configuration, 10 GiB and 2 GiB by default.
- **The operator is told** (DL-0295, DL-0305, DL-0306). `/health/` carries a `backup` entry — the newest clean marker's age, whether any repository is failing, the time of the last segment archived, the log not yet archived — without changing its status code; which repositories are failing is not shown there, since the endpoint answers anyone. Every platform administrator receives an *Administrative* notification and an email when a repository's bundle first fails, when the newest clean marker is older than fifteen minutes, and when the unarchived log passes its alert size; once as each begins and once as it clears, with numbers and ages and never a title. A task in the worker checks the three conditions every minute. The state behind them is three files on the state volume: the run's result and what it has notified; the base backup's label; and the size of the log not yet archived with the time of the last segment archived, written each minute by `backup`. If the worker itself stops, no run writes a marker, and the clean marker's age in `/health/` grows past fifteen minutes for the external check to see (DL-0306).
- **The host cannot destroy the production store** (DL-0298). The production backup store accepts the host's writes and deletions without destroying what was written — a versioned object store whose credentials on the host cannot delete a version, its own lifecycle removing a superseded or deleted version after thirty days, or an equivalent the store enforces. A store that cannot is not a production backup store. The development store is exempt: it holds invented content only.

## Rationale

**The strict rule stays the default; the trade becomes visible.** Restoring the database no later than every repository is what keeps the write protocol's superset property (DL-0276), and a clean marker keeps it. The exception differs from the option DL-0276 declined — the database restored to its latest point, whatever commits it named — in being bounded to the repositories a marker names and chosen by the operator with that list in hand. What the all-or-nothing set lacked was a way to see, and to decide, when one document's fault was costing every tenant: a marker listing its failures gives the operator both the safe point and the price of a later one, at the moment it matters. Excluding a repository automatically after some number of failures would have made that decision for the operator, silently, with a number to tune.

**The figure an operator is held to should be one the platform meets.** A ten-minute interval keeps ASR-25's fifteen minutes true without changing the requirement, and makes the alert the requirement's breach itself. Only repositories whose refs moved are bundled, so more frequent runs are smaller ones.

**A failure should cost disk, not history.** Counting chains per repository means a full bundle that failed leaves an extra chain behind rather than none, and matches the database's own two full backups.

**Each key stays in one container.** The service that takes a base backup is the one that knows it succeeded; a file on a shared volume carries the fact without carrying pgBackRest or its key into the worker, which reaches the network for mail.

**The restore target is a minimum of bounds.** The repositories, the damage and what was archived each bound the point from above for their own reason; their minimum is never later than the repositories the clean marker covers, and it is a point PostgreSQL can reach, since recovery cannot cross a gap in the archive.

**A backup must not stop what it protects.** On a disk shared with other workloads, an archive that waits forever for its store turns an outage of the store into an outage of the platform and its neighbours. A gap in the archive costs the ability to restore to a moment inside the gap; a full disk costs every write.

**Retention stays with the platform; destruction moves to the store.** The host needs to delete to keep the store's size in hand, and anyone who holds the host inherits that right. A versioned store whose host credentials cannot remove a version turns every deletion into a hide for the store's window.

## Consequences

- `compose.yaml` gains a state volume, written by `backup` and `worker`, mounted read-only into `web`; the bundle run moves to every ten minutes; `pgbackrest.conf` sets asynchronous archiving and `archive-push-queue-max`; `.env.example` gains the cap and the alert size.
- The health view and the notifications gain the backup's state; the notification is the platform administrator's, the nearest role the platform has to the operator.
- Until the platform sends mail and notifications, the health entry is the only channel, watched by an external check the deployment sets up; the backup leaves its notifying step as one function the mail fills when it is built (DL-0306).
- The runbook gains a step for an outage of the store; case A's step 4 computes the target from three bounds and puts the choice to the operator when a newer marker lists failures.
- The production backup store must be versioned, or equivalent, with thirty days' retention of what the host deletes; the choice of store is narrowed by it.
- A bundle run longer than five minutes breaks ASR-25's fifteen minutes; the nightly run of full bundles is measured against it when backup is implemented.
- After a long outage of the store, point-in-time recovery cannot reach a moment inside the gap until the full base backup that follows it.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| A marker per run listing failures; the newest clean one by default | agent | **chosen** by the owner (DL-0294) |
| A repository excluded from the set after N consecutive failures, the restore always to the newest marker | agent | declined — the platform would decide alone to lose one document's commits, and N would need tuning |
| The all-or-nothing marker kept, an alert added | agent | declined |
| Runs every fifteen minutes, the recovery point restated as fifteen minutes plus one run | agent | declined — the requirement's figure would have become a formula (DL-0296) |
| Deletion by age with a guard for the newest chain | agent | declined; the owner chose two chains by count (DL-0303) |
| A row in the shared schema, or a marker in the store, announcing a base backup; pgBackRest and its key in the worker | agent | declined — a table and a role for one fact; the store's credentials in `backup`; the archive's key in a container with network egress (DL-0299) |
| The run's state as a row per run in the shared schema | agent | declined — the signal needs the latest state, not a history (DL-0305) |
| The restore target kept, the error documented | agent | declined (DL-0300) |
| The lock held through the copy | ADR-0018 as written | declined — ASR-21's time to finish an edit would depend on the link to the store (DL-0301) |
| Never dropping a segment, relying on the alert | agent | declined — a long outage would still end in a full disk (DL-0297) |
| Losing the store to whoever holds the host, as an accepted risk in production | agent | declined; accepted for the development store only (DL-0298) |
| Add-only credentials on an SFTP store | agent | declined — they break pgBackRest's own expiry and the bundle retention (DL-0298) |
| Borg for the bundles, for its deduplication and append-only mode | owner | declined — it cannot carry the database archive, needs its own server on the store, and its protection is the one DL-0298 obtains for both backups at once (DL-0304) |

## Review triggers

- A bundle run takes longer than five minutes.
- The production backup store is chosen: it meets DL-0298, and the restore is rehearsed from it. If it is a server the operator controls where Borg can run, DL-0304 is revisited.
- The unarchived log reaches its cap in production: the cap, the alert size or the store's reliability is revisited.

## References

- Originating decision-log entries: DL-0294 to DL-0301, DL-0303 to DL-0306; DL-0302, taken with them, changes ASR-24 and ASR-25 only
- ADR-0018; DL-0276, DL-0277, DL-0279
- ASR-21, ASR-24, ASR-25; T-20
- `runbook.md §§ Backup, Restore`

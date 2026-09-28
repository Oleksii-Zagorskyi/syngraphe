---
tags:
  - runbook
aliases:
  - Syngraphē runbook
status: draft
fidelity: provisional
date: 2026-09-23
---

# Runbook


> **Status.** Written before the system it operates. Every procedure here is
> the intended one; none has been executed against a running deployment, and a
> restore that nobody has rehearsed is a hypothesis. The rehearsal is a task in
> its own right and is not done.

How to deploy the platform, back it up, and **restore it when something has gone wrong**. A backup nobody has restored is a hypothesis, so the restore procedure is the part of this file that matters most, and it is written to be followed under pressure.

> [!warning] Provisional — the procedure is fixed, the commands are not
> The order of steps and what each must achieve follow from the write protocol in [`technical-design.md`](technical-design.md) and do not change. The **tools** are [ADR-0018](adr/ADR-0018-backup-and-restore.md)'s — pgBackRest for the database's continuous archive, a `git bundle` taken under each repository's writer lock, one encrypted off-host backup store the operator names. Only the **commands** wait for backup to be implemented: every step that needs one says **⟨command: fixed when backup is implemented⟩** until then. The backup work extends this file; it does not start another one.

## What exists and where

| Thing | Where | In the backup set |
|---|---|---|
| **Database** — PostgreSQL, one schema per tenant plus a shared schema | the `db` container, on its data volume | **yes** — a base backup plus the continuous archive of the write-ahead log |
| **Repositories** — one bare repository per document | the repository root, mounted at `/srv/repos` in `web` and `worker` | **yes** — a bundle every fifteen minutes of each repository that changed, on a full bundle taken nightly |
| **Broker** — Redis | the `redis` container | **no** — it holds nothing that is not also a row; it starts empty and the reconciler re-enqueues |
| **Configuration** — `.env` | the host, beside the compose file | **no** — kept with the host's credentials, never in this repository. It holds the backup keys, without which no backup can be read |
| **Off-host copy** | ⟨destination: supplied by the operator⟩ | holds two full database backups and their archive, and each repository's bundles back to the older of them — all encrypted |

Every step below says **where it runs** — the host shell, or inside a named container — and **as whom**.

## Deploy

**Development host.** On the host, as the deploying user, in the repository checkout:

```bash
cp .env.example .env     # fill in every ??? — the app reports every missing key at once
docker compose up -d
```

Then migrate every schema ⟨command: fixed when the stack is stood up⟩, and confirm the health endpoint answers and a platform administrator can sign in **on the host**, not only locally.

**Production** is a deployment decided when the platform is ready to leave development (DL-0117). Its procedure is written with the deployment architecture at first deploy; until then this section is the development host's.

## Backup

**Order is the whole point: the database is never restored past the repositories.** History is append-only and no commit spans two documents, so each repository copied *after* the database's recovery point contains at least what the database knew about it. The reverse can leave a row pointing at a commit no copy holds — a version gone from both stores.

1. **Database — continuously.** pgBackRest ships each completed segment of the write-ahead log off-host, and a segment that has not filled is closed within five minutes; a full base backup is taken nightly, and two are kept with their archive. ⟨command: fixed when backup is implemented⟩. This is what makes point-in-time recovery possible, and it is not optional: holds, access rows and above all **drafts** live only in the database.
2. **Repositories — every fifteen minutes.** Each repository that changed is written as a `git bundle` **while holding its writer lock**, verified, and copied off-host; after each nightly base backup every repository gets a full bundle, which starts its next chain. A bundle that fails verification is not copied, and that run is not recorded as complete. Never a plain copy of a repository that may be mid-write: it can yield a ref pointing at an object the copy missed. ⟨command: fixed when backup is implemented⟩
3. **Off-host, encrypted.** Both copies leave the host encrypted, under keys kept in `.env` and never in the backup store. **Keep a copy of those keys away from the platform**: without them no backup can be read, and a fresh host needs them in step 3 of case A. *Nothing is ever lost* is true only while this step runs.
4. **Housekeeping.** A periodic repack runs per repository, under its lock. Pruning removes only unreachable objects, and in an append-only history those are debris from failed writes — it cannot remove a version (ASR-02, `verification-plan.md` V-08).

How much may be lost, and how long a restore may take, are the recovery objectives in [`asr.md`](asr.md).

**Rehearse.** A restore is rehearsed on a copy — never on the live host — before production opens and after any change to the backup tooling, and the rehearsal is logged with its date and how long it took.

## Restore

### First, decide which case this is

| What happened | Case |
|---|---|
| The host is gone or its disks cannot be trusted | **A — full restore to a fresh host** |
| The host and its repositories are fine; the database is lost, or holds bad data from a known time | **B — database to a point in time** |
| One document's repository is damaged; everything else is fine | **C — one repository** |

Write down, before touching anything: **what happened, when it was noticed, and the recovery point you are aiming for** — the last moment known to be good. In case A it can be no later than the start of the last complete bundle run (step 4). Every later step refers to it.

### A — full restore to a fresh host

1. **Stop anything still writing.** On the old host, if it is reachable, as the deploying user: stop `web` and `worker`. Nothing may write to either store while you restore.
2. **Preserve the damaged state.** Copy what is left aside; do not delete it. It is the evidence of what failed and the fallback if the restore goes wrong.
3. **Prepare the new host.** Install the containers from the repository checkout, and put `.env` in place from where the host's credentials are kept — the backup keys with it. Do not start `web` or `worker`.
4. **Restore the database — no later than the repositories.** Read from the off-host copy when the last complete bundle run began ⟨command: fixed when backup is implemented⟩; the recovery point is that time, or the last moment known to be good if that is earlier, and **never later**: a database restored past its repositories names commits no copy holds. Inside a fresh `db` container, as the database superuser: restore the base backup before the recovery point from the off-host copy and replay the archived log **up to the recovery point** ⟨command: fixed when backup is implemented⟩. Start `db` alone and confirm it accepts connections.
5. **Restore the repositories.** On the new host, as the application user: restore each repository from its bundles in the off-host copy — the latest full bundle, then every bundle after it, in order ⟨command: fixed when backup is implemented⟩. A repository may come back ahead of the database; step 6 replays the difference. Ownership is the application user, mode `0750`.
6. **Run the reconciler in report mode** ⟨command: fixed when the reconciler is implemented⟩ and read its report before repairing anything. Expect:
   - **commits without rows** — git is ahead of the database; the reconciler replays them. Normal after any restore;
   - **rows whose commit is missing** — not expected here, since the database was restored no later than the repositories. One that appears means a bundle is missing: stop and find it. The reconciler deletes nothing on its own ⟨procedure: fixed when the reconciler is implemented⟩;
   - **rows in `creating` without a repository** — retried;
   - **repositories without a row** — reported as orphans and recreated from `document.md`'s frontmatter **with no access rows at all**. The tenant administrator is notified and grants access again. This fails closed on purpose;
   - **a passport that disagrees with the rows** — reported as an audit event; the passport is believed.
7. **Run the reconciler in repair mode**, then run it again in report mode and confirm it reports nothing new.
8. **Start `redis`, then `worker`, then `web`.** Redis starts empty; the reconciler re-enqueues every task that has a row.
9. **Verify as a user would.** Sign in; open a restored document; confirm its latest version and its last acceptance match its passport; export it.
10. **Tell the people who lost work.** Whatever was only in the database after the recovery point is gone — above all **drafts**. List the documents whose holds were open at the recovery point and tell each holder.
11. **Record it**: what failed, the recovery point, how long each step took, and anything in this procedure that was wrong.

### B — database to a point in time

Steps 1, 2, 4 and 6 to 11 of case A, on the same host, except that at step 4 the repositories are intact on the host and do not bound the recovery point: it is the last moment known to be good — for a lost database, its latest archived point, at most five minutes back. The repositories stay where they are: they are ahead of the restored database, and step 6 replays the difference. If the bad data was *written through git* — a wrong acceptance, a wrong version — it is not undone by a restore at all: history only moves forward, and the correction is a new commit that reverts it.

### C — one repository

1. Stop `web` and `worker`, or take that document's writer lock ⟨command: fixed when the git service layer is implemented⟩.
2. Move the damaged repository aside.
3. Restore that one repository into place from its bundles in the off-host copy — the latest full bundle, then every bundle after it, in order ⟨command: fixed when backup is implemented⟩.
4. Run the reconciler for that document, then release the lock or restart the containers.
5. Commits made to that document after its last bundle are lost, and the database still has version rows for them; the reconciler's handling of those rows is ⟨procedure: fixed when the reconciler is implemented⟩. Tell the authors, and record it.

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
> The order of steps and what each must achieve follow from the write protocol in [`technical-design.md`](technical-design.md) and do not change. The **tools** — which program takes the database's continuous archive, how repositories are snapshotted, where the off-host copy lives — are chosen in Epic 3, Story 5. Every step that needs a command says **⟨command: fixed when backup is implemented⟩** until then. Epic 3's documentation story extends this file; it does not start another one.

## What exists and where

| Thing | Where | In the backup set |
|---|---|---|
| **Database** — PostgreSQL, one schema per tenant plus a shared schema | the `db` container, on its data volume | **yes** — a base backup plus the continuous archive of the write-ahead log |
| **Repositories** — one bare repository per document | the repository root, mounted at `/srv/repos` in `web` and `worker` | **yes** — copied after the database |
| **Broker** — Redis | the `redis` container | **no** — it holds nothing that is not also a row; it starts empty and the reconciler re-enqueues |
| **Configuration** — `.env` | the host, beside the compose file | **no** — kept with the host's credentials, never in this repository |
| **Off-host copy** | ⟨destination: supplied by the operator⟩ | holds the latest database backup, its archive, and the repositories |

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

**Order is the whole point: the database first, the repositories second.** History is append-only and no commit spans two documents, so each repository copied *after* the database contains at least what the database knew about it. The reverse order can leave a row pointing at a commit no copy holds.

1. **Database — continuously.** The write-ahead log is archived as it is written and shipped off-host; a base backup is taken on a schedule. ⟨command: fixed when backup is implemented⟩. This is what makes point-in-time recovery possible, and it is not optional: holds, access rows and above all **drafts** live only in the database.
2. **Repositories — after each database base backup.** Either a filesystem snapshot of the whole repository root, or each repository copied **while holding its writer lock**. Never a plain copy of a repository that may be mid-write: it can yield a ref pointing at an object the copy missed. ⟨command: fixed when backup is implemented⟩
3. **Off-host.** Both copies leave the host. *Nothing is ever lost* is true only while this step runs.
4. **Housekeeping.** A periodic repack runs per repository, under its lock. Pruning removes only unreachable objects, and in an append-only history those are debris from failed writes — it cannot remove a version (ASR-02, `verification-plan.md` V-08).

How much may be lost, and how long a restore may take, are the recovery objectives in [`asr.md`](asr.md).

**Rehearse.** A restore is rehearsed on a copy — never on the live host — before production opens and after any change to the backup tooling, and the rehearsal is logged with its date and how long it took.

## Restore

### First, decide which case this is

| What happened | Case |
|---|---|
| The host is gone or its disks cannot be trusted | **A — full restore to a fresh host** |
| The host is fine; the database holds bad data from a known time | **B — database to a point in time** |
| One document's repository is damaged; everything else is fine | **C — one repository** |

Write down, before touching anything: **what happened, when it was noticed, and the recovery point you are aiming for** — the last moment known to be good. Every later step refers to it.

### A — full restore to a fresh host

1. **Stop anything still writing.** On the old host, if it is reachable, as the deploying user: stop `web` and `worker`. Nothing may write to either store while you restore.
2. **Preserve the damaged state.** Copy what is left aside; do not delete it. It is the evidence of what failed and the fallback if the restore goes wrong.
3. **Prepare the new host.** Install the containers from the repository checkout, and put `.env` in place from where the host's credentials are kept. Do not start `web` or `worker`.
4. **Restore the database.** Inside a fresh `db` container, as the database superuser: restore the latest base backup from the off-host copy and replay the archived log **up to the recovery point** ⟨command: fixed when backup is implemented⟩. Start `db` alone and confirm it accepts connections.
5. **Restore the repositories.** On the new host, as the application user: copy the repositories from the off-host copy into the repository root, **from a copy taken after the database backup you just restored**. Ownership is the application user, mode `0750`.
6. **Run the reconciler in report mode** ⟨command: fixed when the reconciler is implemented⟩ and read its report before repairing anything. Expect:
   - **commits without rows** — git is ahead of the database; the reconciler replays them. Normal after any restore;
   - **rows in `creating` without a repository** — retried;
   - **repositories without a row** — reported as orphans and recreated from `document.md`'s frontmatter **with no access rows at all**. The tenant administrator is notified and grants access again. This fails closed on purpose;
   - **a passport that disagrees with the rows** — reported as an audit event; the passport is believed.
7. **Run the reconciler in repair mode**, then run it again in report mode and confirm it reports nothing new.
8. **Start `redis`, then `worker`, then `web`.** Redis starts empty; the reconciler re-enqueues every task that has a row.
9. **Verify as a user would.** Sign in; open a restored document; confirm its latest version and its last acceptance match its passport; export it.
10. **Tell the people who lost work.** Whatever was only in the database after the recovery point is gone — above all **drafts**. List the documents whose holds were open at the recovery point and tell each holder.
11. **Record it**: what failed, the recovery point, how long each step took, and anything in this procedure that was wrong.

### B — database to a point in time

Steps 1, 2, 4 and 6 to 11 of case A, on the same host. The repositories stay where they are: they are ahead of the restored database, and step 6 replays the difference. If the bad data was *written through git* — a wrong acceptance, a wrong version — it is not undone by a restore at all: history only moves forward, and the correction is a new commit that reverts it.

### C — one repository

1. Stop `web` and `worker`, or take that document's writer lock ⟨command: fixed when the git service layer is implemented⟩.
2. Move the damaged repository aside.
3. Copy that one repository from the latest off-host copy into place.
4. Run the reconciler for that document, then release the lock or restart the containers.
5. Commits made to that document after the copy was taken are lost, and the database still has version rows for them; the reconciler's handling of those rows is ⟨procedure: fixed when the reconciler is implemented⟩. Tell the authors, and record it.

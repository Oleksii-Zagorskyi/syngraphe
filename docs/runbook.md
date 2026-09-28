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


> **Status.** § Deploy, § First run and § Create an organisation name commands that run. § Backup and
> § Restore were written before the system they operate: every procedure there is
> the intended one, none has been executed against a running deployment, and the
> rehearsal of a restore is a task of its own.

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
cp .env.example .env         # fill in every ??? — the application reports every missing key at once
mkdir -p .repos              # or the directory GIT_REPO_ROOT_HOST names
docker compose up -d --build # web migrates every schema and seeds the language lists before it answers
docker compose ps --format '{{.Service}} {{.State}}'    # web, worker, db, redis — each running
curl -s http://127.0.0.1:8000/health/                    # {"database": "ok", "redis": "ok"}
```

The health check uses the port `WEB_PORT` names, `8000` by default. **Behind the host's reverse proxy**, set in `.env`:

- `WEB_PORT` — the loopback port the proxy forwards to;
- `TRUSTED_PROXIES` — `none` on an installation reached directly; behind a proxy, where the proxy's connections arrive from as `web` sees them. Through Compose's published port that is the gateway of the project's network, not the loopback: `docker network inspect <project>_default --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'`. The client's address, the scheme and the host are then read from the last entry of the proxy's `X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host`: the proxy must **append** the client's address to `X-Forwarded-For` and **overwrite** the other two, never pass a client's own values through. Set to `none` behind a proxy, every client would share one address for sign-in throttling and the host check would see the upstream address instead of the installation's name;
- `SITE_HTTPS=true` when the proxy terminates TLS, so the session and CSRF cookies are sent over HTTPS only; `false` for an installation reached over plain HTTP, such as a check through a tunnel to `127.0.0.1`, where secure-only cookies would never be sent and nobody could sign in.

The containers restart with the host's Docker unless stopped by hand. **After an update:** `git pull`, then `docker compose up -d --build`; the migrations run as `web` starts. A migration that failed for one organisation is completed with `docker compose exec web python manage.py migrate_schemas --tenant N`, `N` being the organisation's number; nothing else is needed.

**Production** runs behind the operator's reverse proxy (DL-0281); its procedure arrives with the production Compose override, and until then this section is the development host's.

## First run

Once, on a fresh installation, to create the first platform administrator (DL-0231):

```bash
docker compose exec web python manage.py setup_token --host <the installation's host name>
```

The command prints a token, valid once for sixty minutes, and makes that host the default platform host; the running `web` accepts the host within thirty seconds. Open `/setup/` on the installation's host name, enter the token, then the administrator's email address and a password. The administrator is signed in and lands in Administration.

- **The token expired or was lost:** run the command again. A new token replaces the old one.
- **Afterwards** the page answers *Nothing to show here*, and the command refuses with `A platform administrator already exists.`

## Create an organisation

In Administration › Platform › Organisations, *Create an organisation*: its name, and the email address of a registered person who becomes its first administrator. The organisation gets the next number, and its schema is created and migrated in the same act; it is listed *active*.

- **A migration that failed** leaves the organisation listed *being set up*, reachable by nobody, with the failure in the audit log. Once the fault is fixed: `docker compose exec web python manage.py migrate_schemas --tenant N`, `N` being its number; it becomes active.
- **Its own domain**, if it has one: Administration › Platform › Hosts, *Add a host*, belonging to the organisation. Its first domain is its default. A removed host stops answering within thirty seconds.

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

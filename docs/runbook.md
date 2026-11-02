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

How to deploy the platform, back it up, and **restore it when something has gone wrong**.

The order of the restore's steps, and what each must achieve, follow from the write protocol in [`technical-design.md`](technical-design.md). The tools are [ADR-0018](adr/ADR-0018-backup-and-restore.md)'s and [ADR-0019](adr/ADR-0019-backup-when-something-fails.md)'s: pgBackRest for the database's continuous archive, a `git bundle` of each repository written under its writer lock, one encrypted off-host backup store the operator names.

## What exists and where

| Thing | Where | In the backup set |
|---|---|---|
| **Database** — PostgreSQL, one schema per tenant plus a shared schema | the `db` container, on its data volume | **yes** — a nightly base backup plus the continuous archive of the write-ahead log, taken by the `backup` container |
| **Repositories** — one bare repository per document | the repository root, mounted at `/srv/repos` in `web` and `worker`, and read-only in `render` | **yes** — a bundle every ten minutes of each repository that changed, a full bundle after each base backup |
| **Backup state** — the newest marker, the base backup's label, the log waiting | the `backup-state` volume: `backup/` written by `backup`, `worker/` by `worker`, read by `web` | **no** — rebuilt by the next run |
| **Exports** — the files people export, each kept a day, then swept; the job rows stay | the `exports` volume at `/srv/exports`: written by `render`, served by `web` | **no** — a download, not a record; exported again at will |
| **Broker** — Redis | the `redis` container | **no** — it holds nothing that is not also a row; it starts empty |
| **Configuration** — `.env` | the host, beside the compose file | **no** — kept with the host's credentials, never in this repository. It holds the backup keys, without which no backup can be read |
| **Off-host copy** | the backup store `.env` names | holds two full database backups and their archive, and each repository's newest two chains of bundles — all encrypted |

Every step below says **where it runs** — the host shell, or inside a named container — and **as whom**. Commands on the host run in the repository checkout, as the deploying user.

## Deploy

**Development host.** On the host, as the deploying user, in the repository checkout:

```bash
cp .env.example .env         # fill in every ???, the store's for its kind only — every missing key is reported at once
mkdir -p .repos              # or the directory GIT_REPO_ROOT_HOST names
docker compose up -d --build # web migrates every schema and seeds the language lists before it answers
docker compose ps --format '{{.Service}} {{.State}}'    # web, worker, render, db, backup, redis — each running
curl -s http://127.0.0.1:8000/health/    # {"database": "ok", "redis": "ok", "backup": {…}}
```

`.env` names the backup store and its keys before the first start (§ Backup, *The store*): `db` and `backup` refuse to start without the store's settings and the database archive's key, naming every key missing; the bundles' key is checked when the worker's first bundle run starts, and a missing one fails that run. The health check uses the port `WEB_PORT` names, `8000` by default. **Behind the host's reverse proxy**, set in `.env`:

- `WEB_PORT` — the loopback port the proxy forwards to;
- `TRUSTED_PROXIES` — `none` on an installation reached directly; behind a proxy, where the proxy's connections arrive from as `web` sees them. Through Compose's published port that is the gateway of the project's network, not the loopback: `docker network inspect <project>_default --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'`. The client's address, the scheme and the host are then read from the last entry of the proxy's `X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host`: the proxy must **append** the client's address to `X-Forwarded-For` and **overwrite** the other two, never pass a client's own values through. Set to `none` behind a proxy, every client would share one address for sign-in throttling and the host check would see the upstream address instead of the installation's name;
- `SITE_HTTPS=true` when the proxy terminates TLS, so the session and CSRF cookies are sent over HTTPS only; `false` for an installation reached over plain HTTP, such as a check through a tunnel to `127.0.0.1`, where secure-only cookies would never be sent and nobody could sign in.

`db` is built on `postgres:16`, which carries ICU: the document list orders titles by the `uk-x-icu` collation, and a PostgreSQL built without ICU fails that page. The containers restart with the host's Docker unless stopped by hand. **After an update:** `git pull`, then `docker compose up -d --build`; the migrations run as `web` starts. A migration that failed for one organisation is completed with `docker compose exec web python manage.py migrate_schemas --tenant N`, `N` being the organisation's number; nothing else is needed.

**Production** runs behind the operator's reverse proxy (DL-0281) with the production override, `deploy/compose.prod.yaml`, read over the base file: `docker compose -f compose.yaml -f deploy/compose.prod.yaml …` for every command, written `$C` below. It adds `front`, an nginx that terminates the installation's own TLS on the one port the host allows and forwards to `web`, which then publishes no port; it runs `web`, `worker` and `render` on the release's image; it puts the repositories, the database, the archive's spool and the backup state under one data directory as bind mounts — the exports stay on their named volume, a download kept a day; and it pins the stack's network, so `TRUSTED_PROXIES` names it. Its keys are the block *Compose only — the production override* of `.env.example` — fill every `???` there first: the override refuses a key that is unset, but not one still reading `???`: `RELEASE_TAG`, `FRONT_PORT`, `FRONT_CERT_FILE`, `FRONT_KEY_FILE`, `FRONT_SERVER_NAME`, `FRONT_CLIENT_IP_HEADER` (the header the operator's proxy carries the client's address in; the front passes it to the application as `X-Forwarded-For`), `DATA_DIR` and `STACK_SUBNET`. The front also reads `UPLOAD_MAX_MB`, which the application reads too (§ The upload maximum). The override sets `web`'s `TRUSTED_PROXIES` to `STACK_SUBNET`, so the front's headers are believed; `COMPOSE_PROJECT_NAME` is set, so one project spans every release's checkout. **`FRONT_PORT` must be reachable from the operator's proxy alone**: the front passes on the client's address as that proxy reports it, and a client reaching the port directly could report its own.

- **The data directory's owners.** On a host whose Docker maps container users to other host users, create `repos/`, `backup-state/`, `pgdata/` and `pgspool/` through a one-off container, so they belong to the mapped users of `app` (1000) and `postgres` (999): `docker run --rm -v "$DATA_DIR:/d" alpine sh -c 'mkdir -p /d/pgdata /d/pgspool /d/repos /d/backup-state && chown -R 999:999 /d/pgdata /d/pgspool && chown -R 1000:1000 /d/repos /d/backup-state'`; then `chmod 700 "$DATA_DIR"`, so no other account on the host reads the repositories, and `ls -ld "$DATA_DIR"` shows `drwx------`.
- **Delivery.** Nothing is deployed to production before the launch, which settles how code reaches it (DL-0364).
- `front` resolves `web` through Docker's resolver on every request, so recreating `web` needs nothing of `front`.

### Adding a member by command

Invitations are the way in (DL-0374), sent from the organisation's sending address or else the platform's. Where neither exists, so no invitation can be sent, an operator adds a person as an ordinary member by command (DL-0343):

```bash
$C exec web python manage.py create_member --tenant N --email ADDRESS --name "Display name"
```

A new person gets a generated password, **printed once** — run the command in the operator's own terminal and hand the password over by hand; it is shown nowhere again. The person keeps it until a sending address exists: *Forgot your password?* on the sign-in page sends its link by email, and without a sender no email leaves. A person already registered gets the membership only, and their password is never changed; an existing active member is reported and nothing is written. Then add the membership to its groups on the group's page.

### Loading a document

A document prepared outside the platform enters it by command (DL-0341, DL-0348), one folder per document:

```
<folder>/
  document.yaml      title, language, attachments: [{file, title}]
  document.md        the body only, Markdown inside the whitelist, no frontmatter
  <file> …           each attachment document.yaml names, beside it
```

```bash
$C run --rm --no-deps -v /path/to/folders:/srv/load:ro web \
  python manage.py load_document --tenant N --as ADDRESS --group GROUP_ID /srv/load/<each> …
```

`GROUP_ID` is the group's id, from the address of its rights page. The member must belong to that group, and the group must hold *create and edit* and *accept*. The loader links each document to that group alone: for readers, link it to their group on the document-links page, and make it canonical (§ Making a document canonical) before that group holds only *view canonical* — a reader of canonical text does not see a document before its first edition (DL-0350). Each folder becomes a document linked to the group, its text and attachments committed as one version and accepted as `0.1`; the command prints `document M · version 0.1 · attachments: K`, after a line `line N is joined with the next` for each line the stored form joins to the next — a sentence the folder carried over a line — which refuses nothing. A number before a heading's text that equals the number the outline gives it is taken away. Every check — the folder against its description, the whitelist, image references (the loader takes no images; add them in the editor after loading), each file against the organisation's attachment limit, the member's rights, and once those pass the size of the normalised text — runs before anything is written, and every reason found is reported at once. The first folder refused stops the run; those loaded before it stand, and running the same command again skips them (`document M already loaded — skipped`). A load that stops after the document exists names the step: `reconcile --tenant N --document M` and the interface continue it, and nothing is deleted. Remove the folders from the host afterwards.

### Making a document canonical

A loaded document, or any accepted one, becomes its next edition by command (DL-0350): the act itself needs no freeze (DL-0515), but the command freezes first, so that the operator's reason stands on the freeze with the approval and is shown to readers, and then makes it canonical through the same acts as the document page.

```bash
$C exec web python manage.py make_canonical --tenant N --document M --as ADDRESS --reason "…"
```

The member must hold *make canonical* on the document through a group, and *freeze* only because the command freezes. Where the organisation requires a distinct approver, name a member who accepted none of the runs since the previous edition; the loading member accepted the loaded version, so name another. The command prints `document M · edition N.0`; run again on a document already at its edition, it prints `document M · edition N.0 already made — skipped` and changes nothing. Nothing is frozen when a refusal can be known beforehand — versions waiting for review, a refused approver, a reason of more than one line or 500 characters, a tag already bearing the next edition's number — and the refusal is named, as it is for a document with nothing accepted at all (`nothing_accepted`). A document already frozen is made canonical under its freeze, and `--reason` is not used. **Readers holding *view accepted* are lowered to *view canonical* only after each of their documents has an edition**; in the other order the documents disappear for them.

### A freeze nobody can end

A holder of *freeze and unfreeze* ends a freeze with *Unfreeze*, and a holder of *make canonical* by making the document canonical. Where no member holds either right, the operator ends it:

```bash
$C exec web python manage.py end_freeze --tenant N --document M --reason "…"
```

The command prints `document M · freeze ended`; the freeze ends as *unfrozen*, the numbering unchanged, and the reason is written to the audit log. A document that is not frozen is reported — `document M is not frozen` — and nothing changes. **An edition made by mistake is never removed**: the correction is edited, accepted and made canonical as the next edition, and the record keeps both.

### Help as work in progress

`HELP_WORK_IN_PROGRESS=true` in `.env` makes every help page show its heading and *Work in progress* alone, until the pages' text is agreed (DL-0344); `$C up -d web` applies it.

### The upload maximum

`UPLOAD_MAX_MB` in `.env` sets the platform's largest upload, in whole megabytes of 1024 × 1024 bytes, 20 by default (DL-0432) — an image at most 10 MB, or `UPLOAD_MAX_MB` where that is lower, and held to 40 megapixels and 10,000 pixels a side whatever `UPLOAD_MAX_MB` allows; the application and, in production, the front read it. The front admits a request body one megabyte larger, for the form's other fields, and refuses a larger one itself. A value that is not a whole number above zero is refused by `web` as a configuration error, and stops the front as it starts, naming the key. `$C up -d` applies a change.

An organisation's attachment size cap cannot be set above the maximum (DL-0469). Lowering the maximum leaves a larger cap stored as it is: uploads are then refused at the maximum, and the organisation's settings page shows the cap and refuses to save it until an administrator lowers it.

## First run

Once, on a fresh installation, to create the first platform administrator (DL-0231):

```bash
docker compose exec web python manage.py setup_token --host <the installation's host name>
```

The command prints a token, valid once for sixty minutes, and makes that host the default platform host; the running `web` accepts the host within thirty seconds. `127.0.0.1` stays in the set — the container's own health check and a tunnel reach it — until a platform administrator removes it on the hosts page. Open `/setup/` on the installation's host name, enter the token, then the administrator's email address and a password. The administrator is signed in and lands in Administration.

- **The token expired or was lost:** run the command again. A new token replaces the old one.
- **Afterwards** the page answers *Nothing to show here*, and the command refuses with `A platform administrator already exists.`

## Create an organisation

In Administration › Platform › Organisations, *Create an organisation*: its name, and the email address of a registered person who becomes its first administrator. The organisation gets the next number, and its schema is created and migrated in the same act; it is listed *active*.

- **A migration that failed** leaves the organisation listed *being set up*, reachable by nobody, with the failure in the audit log. Once the fault is fixed: `docker compose exec web python manage.py migrate_schemas --tenant N`, `N` being its number; it becomes active.
- **Its own domain**, if it has one: Administration › Platform › Hosts, *Add a host*, belonging to the organisation. Its first domain is its default. A removed host stops answering within thirty seconds.

## People

Invitations, resets and blocks are the administrators' own pages; help page *People and access* describes them. Three cases need an operator. Lifting a block leaves ended what the block ended. Every block — a membership's, an organisation's, a person's own — ends the holds it reaches. A membership's and an organisation's block also end the invitations still open there when it was written; the person is invited again for a fresh link. A person's own block ends no invitation: a link sent before it still sets the password, and the account reaches nothing until the block is lifted.

- **Lifting a person's own block.** Nothing in the platform lifts it in this release (DL-0254): a platform administrator asks the operator, who lifts it in the database. With the person's address in `ADDRESS`, write the flag, its history row and the audit event in one transaction; the address is folded as the platform stores it, and a person not blocked by themselves is left untouched:

  ```bash
  $C exec web python manage.py shell -c "
  from django.db import transaction
  from audit.record import record
  from identity.models import AccountBlockHistory, User, fold_email
  with transaction.atomic():
      person = User.objects.select_for_update().get(email=fold_email('ADDRESS'))
      if not person.self_blocked:
          raise SystemExit('not blocked by themselves; nothing written')
      person.self_blocked = False
      person.save(update_fields=['self_blocked'])
      AccountBlockHistory.objects.create(user=person, action='block_lifted', by=None)
      record(actor=None, action='user.self_block_lifted', obj=person,
             before={'self_blocked': True}, after={'user': str(person.pk)})
  "
  ```

  The person's memberships and groups apply as they stood. The documents they held were released when they blocked their account; their drafts are kept.
- **An organisation blocked by mistake** is lifted from Administration › Platform › Organisations, *Lift the block*. Nothing is rebuilt: its memberships, groups and links stand as they were. The holds the block ended stay ended, their drafts kept.
- **The platform's last administrator lost** — erased, or blocked with nobody left to lift it — is recovered in the database the same way, by setting `is_platform_admin` or lifting the block as above (backlog B-035).

## Backup

**The database is never restored past the repositories.** History is append-only and no commit spans two documents, so each repository copied *after* the database's recovery point contains at least what the database knew about it. The reverse can leave a row pointing at a commit no copy holds — a version gone from both stores.

**The store.** `.env` names it: `BACKUP_TARGET` — `sftp` or `s3` — and the keys that kind needs, with a path of the installation's own (`BACKUP_SFTP_PATH` or `BACKUP_S3_PATH`), under which the database's archive goes to `database/` and the bundles to `bundles/`. For `sftp`: `BACKUP_KEY_FILE`, the host path of the SSH private key, readable by the application's user (uid 1000) — `db` and `backup` copy it for their own user as they start; and `BACKUP_SFTP_KNOWN_HOSTS`, the store's host key as one `known_hosts` line, which both tools pin. `BACKUP_EXTRA_HOST` gives the containers an address for a store whose name they cannot resolve. For `s3`, set `BACKUP_KEY_FILE=/dev/null`. A production store keeps whatever the host deletes for thirty days, by its own control (DL-0298).

1. **Database — continuously.** pgBackRest ships each completed segment of the write-ahead log off-host, asynchronously, and a segment that has not filled is closed within five minutes; a full base backup is taken nightly at 02:00 UTC, and two are kept with their archive. If the store cannot be reached, the log waits on the host up to `BACKUP_WAL_QUEUE_MAX`; past it, segments are dropped rather than let the disk fill, and the archive has a gap until the next full base backup (see *The store is unreachable*). This is what makes point-in-time recovery possible, and it is not optional: holds, access rows and above all **drafts** live only in the database.

   ```bash
   docker compose exec -u postgres db pgbackrest --stanza=syngraphe check   # a segment reaches the store
   docker compose exec -u postgres db pgbackrest --stanza=syngraphe info    # the backups, the archive, cipher: aes-256-cbc
   ```

2. **Repositories — every ten minutes.** Each repository that changed is written as a `git bundle` **while holding its writer lock**, the lock released as soon as the file is written; the bundle is then verified and copied off-host. Every repository whose newest full bundle is older than the newest base backup gets a full bundle, which starts its next chain, and gets one again on every run until one lands. **Every run writes a marker** in the store, listing any repository whose bundle failed and since when; a marker listing none is *clean*, and is what a full restore aims at. Each repository keeps its newest two chains — a *chain* being a full bundle and the bundles after it — and a marker is kept until it is older than the oldest chain any repository keeps, the newest clean marker always (DL-0316). Never a plain copy of a repository that may be mid-write: it can yield a ref pointing at an object the copy missed. The worker runs this on its own; a run now, from the host:

   ```bash
   scripts/backup-repositories.sh   # prints the run's marker and any repository that failed
   ```

3. **Off-host, encrypted.** Both copies leave the host encrypted, the database's archive under `BACKUP_DB_CIPHER_PASS` and the bundles under `BACKUP_BUNDLE_CRYPT_PASSWORD`, keys kept in `.env` and never in the backup store. In production the store keeps whatever the host deletes for thirty days, by its own control, so that whoever takes the host cannot destroy the backups. **Keep a copy of `.env` and of the key file `BACKUP_KEY_FILE` names away from the platform**: without the two encryption keys no backup can be read, and without the store's credentials no backup can be reached; a fresh host needs all of them in step 3 of case A. *Nothing is ever lost* is true only while this step runs.

**Watch it.** `/health/` shows the backup's state: the age of the newest clean marker, whether any repository is failing — which ones only in the worker's log, as *a repository's bundle failed* with its numbers — the last segment archived and the log waiting. It does not change the endpoint's status. Each change of the three conditions — a repository failing, no clean marker newer than fifteen minutes, the waiting log past `BACKUP_WAL_ALERT` — is logged once at error level by the worker, and told to every platform administrator as an administrative notification — by email too, once the platform has a sending address (§ Mail). With no platform administrator to tell, the worker tries again on its next run.

**The store is unreachable.** The waiting log grows on the host's disk. Bring the store back; confirm `pgbackrest check` passes and a new clean marker appears. If the waiting log reached `BACKUP_WAL_QUEUE_MAX`, the archive has a gap: take a full base backup at once — until it completes, no restore can reach a moment after the gap began:

```bash
docker compose exec backup su postgres -s /bin/sh -c '. /run/backup/environment; /usr/local/bin/backup-state.sh base'
```

It takes the full base backup and records it, so the next bundle run starts new chains after it.

How much may be lost, and how long a restore may take, are the recovery objectives in [`asr.md`](asr.md).

**Rehearse.** A restore is rehearsed on a copy — never on the live host — before production opens and after any change to the backup tooling, and the rehearsal is logged with its date and how long it took.

## Housekeeping

**No row of the history is ever deleted.** The access changes, the memberships' history, the account blocks' history, the organisations' state history and the audit trail refuse an update or a delete by database trigger (DL-0459). A restore replaces them whole; nothing in operating the platform removes a row of them.

Nightly at 01:35 UTC, before the base backup, the worker repacks every repository and prunes what nothing reaches, each under its writer lock. **Pruning cannot remove a version**: it removes only unreachable objects, and in an append-only linear history those are debris from failed writes (ASR-02, [`verification-plan.md`](verification-plan.md) V-08). A repository whose lock stays held is left for the next night and logged. The repack is also what keeps the nightly run of full bundles inside five minutes (DL-0313).

## The reconciler

Git is the commit point and the rows are its cache; the reconciler is the second path from git to the rows. It runs **hourly in repair mode** without deleting anything, and an operator runs it by hand after a restore. Each finding names the organisation's number (*tenant*) and the document's; every repair is recorded in the audit log.

```bash
docker compose exec web python manage.py reconcile                        # report: changes nothing; exit 1 when anything is found
docker compose exec web python manage.py reconcile --repair               # repair what git implies; exit 1 while anything is left
docker compose exec web python manage.py reconcile --repair --prune-rows  # also delete version rows whose commit is gone
docker compose exec web python manage.py reconcile --tenant N --document M   # one document
```

Run report mode first and read it before repairing anything; `--prune-rows` only after reading the report, since it is the one deletion. When `web` is stopped, as during a restore, run the same commands with `docker compose run --rm web python manage.py reconcile …`; the output is the command's own.

| Finding | Means | `--repair` | `--prune-rows` |
|---|---|---|---|
| `creating_without_repository`, `creating_without_commit`, `creating_without_version`, `creating_unfinished` | a creation stopped at that step (ten minutes or more ago) | finishes it: the document becomes active, reaching its creator alone — nobody while the creator is blocked. Left as found when the creator was never a member of the organisation; a repository at its number that names another document is reported as `identity_mismatch` instead | — |
| `copy_stopped` | a copy stopped after its row and the record of its source were written (ten minutes or more ago): it stays invisible, reaching nobody, and its copier was told to copy again (DL-0455) | reports it; **never finished** — finishing it would make the template's document under the copy's title. Remove it with `remove_stopped_copy` (below) | — |
| `commit_without_row` | git is ahead of the rows — normal after any restore | derives the version row, for a commit by a member of the organisation, of an ordinary kind — or an acceptance, a return or an approval, from the one passport section its commit appended, exactly as the platform writes one: an acceptance with its correction notices, a return with its authors told, an approval with its tag, its edition and its freeze's end — after the newest commit the rows know. It stops at the first commit it cannot derive, and derives nothing while the document has a `row_without_commit`: what follows is reported, never derived past a hole | — |
| `row_without_commit` | a version row names a commit its repository does not hold — a repository restored from an older bundle | reports it | deletes the row, and with it the rows derived from it: an acceptance or a return it records or started from, a correction notice naming it, their notifications, the export jobs that exported it or marked against it — each counted in the audit |
| `orphan_repository` | a repository with no row | recreates the row from `document.md`, in the root folder, type *document*, **with no groups and not author-only** — only administrators reach it until the tenant administrator links groups. Only when its first commit's author is a member of the organisation and its language is known; otherwise reported | — |
| `frontmatter_differs` | the row's title or language differs from `document.md` | rewrites the row from the file | — |
| `orphan_part` | a file under `appendices/` or `attachments/` at the head that the head's frontmatter does not list; the detail names its path | reports it; **never repaired or deleted** — the history keeps it, and whether it belongs is the document's editors' to say | — |
| `part_missing` | a part the head's frontmatter lists whose file is absent; the detail names its path | reports it; never repaired — the reading view leaves the appendix out and the download answers as missing until an editor replaces or removes the part | — |
| `passport_entry_without_row` | the passport records an acceptance, a return or an approval no row records | reports it; the passport is believed, and repair derives the row as `commit_without_row` does. A passport that does not read is reported heading by heading | — |
| `repository_missing` | a document's repository is not on disk | reports it; **nothing is pruned** — it may be a missing mount, not a loss | — |
| `identity_mismatch` | a repository whose passport names another organisation or number, or not the creation its row began | reports it; never trusted | — |
| `sequence_behind` | the next document number would repeat one a repository directory already has, with a row or without | moves the number past it | — |
| `locked` | the document's writer lock stayed held for thirty seconds | tried again next run | — |
| `unreadable` | a repository or file the reconciler could not read; the log — the worker's, or the command's own output — names the error | reports it | — |
| `finish_stopped` | a *send for review* stopped after its commit: the holder's hold is still open with a draft whose base is behind a content commit of theirs, `edit` or `reviewer_edit`, or a finished hold still has its draft | releases the hold as finished and deletes the draft that commit consumed; the version row is `commit_without_row`'s. Left as found, and reported with its reason, while the holder is no longer a member, the commit has no version row yet, or the draft holds work written after the stop — text, entities, appendices or files — the holder's next *send for review* then finishes it | — |
| `accept_as_stopped` | an *accept as* stopped between its version and its acceptance: the hold was released *accepting* and never turned *finished* | tells the reviewers the version awaits them — nobody, once an acceptance has taken it in — finishes the hold and deletes what is left of its draft (DL-0397) | — |
| `authorship_missing` | the newest version, or the latest accepted one, has no per-line authorship though its text has lines — the worker has not run yet, or its job was lost or failed | asks the worker for it again; a finding that returns on every run means the job fails, and the worker's log says why | — |
| `acceptance_differs` | an acceptance row disagrees with the passport section its commit appended — its number, reviewer, time or the version it started from — or no section of the platform's form stands behind it | rewrites the row from its section, audited; the passport is believed | — |
| `return_differs` | a return's row disagrees with the passport section its commit appended — its reviewer, time, reason or the version it started from — or its commit is not a return of the platform's form | rewrites the row from its section, audited without the reason's text; the passport is believed — reported only, when its commit is not of the platform's form | — |
| `notices_missing` | an acceptance whose correction notices were never computed — a stop after its rows, or a computation that failed | computes them; a failure is reported with its error and tried again next run | — |
| `edition_unfinished` | an approval's version whose edition row, tag or freeze's end is missing | derives what is missing from the approval's section: the tag with the approver's identity, the edition, the freeze's end — and, where a restore lost the freeze itself, the freeze the section proves (DL-0355) | — |
| `edition_differs` | an edition row disagrees with its approval's section, or an approval commit is not of the platform's form | reports it; the passport is believed | — |
| `export_stuck` | an export still queued ten minutes after it was asked for, at the next hourly run — `render` was down, or the broker lost the entry | queues it again; a job runs once however often it is queued. One that returns on every run means `render` fails it or is down: `docker compose ps render`, `docker compose logs render` | — |
| `export_abandoned` | an export still queued an hour after it was asked for, at the next hourly run — `render` has been down that long | fails it, *not made in time*, so its person may ask again; a job a render is making is left alone | — |
| `tag_without_section` | a tag names a commit that is not the approval of that number | reports it; **never repaired** — a person decides what the tag was | — |

**A stopped copy** is removed by its number, once the report has named it:

```bash
docker compose exec web python manage.py remove_stopped_copy --tenant N --document M
```

It refuses anything but a copy still being created past the ten minutes, deciding under the document's writer lock — a copy that finished meanwhile is kept. It removes the repository first, then the version rows and the document's row, audited as `document.stopped_copy_removed`; run again after a stop between the two, it removes what is left, and with nothing left it says so. The number is never given again.

A recreated orphan notifies nobody. Exports are the one task queued again from its row; the broker holds no other that matters.

## Editing

A person edits a document while they hold it; what they type is kept as a draft in the database, captured as they type, until they finish and a version is committed. The draft is theirs: an operator reads it but never edits or deletes it.

### A hold that will not release

A hold ends when its holder finishes. One that stays open — the holder has left, the document is needed — is released from the shell, with a reason that names neither the document nor a person:

```bash
docker compose exec web python manage.py release_hold --tenant N --document M --reason "…"
```

It marks the hold *forced*, **keeps the draft**, and records the release, with its reason, in the audit log. It waits for the document's writer lock, so it never releases a hold in the middle of a commit. **Never delete a hold or a draft row** — the draft is the holder's text. In the interface the same release is *Звільнити документ примусово* behind the document heading's *More* icon, for a tenant or platform administrator (DL-0522), and the holder ends their own hold with *Release the document*, or *Discard my edits* once something is edited (DL-0510).

A holder who cannot finish because *an editor is still open* first closes their other tabs on the document: an open tab keeps its editor open, however long. An editor whose page went away without closing it — a closed laptop, a crashed browser — is closed by the worker within about four minutes: silent for three, found by the check that runs every minute. If the wait lasts longer, the worker is not running.

### A draft that fails to load

Print the draft's content, as JSON, with its hold's details — the open hold's, or, when none is open, the latest hold's; the read is recorded in the audit log:

```bash
docker compose exec web python manage.py inspect_draft --tenant N --document M
```

A draft whose text the editor does not accept is never lost: the editor opens it in the source view, as Markdown, with each refused line named, and the holder corrects it there. An operator does not repair a draft by hand. When the editor says *busy*, the document's writer lock is held by another write — a commit or a backup bundle — and the holder tries again. Any other failure is in `web`'s log.

### Rolling back history, comparison, return and undo

The return adds a table and a notification event, and an export job a column, in every organisation's schema. No command migrates a schema backward: going back to the code before them is a restore to before the update (§ Restore). A `return` commit already in a passport stays in its repository; code from before the return reports it as `commit_without_row` and stops its replay there, and refuses every write to that document — a finish, an acceptance, a freeze — until the code is updated again. An undo commits nothing until its reviewer finishes; a draft an undo left wrong is the reviewer's to discard.

## The corpus

Folders, document types, archive and restore are acts of the tenant administrator in the interface, audited each; none touches a repository. **An archived document** is opened by administrators alone, read only, and restored from its page or *Administration › Archive*; its group links apply again as they stand. A document nobody can find is first looked for there.

### Rolling back folders, types, copying and archiving

The update adds, in every organisation's schema, a sequence for folder numbers, the uniqueness of a folder's name among its siblings and of a type's label, the rule that only the root folder has no parent, and a notification event for the holder of an archived document's work. No command migrates a schema backward: going back to the code before them is a restore to before the update (§ Restore). That restore takes with the database every copy made since — its row and the record of its source — while its repository stays on disk: the reconciler then reports it `orphan_repository` and recreates its row in the root folder, reaching administrators alone, its creator taken from its first commit's author where that person is still a member, and its source no longer known. **Remove every stopped copy first** — `reconcile` names them `copy_stopped` — so that none comes back as a document its copier was told did not exist.

## Reading and export

The reading view and every export render the text of a version the platform committed. An export is made by `render`, one job per request, and its file is kept a day under the exports volume, then swept; the job's row stays. Nothing there is a record: a lost file is exported again.

### A failed export job

The person who asked sees the reason on the job's page.

- **The text holds what the platform does not accept**, with the constructs named as the editor names them and their codes. The document's text is corrected in the editor, sent for review and accepted like any other change; where the refused version is the canonical one, the correction is also made canonical as the next edition (§ Making a document canonical), since a reader of canonical text exports nothing else. The export is then asked for again. An operator does not edit the repository.
- **The version asked for is no longer one you may export**: the person lost the right between asking and the run. This is not a fault.
- **Your draft has been finished or discarded since you asked**: a *my edits* export whose draft was sent for review or discarded before the run. Not a fault; the person exports another version.
- **The chosen version has no attachments to export**: attachments alone were asked of a version that has none. Not a fault.
- **An attachment has gone since you asked**: an attachment the export lists was not found when the zip was made. Not a fault; the person exports again.
- **An attachment's file does not match its record**: an attachment's stored bytes are not the ones its version lists — a defect. The render worker's log has *an attachment's file does not match its listed hash* with the document, the commit and the number; for a *my edits* export it reads *a draft's attachment does not match its listed hash*, with the draft.
- **The file could not be made**: the renderer failed. `docker compose logs render` has the error under *an export failed*, with the job's id. Failures of one document's every export point at its text, an image it names or the fonts; failures of every export point at `render` itself.
- ***Not made in time***: the job was still unrun at the first hourly reconciler run after it had waited an hour, one to two hours after the request, and `export_abandoned` failed it. `docker compose ps render` shows whether `render` is running; the person asks again once it is.

A job still queued is the reconciler's `export_stuck`: the first hourly run after it has waited ten minutes queues it again, and a job runs once however often it is queued. A job the broker refused when it was asked for is logged in `web` as *an export could not be queued* and waits for that run.

### The organisation's stylesheet and its fonts

A stylesheet names only the fonts the image installs, listed in `rendering.stylesheet.FONTS` and on the styles page; the checker refuses any other family, and the Word file's styles take their names from the same list. **Adding a font family is two changes in one release**: its package in `deploy/Dockerfile`, beside `fonts-dejavu-core` and `fonts-dejavu-extra`, and its name in `FONTS`. A name in `FONTS` the image does not install passes the checker and the renderer falls back to another font without saying so; a package without its name is never reachable. Check the result in the built image, in `render`: `fc-list : family` lists every name in `FONTS`.

A stylesheet the checker accepted when it was applied and refuses after a release — a rule tightened — reaches no reader: the reading view and every export use the platform's default look. The styles page still shows the stored text; *Apply* on it lists each refusal by its line, and the organisation's administrator corrects the text and applies it again.

### A sample that never finishes

The styles page's *Export a sample PDF* or *Word file* makes one sample at a time per organisation, on `render`. A sample still queued and not being made half an hour after it was asked for is failed, *the sample was not made in time*, when the organisation's next sample is asked for — the reconciler does not watch samples. One that never leaves *being made* means `render` is down or not consuming its queue: `docker compose ps render`, `docker compose logs render`. A failed sample's reason is on the styles page; `render`'s log has *a sample failed* with the sample's id, and `web`'s *a sample could not be queued* when the broker refused it. A sample is no record: its file is swept with the exports after a day.

### A document whose text will not parse

Every text the platform commits has passed the validator, so this happens only to a repository written outside the platform: restored from a foreign bundle, or edited by hand. Two cases. **A file that does not read** (its frontmatter broken, or not UTF-8): the reading view answers *Nothing to show here*, as for a missing document, and `web`'s log has *a document's text could not be read* with the document's number. **A text that reads but holds constructs the platform refuses**: the reading view shows it, raw HTML as plain text, and every export of it fails with the constructs named.

Run the reconciler for that document first (`reconcile --tenant N --document M`); `identity_mismatch` or `unreadable` there means the repository is not the platform's own, and the restore is what to revisit (§ Restore, case C). A text that reads but holds refused constructs is corrected by its editors in the editor: the editor opens it in the source view with each refused line named (§ A draft that fails to load). The repository is never edited in place.

## Mail

Every notification but a failed email's queues one email in the outbox of its schema — an organisation's, or the shared one for a platform administrator's — sent from that organisation's own sending address, else the platform's; with neither, nothing is queued and the notification stays in the application alone. The worker sends what is due every minute. The platform's address is set in Administration › Platform › *Mail and outbox*, an organisation's in its Administration › *Sending address*; each page lists its outbox below the form, the newest 200, and offers *Send a test email*, which reports *connection*, *sign-in* and *sending* apart. An email links to its notification on the organisation's default domain, else the platform's host (DL-0394): **give an organisation whose people receive mail a default domain**, or a member of several organisations who follows a link with another chosen is answered *Nothing to show here*.

### The mail key

A sending password is stored encrypted under `MAIL_PASSWORD_KEY`, which only `web` and `worker` receive. Set it in `.env` **before the first sending address with a password is saved**. Generate one on the host, inside the running stack:

```bash
$C exec web python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the printed value in `.env` as `MAIL_PASSWORD_KEY`, then `$C up -d web worker`. Keep a copy of it with `.env`'s other keys: a stored password cannot be read without it, and the addresses that sign in would have to be entered again. **Without the key**, the pages refuse to store a password, and every email of an address that signs in waits in the outbox, its attempts untouched, reading *The sending password cannot be read until the mail key is set.*; the worker logs *an email waits for the mail key* once per email. Setting the key sends them at the next minute.

**Rotating the key**, in three steps:

1. In `.env`, move the current value to `MAIL_PASSWORD_KEY_PREVIOUS` and set a newly generated one as `MAIL_PASSWORD_KEY`; `$C up -d web worker`. Both keys now read a stored password.
2. Re-encrypt every stored password — the platform's and each organisation's — under the new key; each schema's run is audited as `mail.key_rotated`. Run it again if it stops part way; it changes nothing a reader sees:

   ```bash
   $C exec worker python manage.py rotate_mail_key
   ```

3. Empty `MAIL_PASSWORD_KEY_PREVIOUS` and `$C up -d web worker`.

A key that is not a valid key — the current one or the previous — is reported by its name, never its value: the pages refuse to store a password and mail of an address that signs in waits until it is corrected. A valid key that is not the one a password was stored under holds that address's mail with *The mail key does not open the sending password: enter it again.*: restore the right key, or enter the password again on the address's page.

### When mail fails

The outbox row says why, in the page's language. A refusal is tried again five minutes later; the third fails the row and tells the organisation's administrators and the platform's, in the application only. What the reasons mean:

- ***The server answered: …*** — the sending server refused, in its own words: a wrong user name or password, an address it will not send from, a recipient it rejects. Correct the address's settings and *Send a test email*.
- ***The server did not answer in time***, ***No server of that name was found***, ***The server refused the connection***, ***The server could not be reached*** — the host or port is wrong, or the server is down; *Send a test email* says which step failed.
- ***The server's certificate was not accepted***, ***No encrypted connection could be made*** — the connection's security does not match the server: *STARTTLS* for port 587, *TLS* for 465. Sign-in without encryption is allowed only to a server on the same machine.
- ***The recipient may no longer open the document*** — the person lost the right to the document between the notification and the send. Not a fault, and nobody is told.
- ***The server offers no sign-in*** — a user name is set for a server that takes none: clear it.
- ***The server closed the connection*** — the server dropped it mid-way, often a limit on connections or messages; the next attempt usually passes.
- ***The email could not be sent.*** — a refusal the platform has no words for; the worker's log has it under the row's id.
- ***The sending password cannot be read until the mail key is set***, ***The mail key does not open the sending password: enter it again.*** — § The mail key. These emails wait, their attempts untouched.
- ***No sending address is set.*** — the address was removed and none is left, the organisation's nor the platform's. The emails wait, their attempts untouched, and leave once an address is set (DL-0395); nobody is told, since an administrator removed it.

A stored password is kept only while the host, port, security and user name it was entered for are unchanged; change any of them and enter the password again. `docker compose logs worker` has *an email not sent* or *an outbox not sent* where the database itself refused, with the row's id or the organisation's number; the outbox continues with the rest.

## Restore

> [!note] Rehearsed — case A only
> Case A has been rehearsed end to end and corrected here; cases B and C have not.

### First, decide which case this is

| What happened | Case |
|---|---|
| The host is gone, its disks cannot be trusted, or the data of both stores is lost | **A — full restore** (a fresh host, or the same one) |
| The host and its repositories are fine; the database is lost, or holds bad data from a known time | **B — database to a point in time** |
| One document's repository is damaged; everything else is fine | **C — one repository** |

Write down, before touching anything: **what happened, when it was noticed, and the recovery point you are aiming for** — the last moment known to be good, in UTC as `YYYYMMDDTHHMMSSZ`. In case A it can be no later than the start of the newest clean bundle run, nor than the end of the archive (step 4). Every later step refers to it.

### A — full restore

1. **Stop anything still writing.** On the old host, if it is reachable: `docker compose stop web worker render backup`. Nothing may write to either store while you restore.
2. **Preserve the damaged state.** Copy what is left aside, the repository root included; do not delete it. It is the evidence of what failed and the fallback if the restore goes wrong.
3. **Prepare the host.** Install the checkout, put `.env` and the store's key file in place from where the host's credentials are kept, and build: `docker compose build`. Do not start `web`, `worker` or `render`. Make an empty repository root, writable by uid 1000: `mkdir -p .repos && sudo chown 1000:1000 .repos` (or the directory `GIT_REPO_ROOT_HOST` names); on a host that held the stack before, move the old root aside first, and remove the old database volume only once step 2 has copied it — first the stopped containers that hold it, `docker compose rm -f db backup`, or Docker refuses: `docker volume rm <project>_pgdata`.
4. **Restore the database — no later than the repositories.** Run the database restore in dry-run mode:

   ```bash
   scripts/restore-database.sh --dry-run [--good YYYYMMDDTHHMMSSZ]
   ```

   It prints the start of the newest clean bundle run, the last good moment you give it, and about when the markers last saw a segment archived — an estimate, never a bound — and which governs: the earlier of the first two (DL-0314), with a warning when the archive may end before it. **Never aim later**: a database restored past its repositories names commits no copy holds. If it reports a newer bundle run that listed failed repositories, you may choose that run instead with `--marker`: you gain the database changes up to it and lose the listed repositories' commits since their last bundle, which step 6 then reports as rows whose commit is missing — decide, and write down which. If `pgbackrest verify` fails, the script stops and prints it; `--despite-verify` goes on once you have read it. Then stop `db` if it runs (`docker compose stop db`) and run the script without `--dry-run`, with the same options; it restores only after you type `restore`. Start `db` alone and confirm it accepts connections (below) — and that its log says *archive recovery complete*: it accepts read-only connections while it is still replaying. Its *last completed transaction* is where the database now stands; the markers' estimate is no bound on it. If PostgreSQL instead stops with *recovery ended before configured recovery target was reached*, the archive holds no commit after that time: the database was quiet since, the archive has a gap, or the host was lost soon after the last marker. In every case the end of the archive is then no later than the target, so recovering to it passes nothing: stop `db`, which Docker otherwise keeps restarting (`docker compose stop db`), and run the script again with `--end-of-archive`.

   ```bash
   docker compose up -d db && docker compose exec db sh -c 'pg_isready -U "$POSTGRES_USER"'
   ```

5. **Restore the repositories.** Each from its newest full bundle and every bundle after it, in order; a repository already on disk is left alone, so the command can be run again:

   ```bash
   scripts/restore-repositories.sh
   ```

   A repository may come back ahead of the database; step 6 replays the difference.
6. **Run the reconciler in report mode** — `docker compose run --rm web python manage.py reconcile`, since `web` is not running (§ The reconciler) — and read its report before repairing anything. Expect:
   - **commits without rows** — git is ahead of the database; the reconciler replays them. Normal after any restore;
   - **rows whose commit is missing** — not expected here, since the database was restored no later than the repositories — unless you chose a newer run with `--marker` at step 4, in which case exactly the listed repositories appear here, as you decided: record them, then delete those rows with `reconcile --tenant N --document M --repair --prune-rows` for each. One that appears otherwise means a bundle is missing: stop and find it;
   - **creations that stopped** — finished, except a copy, reported `copy_stopped` and left (DL-0455);
   - **repositories without a row** — recreated with no access at all; the tenant administrator grants access again;
   - **passport entries without their row** — reported; the passport is believed.
7. **Run the reconciler in repair mode**, `docker compose run --rm web python manage.py reconcile --repair`, then again in report mode, and confirm it reports nothing it did not repair. What it leaves are the cases its table says it will not repair — a commit by someone the restored database does not hold as a member, a creation whose creator was never one, a repository that names another document, a stopped copy, which `remove_stopped_copy` removes (§ The reconciler). Record each with its numbers; a commit by a person whose membership the restore lost is derived once the tenant administrator has restored that membership and the reconciler runs again.
8. **Start the rest:** `docker compose up -d`. The backup resumes on its own; take a full base backup at once (§ Backup, *The store is unreachable*), since the restored database starts a new timeline.
9. **Verify as a user would.** Sign in; open a restored document; confirm its latest version matches its passport.
10. **Tell the people who lost work.** Whatever was only in the database after the recovery point is gone — above all **drafts**. List the documents whose holds were open at the recovery point and tell each holder.
11. **Record it**: what failed, the recovery point, how long each step took, and anything in this procedure that was wrong.

### B — database to a point in time

Steps 1, 2, 4 and 6 to 11 of case A, on the same host, with `db` stopped too, except that at step 4 the repositories are intact on the host and do not bound the recovery point: run `scripts/restore-database.sh --database-only`, with `--good` for the last good moment, or without it for a lost database's latest archived point. The repositories stay where they are: they are ahead of the restored database, and step 6 replays the difference. If the bad data was *written through git* — a wrong acceptance, a wrong version — it is not undone by a restore at all: history only moves forward, and the correction is a new commit that reverts it.

### C — one repository

1. Stop `web`, `worker` and `render`: `docker compose stop web worker render`.
2. Move the damaged repository aside, `.repos/tenant-N/document-M` to a name of its own.
3. Restore that one repository from its bundles: `scripts/restore-repositories.sh --tenant N --document M`.
4. Start them again, `docker compose up -d web worker render`, and run the reconciler for that document: `docker compose exec web python manage.py reconcile --tenant N --document M`.
5. Commits made to that document after its last bundle are lost, and the database still has version rows for them: the report lists them as `row_without_commit`. Tell the authors, record it, then delete those rows with `docker compose exec web python manage.py reconcile --tenant N --document M --repair --prune-rows`.

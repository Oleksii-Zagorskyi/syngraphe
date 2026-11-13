---
tags:
  - technical-design
aliases:
  - Syngraphē architecturally significant requirements
status: active
date: 2026-09-21
---

# Architecturally Significant Requirements

Requirements that constrain the architecture rather than describe a feature — where getting it wrong is not a bug to fix but a rebuild.

## Two shapes, and the six elements as the test

Every entry is tested against the SEI **quality-attribute scenario**, whose six parts are canonical and, for a scenario, all required:

**Source** of the stimulus · **Stimulus** · **Environment** · **Artifact** · **Response** · **Response measure**

The test is what tells the two shapes apart. An entry that fills all six is a **scenario** and carries them as a bullet list. An entry that cannot — because it names a property the architecture must always have rather than an event it must handle — is a **constraint**, and forcing six parts onto it produces ritual rather than rigour. A constraint states what it **forbids**, because that is the part that constrains.

*No tables: Obsidian's prettifier rewrites cell padding between sessions, producing diff noise on files nobody edited (DL-0062).*

Where *Environment* is ordinary operation, it is written as such rather than omitted.

---

## ASR-01 — Tenant isolation is enforced below the application *(scenario)*

- **Source**: Application code with a defect, or a compromised session
- **Stimulus**: A query that omits the tenant boundary
- **Environment**: Normal operation, many tenants on one deployment
- **Artifact**: The application database
- **Response**: The query reaches only the acting tenant's schema; it cannot address another's
- **Response measure**: Zero rows of another tenant returned, for any query, without a deliberate schema switch

Isolation is enforced by schema separation (DL-0029). *Forbids:* a shared table with a tenant column as the primary boundary.

## ASR-02 — The record of what a document said is immutable *(scenario)*

- **Source**: An editor, a reviewer, or an administrator
- **Stimulus**: An attempt to remove an unwanted change
- **Environment**: Normal operation, at any point in a document's life
- **Artifact**: The document's version history
- **Response**: A new version is created that reverts the change; the original remains reachable and attributed
- **Response measure**: Every version ever committed is retrievable; no operation exists that removes one

*Forbids:* history rewriting in any form — rebase, amend after commit, dropping a version, force-updating a ref (ADR-0003). **And forbids the platform writing personal data into commit metadata**: an author is a user identifier and a non-routable address (DL-0088), so erasure is a database operation and never a history rewrite. Personal data *inside document text* — a policy naming a person, a job description — is the tenant's content and outside this requirement; the platform cannot and does not police it.

## ASR-03 — A finding cannot reach a recipient who could not derive it *(scenario)*

- **Source**: The reviewer agent
- **Stimulus**: A cross-document finding, derived from the document under review and a neighbour in the reviewer's scope
- **Environment**: Normal operation; the recipient may read the document and lacks read access to the neighbour
- **Artifact**: The finding and its delivery path
- **Response**: The platform computes the audience from the finding's sources — the documents it put into the call that produced the finding — and withholds it from that recipient
- **Response measure**:  No finding is delivered to a recipient who lacks read access to every source it was derived from; a finding whose sources cannot be established is withheld from everyone and counted as an error (DL-0571 (13))

Audience is computed per recipient, never per finding, and never by the prompt (DL-0021). A finding's provenance is its call's context: its sources are exactly the documents the platform assembled for the call — this document; this document and one neighbour; this document and the guidance — never a tag the agent writes, which could be wrong and could not bound what the finding draws on (ADR-0022). Release 0.2 sends no guidance to a model (DL-0568, B-079), so the scenario is a cross-document finding; a finding derived from the confidential guidance meets the same response and measure when the guidance returns. When it does, the publishable artefact comes from a run whose context never held the confidential material (DL-0095). *Forbids:* routing agent output without an audience computation; redacting a confidential analysis into a publishable one; producing both artefacts from one context.

## ASR-04 — Nothing enters the approved state without an approval *(constraint)*

The working state accepts versions immediately; *Accepted* requires a reviewer accepting the whole run since the last acceptance (DL-0090); *Canonical* requires an approver, and — where a tenant has switched the check on — an approver who performed **none of the acceptances since the previous canonical edition** (DL-0101, DL-0115).

*Forbids:* an approval recorded only as application state — acceptance is a commit to the document's passport, so approval history travels with the document. Also forbids a change the review surface cannot render: a replaced image produces a diff a reviewer cannot read, so image changes are flagged and shown before-and-after (DL-0059), and every attachment added, replaced, renamed, reordered or removed is listed in the review with each version downloadable (DL-0168).

## ASR-05 — One editing sequence per document *(constraint)*

No branches, no forks, no merges (ADR-0003). Editing is exclusive while the document is held.

*Forbids:* any feature that reintroduces concurrent divergent states — parallel drafts, forked revisions, a second editor inside a held document.

## ASR-06 — Git vocabulary never reaches the user *(constraint)*

The substrate is invisible; the interface has its own terms, Ukrainian and English (DL-0003, DL-0047, DL-0498).

*Forbids:* commit, branch, merge, repository or ref in any user-facing surface, error messages included.

## ASR-07 — One authorisation surface *(constraint)*

Identity and access control are Django's; no second system holds overlapping permissions (DL-0042, ADR-0002).

*Forbids:* granting rights in any other system; synchronising two permission models.

## ASR-08 — Access is data, and its history is part of the record *(constraint)*

Rights are held by groups and reach documents through the groups linked to them (ADR-0007); groups, their rights, their members and their links are edited only by a tenant or platform administrator, and every change carries a timestamp and an actor (DL-0051).

*Forbids:* permissions encoded in code, in file layout, or anywhere a change leaves no trace. Confidential material is an ordinary document linked to few groups, not a separate mechanism.

## ASR-09 — Generated views have exactly one author, the system *(constraint)*

The role directory, control directory, contradictions, ambiguities and blind-spot lists are written by the system and by nobody else. Wherever a generated view's author is shown — the interface, and the MCP server later — it is *system*, never a person; the record beneath may carry the account a view was produced under (DL-0448). In stage 1 the role directory is derived from the version shown, each time it is rendered, with no store and no agent (DL-0073). From release 0.2 the contradiction, ambiguity and blind-spot lists are the **standing findings set shown as lists**: computed once per accepted state and refreshed when that state changes, not recompiled on every commit, and holding only findings derived from the document alone, so every reader of the document sees the same lists (DL-0032, DL-0555). The control directory, which the agent is to write and recompile on every commit (DL-0044, DL-0063), is not in release 0.2 (DL-0555, B-068).

*Forbids:* a human editing a generated view; a generated view being treated as **source text** — it is derived from the documents and never the other way round. Reading one to decide what to edit next, or to drive future work items, is exactly what it is for.

## ASR-10 — A document's language is fixed; the platform's is not *(constraint)*

Each document carries exactly one language; the platform handles any (DL-0003). The interface is Ukrainian or English, each person's own choice (DL-0498); a document's exports are in the document's language, never the person's (DL-0502).

*Forbids:* language assumptions in storage, search, sentence splitting or rendering; interface strings outside the translation layer.

## ASR-11 — A user cannot converse with an agent *(constraint)*

Interaction is by predefined actions only — a user calls an action, never composes a prompt (DL-0050, superseded in its timing by DL-0056).

*Forbids:* a free-text channel to any agent; user-authored prompt text reaching a model.

## ASR-12 — Analysis is keyed to content and never recomputed for it *(scenario)*

- **Source**: An editor
- **Stimulus**: A request for an analysis that has already run against this exact content
- **Environment**: Normal operation, inside or outside an editing session
- **Artifact**: The companion action and its stored result
- **Response**: The stored result is returned; no model call is made
- **Response measure**: At most one model call per heuristic per key

The unit stored and reused is the **call** (DL-0567): one heuristic over the documents the platform put into it (ADR-0022), keyed by its prompt version and the content states of the documents it read; a companion call's key also holds the draft's base commit, against which the changes it marks are measured (DL-0571 (5)). An analysis is the set of calls made for one purpose — an action on a content state, the reviewer agent's analysis of a run, a standing set of an accepted state (DL-0571 (4)) — so two scopes that share a neighbour share that pair's calls, and a result is never keyed by person (DL-0567). A failed call is not stored, so *run again* makes a new call. A document's content state is a hash of its tree (DL-0056) that excludes `passport.md` as it excludes `analysis/` (DL-0571 (5)), so an acceptance does not move it; no analysis is written into the tree, so no result can move it either (DL-0567). A review that needs a standing set before its batch returns, or one that is missing, computes it live and reuses any call the batch already stored; a batch result that arrives for a key already stored is discarded, so the measure holds for stored calls (DL-0571 (6)). A commit is one content state among others, which is what lets an editor ask mid-session and still see the answer already computed on the send-for-review screen. *Forbids:* keying a stored call to anything that changes when the content does not, or recomputing one when it has not; keying by review scope, which would recompute every pair when one neighbour changes; writing a result into the tree it was computed from.

## ASR-13 — The platform must be publishable *(constraint)*

The product ships under the Apache License 2.0 (DL-0011, DL-0162).

*Forbids:* tenant data, credentials or confidential guidance in the repository's history; committed configuration; a dependency that cannot be redistributed. The agent runtime is a **provider interface over a plain model API** for this reason (DL-0120) — an adopter needs an API key, not a proprietary binary in the runtime path.

## ASR-14 — Stage 2 must not require rebuilding stage 1 *(scenario)*

- **Source**: The development team
- **Stimulus**: Adding the agents and generated views after the editor is in production
- **Environment**: Stage 1 deployed, real documents in use
- **Artifact**: The stage 1 data model and its interfaces
- **Response**: Findings, heuristics, each finding's sources and derived views attach to existing entities
- **Response measure**: No migration that rewrites document, version or acceptance records; nothing of the editing or review interfaces is rebuilt — the regions of release 0.2 are added to them (DL-0565)

*Forbids:* a stage 1 data model with no place for what stage 2 attaches (DL-0043).

## ASR-15 — A document's identity is independent of where it is shown *(constraint)*

A document is **one repository**, `document-M`, in a flat directory under its tenant, `tenant-N` (DL-0111, ADR-0008); people know it by its number, `#7`, which never changes (ADR-0008). The interface shows folders with unlimited nesting, held as metadata. Moving or renaming a document in the interface never changes anything on disk (DL-0058).

*Forbids:* deriving a document's storage path from its presentation location, or from its title. A reorganised tree would otherwise rewrite paths, break every link, and orphan history; a path built from a title would also put document titles — including a confidential guidance document's — into filesystem listings and backup manifests the access table does not govern.

## ASR-16 — A link grants no access it does not already have *(scenario)*

- **Source**: A document author, or the generated "see also"
- **Stimulus**: A reference to a document the reader may not access
- **Environment**: Normal operation, any reader
- **Artifact**: The rendered document and its navigation
- **Response**: The reference renders as plain text; no navigation is offered
- **Response measure**: No reader reaches a document they lack rights to, by any link, deep link or export

The document's **name** is not protected and cannot be — it appears in the prose of the document that mentions it, written there deliberately (DL-0071). What is protected is reaching it. *Forbids:* a rendered link, a deep link or an export path that resolves for a reader without rights.

## ASR-17 — A tenant is invisible to another tenant, including its people *(constraint)*

No document links, analyses or searches cross a tenant boundary. A user holding several memberships switches between tenants; a user holding one sees the tenant's name and no switcher. A tenant administrator adding a user by email **learns nothing about that user's existence elsewhere** — no platform-wide creation date, no other membership, no prior account (DL-0079).

*Forbids:* any interface that distinguishes "user created" from "user added to this tenant", and any cross-tenant query at all. The email is the platform identifier, so the disclosure risk sits precisely where the convenience does.

*Accepted residual:* an invitation is refused while the person it would bring in has a display name another member of the tenant already uses, so a tenant administrator can tell a known address from an unknown one when its name collides — and only then (DL-0538).

## ASR-18 — Every change is attributable, and authorisation is reconstructible *(scenario)*

- **Source**: An auditor, a reviewer, or an administrator investigating
- **Stimulus**: The question *"who could read this document on the day that edition was approved, and who granted them that"*
- **Environment**: Normal operation, any time after the fact
- **Artifact**: The authorisation history and the audit log
- **Response**: The permission set at that moment is returned by query, with the actor and timestamp of each grant
- **Response measure**: Answerable without replaying an event stream, for any past date, including for rights on an archived document

Every row carries `created_at`, `created_by` and an `actor_kind` of user, system or agent; authorisation-bearing tables additionally carry typed append-only history (DL-0082). Current-state rows are removed with their removal written to the typed history in the same transaction, and the history tables refuse update and delete in the database (DL-0459). *Forbids:* updating a rights row in place without a history entry; removing a rights row without its history entry; attributing an agent-written or system-written row to a person.

## ASR-19 — Stored content never executes *(constraint)*

The construct whitelist binds the **parser**, not only the editor (DL-0096): raw HTML disabled, no script, no remote image or stylesheet references, no network for the renderer, and SVG never among the accepted image types.

*Forbids:* a whitelist enforced only by the interface. Text arrives by paste and by import as well as by typing, and a document that can carry markup is an injection vector into every reader's browser and every export.

## ASR-20 — A stored line is never re-normalised *(constraint)*

No normalizer rule is ever applied to a line its edit did not touch — the sentence splitter and every other rule alike (DL-0112). *Touched* is defined as: the submitted line differs from the stored line **after canonicalising the submitted one**. Normalisation preserves the parse, checked on every write. The normal form is **path-dependent** and the stored newline is the authority.

*Forbids:* a sweep of any normalizer rule over existing text; a validity check that re-runs the splitter and compares; rebuilding line structure from the text. A better rule improves new text only. If existing text ever must be re-split, the mechanism is an explicit commit with `actor_kind` system, excluded from blame attribution — written down so nobody invents a migration instead, and not to be built.

---

## Performance, capacity and recovery

Proposed with their reasoning in DL-0151 and approved as proposed in DL-0216; stories are estimated and accepted against them.

## ASR-21 — Interactive operations stay within a waiting budget *(scenario)*

- **Source**: An editor or a reader
- **Stimulus**: A keystroke in the editor; committing a finished session — *send for review*, *create version* or *accept as*; opening a document to read; opening a document to edit
- **Environment**: Normal operation, a forty-page document, within the size and load envelope of ASR-23
- **Artifact**: The editor, the commit path including normalisation, the read view, the editor's opening
- **Response**: The character appears; the commit lands; the document renders; the editor is ready to type in
- **Response measure**: At the 95th percentile — keystroke to screen **≤ 50 ms**; finishing to a committed version **≤ 5 s**; opening a document to its first render **≤ 2 s**; *Edit* to the whole document's editor ready **≤ 2 s** (DL-0484)

Fifty milliseconds is below what a typist perceives. Five seconds is tolerable for an act performed once per editing session; two seconds is the ordinary budget for opening a page, the editor's as a reading page's. *Forbids:* running blame, an export or any agent call inside any of these paths — authorship is read from its cache, and rendering to PDF is the worker's.

## ASR-22 — A crash loses seconds of typing, not a session *(scenario)*

- **Source**: The browser, the network or the server
- **Stimulus**: The editing session ends without warning — a closed laptop, a lost connection, a restarted container
- **Environment**: An editor holding a document with unsent work
- **Artifact**: The server-side draft
- **Response**: Reopening the document restores the draft
- **Response measure**: **≤ 2 s** of typing lost

With no Save control and no intermediate commits, the draft is the only copy of a session's work (ADR-0003). *Forbids:* a draft held only in the browser; a draft written less often than the measure allows.

## ASR-23 — The envelope the budgets hold within *(constraint)*

A document of up to **100 pages** — about 300 KB of Markdown, body and appendices together — with each image up to **10 MB**, and up to **20 attachments**, each within the tenant's cap of **5 MB** by default. Up to **50 signed-in users per tenant** and **300 across the platform**. Tens of tenants on one host.

One hundred pages is two and a half times the longest document the platform is expected to hold, and forty pages is what the verification spikes measure. *Forbids:* a promise in ASR-21 or ASR-22 made beyond this envelope; an estimate or a capacity decision that assumes a larger one without revising this entry first.

## ASR-24 — Availability *(scenario)*

- **Source**: Any user
- **Stimulus**: A request at any time
- **Environment**: Production, on one host with no failover (DL-0086)
- **Artifact**: The platform as a whole
- **Response**: The request is served
- **Response measure**: **99.5% of each month**, announced maintenance and the recovery of a disaster excluded — about three and a half hours of unplanned downtime a month

One host without failover cannot honestly promise more; a higher figure is a decision to pay for a second host, and would be recorded as one. The measure counts ordinary unplanned downtime, the failures the running installation recovers from — a database restored to a point in time and a single repository restored, the rest of the installation intact, included (DL-0302). A disaster — the loss of the host, its disks or the data of both stores, both restored from the off-host copies on a fresh host or the same one — is counted apart and held to ASR-25 instead, since one restore within ASR-25's four hours would by itself spend this entry's month (DL-0279, DL-0302).

## ASR-25 — Recovery objectives *(scenario)*

- **Source**: A failure of the host, its disks, or a bad write
- **Stimulus**: The platform has to be restored from its backups
- **Environment**: Production, following [`runbook.md § Restore`](runbook.md)
- **Artifact**: The database's continuous archive and the repositories' off-host copy
- **Response**: The platform is running again from the off-host copies, reconciled
- **Response measure**: **Recovery point** — for a failure of the database alone, the repositories intact on the host, at most **5 minutes** of database changes lost, the write-ahead log being shipped off-host continuously except as an outage of the store allows (DL-0297); for a restore of the whole host, at most **15 minutes** of changes to either store, the database being restored to the time the newest bundle run with no failed repository began, or to the end of its archive if that is earlier, and never past the repositories unless the operator chooses a newer run that names the repositories it gives up (DL-0276, DL-0294, DL-0300). **Recovery time** — **≤ 4 hours** to a running platform after a disaster, on a fresh host or the same one

Mandating continuous archiving with point-in-time recovery was already a recovery-point decision; this entry states the point it was taken for. The database's figure is the tighter one because holds, access rows and drafts exist nowhere else. It gives way when the whole host is lost: a database restored past its repositories would name commits no copy holds, and those versions, with the drafts they used up, would be gone from both stores (DL-0276). A restore of both stores — a disaster — is counted apart from ASR-24's monthly measure: it answers to these figures, not to the availability percentage; a restore of the database alone or of one repository counts against ASR-24 (DL-0279, DL-0302). The bundle runs start every ten minutes so that a run of up to five keeps the fifteen (DL-0296). *Forbids:* a backup arrangement that cannot meet these figures without a rehearsed restore proving it does.

---

## The agents' model calls

Two invariants of release 0.2, the AI reader, made requirements so that each has a *Forbids* (DL-0569).

## ASR-26 — Every model call in production traces to a prompt version with passing eval results *(constraint)*

A prompt version is one hash over the base prompt, the heuristic, the model and the effort. Every model call writes a trace that records it, and the command that loads the prompts refuses a version with no dated result at its target in `evals/` under the same hash (ADR-0024, DL-0554), so the prompt production sends is the prompt the evals measured. The load command and CI refuse in the same way a prompt version without a passing adversarial result under its hash (DL-0571 (12)).

*Forbids:* loading a prompt version without a passing result — at its target and on the adversarial set — or with a warning in place of a refusal; a heuristic edited in place in the platform, whose text no eval measured — the hotfix is to switch it off (DL-0567); a fallback to a model the heuristic was not evaluated on (DL-0560); a model call that writes no trace, or that goes around the provider interface.

## ASR-27 — A document's text is data to the agents, never an instruction *(constraint)*

Instructions live only in system-role messages — the base before the document, the heuristic after it. Each document a call reads goes in the user turn, inside a delimiter carrying a marker made fresh for that call; the answer returns only through the enforced output structure, and a finding is drawn as limited Markdown with no link made from it (ADR-0022). An attempt to instruct the agent is made visible — by structural checks on every document a call reads and by the model's own report — as a finding shown to whoever sees the analysis and one notification to administrators per document and content state (DL-0571 (11)), and one shared adversarial case set runs against every prompt version.

*Forbids:* document text, or anything a person typed, in a system-role message; a fixed delimiter, which a document can contain; reading a model's answer outside the enforced structure; drawing from a finding a link or any markup beyond the whitelist; shipping a prompt version that followed an injected instruction of the adversarial set; an automatic step against a person or a document when an attempt is detected.

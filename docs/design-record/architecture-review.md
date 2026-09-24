---
tags:
  - report
  - engineering
aliases:
  - Syngraphē architecture review report
status: draft
date: 2026-09-21
---

# Architecture Review - Syngraphē Discovery set

Reviewed: the authoring session's set as it stood on 2026-09-21 after DL-0097. Reviewer stance: senior software architect, fresh context, read-only.

## Verdict

**G1 - Discovery Completion should not close on this set yet.** The core architecture is sound and should be kept: one linear history per document, Django as the only authorisation surface, git as a library, schema per tenant, access as rows with history, a parser-level whitelist. Nothing below asks for a rebuild of that core.

Four things stand between the set and the gate. One requirement is wrong against the business driver (tables). One safety mechanism was cut while the power it guards stayed in (reviewer rewrite). One structural question every two-store system must answer is not answered (git and PostgreSQL). And the documents disagree with each other after the last three pivots, in places where the stale text would instruct an implementer to build what was deleted.

Findings are ordered by consequence. Each carries an id so the authoring session can drive them to closure as a register. F-01 to F-05 are gate blockers; F-06 to F-09 need a decision but not before the gate if they are recorded as open; F-10 to F-12 are notes.

## Gate blockers

### F-01 - Tables are excluded, and the documents the product exists for contain them

The format whitelist says no tables (`technical-design.md § Document storage and diff semantics`, from the owner's first-round answer recorded as DL-0004 and carried into DL-0046). The owner confirmed during this review that the real policies contain tables and that regular tables must survive; merged-cell tables need not.

This is not a whitelist entry to add. A table collides with three load-bearing mechanisms at once:

- **Sentence-per-line.** A pipe-table row is one physical line and a cell cannot hold a line break. Inside a table the unit of diff, authorship and per-author undo becomes the row, not the sentence. The pending view, the author toggle and ST-0037 all need a stated rule for that.
- **The editor choice.** `technical-design.md § Verification spikes` lists lossless WYSIWYG round-trip as unverified and the library as not chosen. Table editing is the feature that most narrows that choice, so it must be in the spike, not added after it.
- **Paragraph numbering and anchors.** Whether a table is one numbered paragraph, and how a text-quote anchor points into a cell, are undefined.

Recommendation: admit pipe tables only - one row per line, inline content only, no merged cells, no nested blocks; declare the row the unit of attribution inside a table; extend the server-side normalizer to tables so that a row has exactly one canonical spelling - one space inside each cell edge, no alignment padding, a fixed delimiter row that keeps only its alignment colons - because padding added by an editor, a paste or a prettifier otherwise rewrites every row of a table when one cell changes, and each rewritten row is re-attributed to the person who touched one of them; add the table to the editor round-trip spike and to the DOCX and PDF export checks; supersede the no-tables clause by a new decision-log row. A policy table that needs merged cells is restructured by its author, which is a constraint the scope agreement should state to the business users.

### F-02 - The reviewer can rewrite an editor's wording in stage 1 with nothing generated to tell the editor

ADR-0001 grants the reviewer the right to correct and accept, and states its own condition: the generated rejection record "is what makes it safe", and it is "a blocker for the story that implements reviewer commits". The project `CLAUDE.md` repeats it as a gotcha: never implement the first without the second. DL-0076 then moved rejection records to stage 2 together with disputes, while ST-0035 - reviewer corrects and accepts - stayed in the stage 1 walking skeleton with the note that the editor "is told what changed by reading the history".

Two further facts compound it. ADR-0001 keeps *return for revision* as an explicit reviewer action, and no such action exists in `document-lifecycle.md`: a stage 1 reviewer can accept the whole run, rewrite it, or revert sentences, and cannot decline. And no segregation of duties is enforced (F-07), so the rewrite and its acceptance can be one person's single motion.

The owner confirmed this slipped through when disputes were cut. What was deferred correctly is the dispute machinery - register, decider, escalation. What must not be deferred is the disclosure.

Recommendation: stage 1 generates, at acceptance, a plain notice to each affected author - your text, the accepted text, who changed it - computed from the same diff the rejection record will later use, delivered through the notification surface that already exists. No state machine, no escalation. Add a *return without accepting* action with a free-text reason to the lifecycle. Amend ADR-0001 to say which half ships when.

### F-03 - Git and PostgreSQL are two stores with no stated write protocol

`data-model.md` sets the right principle - git holds content, PostgreSQL never holds a second copy, `VERSION` is a rebuildable cache. The design stops there. Not stated anywhere:

- **Order and failure.** Send for review writes a commit and a `VERSION` row, releases a `HOLD`, deletes a `DRAFT` and raises notifications. Acceptance writes a passport commit and an `ACCEPTANCE` row. No two of these share a transaction. What state is legal after a crash between them, and what repairs it, is undefined.
- **Authority.** DL-0041 says acceptance is a commit, not application state; the stances are computed from `ACCEPTANCE` and `EDITION` rows. When the passport and the row disagree, which one the interface believes is not written down. The threat model relies on that disagreement as tamper detection (T-07) while nothing is specified that would ever compare them.
- **Writers.** The web and worker containers share one volume of bare repositories. One repository holds a whole document set, so every commit to any document in the set advances the same ref. The whole-document hold serialises editors of one document; it does nothing for two editors of two documents in one set, or for a stage 2 worker writing generated views.
- **Backup.** The scope agreement promises that nothing is ever lost. The record lives in two stores that must be restorable to a mutually consistent point, on one VDS, and the only mention of backup in the set is about the contributor map.

Recommendation, as one ASR and one short technical-design section: git is the commit point - the ref update is the moment a version or an acceptance exists; database rows for it are derived idempotently, by the request and again by a reconciler that replays any commit lacking its row; a per-repository single-writer lock (a PostgreSQL advisory lock is enough) covers every ref update; the passport wins over the row, and the reconciler reports disagreement as an audit event; backup takes the database first and the repositories second, because the repositories are then a superset. Deployment detail can wait for its scheduled document; these four rules cannot, because the stage 1 data model is built on them.

### F-04 - The set was not reconciled after its pivots, and the stale text is instructive rather than harmless

Three pivots landed late: linear history replaced branching (DL-0039, DL-0042), Markdown replaced LaTeX (DL-0046), and section-scoped roles with per-file approval were dropped (DL-0090, DL-0091). The documents still teach the earlier designs in places a fresh implementer will read first:

- **ADR-0001 and ADR-0002 are marked accepted and written in the deleted model.** ADR-0001 speaks of proposal branches, merge conflicts presented to the reviewer, squash-merge and the per-file approval ledger. ADR-0002 keeps Forgejo for identity, lists "merge mechanics are ours - three-way merge, conflict detection at sentence granularity" as a consequence, and mandates `refs/proposals/{id}/head` retention. The project `CLAUDE.md` sends every future session to both as required reading before touching those areas.
- **`technical-design.md` contradicts the decision log it cites.** It carries DL-0068's tenant-wide agent identity and "the filter is the control, not the agent's ignorance" although DL-0077 superseded it and DL-0095 says the opposite; "role assignments at document and section granularity"; presence of whoever holds "a section"; `document.yaml` as "its own lock unit"; a "confidential guidance repository" that DL-0051 abolished; "nothing is written into the LaTeX"; export "via the LaTeX toolchain"; an MCP server under Interfaces that the PRD scopes out; access profiles where DL-0078 decided review scopes; and open questions Q31 and Q33 while the register says none are open.
- **ASR-04 still requires "the reviewer of every changed file"** and cites the superseded DL-0025. An ASR is the document a reviewer uses to catch violations in one read; a wrong one inverts that.
- **The PRD describes stage 2 behaviour as present tense** in Acceptance and Editions - rejection records, Statement entries, the decider, the open-dispute guard - with no stage marker, and its role table lists decider, designer and pending-edits viewer while Rights lists five rights with no mapping between the two.
- **The decision log has status drift.** DL-0015 (Forgejo is the identity provider) is still `active`.
- **`work/release-0.1-passport.md`** shows G1 blocked on Q27, 18 ASRs and the log ending at DL-0086. **The project `CLAUDE.md`** still lists section code owners, a separate guidance path and an open Q27 among its critical gotchas, and says user stories are the next deliverable.
- **Small direct contradictions:** HEIC is refused (ST-0028) and converted (`technical-design.md`, DL-0066); Word export is in stage 1 (ST-0045, scope agreement) and out (PRD scope, technical design); underline is offered by the editor and absent from the stored construct list, while callouts are in the stored list and absent from the editor's.

Recommendation: one reconciliation pass before the gate, driven from the decision log as the single authority - rewrite ADR-0001 and ADR-0002 in the linear vocabulary or supersede them with amended records; move every stage 2 mechanism in the PRD and technical design under a marked stage 2 heading at stated low fidelity; correct ASR-04; fix the DL-0015 status; refresh the passport and the `CLAUDE.md` gotchas. The story map should be written only against the reconciled set.

### F-05 - There is no authentication design

DL-0015 made Forgejo the identity provider over OIDC. DL-0042 moved identity to Django and dropped Forgejo. Nothing replaced what lapsed: the set contains no statement on how a person proves who they are. ST-0008 is one line - "I sign in". The threat model lists a compromised account as an actor and has no threat about credentials, sessions or recovery.

For a multi-tenant platform whose first asset is confidential guidance this is the most conspicuous absence against enterprise expectations. It also hides a stage 1 dependency: a tenant administrator adds a user by email (ST-0003), and that person can only obtain a credential through an emailed invitation, so the email path is on the walking skeleton's critical path rather than a notification convenience. And ASR-17 - a tenant learns nothing of a user's existence elsewhere - has to hold on the sign-in, invitation and password-reset screens, which are the classic account-enumeration surfaces.

The owner confirmed the first tenant has no shared identity provider. Recommendation: local Django accounts with invitation by email, a modern password hash, time-based one-time codes mandatory for tenant and platform administrators and available to everyone, session expiry and lockout, reset and invitation flows that answer identically whether or not the address is known; keep external OIDC as a named attachment point so a later tenant with Microsoft 365 or Google does not force a rework. Add the missing threat to the threat model and move email sending into stage 1's skeleton.

## Decisions needed, not gate-blocking if recorded as open

### F-06 - Conflict resolution re-enters through per-author undo and through preserved drafts

ADR-0003's central claim is no merges, therefore no conflicts, therefore no conflict interface. Two stage 1 features are conflict resolution under another name:

- **ST-0037**, undoing one author's contribution, shows "which sentences somebody else has since built on" and asks "which wording should survive". That is a merge-conflict interface at sentence granularity. It is also the hardest algorithm in stage 1, it is listed as unverified, and the scope agreement already promises it to business users.
- **A draft preserved after a forced release** (ADR-0003) is based on a version that stops being the head as soon as the next editor commits. Reopening it means rebasing a private draft onto moved text. The set says the draft is preserved and nothing about what happens next.

Neither invalidates the linear model; both contradict the claim made for it. Recommendation: say in ADR-0003 that divergence is confined to these two places; run the blame-based undo as a spike before it is promised, and phrase the scope agreement accordingly; decide the preserved-draft rule now - the cheapest honest one is that a stale draft opens read-only beside the current text for the editor to copy from.

### F-07 - No segregation of duties, not even as an option

Segregation of duties here means one narrow thing: the person who makes a change is not the only person who lets it through. The design has three points where one person can be both:

1. an editor with the accept right accepts a run containing their own versions;
2. a reviewer rewrites text and accepts the rewrite in the same commit;
3. the person who froze an edition approves it as canonical.

DL-0092 allows all three, by owner decision against the authoring agent's advice, and the threat model records it honestly as accepted risk T-08: the control is the record, not prevention. The decision is reasonable for a small first tenant where the reviewer is the accountable executive. It is odd for enterprise software in this domain for a specific reason: a record detects only if someone reads it, and an accounting policy is a document an external auditor treats as a control. Taken together with F-02, one person can change a capitalisation threshold, accept it and make it canonical, and no other human is ever prompted to look.

Recommendation: keep the default as decided, and add one per-tenant setting with one check - an edition cannot be approved by the person who performed the last acceptance before it was frozen. One comparison at one transition restores a second pair of eyes at the only point where text becomes authoritative, leaves everyday editing as fast as Word, and gives a tenant something to answer an auditor with.

*Owner ruling, 2026-09-21: agreed - a per-tenant setting, off by default.* His reasoning belongs in the decision row the authoring session writes: small tenants have nobody to check the reviewer, and the approval of a canonical edition is already the place where a second person with authority can refuse, so that is where the optional check sits.

### F-08 - Sentence-per-line carries authorship, undo and anchors, and the sentence splitter is unspecified

Per-sentence attribution, per-author undo, and text-quote anchors for findings and later comments all rest on the normalizer's sentence boundaries. The set names the normalizer and specifies nothing about it. The risks are concrete for Ukrainian policy text: abbreviations and references ending in a period (cl., art., thous., $, yr., etc.), numbered clauses, initials, quoted speech. A splitter that errs inconsistently produces diff noise; a splitter that is later improved re-splits existing text, and every re-split line is re-attributed to whoever committed next, silently corrupting the authorship record the product sells.

Recommendation: an ASR stating that the splitter is deterministic, versioned, recorded per document, and never changed for existing text except by an explicit attributed system commit; a rule-based splitter per `LANGUAGE` row with an abbreviation list rather than a statistical one; a spike on real Ukrainian policy text alongside the editor spike.

### F-09 - Erasure by deleting the user mapping collides with attributability, and the repository cannot be kept free of personal data

`data-model.md` says removing a person from the database removes them from the record. ASR-18 says every change stays attributable and that authorisation at any past date is a query. Every table carries `created_by`; `ACCESS_CHANGE`, `ACCEPTANCE` and `EDITION` name users. Deleting the row either breaks those references or empties the audit answers the platform promises. Separately, ASR-02 "forbids personal data in the repository", which the platform cannot enforce: job descriptions and policies name people, and that text is the repository.

The pseudonymous commit identity (DL-0088) is a good decision and should stay. What is wrong is the claim built on it. Recommendation: erasure tombstones the user - display name and email removed, identifier and a "former user" label kept - so the audit trail stays whole; narrow ASR-02's clause to "the platform writes no personal data into commit metadata"; state in the threat model that personal data inside document text is the tenant's content and responsibility. For an employer's governed documents, authorship of an approval is typically data the tenant has a lawful basis to retain, so the tombstone is the rare case rather than the routine one - *inference; to be confirmed by whoever advises the first tenant on data protection.*

## Notes

### F-10 - Whole-document hold with whole-run acceptance

With one to three editors per document per week (owner's figure) exclusive holds are adequate, and this is a note rather than a blocker. The coupling to watch is not the hold but the run: versions by several authors stack, acceptance covers all of them or none (DL-0090), and with no *return* action (F-02) one doubtful contribution leaves the reviewer choosing between holding everyone's work and using the per-author undo of F-06. Partial acceptance is already in the backlog as B-014; its trigger should be written as "the first time a reviewer delays a run because of one author's part".

### F-11 - Stage 2 statements that are marked decided and do not hold together

Stage 2 detail is rightly deferred. These are recorded as decided, and they shape stage 1 attachment points:

- **Claude Code as the agent runtime** (technical design, from the seed). An agentic command-line tool makes many model calls per task, against ASR-12's measure of at most one model call per action per content state; it is a proprietary dependency inside a product whose ASR-13 forbids dependencies that cannot be redistributed; and it binds the platform to one provider while threat T-03 leaves the provider question open. A plain model API call behind a provider interface satisfies all three. The sandboxed container job remains right either way.
- **The analysis cache key.** ASR-12 keys results to a hash of the document tree. The tree contains `analysis/`, which the result is written into, and the key omits what DL-0078 later added - the other documents in scope and the heuristic set version. ASR-12 should be restated on DL-0078's key, with `analysis/` excluded from the hash.
- **Mandatory generated views recompiled by a model on every commit.** A regenerated list of contradictions has no stable item identity from one run to the next, so a "standing backlog editors act against" will reshuffle under them, and the cost scales with commits rather than with need. Needs finding identity across runs before it is promised.
- **Style hunks auto-accept.** With document-level acceptance there is no per-hunk acceptance for a style hunk to skip; and a classifier deciding that a change needs no human eyes contradicts ASR-04. Collapse them in the review view, accept them with the run.

### F-12 - The lifecycle diagram is a single state machine over a layered reality

`document-lifecycle.md` draws one state per document; `data-model.md` correctly derives three independent layers - canonical edition, accepted baseline, pending versions - and the diagram's own prose says the document "keeps moving past" canonical. Read literally, the diagram says a frozen document cannot be edited until the approver acts, which for a board approval may be weeks. The data model is right; the diagram should be redrawn as three small machines or state the rule that a freeze does not block editing.

## The owner's question - which state of neighbouring documents a multi-document analysis reads

*Raised by the owner during this review; the recommendation below is agreed by him and is handed to the authoring session as a stage 2 design input, to be recorded next to the review-scope decisions DL-0077 and DL-0078.*

The situation: a scope of several documents, some with pending edits, some with accepted edits beyond their canonical edition, some untouched.

Recommendation: the document under review is read at its pending head; every other document in scope is read at its **accepted** state by default, falling back to canonical where nothing has been accepted since; and the reviewer may switch an individual neighbour to its pending state, which puts a notice on the analysis listing those documents.

Why accepted as the default. Pending text is unreviewed and may be undone, so findings against it are unstable and train reviewers to distrust the list. Pending text is also visible only to people with an editing or reviewing role on that document, so an analysis that silently reads it can carry a neighbour's unaccepted wording to someone who may not see it; the provenance rule would then have to treat "document B" and "document B pending" as different sources. Accepted rather than canonical-only, because canonical can be months behind what the organisation has already agreed.

Why the switch must exist. The business driver is a transformation that revises a group of policies together. Checking policy A's new wording against policy B's old accepted wording reports contradictions that B's pending edits already resolve, which is noise of the opposite kind. For documents being revised as a set, pending-against-pending is the true question.

Conditions that make the switch safe: it is offered per neighbour and only where the reviewer holds the right to see that neighbour's pending edits; each finding records the exact state of every source it drew on, which DL-0078's key already carries; a finding that drew on a pending neighbour is marked provisional and re-run when that neighbour's run is accepted or undone.

## What holds up

Stated so the reconciliation pass does not reopen it. Linear history with revert-only undo is the right model for governed documents and removed more risk than any other decision in the log. One authorisation surface, with access as historised rows and confidential guidance as an ordinary restricted document, is cleaner than the repository-separation design it replaced. Two model runs with the guidance absent from the publishable one is the correct control and a real catch by the threat model. The parser-bound whitelist, the refusal of SVG, links that render as plain text without rights, the flat storage layout with presentation folders, the required export version, and keeping container-start capability out of the web process are all decisions an experienced team would make.

## Coverage

Read in full: PRD, technical design, ASRs, data model, threat model, document lifecycle, user stories, scope agreement, backlog, open questions, the three ADRs, `work/linear-workflow.md`, `work/release-0.1-passport.md`, `SESSION.md`, the heuristic catalogue's provenance and kinds sections. Decision log: read by targeted rows, not end to end. Not read: the working chat notes, `glossary.md`, `concept.md`, the source inventory, `work/markdown-vs-latex.md` beyond one passage.

Not judged, because the workflow schedules them later: story map, epics and story detail, deployment architecture, test strategy, API design, wireframes, Ukrainian vocabulary.

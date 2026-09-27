---
tags:
  - report
  - engineering
aliases:
  - Syngraphē architecture review — third report
status: approved
date: 2026-09-27
---

# Architecture Review — Syngraphē design set, before G2

Reviewed: `docs/` as it stood on 2026-09-27 at commit `25ab667`, after DL-0254. Reviewer stance: senior software architect, fresh context, read-only. The set was reviewed on 2026-09-21 (`architecture-review-report-01.md`, findings F-01 to F-12) and its repairs re-read by diff (`architecture-review-report-02.md`, F-13 to F-18). This report reads the whole set again after the changes of 2026-09-25 to 2026-09-27 — reserving a document for editing (ADR-0009), the editor and its parsers (ADR-0010), the Git library and the move rule (ADR-0011), undoing a contribution redefined (DL-0243), and the pages — and continues the finding series.

*Status of this report.* The findings are a reviewer's reading of the set from outside, without the reasoning that produced it; each names the basis it rests on. Nothing here is binding. The author dispositions every finding — adopt, adapt, or reject with a reason — and the owner agrees the dispositions; a rejection that records its reason is as good an outcome as an adoption. Where an override may defeat a failure mode the reviewer saw, ask the reviewer before deciding.

## Verdict

**G2 — Design review should not close on this set yet; it is one fix and two spike results away from closing.** The architecture holds: the documents still describe one system after three parallel rounds of authoring wrote into them at once, the reservation arrived with its break-the-glass, its visibility and its audit intact, *accept as* is caught by the distinct-approver check exactly as a separate acceptance would be, and the editor, parser and Git decisions rest on measured spikes. In the way: F-19 — the correction notice, the safeguard ADR-0001 ships with the reviewer's power, is defined against a correction flow that DL-0222 and DL-0243 replaced, so under the flow the set now describes it has no trigger; and V-09 and V-10, whose spikes were running as this report was written, which the gate's second condition needs settled. Three middle findings each need a decision and can travel as open items; five low findings are notes.

## Findings by priority

| ID | Priority | Finding | Basis | Area | Documents |
|---|---|---|---|---|---|
| F-19 | top | The correction notice's trigger and computation are written for a correction that lives inside the accepting commit, a flow DL-0222 and DL-0243 replaced | set | review workflow | ADR-0001, technical design, PRD, stories, lifecycle, data model, pages |
| F-21 | middle | The authorship cache the worker writes has no table, no rule for the gap between a commit and the worker, and no repair | set, outside | attribution | technical design, data model, ADR-0011, ASR-21 |
| F-20 | middle | Data-model enumerations no longer match the prose: the passport commits, the notification events, the document states, who changed the text | set | data model | data model, technical design, stories, pages |
| F-22 | middle | The *mechanical analyses* of the Analysis tab and the send-for-review screen are a 0.1 region nothing in the set defines | set | editing surface | stories, pages, lifecycle |
| F-23 | low | Residue of the per-sentence undo and the pre-DL-0222 correction flow in text every reader meets first | set | supersession | PRD, ADR-0003, ADR-0001, verification plan, data model, decision log |
| F-24 | low | The lifecycle diagram and table disagree with the pages and the technical design on correction, return, undo and freeze | set | lifecycle | lifecycle, pages, technical design |
| F-25 | low | The glossary lacks the reviewer's acts and the interface's state tags, and names the hold state differently from the pages | set | vocabulary | glossary, pages |
| F-26 | low | Blocking a person does not end their hold or reservation; the owner has now decided it does | inference | access | stories, lifecycle, data model, threat model |
| F-27 | low | *Freeze* carries no viewing right, the gap DL-0234 closed for *make canonical* | inference | access | ADR-0007, PRD, stories |

*Top — gate blocker: the next phase would build the wrong thing or could not build. Middle — needs a decision; the next phase can proceed with it recorded as open. Low — a note. Basis: set — two documents disagree; outside — engineering knowledge the reviewer brings; inference — the reviewer's reading of intent or consequence.*

## Top priority

### F-19 — The correction notice is defined against a correction flow the set no longer has

**What the set says.** ADR-0001 § Decision, point 2 — the decision that restored the pairing after F-02 — generates a correction notice *at acceptance* for each author whose text the reviewer changed, computed from the diff. The PRD § Acceptance and the data model follow it: `CORRECTION_NOTICE` hangs off `ACCEPTANCE` through a required key. The technical design § Rejection records gives the computation: *when a reviewer corrects text in the same commit that accepts it, the platform diffs the editor's version against the accepted result*. That sentence describes DL-0041, the decision that made acceptance a passport commit carrying the corrections inside it.

Two later decisions changed the flow without mentioning the notice's trigger. DL-0222, finishing in one act, made a reviewer's correction an editing session: *Correct* on the pending tab takes the hold (pages.md, the Edit tab: *accept* alone to correct a pending run), the reviewer edits a draft, and finishes with *accept as N.M* — a content commit and a passport commit under one lock (technical design § Versions, holds and history) — or with *create version N.M-X*, which leaves the correction pending with no acceptance at all. DL-0243, undoing a contribution, made undo the same: the reversal goes into the reviewer's draft and is committed *as the reviewer's version (accept as or create version)*. ST-0037 and the lifecycle's *revert a contribution* row then say the notice goes to each author *when I finish editing* — at the commit, not at an acceptance — while the lifecycle's *accept as* row and the pages say *correction notices as at acceptance*.

The set therefore gives three triggers — the acceptance, the reviewer's finish, and *as at acceptance* — and one algorithm written for a correction that no flow produces any more: under *accept as* the correction is the commit before the acceptance, not inside it; under *create version* there is no acceptance; a correction or a revert left pending may be accepted later by another reviewer, and then the acceptor is not who changed the text. `CORRECTION_NOTICE` has no column for who changed it, because the design assumed the acceptance's reviewer.

**Why it matters.** Built from the technical design's sentence, the generator finds nothing to diff under every flow the set now describes, and the reviewer's power to rewrite a contributor's words ships without the disclosure ADR-0001 makes its condition — F-02, reopened. Built from ST-0037's sentence, it fires at a commit and has no acceptance to hang on. The review story and the undo story would build it differently, and neither would be wrong by its own document.

**What the owner told the review** (DL-0255). The happy path, expected for most documents and not enforced: one responsible author per document, who is also its reviewer; peers contribute minor changes and do not rewrite large parts; every reviewer edits. The notice is about the responsible person overriding a peer's contribution, which the narrow rule below covers; where peers rewrite each other substantively, their changes stay visible and attributed in pending edits without a notice.

**Recommendation.** One rule, stated in ADR-0001 § Decision and carried into the technical design § Rejection records, the PRD § Acceptance, ST-0035 to ST-0037, the three lifecycle rows and the data model:

> A correction notice is generated at acceptance, for every version of the accepted run committed by a holder of *accept* on the document — a correction, an undo, or a session finished by *accept as* — for each author whose line of the pending run that version replaced or removed, naming that version and its author as who changed it.

Consequences to write with it: a line whose author is in the accepted text rather than the run is ordinary editing and generates nothing; a version by an editor without *accept* generates nothing; nothing is generated when a version is committed, so a correction left pending with *create version* is disclosed at the acceptance that makes it authoritative, whoever performs it; `CORRECTION_NOTICE` gains the changing version, whose author is who changed it, and the reviewer of the acceptance is a separate fact; whether a version was made by a holder of *accept* is either a value of `VERSION.kind` written at commit time or read from the access history at that moment — the former is simpler and the pages already distinguish the paths. ST-0037 and the lifecycle rows change *when the reviewer finishes* to *at acceptance*. The broader rule — a notice for every pending line anyone but its author changed before acceptance — covers peer editing too and needs no classification of versions; the owner's description of practice does not require it, and it would notify peers about each other.

## Middle priority

### F-21 — The authorship cache has no table, no gap rule and no repair

**What the set says.** DL-0135 moved blame out of the page load: the worker computes per-line authorship after each commit and stores it as a derived row keyed by that commit; the technical design § Runtime and ADR-0011 § Consequences build on it — each commit's bounded blame (`git blame ^cached new`) is overlaid on the cached authorship, and the move rule runs over that commit's diff. ASR-21 forbids blame inside the three interactive paths: *authorship is read from its cache*. The data model holds no such table; its opening rule names navigation and search indexes as the only content-derived rows, and the section *What is deliberately absent* does not mention it either.

**Why it matters.** *Show author* on the pending tab, the historical page and the per-author undo all read authorship. Nothing says what the pending tab renders between a commit and the worker's completion — a spinner, the previous commit's authorship, or blame after all, which ASR-21 forbids; what a bounded blame does when the previous commit's row is missing, since it then has no base; or which job notices a version without its authorship row. *A rebuildable cache* is a principle; the write order, the reader's behaviour on a miss and the repair are the protocol, and the data model is where the reconciler's other duties are written.

**Recommendation.** Add the table to the data model — per document, version, file and line, the version that introduced the line and the ambiguous-move mark ADR-0011 records — under the tenant schema, rebuilt per version like `HEADING_INDEX`. State three rules in the technical design § Runtime: authorship of the pending run's own lines is derived from the run's diffs at render and never waits for the worker; older text without its row renders without an author and queues the job, never blocking (ASR-21); a bounded blame whose base row is missing falls back to a cold blame, which V-05 measured at well under a second. Give the reconciler the duty to re-queue any version without its rows. *Outside*: the shape of the table is the reviewer's; the absence and the missing rules are the set's.

### F-20 — Data-model enumerations the prose no longer matches

**What the set says.** Four places where a column's value list and the prose around it describe different things:

- **`VERSION.kind` is `edit | acceptance | revert`.** A return is a passport commit (DL-0114, `RETURN.version` — *the passport commit*) with no kind to be. The data model § Version numbers says the numbers are *written into the passport with the acceptance and the approval*, and DL-0183 says the same, so *make canonical* writes the passport — a commit — while the technical design § Versions says it *tags the latest accepted version* and the lifecycle's history entries list *canonisation* as an event. A tag cannot carry a passport write. Under F-19, correction and undo versions need a kind as well.
- **`NOTIFICATION.event`** lists neither the return (ST-0052: *its authors are notified with my reason*; pages.md § Notifications: *a run returned, with the reason*) nor the correction notice, which the PRD and ADR-0001 deliver *through the notification surface*; `CORRECTION_NOTICE` has no link to a `NOTIFICATION` row and, as F-19 says, no changer.
- **`DOCUMENT.state` is `creating | draft | active | archived`.** Creation ends in `draft` (§ Documents); nothing anywhere moves a document to `active`, and the section *What is deliberately absent* says there is *no state column on DOCUMENT for the review cycle*.
- **`VERSION.summary` reads *agent-written, editor may edit***, which is the 0.2 companion; in 0.1 the summary starts from a mechanical draft (lifecycle § An editing session).

**Why it matters.** These are the columns Epic 3 and Epic 9 create first; each mismatch is a decision an implementer takes alone, and the history tab, the document list's *returned* state and the notice delivery each depend on one of them.

**Recommendation.** Decide that *make canonical* writes a passport commit — approver, edition number, the accepted version it approves — and tags it, so T-07's detection covers the approval as it covers the acceptance; give `VERSION.kind` the values `return` and `approval`, and the value F-19 needs. Add `returned` and `correction_notice` to `NOTIFICATION.event` with a nullable key to the notice. Drop `draft` from `DOCUMENT.state`: `author_only` already carries the only fact it could mean. Correct the summary's comment. The alternative for the approval — a tag alone, and the data model's sentence changed — keeps the repository's record of an edition in a ref rather than in the passport, which is the file the design says an auditor reads.

### F-22 — The *mechanical analyses* are a 0.1 region nothing defines

**What the set says.** ST-0029: *in stage 1 the analyses shown are the mechanical ones; the agent's arrive in stage 2 on the same screen*. pages.md gives the Analysis tab to release 0.1, Epic 4, with *edit* as its right, showing *the mechanical analyses*; the send-for-review screen shows them too; the lifecycle says the change summary starts *from a mechanical one*. No document says what a mechanical analysis is. The PRD § Editing is linear, step 5, still describes the screen as showing *the companion analyses*, which are 0.2. The owner confirmed to the review that nothing outside the set specifies them yet.

**Why it matters.** Epic 4 would build a tab and a screen region from a noun. Everything the screen can show mechanically in 0.1 is already specified elsewhere — the holder's changes marked word by word (*my edits*), the part operations, the images changed, the editable summary — so the region either duplicates them or invents something.

**Recommendation.** Decide one of two: define the list — for example the sections touched with sentence counts, the parts changed, the entities added or removed — in the technical design and ST-0029; or, smaller, state that in 0.1 the send-for-review screen shows *my edits*, the part operations and the summary and nothing else, and draw the Analysis tab as a 0.2 placeholder under DL-0228's rule. Define the mechanical summary the same way: the sections touched, or empty and typed by the editor.

## Low priority

### F-23 — Residue of models that lost

One cause, several passages; each instructs rather than describes, and two are on the path every reader meets first.

- **Per-sentence undo (lost to DL-0243):** PRD § Editing is linear — *computed per sentence from authorship*; ADR-0003 § Consequences — *computed per sentence from blame, with the platform resolving the case where a later author built on top* — and § Where divergence re-enters — *asking which wording should survive, is a conflict interface at sentence granularity*: the frontmatter names DL-0243, the passages carry no note, and the ADR is accepted; ADR-0001 § Rationale — *the per-author undo, a sentence-level instrument*; V-11's claim — *offering a choice for each of the latter, the feature behind reject all changes by this author* — proven as stated, with the re-scope noted under V-06 but not here.
- **Correction inside the accepting commit (lost to DL-0222):** PRD § Acceptance — *the same commit touches the content files too*; technical design § Rejection records (F-19).
- **The log:** DL-0101 stands *active* after DL-0115 reworded its check; mark it partly superseded.
- **A collision, not a supersession:** lifecycle § An editing session — *returning the document produces exactly one version* — where *return* is now the reviewer's act (DL-0114); read *finishing*.

Recommendation: one reconciliation pass over the list, and a note under each ADR passage rather than a rewrite, since the ADRs are records.

### F-24 — The lifecycle against the pages and the technical design

- The document diagram's `Pending --> Pending: reviewer corrects, then accepts` ends in Accepted, and under DL-0222 passes through Held; the diagram has no return transition and no path for the reviewer taking the document to undo.
- The table's *open an editor* row names the editor only; pages.md lets *accept* alone take the hold to correct (and the owner's ruling below may make this moot).
- *Correct before accepting* has the precondition *not reserved* only; the technical design § Versions and the data model § Versions both refuse correction during *any* hold, and pages.md disables *Correct* while an author holds the document. Its effect, *commit touching content and passport*, is the pre-DL-0222 flow.
- The diagram has no `Pending --> Frozen`, while the table's *freeze* row allows it whenever nobody holds the document.

Recommendation: redraw the first diagram with return, correction through Held, and freeze from Pending; align the two rows.

### F-25 — The glossary and the interface's names

The glossary's own rule — *if a second name for a concept appears in a document, that is a finding* — applies to it: the hold state is *held · зайнятий* in the glossary and *being edited* in pages.md's state tags. Missing from the glossary, all user-facing in 0.1: *return without accepting*, *correction notice*, *undo this edit* and *undo all of this author's edits* (the glossary has the internal *undo a contribution*), *compare*, *history*, and the state tags *awaiting review*, *returned*, *no reviewer assigned*, *frozen*, *being edited*. Recommendation: add them, and settle *held* against *being edited*.

### F-26 — Blocking a person and their hold

Nothing in ST-0004, ST-0065 or ST-0066 ends the hold or reservation of the person being blocked; the document stays locked, its group links unchangeable while it is held (ADR-0007), its draft preserved for someone who can no longer sign in, until an administrator notices and releases it as a second act. The threat model names no hold or reservation as an availability lever at all. **The owner decided, asked by this review, that the block ends the hold** (DL-0256): draft preserved, an audit event with the block as its cause and the draft's state, the document free. Recommendation: a criterion on the three stories, a row in the lifecycle table, a value of `HOLD.released_by`'s kind, and a line under T-09 saying that a hold is answered by the inactivity release, forced release, break-the-glass and the block.

### F-27 — *Freeze* without a viewing right

ADR-0007's acts table gives *accept* the pending view and *make canonical* the accepted view (DL-0234: *without it a group could approve text it cannot read*). *Freeze* has neither, so a group holding *freeze* and *view canonical* freezes a document as accepted without being able to read what it freezes. *Inference*: the same reasoning applies. Recommendation: *freeze and unfreeze* include *view accepted*, on the groups page as a faint tick like the others.

## Owner's questions

**The reviewer is always an editor** (DL-0255). Asked whether the organisation has reviewers who hold *accept* without *edit*, the owner answered that there are none and that the rights should form a ladder in which the reviewer is by definition an editor — *the plain coach*, not the software reviewer. ADR-0007 keeps *accept* and *edit* independent, with *accept* including the pending view and correcting (ADR-0001), and DL-0234 set the same instinct for the approver against ADR-0007 and settled on *make canonical includes view accepted* only. The review's recommendation, for the owner to decide outside the review when ADR-0007 is next opened: *accept* includes *edit*, recorded as a decision extending ADR-0007 the way DL-0234 and DL-0251 did, beside *edit* rather than above *create and edit*, so creating documents stays a separate grant. It collapses the Edit tab's rights line to *edit; while frozen, accept*, the freeze rule in its six places to *holders of accept may still edit*, and removes the accept-without-edit edge cases from F-19 and F-24. What it gives up: a group can no longer be given *accept* without *edit*. If the owner rules it a description of practice rather than a rule, ADR-0007 stands and the tenant administrator grants both. The owner has said the ladder of rights will be reviewed as a whole, and the authoring session logs whatever is decided.

## What holds up

The decisions an experienced team would make, named so the fix pass leaves them alone. The reservation as a property of the one hold (ADR-0009), with break-the-glass requiring a reason, the holder's name shown to those it blocks, every start, cancel and end an audit event, and no timeout — the risk of a hold left by someone long gone is answered by the administrators' list, and the owner chose it knowingly. *Accept as* (DL-0222) as the two records the two steps would leave, under one single-writer lock; a crash between the two ref updates degrades to the two-step outcome — a pending version — and the reconciler derives its row, which is the right failure. *Accept as* against the distinct-approver check (DL-0101, DL-0115): the holder becomes an acceptor of the run and cannot approve the edition while the check is on. The draft, the hold and the reservation as database-only state with no second store, covered by ASR-22 and ASR-25's recovery point. The move rule resting on DL-0244's normalizer, with the ambiguous identical-line case recorded rather than guessed (ADR-0011). One specification driving both parsers with a conformance suite in CI, and the fallback's control named where the specification cannot reach (ADR-0010, V-04). The not-found answer for everything a reader may not see (ADR-0008). Images always as a paragraph of their own, on every path (DL-0232, DL-0253). The first-run token (DL-0231). The verification plan's discipline of marking what was proposed during planning and what the owner approved.

## Coverage

Read in full: `prd.md`, `user-stories.md`, `technical-design.md`, `asr.md`, `data-model.md`, `document-lifecycle.md`, `threat-model.md`, `glossary.md`, `verification-plan.md`, ADR-0001 to ADR-0011, `interface/pages.md`, `interface/coverage.md`, `backlog.md`. Read by targeted rows: `design-record/decision-log.md` — DL-0211 to DL-0254 whole, the status of every row not marked active, and the rows the safeguards and the stores cite (DL-0041, DL-0054, DL-0090 to DL-0092, DL-0101, DL-0102, DL-0113 to DL-0115, DL-0135, DL-0189, and the rows behind the stances, the numbering and the notifications). Read as context only: the two earlier reviews' priority tables and finding titles. Consulted, not reviewed: `interface/mockup.html`. Not read: `design-record/concept.md`, the other design-record analyses, `docs/enhancements/`, `runbook.md`, `test-strategy.md`, `evaluation-strategy.md`, `review-findings.md`, and the release planning and working notes, which are not part of the set.

Not judged, because the workflow schedules it later or the owner accepted it: V-09 and V-10, whose spikes were running as this was written; V-12, V-14 and V-15, accepted as risks with nothing to add to what the plan already states; everything marked 0.2 or stage 2; the interface regions marked *not yet drawn*, visual style and the mobile layout; the deployment architecture; typing speed on the organisation's hardware.

---
tags:
  - report
  - engineering
aliases:
  - Syngraphē architecture review — fourth report, the second pass over report 03
status: approved
date: 2026-09-28
---

# Architecture Review — second pass over the repairs to report 03

Read: the authoring session's changes to `docs/` against commit `25ab667`, the state report 03 reviewed, by diff — staged and working tree, since the fixes were not yet committed. Finding ids continue report 03's series, so the two sit in one register. Reviewer stance as before: senior software architect, fresh context, read-only.

*Status of this report.* The findings are a reviewer's reading of the set from outside, without the reasoning that produced it; each names the basis it rests on. Nothing here is binding. The author dispositions every finding — adopt, adapt, or reject with a reason — and the owner agrees the dispositions; a rejection that records its reason is as good an outcome as an adoption. Where an override may defeat a failure mode the reviewer saw, ask the reviewer before deciding.

## Verdict

**G2 — Design review should close on this set once the owner approves the sample behind V-09, which is the one act left under the gate's second condition.** F-19, the blocker, is closed by ADR-0014 as recommended and then refined — one notice per author per acceptance, the classification written at commit — and the rule reads the same in the technical design, the PRD, the stories, the lifecycle and the data model. F-20 to F-27 are closed as the authoring session describes; the superseding ADRs (ADR-0014 to ADR-0016) are better records than notes under the old passages would have been, and the pages, the glossary and the mockup's groups grid follow them. The pass found one middle finding the fix introduced (F-31, the size of the authorship cache) and five low ones, three of them ways round or false positives in the rule the review itself recommended (F-28 to F-30). None holds the gate; F-31 travels as an open item.

## Findings by priority

| ID | Priority | Finding | Basis | Area | Documents |
|---|---|---|---|---|---|
| F-31 | middle | `LINE_AUTHORSHIP` is rebuilt per version and kept for every version, so it grows as lines times versions with no retention rule | outside | attribution | data model, technical design, ASR-23 |
| F-28 | low | A version committed as an editor and accepted by its own author after gaining *accept* generates no notice | inference | review workflow | ADR-0014, technical design |
| F-29 | low | The notice's diff counts a moved line as removed; the move rule says it is not | set | review workflow | ADR-0014, ADR-0011, technical design |
| F-30 | low | *Commits since the last acceptance* now includes passport commits, so the first version after an edition reads `2.0-2` | set | numbering | technical design, lifecycle, pages, data model |
| F-32 | low | ADR-0016's named consequence — an approver group holding *freeze* can write in a run — is not in the threat model's accepted risks | set | access | ADR-0016, threat model |
| F-33 | low | Residue: a missing supersession pointer, a hold bullet without the block, and the self-correction case unstated | set | supersession | ADR-0001, ADR-0015, ADR-0014, technical design |

*Top — gate blocker. Middle — needs a decision; the next phase can proceed with it recorded as open. Low — a note. Basis: set — two documents disagree; outside — engineering knowledge the reviewer brings; inference — the reviewer's reading of intent or consequence.*

## Middle priority

### F-31 — The authorship cache has no retention rule

**What the fix added.** `LINE_AUTHORSHIP` — one row per version, file and line, carrying the version that introduced the line — *rebuilt per version* (data model § Versions, holds and drafts), written by the worker after each commit as report 03's F-21 asked. The three rules keeping it off the interactive paths are in the technical design § Runtime and read correctly.

**Why it matters.** The table is kept for every version, so a document's rows grow as its line count times its version count. The Git spike's forty-page corpus had 1,624 lines over 203 commits, which is about 330,000 rows for one document; ASR-23's envelope allows a hundred pages, and a policy maturing over years passes many hundreds of versions. Across a tenant's corpus the cache becomes the largest table in the schema by an order of magnitude, for rows almost nothing reads: the pending tab and *my edits* attribute against the head, the historical page rarely toggles *show author*, and per-author undo walks git, not the cache (ADR-0011). *Outside*: the sizing is the reviewer's arithmetic on the spike's figures; the absence of a rule is the set's.

**Recommendation.** Decide the retention and write it beside the table: keep rows for the head version and the latest accepted version — the overlay ADR-0011 describes needs only the previous head, and the reconciler rebuilds — and attribute an older version on demand by a worker job whose result is cached with a lifetime, never blocking (the third of the § Runtime rules already covers the wait); or keep every version and put the growth as a number in ASR-23's envelope so the capacity decision is explicit. The first is smaller and loses nothing a user reaches today.

## Low priority

### F-28 — The classification at commit leaves one route round the notice

ADR-0014 classifies a version as a reviewer's at commit time, by the right its committer held then — the simpler of the two ways report 03 offered, and right for every flow the design describes. The route round it is a change of rights inside one run: a person commits a version as an editor, rewriting a peer's pending line, is then added to a group holding *accept*, and accepts the run themselves. The version's kind is `edit`, so the peer receives no notice, although the rewrite and the acceptance are one person's two acts — the case ADR-0001 exists for. *Inference*: rights change mid-run rarely, and the owner's practice (DL-0255) makes the responsible author a holder of *accept* from the start. Recommendation: one clause in ADR-0014 and the technical design § Rejection records — at acceptance, the acceptor's own versions in the run count as a reviewer's whatever their kind. The stored kind stays the fact for everyone else.

### F-29 — A moved line is not a removed line

ADR-0014 computes each notice from a reviewer's version diffed against its parent: *each line of the pending run it replaced or removed*. ADR-0011 recognises a moved sentence as a line removed and re-added verbatim within one commit and keeps its author; DL-0244 keeps a moved paragraph's stored bytes on every path so that the rule can. Read as written, the notice generator counts the removed half of every move: a reviewer who moves a peer's paragraph to another section sends that peer a notice for a change that did not happen, and the notice's *accepted text* for the line is empty. Recommendation: one sentence in ADR-0014 and the technical design — a line the move rule recognises as moved is neither replaced nor removed — and the same exclusion in the notice generator's tests as in the authorship worker's.

### F-30 — Which commits count as pending

`N.M-X` shows *the last accepted number plus the commits since it* (technical design § Versions; DL-0183), and *make canonical* is *refused while commits since the latest acceptance are unaccepted* (lifecycle, pages). DL-0260 gives the passport commits their kinds — `acceptance`, `return`, `approval` — and makes the approval a commit after the accepted version. Counted as written, the first content version after an edition reads `2.0-2`, since the approval commit sits between the acceptance and it, and a run that was returned once carries one extra in its count. Recommendation: define X, and *unaccepted commits*, as the content versions — `edit` and `reviewer_edit` — since the last acceptance, in the technical design and the glossary's *version number*; the data model already has the kinds to count by.

### F-32 — The threat model does not carry ADR-0016's named risk

ADR-0016 § Consequences names and accepts that a group holding *freeze* and *make canonical* can now write text in a run, and that the distinct-approver check (DL-0101, DL-0115) refuses an approver who *accepted* a run, not one who *wrote* in it. The threat model's T-08 and its accepted-risks list, which is where an auditor reads what the owner has knowingly taken, still describe the reviewer's self-acceptance only. Recommendation: one sentence under T-08 and one line in *Accepted risks*, citing ADR-0016.

### F-33 — Residue of the fix pass

- ADR-0001 § Rationale still calls the per-author undo *a sentence-level instrument*. The passage is superseded by ADR-0015, but ADR-0001's `superseded_by` names ADR-0014 only and ADR-0015's `supersedes` names ADR-0003 only; the workflow's pointer convention needs the pair added.
- The technical design's *Holds* bullet (§ Versions, holds and history) still ends a hold by inactivity or a forced release only; the data model, ST-0004, ST-0065, ST-0066, the lifecycle table and T-09 add the block (DL-0256).
- ADR-0014 does not say that the changing version's own author receives no notice for their own lines. ADR-0001 implied it; a line-based generator needs it stated, or a reviewer who rewrites their own pending sentence notifies themselves.

## Coverage

Read by diff, staged and working tree against `25ab667`: ADR-0001, ADR-0003, ADR-0007 and ADR-0009 (pointers only), `data-model.md`, `document-lifecycle.md`, `glossary.md`, `interface/coverage.md`, `interface/pages.md`, `prd.md`, `technical-design.md`, `threat-model.md`, `user-stories.md`, `verification-plan.md`; `interface/mockup.html` by its changed lines, its personas and its groups grid, which follow ADR-0016. Read in full: ADR-0014, ADR-0015, ADR-0016. The decision log: DL-0257 to DL-0265 whole, and the status changes on DL-0101, DL-0218 and DL-0243 checked against their unchanged text. Swept the current files for the vocabulary of the models that lost; what remains is inside frozen ADRs that carry a pointer, and ADR-0001's one passage in F-33. Decision ids checked for collision across both logs: none.

Not judged: ADR-0012 and ADR-0013 and the splitter bullet in the technical design, which are the text-and-rendering spikes' results and not this review's; their statuses were read for the gate — V-10 proven, V-09 measured at zero disagreements and open until the owner approves the sample. Not re-read: text the diff did not touch, beyond the vocabulary sweep. Every adopted recommendation of report 03 was re-read as someone else's design; the ways round found are F-28 to F-30.

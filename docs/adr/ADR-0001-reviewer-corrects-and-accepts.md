---
tags:
  - adr
aliases:
  - ADR-0001 Reviewer corrects and accepts
status: accepted
date: 2026-09-18
amended: 2026-09-21
title: The reviewer corrects and accepts, and the disclosure ships with the power
supersedes: []
superseded_by:
  - ADR-0014 (in part — which changes the correction notice covers and what it is computed from)
  - ADR-0015 (in part — the per-author undo as a sentence-level instrument)
---

# ADR-0001: The reviewer corrects and accepts, and the disclosure ships with the power

**Date:** 2026-09-18
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** None

## Context

Syngraphē borrows its review workflow from software development: someone changes the text, someone else reads the change and lets it through. That inheritance carries a default the platform must consciously reject.

In software, when a change contains something unacceptable, the **author** fixes it. The reviewer comments, or proposes a suggestion the author accepts. The reason is accountability: the author of a code change owns its correctness, and a reviewer who rewrites it takes on responsibility for behaviour they did not design.

**In a governed enterprise document, accountability sits somewhere else.** The person who signs off a policy section is answerable for its wording to the board, the auditor and the regulator. The editor drafting it may be a subject-matter contributor with no such exposure. When the accountable person finds a sentence unacceptable, sending it back adds a round trip and moves no responsibility — they will still be answerable for whatever comes back.

The tool being replaced already works this way. In Microsoft Word the person holding the document edits it directly and contributors' tracked changes are accepted, rejected or rewritten by that person. A workflow that is a round trip slower than Word for the routine case will not be adopted, whatever else it offers.

## Decision

**A reviewer may correct wording and accept the result, and the correction is disclosed by the platform rather than by the reviewer's goodwill.**

1. The reviewer takes the document, corrects the text and commits, then accepts the run since the last accepted version (DL-0090). Acceptance is recorded in the passport (DL-0041).
2. **A correction notice is generated at acceptance** for each author whose text the reviewer changed: what they wrote, what was accepted, who changed it. Computed from the diff, delivered through the notification surface. Generated, not authored — the reviewer has no discretion about whether the author finds out.
3. **Return without accepting** is an explicit reviewer action carrying a free-text reason. The run stays pending and its authors are notified.
4. Stage 2 turns the notice into a durable **rejection record** the editor may escalate into the Statement of Disagreements, settled by agreement or by the decider (DL-0026, DL-0076).

There are no branches and no merge; the history is linear (ADR-0003) and acceptance covers a whole document (DL-0090, DL-0091).

## Rationale

**Accountability decides who resolves.** Software's author-resolves default follows from the author owning correctness. Reverse that premise and the conclusion reverses with it. This is not a deviation from good practice — it is the same principle applied where the accountable party is the reviewer.

**The round trip is the cost that kills adoption.** The routine case is a reviewer who wants one sentence phrased differently. Returning it means a re-draft, a re-review and a second acceptance. Correcting it means an edit and an acceptance.

**The disclosure is the condition on the power, not a feature of the dispute machinery.** Rewriting a contributor's meaning without telling them is a different act from rewriting it and saying so, and only the second is reviewable. This was the amendment's occasion: DL-0076 deferred rejection records to stage 2 together with the dispute machinery, while the correction right stayed in the stage 1 walking skeleton. What DL-0076 correctly cut was the machinery for *arguing about* a rejection — register, escalation, decider. Telling the author is not machinery, and *"the editor is told by reading the history"* is not disclosure: it requires the author to first suspect that something changed.

**Declining has to be possible.** Without a return action a reviewer with one doubtful contribution in a run must either hold everyone's work or use the per-author undo — a sentence-level instrument — to remove it. That is heavy for *"this needs rework, talk to me"*.

## Consequences

- The correction-notice generator is a **stage 1 component and a blocker** for the story that implements reviewer corrections. The obligation survives the deferral of the object that used to carry it.
- The lifecycle gains a *return without accepting* transition; the stories gain it as ST-0052.
- Stage 2 replaces the notice with the durable rejection record. The notice is not discarded; it becomes the record's delivery.
- With no segregation of duties enforced by default (DL-0092), a reviewer may correct and accept in one motion. The notice makes that visible to the person whose words changed, and the optional approval check (DL-0101) gives a tenant a second pair of eyes at the canonical gate.
- Attribution inside a run is mixed: some sentences are the editor's, some the reviewer's. Sentence-per-line attribution and the *show author* toggle are what keep that legible.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| Author resolves, as in software | — | Rejected — misplaces accountability in this domain and costs a round trip on the routine case. Retained as the explicit *return without accepting* action, so the behaviour is available where it is right |
| Reviewer suggests, editor commits the suggestion | agent | Rejected as the default — it still requires the editor to act before an accountable reviewer can approve their own wording. Remains a reasonable interaction to offer in addition |
| Reviewer corrects with no record | — | Rejected outright — it makes the rewrite invisible to the person whose words were replaced |
| Correction right in stage 1, rejection record deferred to stage 2 | agent | **Withdrawn after challenge** — shipped the power without its condition; found by the architecture review as F-02 |
| Correction right with a generated notice, plus a return action | reviewer (architecture review) | **Chosen** — restores the pairing at a fraction of the cost of the full record, and the notice becomes that record's delivery mechanism |
| Forbid the reviewer to touch text at all | agent | Rejected — forces every wording disagreement through a dispute, making the decider a bottleneck on ordinary editorial friction |

## References

- Originating decision-log entries: DL-0024, DL-0026, DL-0102.
- Amended 2026-09-21 by owner override of the freeze rule, after ADR-0003 removed the branching vocabulary this was first written in and the architecture review's F-02 found that its safety mechanism had been deferred out from under it.

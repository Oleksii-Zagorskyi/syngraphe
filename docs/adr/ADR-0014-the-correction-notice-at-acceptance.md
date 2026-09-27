---
tags:
  - adr
aliases:
  - ADR-0014 The correction notice at acceptance
status: accepted
date: 2026-09-27
supersedes:
  - ADR-0001 (in part — which changes a correction notice covers and what it is computed from)
superseded_by: []
---

# ADR-0014: The correction notice is generated at acceptance, for every version a holder of *accept* committed

**Date:** 2026-09-27
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** in ADR-0001 § Decision, point 2, which changes the correction notice covers and what it is computed from — *for each author whose text the reviewer changed … computed from the diff*. The notice is still generated at acceptance, and ADR-0001's decision that the disclosure ships with the power stands.

## Context

ADR-0001 gives a reviewer the power to rewrite a contributor's words and makes a generated notice the condition on that power: the author is told, and the reviewer has no discretion about it. When it was written, the technical design had a reviewer's corrective edits ride in the accepting commit (DL-0041), so *the diff* the notice was computed from was the acceptance's own.

Two later decisions moved correction out of that commit. **DL-0222** lets a holder of *accept* finish an editing session in one act — *accept as N.M* — so a correction is a version of the run, committed before the acceptance, or left pending with *create version*. **DL-0243** makes undoing a contribution a reviewer's act applied to the reviewer's draft and finished the same way. Neither said what happens to the notice. Under the flows the design now describes, the rule as written finds nothing to diff: the third architecture review's F-19, which it ranked as blocking the design review.

The owner told the review how documents are edited in the organisation the platform serves (DL-0255): one responsible author per document, who is also its reviewer; peers contribute minor changes; every reviewer edits.

## Decision

**A correction notice is generated at acceptance, for every version of the accepted run committed by a holder of *accept* on the document — a correction, an undo, or a session finished by *accept as* — for each author whose change in the pending run that version replaced or reversed, naming that version and its author as who changed it.** A change is a line the author wrote, a line the author removed that the version restored, or an appendix or attachment operation the version reverted.

- **The acceptor's own versions in the run count as a reviewer's**, whatever their stored kind — so a person who rewrote a peer's line as an editor and later accepts the run as a reviewer still discloses it.
- **A moved line is neither replaced nor removed**: a line the move rule recognises as moved (ADR-0011, DL-0244) generates nothing.
- **Nobody is notified about their own lines.**
- **One notice per author per acceptance.** An author whose lines several versions replaced or removed receives a single notice listing every such line, each with the version that changed it and that version's author — never one notice per version or per line.
- A line whose author is in the accepted text rather than the run is ordinary editing and generates nothing.
- A version committed by an editor without *accept* generates nothing.
- Nothing is generated when a version is committed. A correction left pending with *create version* is disclosed at the acceptance that makes it authoritative, whoever performs that acceptance.
- `CORRECTION_NOTICE` is one row per author per acceptance; each entry it lists — a line, a restored line, or a part operation — records the changing version, whose author is who changed the text. The reviewer of the acceptance is a separate fact.
- Whether a version was committed by a holder of *accept* is written at commit time, as a value of `VERSION.kind`.

## Rationale

**Acceptance is the one moment a correction becomes authoritative.** Until then it is a pending version that another reviewer may still accept, revert or change; telling an author about a change that may not survive is noise, and telling them only if one particular person accepts it leaves a gap. Hanging the notice on acceptance gives one moment and one place the notice is generated, under every path to it.

**The version, not the acceptance, is what carries the change.** Computing per version names who actually changed the text — which may not be the person who accepts — and it survives the flows DL-0222 and DL-0243 introduced, because each of them ends in a version of the run.

**Holders of *accept* only.** The notice is the condition on the reviewer's power; peers editing each other's minor changes before review is the ordinary collaboration the design serves (DL-0255), and notifying peers about each other would bury the notices that matter.

**Grouped by author.** An author whose ten lines were changed in one acceptance needs to know that, once, with the ten lines in front of them; ten notices — or ten emails — would teach them to ignore the channel the disclosure depends on. The owner set the grouping.

**Classified at commit time.** Whether the committer held *accept* could be read from the access history at the moment of commit; writing it as the version's kind is simpler, is what the pages already distinguish, and does not depend on reconstructing rights later.

## Consequences

- The disclosure ADR-0001 requires reaches every flow the design has — correction in an editing session, undo, *accept as*, and a correction accepted later by someone else.
- `VERSION.kind` gains a value for a content version committed by a holder of *accept*; `CORRECTION_NOTICE` holds one row per author per acceptance and a line per change, each with its changing version; `NOTIFICATION.event` carries the notice, one notification per notice (DL-0260).
- ST-0035 to ST-0037, the lifecycle rows for correcting, undoing and finishing, the PRD § Acceptance and the technical design § Rejection records say *at acceptance*.
- A peer whose minor edit replaces another peer's line is not notified. Where an organisation's practice departs from DL-0255 — peers rewriting each other at length — that is the rule to revisit.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| A notice at acceptance per version committed by a holder of *accept* | reviewer (architecture review 03, F-19) | **chosen** |
| The same, covering restored deletions and reverted part operations as well as replaced or removed lines | reviewer (staged review of this change), agent | **chosen** — every override of an author's change is disclosed, not only overwritten text |
| Text lines only, restored deletions and part operations stated as not notified | agent | rejected — a reviewer reverting an author's attachment or restoring what they deleted overrides them as surely as rewriting a sentence |
| A notice for every pending line anyone but its author changed before acceptance | reviewer | rejected — covers peer editing, which DL-0255 does not call for, and would notify peers about each other |
| A notice when the reviewer finishes a correcting session | ST-0037 as written | rejected — fires on a commit that may never be accepted and has no acceptance to hang on |
| Keep ADR-0001's computation from the accepting commit's diff | ADR-0001 as written | rejected — no current flow puts a correction inside the accepting commit, so it finds nothing |
| Classify the committer from the access history at the moment of commit | reviewer | rejected — equivalent, but a reconstruction where a stored kind is a fact |

## References

- ADR-0001 — the power and its disclosure
- DL-0222 (finishing in one act), DL-0243 (undoing a contribution, ADR-0015), DL-0255 (the editing practice), DL-0259 (this decision, promoted here), DL-0260 (the data model's value lists)
- `docs/design-record/architecture-review-report-03.md` — F-19

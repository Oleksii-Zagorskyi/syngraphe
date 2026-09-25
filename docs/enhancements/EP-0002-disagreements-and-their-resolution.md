---
tags:
  - enhancement-proposal
id: EP-0002
title: Disagreements and their resolution
status: provisional
horizon: next
created: 2026-09-25
last-updated: 2026-09-25
authors:
  - Oleksii
related-adrs:
  - ADR-0001
supersedes: []
superseded_by: []
---

# EP-0002: Disagreements and their resolution

## Summary

When the people behind a document disagree about its wording, the platform should hold the disagreement as part of the document's record — each disputed passage with its competing wordings — until it is settled, and should refuse to make the document canonical while any disagreement is open. Release 0.1 ships the reviewer's power to correct with its disclosure, the correction notice and the return with a reason (ADR-0001); the register, its states and the role that rules on deadlock are this proposal.

## Motivation

A reviewer who corrects an author's wording and accepts the result settles the text, not the disagreement. Without a record, the author's objection lives in email or memory, and a document reaches canonical status with a dispute nobody can see. An organisation that has to stand behind a document needs to know that every objection raised against its wording was resolved, and how.

### Goals

- A disagreement about a passage is recorded against the document, with each competing wording, until it is resolved.
- A document cannot be made canonical while any disagreement is open (DL-0010).
- A disagreement ends by agreement between the people involved, or, on deadlock, by the ruling of someone with the authority to rule (DL-0026).
- Exactly one wording survives each resolved disagreement, and the record keeps the others.

### Non-goals

- Discussion that is not about wording — comments and the annotation surface are backlog B-013.
- Voting or board procedure; the approving body's own process stays outside the platform.

## First principles

- **The record, not the prevention.** A reviewer keeps the power to correct and accept; what the platform adds is that an objection to that power is recorded and must be answered.
- **One wording survives.** A disagreement is resolved when the text says one thing, not when the discussion stops.
- **Canonical means uncontested.** Nothing becomes the authoritative text over an open objection.

## Proposal

- **The Statement of Disagreements** — a register attached to the document, holding each disputed passage in its competing variants (DL-0009), anchored to the text the way findings and comments are (DL-0027).
- **Two ways in.** A reviewer marks a passage disputed; an author escalates a correction notice into an entry.
- **States.** `open → agreed → closed`, or `open → escalated → decided` (DL-0026).
- **The decider** — a right held through groups (ADR-0007), ruling only on escalated entries.
- **The gate.** *Make canonical* is refused while any entry is open.

### Notes and constraints

- The correction notice (ADR-0001, DL-0102) is the first form of the rejection record; its table becomes the source of escalated entries.
- A freeze (DL-0189) may be the moment disagreements surface; how the two interact is unresolved.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Every correction escalated, blocking canonicalisation | Escalation is the author's act on a specific notice, and agreement closes an entry without a ruling |
| No one holds the decider right | A document with escalated entries shows *no decider assigned*, as acceptance shows *no reviewer assigned* |

## Design details

*Not yet written — the proposal is provisional.*

## Alternatives considered

| Option | Raised by | Outcome |
|---|---|---|
| A register gating canonicalisation | owner | proposed |
| Disagreements settled outside the platform (release 0.1) | owner | the interim state, DL-0076 |
| A backlog row only | agent | rejected by the owner — the idea carries several decisions and open questions |

## Unresolved questions

- Who may open an entry besides the reviewer and the author whose text changed.
- Whether an entry opened during a freeze blocks unfreezing as well as canonicalisation.
- How the decider is chosen per document, and whether they may rule on text they wrote.
- What an export shows of open and closed entries.
- Whether a stale entry — its passage since rewritten — closes itself or needs an act.

## Triggers

- **Accepted** when the review cycle of release 0.1 is in real use and the first disagreement has been settled outside the platform.
- **Implementable** once the correction notices of release 0.1 show how often authors object.

## Graduation criteria

*Set when the proposal is accepted.*

## Implementation history

- 2026-09-25 — written as provisional; supersedes backlog B-010.

## References

- ADR-0001 — the reviewer corrects and accepts
- DL-0009, DL-0010, DL-0026, DL-0076, DL-0102
- `document-lifecycle.md § A disagreement`

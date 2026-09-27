---
tags:
  - adr
aliases:
  - ADR-0015 Undoing a contribution
status: accepted
date: 2026-09-27
supersedes:
  - ADR-0003 (in part — the platform resolving sentences a later author built on, and per-author undo as a conflict interface)
  - ADR-0001 (in part — the per-author undo as a sentence-level instrument)
superseded_by: []
---

# ADR-0015: Undoing a contribution is a reviewer's act on the pending run, applied to the reviewer's draft

**Date:** 2026-09-27
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** in ADR-0003 § Consequences, *undoing one author's contribution is a revert, computed per sentence from blame, with the platform resolving the case where a later author built on top*; and in § Where divergence re-enters, the per-author undo as *a conflict interface at sentence granularity* that asks *which wording should survive*. The linear history and everything else in ADR-0003 stand. In ADR-0001 § Rationale, the per-author undo as *a sentence-level instrument*.

## Context

ADR-0003 kept the history linear and named the one place divergence re-enters the product: undoing one author's work where a later author has since built on it. As written, the platform would show which sentences were built on and ask which wording should survive — a conflict interface, and the hardest algorithm in stage 1. Verification claim V-11 proved the classification it needs: on a generated forty-page history, every sentence one author added was classified as untouched, built on or removed, within the five-second budget.

The act was then redesigned around how reviewing works in the organisation the platform serves (DL-0255): the reviewer is the document's responsible author and edits what they do not agree with. It was recorded as DL-0243, with a pointer in ADR-0003's frontmatter; the third architecture review found ADR-0003's passages still instructing the old model (F-23). A change to an accepted decision is recorded as a superseding ADR, which this is.

## Decision

**Undoing a contribution is a reviewer's act, started from the History tab, in two units: *undo this edit* on any version after the last acceptance, and *undo all of this author's edits* for any author of the pending run.**

- **The reversal is computed automatically against the latest commit and applied to the reviewer's draft** — the one they have open, or a new one that takes the document. Nothing is deleted from the history: the removed text is taken out and the earlier text typed back as ordinary edits.
- **Sentences a later version changed are not reverted.** They are left as they stand and listed at the top of the draft for the reviewer to edit by hand; choosing sentence by sentence or word by word is ordinary editing.
- **Finishing commits the reviewer's version** — *accept as* or *create version* (DL-0222) — and each author whose text was removed receives a correction notice at acceptance (ADR-0014).
- **Editors no longer have the act**: their own unsent work is discarded with *discard my edits*, and accepted text is changed by editing.
- A holder of *accept* reaches the pending run's versions in the History tab (DL-0251).

## Rationale

**Automation where the reversal is mechanical, the editor where it is a choice.** A sentence nobody touched since can be reverted without asking anyone. A sentence a later author changed poses an editorial question, and the reviewer already has the interface for editorial questions: the editor. A separate screen offering the competing wordings would duplicate it, and would be the one conflict interface a linear design exists to avoid.

**Both units.** The owner's first description was per version; the agent pushed back that per version alone would drop the per-author promise V-11 had just proved, and the owner chose both. Per version answers *this edit was a mistake*; per author answers *this person's contribution should come out*.

**The pending run only.** Once text is accepted it is the reviewer's own, and changing it is editing, with the history as its record. Limiting the act to the pending run keeps the computation against a short, known span.

## Consequences

- No conflict interface is built. V-11's classification separates the sentences reverted automatically from those listed for the reviewer.
- The per-version reversal's classification is claim V-14, accepted as a risk and proven by the tests of the story that builds undo.
- ST-0037, the lifecycle's *undo a contribution*, the glossary's *undo a contribution*, the PRD's description of undo and the technical design's paragraph on it are read against this ADR, not ADR-0003's passages.
- A reviewer undoing a large contribution still does the built-on sentences by hand; the list at the top of the draft is the only help.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| Per version and per author, into the reviewer's draft, built-on sentences listed | owner, per author added after the agent's pushback | **chosen** |
| Per author only | agent | rejected — *this edit was a mistake* is the commoner case and would need the author's whole contribution undone |
| Per version only | owner's first description | rejected after pushback — drops the per-author promise the scope agreement makes and V-11 proved |
| The platform resolves built-on sentences by asking which wording survives | ADR-0003 as written | rejected — a conflict interface duplicating the editor, and the hardest algorithm in stage 1 for a choice the reviewer makes better by editing |
| Editors keep an undo of their own | the design before DL-0243 | rejected — their unsent work has *discard my edits*; their sent work is the reviewer's to judge |

## References

- ADR-0003 — linear edit history; ADR-0001, ADR-0014 — the correction notice
- DL-0222 (finishing in one act), DL-0243 (this decision, promoted here), DL-0251 (*accept* opens the History tab for the pending run), DL-0255 (the editing practice)
- `docs/verification-plan.md` — V-11, V-14
- `docs/design-record/architecture-review-report-03.md` — F-23

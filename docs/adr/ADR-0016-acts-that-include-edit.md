---
tags:
  - adr
aliases:
  - ADR-0016 Acts that include edit
status: accepted
date: 2026-09-27
supersedes:
  - ADR-0007 (in part — the acts as rights that include only what their holder needs to see)
  - ADR-0009 (in part — *reserve for editing* usable only where the group can also edit)
superseded_by: []
---

# ADR-0016: *Accept*, *freeze and unfreeze* and *reserve for editing* include *edit*

**Date:** 2026-09-27
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** in ADR-0007 § Decision, the acts row — *accept* including the pending view and correcting, *freeze and unfreeze* including nothing — and the independence of those acts from *edit*; in ADR-0009 § Decision, *usable only where the group can also edit* for *reserve for editing*. Group-based access, the viewing ladder, the history rights, the part rights, *make canonical* and everything held by a person stand.

## Context

ADR-0007 gives groups a viewing ladder — view canonical, view accepted, view pending, edit, create and edit, each including those below — and beside it a set of **acts**, each an independent right including only what its holder needs to see: *accept* the pending view and correcting (ADR-0001), *freeze and unfreeze* nothing, *make canonical* the accepted view (DL-0234). ADR-0009 added *reserve for editing* as an act usable only where the group also holds *edit*. While a document is frozen, only holders of both *accept* and *edit* take the hold (DL-0189).

The third architecture review found *freeze* without any view — a group could freeze text it cannot read (F-27) — and asked where *accept* stands. The owner described the practice the platform serves (DL-0255): the reviewer is the document's responsible author, *by definition an editor*; there are no reviewers who cannot edit. Reviewing the ladder the review compiled, the owner decided that the acts which work on a document's text form a ladder with *edit*.

## Decision

**Three acts include *edit*, and through it *view pending* and *view accepted*; none of them includes *create and edit*:**

- ***accept*** — every reviewer can edit. A group that accepts and cannot edit no longer exists.
- ***freeze and unfreeze*** — a group reads and can work on what it freezes. No group holds *freeze* without *edit*.
- ***reserve for editing*** — the right includes *edit* instead of being usable only beside it.

**During a freeze, holders of *accept* take the hold**; DL-0189's *both accept and edit* reads *accept*, with no change of meaning. Holders of *freeze* without *accept* edit like any editor outside a freeze and do not take the hold during one. ***Make canonical*** is unchanged: it includes *view accepted* and not *view pending* (DL-0234), and not *edit*.

## Rationale

**A right that cannot be used alone is an inclusion written the long way.** Reserving a document one cannot edit does nothing; reviewing without editing is not a case the organisation has (DL-0255). Writing these as inclusions removes combinations that do nothing and settings an administrator can get wrong.

**Freeze sees what it freezes.** The review's F-27 asked for *view accepted*; the owner went further, placing *freeze* on the ladder with *edit*, so whoever decides that a document is ready can also work on it. The owner confirmed that no freeze-only role — someone who prepares a document for the approving body without editing it — is needed.

**Creating documents stays separate.** *Create and edit* is the one right not tied to a document (ADR-0007): an organisational permission, not a step in reviewing one.

**The approver stays apart.** *Make canonical* keeps its narrow view, and the distinct-approver check (DL-0101, DL-0115) still refuses an approver who accepted a run since the previous edition.

## Consequences

- The groups page shows *edit* and the views as included — faint ticks — under *accept*, *freeze and unfreeze* and *reserve for editing*, as it already does for *make canonical*'s view (DL-0234).
- The Edit tab's path for a holder of *accept* alone and the send-for-review screen's variant for *edit and accept* (ADR-0009, DL-0222) become one path: a holder of *accept*.
- The part rights — appendices and attachments — remain usable wherever the group can edit, which now includes these three acts.
- **Named and accepted:** a group holding *freeze* and *make canonical* can now write text in a run. The distinct-approver check refuses an approver who *accepted* a run since the previous edition, and — as before — not one who *wrote* in it.
- F-27 is closed by this decision.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| *Accept*, *freeze* and *reserve* include *edit*, not *create and edit* | owner | **chosen** |
| The acts independent of *edit*, as ADR-0007 wrote them | ADR-0007 | rejected — leaves combinations that do nothing and a reviewer who cannot edit, which the organisation does not have |
| *Accept* above *create and edit*, so every reviewer can create documents | reviewer, as a second choice | rejected — creating is an organisational permission, not a step in reviewing |
| *Freeze* includes *view accepted* only | reviewer (F-27) | superseded by the inclusion of *edit*, which contains it |
| *Freeze* independent of *edit*, *edit* granted separately where wanted | agent | rejected — the owner confirmed no freeze-only role is needed |
| Holders of *freeze* may take the hold during their own freeze | agent, as an alternative reading | rejected — during a freeze, only holders of *accept* edit (DL-0189) |
| *Reserve for editing* usable only where the group can also edit | ADR-0009, DL-0218 | replaced by the inclusion |

## References

- ADR-0007 — group-based access; ADR-0009 — reserving a document for editing; ADR-0001 — the reviewer corrects and accepts
- DL-0189 (freezing), DL-0218 (who may reserve), DL-0234 (*make canonical* includes *view accepted*), DL-0251 (*accept* opens the History tab for the pending run), DL-0255 (the editing practice), DL-0263 to DL-0265 (this decision, promoted here)
- `docs/design-record/architecture-review-report-03.md` — F-27 and the owner's question on the ladder

---
tags:
  - adr
aliases:
  - ADR-0009 Reserving a document for editing
status: approved
date: 2026-09-27
supersedes:
  - ADR-0006 (in part — the release of a reserved hold, who sees its holder, and the send-for-review screen)
superseded_by: []
---

# ADR-0009: Reserving a document for editing — a hold that lasts, and finishing it in one act

**Date:** 2026-09-27
**Status:** Approved
**Deciders:** Oleksii
**Supersedes:** in ADR-0006, for a reserved hold, the inactivity release, the rule that only the tenant administrator sees who holds a document, and the rule that the tenant administrator is the only role that can end someone else's session (a platform administrator, who can do everything a tenant administrator can — ADR-0007, DL-0079 — ends a reservation too, DL-0214); and the three-choice send-for-review screen for a holder of *accept*. Extends ADR-0007 with one right.

## Context

Maturing a long document can take weeks of sittings before its author considers the next iteration ready for peers. The editing model already fits that: a draft persists across sittings, nobody else sees it, and only finishing the session commits, so weeks of work still produce one version (ADR-0003, ADR-0006). What did not fit was the hold's lifetime. After a period without activity — 30 minutes by default, set per tenant — and an unanswered prompt, the hold is released; if someone else commits meanwhile, the long-running draft goes stale, and the linear model has no merge (DL-0212).

A second friction surfaced with it. A person who holds both *edit* and *accept* finished a session with *send for review* and then accepted their own run as a separate step — sending, in effect, to themselves (DL-0092 already allows self-acceptance).

## Decision

**A holder may reserve the document for editing** — *reserve for editing* · *зарезервувати для редагування* (DL-0217).

- **A property of the one hold, not a state of its own** (DL-0221). Exclusivity, the one draft, the open editors and the capture rules are unchanged; a reserved hold is exempt from the inactivity release. The document is held throughout.
- **Who:** a member of a group holding the right *reserve for editing*, linked to the document — one of ADR-0007's acts, usable only where the group can also edit (DL-0218). Only the current holder can reserve, so eligible members never contest a reservation.
- **Starting:** only from an editing session the holder already has — open an editor, then reserve; never while someone else holds the document (DL-0219). *Cancel the reservation* returns it to an ordinary hold, whose inactivity clock starts again. Drafts preserved from earlier released holds are neither merged nor branched.
- **Ending:** finishing the session (one version, never an edition, DL-0213), discarding, cancelling, or break-the-glass by a tenant or platform administrator (DL-0214, DL-0220). There is no timeout and no expiry: when to end it is agreed between people, outside the platform.
- **What it blocks:** as for any hold, freezing, changes to the document's group links and correction wait, with no exceptions — but a reserved hold has no inactivity release to end the wait; a frozen document cannot be reserved (DL-0223). New with the reservation: accepting and returning by anyone else wait until it ends too (DL-0224). One person may hold any number of reservations; each document is independent (DL-0227).
- **Break-the-glass** requires a reason; the holder is notified of who, when and why; the audit event records it with the draft's state. On return the holder takes the hold back if nothing was committed meanwhile; otherwise the draft opens read-only as changes against the current text, switchable to any version they may see (DL-0225).
- **Visibility:** everyone who may read the document sees *reserved for editing, since* a date; holders of *edit* or *accept* on it, and administrators, also see who; the tenant administrator is notified when a reservation starts (DL-0226). Ordinary holds keep ADR-0006's rule.

**Finishing a session in one act, for a holder of *accept*** (DL-0222). The send-for-review screen names what each choice produces, with the number that results — shown here for a synthetic document whose last acceptance is 2.3, with nothing pending:

| The holder holds | Choices besides *continue editing* and *discard my edits* |
|---|---|
| *edit* | *send for review* — the version waits as `2.3-1` |
| *edit* and *accept* | *accept as 2.4* — the version is made and the run accepted, both attributed to the holder · *create version 2.3-1* — the version waits in pending edits |

The screen is opened by *finish editing* · *завершити редагування* for everyone. The change summary of a version made by *accept as* shows in its history entry, since it is never pending. *Accept as* accepts the whole run since the last acceptance, other editors' versions included, with correction notices as usual (ADR-0001). How it relates to the reviewer agent's run, which starts at *send for review*, is decided with that run in release 0.2.

## Rationale

The inactivity release exists because thinking looks like absence for minutes (ADR-0006); it stays right for ordinary edits. Weeks of maturing are a different act, declared by the holder rather than inferred by the platform, and ended by people who can talk to each other — so no clock, and a break-the-glass path for the case where they cannot.

Making the reservation a property of the hold keeps every guarantee a hold gives and adds only a different release; a second state would have had to restate those guarantees and would drift from them. Showing the holder's name to the people it blocks follows from the same fact: an agreement between people needs to know who the other person is.

Finishing in one act removes a step with no control in it. Self-acceptance is already allowed and recorded, so the act produces exactly the records the two steps would; naming the choices by their result — a number — removes the question *whom am I sending this to*.

## Consequences

- `HOLD` gains the reservation mark and its start; the inactivity release skips a reserved hold; `GROUP_RIGHT` gains *reserve for editing*; starting, cancelling and ending a reservation are audit events, and break-the-glass adds a reason and a notification (DL-0221, DL-0225).
- A reserved document can be unavailable for review, freezing and access changes for weeks. The escape is break-the-glass, not a routine path.
- A draft may now hold weeks of work that exists only in the database; ASR-22 and ASR-25's recovery point already cover it (DL-0216).
- The send-for-review screen computes the numbers it shows.
- A reservation left by someone long gone is the risk ADR-0006 named; it is answered by administrators seeing every reservation with its start date, not by a timeout.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| A reserved hold exempt from the inactivity release | owner | chosen |
| Private checkpoints inside a draft, not versions | agent | rejected (DL-0212) — adds a second kind of save point |
| A draft becomes a version | agent | rejected (DL-0212) — contradicts the draft-and-one-version model |
| The name *park* | owner | declined for *reserve* (DL-0217) — reads as idle |
| A right granted to a person | owner (first description) | withdrawn after challenge — ADR-0007 grants nothing about documents to a person directly |
| Any editor may reserve, no separate right | agent | rejected (DL-0218) |
| A separate document state | agent | rejected (DL-0221) |
| Reserving without opening an editor; or only from the start | agent | rejected (DL-0219) |
| Keeping the reservation across finishing | agent | rejected (DL-0220) |
| Link changes allowed during a reservation; reserving during a freeze | agent | rejected (DL-0223) |
| Reviewers may accept or return during a reservation | agent | rejected by the owner (DL-0224) — reviewing text under rework is wasted |
| Comparison with the current text only | agent | rejected (DL-0225) — any version is offered |
| The holder's name to the tenant administrator only, as for ordinary holds | existing design | rejected for reservations (DL-0226) |
| One reservation per person | agent | rejected (DL-0227) |
| Automatic acceptance whenever a holder of *accept* sends | agent | rejected (DL-0222) |
| *leave unaccepted*, *put in review*, *keep for review* as wording | agent | rejected (DL-0222) — *create version 2.3-1* names the result |

## References

- Originating decision-log entries: DL-0212 to DL-0215, DL-0217 to DL-0227
- ADR-0001, ADR-0003, ADR-0006, ADR-0007
- DL-0092, DL-0101, DL-0115, DL-0189, DL-0198, DL-0216

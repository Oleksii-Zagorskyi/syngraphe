---
tags:
  - report
  - engineering
aliases:
  - Syngraphē architecture review — second pass
status: draft
date: 2026-09-21
---

# Architecture Review - second pass over the fixes

Read: the authoring session's uncommitted changes to the authoring session's set and the project `CLAUDE.md` as of DL-0110, by diff against the commit that holds the first report. Finding ids continue the first report's series so both can sit in one register.

## Verdict

The fixes for F-01, F-02, F-05, F-07, F-09, F-10 and F-12 are implemented as recommended and read cleanly; the amended ADR-0001 and ADR-0002 are better records than the originals. The pass introduced two defects of its own (F-13, F-14), exposed a hole in a recommendation that was mine (F-15), and left a tail of unreconciled text (F-16). F-17 and F-18 follow from decisions taken since the first report. None of the six is large; F-13 and F-15 should not reach the story map as they stand.

## F-13 - The correction notice copies document text into PostgreSQL and, by email, out of the platform

`CORRECTION_NOTICE` carries `original` and `accepted` as text columns. That breaks the rule `data-model.md` opens with - PostgreSQL never holds a second copy of content - and it breaks it in the one place where the copy matters:

- **The copy escapes the access table.** A notice row is read through the notification surface, not through `DOCUMENT_ACCESS`. An author whose read right is later revoked, or whose document is archived, keeps the text. ASR-08 and the archive rule (DL-0084) both assume the document is the only place its text lives.
- **Notifications go to email** for the same events (DL-0070). A correction notice sent as written puts passages of a possibly confidential document into a mailbox. Nothing else in the design lets document text leave the platform except an audited, per-document export.

Recommendation: the notice stores references, not text - the acceptance, the author, the author's version and the file and line range in each - and the two wordings are rendered from git when the notice is opened, under the reader's current rights. It stays rebuildable, which the other git-derived rows already are. Add one rule to the notifications section: no notification, in the application or by email, carries document text; email carries the event and a link.

## F-14 - Return without accepting has nowhere to be recorded

ST-0052 and the lifecycle row add the action; the data model did not move with them. There is no row, column or file that holds the reviewer's reason, and `NOTIFICATION` has no text field. Two consequences:

- **The document list cannot tell "awaiting review" from "returned to its authors".** ST-0014 exists so a reviewer can decide what to open; a returned run will sit in that list looking like work waiting for them.
- **The decision does not travel with the document.** DL-0041's principle is that a reviewer's decision is a commit to the passport, so that the approval history needs no second system to be believed. A return is a reviewer's decision. Held only in the database it is the first review outcome that an export would not show.

Recommendation: a return is a passport commit, like an acceptance, carrying the reviewer and the reason; a derived row gives the list its state. State what the next send for review presents after a return - the whole run since the last acceptance, returned versions included, which is what the linear model implies.

## F-15 - The optional second-approver check can be stepped around, and the hole was in my wording

I recommended, and DL-0101 adopted: an edition cannot be approved by whoever performed the **last** acceptance before the freeze. A reviewer who accepts a substantive run of their own, then has a colleague accept a following run that changes a comma, is no longer the last acceptor and may approve. The colleague looked at a comma. The check was meant to guarantee that a second person stood behind the text that becomes authoritative, and as worded it guarantees only that a second person touched the document most recently.

Recommendation: the approver must have performed **none of the acceptances between the previous canonical edition and this one**. Still one query at one transition, still off by default. `TENANT.require_distinct_approver`, ST-0053, ASR-04, the PRD paragraph, T-08 and the scope agreement's sentence all carry the old wording.

## F-16 - What the reconciliation pass did not reach

`technical-design.md`, still in the superseded model: the reviewer agent's and the companion's "confidential guidance repository"; "a proposal's findings", "every open proposal" and "the length-limited proposal description" in the agent sections; "style hunks auto-accept" (the first report's F-11 note); "no email path is written until Q33" against the PRD's new "settled at DL-0072"; the "one repository per document set" and per-tenant "service account" paragraphs, which the design consultation will overwrite anyway. `data-model.md` says the tombstone "is pending a ruling" two paragraphs after citing DL-0108 for it, and still says Q33 gates the mail. `document-lifecycle.md` still has "rejection records generated" on the correct-before-accepting row. ST-0028 still refuses HEIC while the design converts it. The passport's ADR table carries both old titles.

Two that matter more than tidiness:

- **The scope agreement still promises per-author undo without qualification**, while DL-0108 says it is spiked before the agreement keeps promising it. The agreement is the one document the business users read; either the spike runs before they see it, or the bullet says "planned, being verified".
- **The project `CLAUDE.md` gotchas**, which every future session reads first, still say the normal form exists because "LaTeX-as-source is unreviewable" with "whitelisted macros", that the git-side tenant boundary "is open (Q27)", that the reviewer agent emits two artefacts "written under a non-disclosure constraint" (DL-0095 replaced that with two runs), and that actions run "against committed versions only ... per version" (DL-0056 made it content state, mid-edit included). The optional-reading table describes ADR-0001 and ADR-0002 as superseding themselves.

## F-17 - Lockout contradicts identical responses

DL-0107 asks for lockout after repeated failures and for sign-in to answer identically whether or not an address is known. An account that locks answers differently from an address that does not exist, which is the enumeration oracle T-14 sets out to close; and a lock that anyone can trigger with a known address lets an outsider shut a reviewer out before a board date. Recommendation: throttle by address and source with growing delay and one uniform response, and never a hard lock that the owner of the address did not cause.

## F-18 - Self-hosting changes what the threat model inherits

DL-0109 moves stage 1 from a rented server to a self-administered development host. Reasonable at this scale. Two statements elsewhere stop being true with it:

- `threat-model.md` scopes out "physical security, the hosting provider and the operating system" as inherited. On a self-administered host nobody else provides them; they fall to whoever runs it, and the model should say so rather than inherit from a provider that no longer exists.
- F-03's backup rule was written for a hosted machine. On a single self-administered host, the scope agreement's "nothing is ever lost" is true only if a copy leaves that host. An off-host copy of the database archive and the repositories is the minimum that makes the sentence honest; it belongs with the write protocol when F-03 closes, not with the deployment document months later.

## Coverage

Read: the full diff of the authoring session except the working chat notes, `glossary.md` and the decision log, whose new rows DL-0100 to DL-0110 were read truncated; the amended ADR-0001 by keyword only. Not re-read: anything the diff did not touch, beyond a keyword sweep for superseded vocabulary. DL-0110's manifest version and hand merge and split are not raised here because the design consultation's second round already answers them.

*Prepared by the review session for the owner; for the authoring session to take into its register.*

---
tags:
  - backlog
aliases:
  - Syngraphē backlog
status: active
date: 2026-09-21
---

# Backlog — Syngraphē

Ideas worth keeping that are not in the current scope. An entry earns a place by being something a future session would otherwise re-derive; it leaves by becoming an epic, a decision, or an explicit rejection.

## B-001 — Work items derived from the generated views

**Idea.** The generated views — contradictions, ambiguities, blind spots, the role and control directories — are read to decide what to edit next. That makes them a natural source for a work-item feed: each unresolved finding becomes a task with an owner, a state and a link back to the passage.

**Why it is parked.** A task manager opens its own question space — assignment, states, notification, due dates, its relationship to the roles already defined, whether it is per document or per tenant. None of it is needed to prove the authoring cycle, and opening it now would fork the architecture discussion.

**What has to be true before it is taken up.** The generated views exist and are in real use (stage 2, DL-0043), and someone has been observed working from one by hand. The manual step is the specification.

**Constraint it must respect.** ASR-09 — a generated view is derived and never a source of text. A work item may *point at* a finding; it may not become the place the finding is edited.

## B-008 — English interface

The platform launches in Ukrainian; an English translation may follow (DL-0061). Nothing about it is designed now. The only thing held from the start is the invariant that interface strings live outside the code (ASR-10), which is cheap to keep and expensive to retrofit.

## B-015 — Stale cross-reference detection

An author writes *"as defined in clause 4.2"* in the text. Somebody later inserts a section above it and the number is wrong, silently.

**Why it is a heuristic and not markup** (DL-0127). An author types the reference as plain text on day one, before any feature exists, so a markup mechanism would only ever catch references created after it shipped. A heuristic catches every one of them, including those written years earlier: *"this passage cites section 4.2 as being about asset disposal; section 4.2 is now about inventory."*

**What has to be true first.** The agents exist (stage 2), and somebody has been observed correcting a stale reference by hand — the manual step is the specification.

## B-014 — Acceptance granularity

Stage 1 accepts a whole run over a whole document (DL-0090). A reviewer may later want to accept some sections and leave others pending. **Trigger: the first time a reviewer delays a run because of one author's part.** This is about what an acceptor **chooses** to accept, not about who owns a section — section ownership was dropped entirely (DL-0091) and is not coming back with it. Needs a rule for what the accepted baseline means when it is no longer a single version.

## B-013 — Comments and the annotation surface

Deferred at DL-0083. Threads anchored to passages, nested replies, resolution that hides but keeps the record — a surface rather than a right, and the reason it left stage 1. The anchoring decision stands (DL-0027): W3C text-quote selectors against the sentence-per-line source, nothing written into the document text.

## B-010 — Disputes, the Statement of Disagreements and the decider

**Taken up as [EP-0002](enhancements/EP-0002-disagreements-and-their-resolution.md).** Deferred at DL-0076; in stage 1 a disagreement is settled by the people involved, outside the platform.

## B-011 — Agent-workflow questions parked at DL-0081

Everything the agent half raises beyond what stage 1 needs: which heuristics ship seeded, how a review scope is proposed rather than chosen by hand, how standing lists are triaged, how document ADRs are drafted, how findings are re-run when a neighbouring document changes. Each is answerable and none is needed to build an editor.

## B-012 — Tenant-wide entity registry

Stage 1 declares entities per document (DL-0073). A role that appears in six policies is six declarations, and keeping them consistent is manual. A tenant-wide registry is the fix, and it is worth building once there are six policies rather than before.

## B-002 — Automatic review of connected documents

Deferred at DL-0018. Detection of cross-document conflict is in scope; notifying the other document's owners when this one changes needs a maintained dependency graph.

## B-003 — Generated views at repository scope

Deferred at DL-0044. Two policies can regulate the same role, so the role directory is more useful across the corpus than within one document. Needs the dependency graph of B-002 — **and a home**: with one repository per document (DL-0111) a cross-document view has no repository to live in, so it needs a per-tenant derived store.

## B-004 — Style linting

Deferred at DL-0004's successor. The sense-versus-style hunk split exists from the start; mechanical enforcement of the style half comes later.

## B-005 — Tenant-authored heuristics

Deferred at DL-0049. Tenants attach composed actions and side-document types; authoring the heuristics underneath stays with the platform administrator until a tenant asks.

## B-006 — MS Word import

The real accounting policy arrives once the platform is ready (DL-0002). Cheaper than it was — Markdown makes pandoc the import path as well as the export one.

## B-007 — MCP server for external agents

An external agent connects as a user and inherits exactly that user's rights. Cheap now that identity is Django's, but it is not needed to prove the cycle.

**What it may show is what the browser shows.** An MCP client authenticates as a user and reaches exactly the information that user reaches in the web interface, through the same rights — never a finer level of detail. Mutating and analysis operations over MCP are not designed yet.

## B-009 — Per-tenant email sending domains

**Taken up in release 0.1 (DL-0202):** a tenant may configure one sending address of its own; without one, its mail goes from the platform address.

## B-016 — Operator guide for the people who use it daily

**Idea.** A guide for the colleagues who will edit, review and approve in the platform, derived from the stories, the help pages and the interface rather than written from nothing — who the reader is, what they may reach, what to keep and what to drop, and an audit that every step can be reached from their own screen.

**Why it is parked.** Written before the cycle works end to end it would describe an intended interface, and every later story would make it wrong.

**What has to be true before it is taken up.** **The review cycle works end to end**: take, edit, send for review, correct, accept, freeze and approve, on the development host.

## B-017 — Data retention and erasure procedure

**Idea.** The procedure that turns the data model's erasure shape into something an administrator can carry out: who may ask, who decides, what is cleared — the tombstone keeps the identifier and clears name and address (DL-0108) — what is kept and for how long, how an export already made is treated, and how the request is recorded.

**Why it is parked.** The mechanism exists in the data model; the procedure that uses it is operational and needs no code until real people's data is held.

**What has to be true before it is taken up.** **Before the first real document is loaded.** A real document brings real authors, and an erasure request arriving before the procedure exists would be answered by improvisation.

## B-018 — Accessibility position

**Idea.** One paragraph stating what the platform commits to for users with disabilities — which standard it measures against, at what level, and what is out of reach for now — so the interface is built towards a stated target rather than reviewed against one afterwards.

**Why it is parked.** Nothing is lost by writing it once the interface has shape, and the editor library chosen in Epic 1 decides much of what is achievable inside the editing surface.

**What has to be true before it is taken up.** **Before the interface is considered complete** — at the latest, before the release's last QA pass.

## B-019 — HTML mockups from the page wireframes

**Taken up:** the interface is drawn in [`interface/mockup.html`](interface/mockup.html), described region by region in [`interface/pages.md`](interface/pages.md). Still to come: the reviewer's pages and the tenant administration pages in detail, a user profile page, visual style, and a mobile layout.

## B-020 — Comments in an export

**Idea.** An option to carry a document's comment threads into a DOCX or PDF export, embedded beside the passages they are anchored to.

**Why it is parked.** Release 0.1 has no comments (B-013), and exports carry text, generated title pages and attachment lists only (DL-0172).

**What has to be true before it is taken up.** Comments exist, and a reader outside the platform has asked for the discussion along with the text.

## B-021 — Per-document rights for a group

**Idea.** A group's rights set per document — the same group an editor of one document and a reader of another — instead of a group carrying one set of roles across the organisation.

**Why it is parked.** Roles held by the group keep the permission model small enough to audit by reading it; per-document rights multiply the rows an administrator has to reason about.

**What has to be true before it is taken up.** An organisation has been observed creating near-duplicate groups only to vary one role between documents.

## B-022 — Deleting a user

**Idea.** A designed path for removing a person from the platform, for the person themselves and for an administrator, beyond blocking.

**Why it is parked.** A person's identifier is referenced by every version, acceptance and access change they took part in, and the record has to keep answering who did what. Blocking stops access without touching that record.

**What has to be true before it is taken up.** The retention and erasure procedure (B-017) exists, since deletion is one of the cases it has to cover.

## B-023 — Visibility per appendix and attachment

**Idea.** Letting a group see a document without some of its appendices or attachments — a confidential annex, a template meant only for its editors.

**Why it is parked.** In 0.1 whoever may view a document sees all of its parts; the parts are approved together and read together (ADR-0005), and a per-part rule would split both.

**What has to be true before it is taken up.** An organisation has been observed keeping material out of a document only because some of its readers must not see it.

## B-024 — An auditor

**Idea.** A read-only role that sees documents, their whole history and the operations log, over a scope set when the role is granted — one folder, one organisation, or the platform — and can never change anything.

**Why it is parked.** In 0.1 the administrators are the only readers of the operations log, and no one outside the organisation audits it yet.

**What has to be true before it is taken up.** An audit is requested by someone who is not an administrator.

## B-025 — Private working rounds during a freeze

**Idea.** While a document is frozen and its reviewer is working through what the approver asked, the intermediate commits (`1.3-1`, `1.3-2`) are hidden from everyone else; after the freeze ends, other readers see only the step from `1.3` to `1.4`.

**Why it is parked.** In 0.1 everyone who may see pending edits sees every commit (DL-0189); hiding some would add a visibility rule to the history.

**What has to be true before it is taken up.** A reviewer has been observed avoiding the platform for a round with the approver because the intermediate work would be visible.

## B-026 — Hiding who acted in a document's history

**Idea.** A setting that hides the person behind each event in a document's history — edit, acceptance, freeze, canonisation — from readers who do not need to know it.

**Why it is parked.** In 0.1 every history entry names who acted, and attribution is part of what the platform promises (ASR-18).

**What has to be true before it is taken up.** An organisation asks for readers to see what changed without seeing who changed it.

## B-027 — Receiving email

**Idea.** Incoming mail — replies to notifications, documents sent in by email — read from a mailbox the tenant configures.

**Why it is parked.** The platform only sends mail (DL-0202); nothing yet needs to read it.

**What has to be true before it is taken up.** A workflow that starts from an incoming message.

## B-028 — Notification levels

**Idea.** Each person chooses which events notify them, in the application and by email.

**Why it is parked.** In 0.1 everyone receives the events that concern them (DL-0204); choosing among them needs a view of what people actually find noisy.

**What has to be true before it is taken up.** Someone has been observed ignoring a class of notifications.

## B-029 — A read-and-act workflow for notifications

**Idea.** Notifications that stay open until acted on — dismissed, snoozed, assigned — rather than read by opening.

**Why it is parked.** In 0.1 opening a notification marks it read (DL-0204).

**What has to be true before it is taken up.** An administrator has lost track of an event they had opened but not dealt with.

## B-030 — A name for a version

**Idea.** Raised while designing reservations (ADR-0009). Beside a version's number, a short name its users give it to mark a milestone — for example, a synthetic *draft for the board*, next to *2.4* — shown wherever the number is shown and searchable in the history.

**Why it is parked.** In 0.1 a version is identified by its number alone (DL-0183, DL-0198); a name raises who may set and change it, whether an edition's name is fixed once canonical, and how it appears in exports.

**What has to be true before it is taken up.** People are observed referring to versions by something other than their number.

## B-031 — Attempts and failure of model jobs

**Idea.** Decide, for the model steps that run as queued jobs from release 0.2, how many attempts each gets, when they happen, and what happens when the last one fails — who is told, and what the person waiting for the result can do.

**Why it is parked.** No model job exists before 0.2, and the answer depends on how the jobs behave against a real provider — its failures, its limits, its cost per repeat. Settling it now would plan a known unknown.

**What has to be true before it is taken up.** The 0.2 agent runs are being designed (DL-0120).

## B-032 — A source view with line numbers

**Idea.** Raised in the editor spike (ADR-0010). The Markdown source view as a code-editor component — CodeMirror 6 is MIT and mounts without a framework — rather than a plain text field, so it can show line numbers and mark the lines a refused paste names.

**Why it is parked.** A plain text field meets DL-0171: a refusal names the offending lines in its message. A second editor library adds weight to the one client island (ADR-0004) for a convenience nobody has yet asked for.

**What has to be true before it is taken up.** Users find the lines a refusal names hard to locate in the source view, or the source view needs features a text field cannot give.

## B-033 — Lifting a self-blocked account

**Idea.** A control, and a story, for lifting the block a person puts on their own account (ST-0066). ADR-0007 already gives the power to a platform administrator; the owner has also raised letting a tenant administrator lift it for their own organisation, which needs a self-block held per membership rather than one flag on the person, and so a change to ADR-0007 and the data model.

**Why it is parked.** Release 0.1 leaves the interface without it; until then the database is the recovery path, as it is for the last platform administrator. Who may lift it is decided when the entry is taken up.

**What has to be true before it is taken up.** A self-blocked person asks to come back.

## B-034 — Editing a language's abbreviation lists in the platform administration

The sentence splitter's two abbreviation lists per language (ADR-0012) are rows in `LANGUAGE`, seeded from the repository. In release 0.1 a list is changed in the repository and re-seeded, or as a hotfix on the row with the same divergence rule as a prompt (`technical-design.md § Prompts are source`); no page in the platform administration edits them. The page is designed when a list edit is first needed on a running installation — the trigger is the first wrong boundary reported from a real document that a list edit corrects. Constraint: an edit applies only to text edited afterwards; a stored line is never re-normalised (DL-0112).

## B-035 — Restoring platform administration when no other administrator can lift a block

**Idea.** A platform administrator who blocked their own account holds no right until another platform administrator lifts the block (DL-0308). Where no other platform administrator exists, a token generated from the command line — the same shape as the first run's (DL-0231) — restores the role to that account.

**Why it is parked.** Release 0.1 has no control for lifting a block a person puts on their own account (B-033); until then the database is the recovery path.

**What has to be true before it is taken up.** B-033 is taken up, or a platform administrator's account is lost with no other administrator to lift its block — tombstoned, or blocked outside the platform (the last one's own block is refused, DL-0315).

## B-036 — Choosing whether to appear by name

**Idea.** A person chooses whether pages show their name beside their changes — *show author*, a correction notice, a run's versions — or show them as an *anonymous editor*; the choice is a switch in their profile, and a display name becomes a required field of at least one character.

**Why it is parked.** Until the switch exists, a person without a display name already reads as *anonymous editor* to everyone (DL-0339); nothing requires the name yet.

**What has to be true before it is taken up.** The user profile is designed; the organisations using the platform say whether an anonymous author is acceptable in their records, since the audit trail keeps the identifier either way (DL-0108).

## B-037 — The render worker's own credentials

**Idea.** The `render` service has no route off its network (ADR-0013), but it holds what every application process holds: the database role the stack was initialised with, the secret key and the whole broker. A flaw in a layout engine parsing a document could leave through those rather than through the network — a query run inside the database, a task put on another worker's queue. Give `render` a database role of its own that reads the tables an export reads and writes only the export's row, a broker user limited to its own queue and results, and no secret key.

**Why it is parked.** The text a renderer parses is escaped and its images are read as their descriptions, so the path needs a flaw in a native parser first; the split touches the backup design, which uses the stack's role, and the configuration reader, which requires the secret key of every process.

**What has to be true before it is taken up.** Before the first production deploy.

## B-038 — A page about the document, or a passport exported beside it

**Idea.** An export carries no page header (DL-0362). What a header used to repeat on every page — the title, the version, the stance — and more of the document's record (who approved it, when, its editions) could stand once: on a last page of information about the document, or in a separate passport document exported together with it.

**Why it is parked.** The file's name says which version and stance a file holds, and the title page where a document has one — off by default, and naming the edition rather than the exported version; nothing in release 0.1 needs more yet.

**What has to be true before it is taken up.** Readers of printed or exported documents ask which version a loose page belongs to, or what stands behind an approval.

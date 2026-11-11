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

The invariant held from the start: interface strings live outside the code (ASR-10), which is cheap to keep and expensive to retrofit.

**Taken up for release 0.1 (DL-0498):** each person chooses Ukrainian or English for the interface on their account page; the installation's language stays the default.

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

Deferred at DL-0004, superseded by DL-0046. The sense-versus-style hunk split exists from the start; mechanical enforcement of the style half comes later.

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

**What has to be true before it is taken up.** **The review cycle works end to end**: take, edit, send for review, correct, accept and approve, on the development host.

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

**Idea.** A person chooses whether pages show their name beside their changes — *Show edit authors*, a correction notice, a run's versions — or show them as an *anonymous editor*; the choice is a switch in their profile, and a display name becomes a required field of at least one character.

**Why it is parked.** Until the switch exists, a person without a display name already reads as *anonymous editor* to everyone (DL-0339); nothing requires the name yet.

**What has to be true before it is taken up.** The user profile is designed; the organisations using the platform say whether an anonymous author is acceptable in their records, since the audit trail keeps the identifier either way (DL-0108).

## B-037 — The render worker's own credentials

**Idea.** The `render` service has no route off its network (ADR-0013), but it holds what every application process holds: the database role the stack was initialised with, the secret key and the whole broker. A flaw in a layout engine parsing a document could leave through those rather than through the network — a query run inside the database, a task put on another worker's queue. Give `render` a database role of its own that reads the tables an export reads and writes only the export's row, a broker user limited to its own queue and results, and no secret key.

**Why it is parked.** The text a renderer parses is escaped, and the images it is given are PNG, JPEG or GIF that passed the platform's checks and stripping (DL-0242, T-06), so the path needs a flaw in a native image decoder first; the split touches the backup design, which uses the stack's role, and the configuration reader, which requires the secret key of every process.

**What has to be true before it is taken up.** Before the first production deploy.

## B-038 — A page about the document, or a passport exported beside it

**Idea.** An export carries no page header (DL-0362). What a header used to repeat on every page — the title, the version, the stance — and more of the document's record (who approved it, when, its editions) could stand once: on a last page of information about the document, or in a separate passport document exported together with it.

**Why it is parked.** The file's name says which version and stance a file holds, and the title page where a document has one — off by default, and naming the edition rather than the exported version; nothing in release 0.1 needs more yet.

**What has to be true before it is taken up.** Readers of printed or exported documents ask which version a loose page belongs to, or what stands behind an approval.

## B-039 — A code or preformatted block in the whitelist

**Idea.** A block of text set as written — an organisation chart drawn with box characters, a command, a form laid out in columns — kept as a preformatted block rather than refused.

**Why it is parked.** The whitelist has no preformatted block, and a tree drawn with box characters was refused when a synthetic regulation was loaded; the author converted it to a nested list. Whether such a block belongs in a governed document is a product decision, and the whitelist is not opened again until marks and images are added to it.

**What has to be true before it is taken up.** A design session on the stored form decides whether a block set as written can live beside one sentence per line and DL-0133's exclusion of code blocks. The whitelist's opening for the mention span did not take it up (DL-0441).

## B-040 — A list written `- 1.` read as a numbered list

**Idea.** Authors write numbered items as `- 1. Text`, which the whitelist reads as an empty bullet and refuses; the platform could read the form as a numbered list.

**Why it is parked.** The loader met it in a synthetic document; whether the platform accepts the author's habit or names the refusal is a whitelist decision, taken with the others.

**What has to be true before it is taken up.** The whitelist is next opened.

**Done in release 0.1 (DL-0441)**, with the whitelist's opening for the mention span.

## B-041 — Telling the author that single line breaks are joined

**Idea.** Lines an author wrote one under another inside a paragraph are joined into one line — Markdown's rule, and what the one-sentence-per-line storage depends on — without a word to the author. The editor, or the loader, could say so where it happens.

**Why it is parked.** It is a notice about the whitelist's reading of a line break, and it is decided with the whitelist.

**What has to be true before it is taken up.** The whitelist is next opened.

**Done in release 0.1 (DL-0441)**, with the whitelist's opening for the mention span.

## B-042 — A leading heading number stripped on load or paste

**Idea.** A Markdown export carries heading numbers in its headings (DL-0363); loaded again or pasted back, they stay as text and gain a second number on the next export. The loader and the paste could strip a leading number equal to the heading's own.

**Why it is parked.** It is a normalizer rule on the whitelist's reading of a heading, decided with the whitelist.

**What has to be true before it is taken up.** The whitelist is next opened.

**Done in release 0.1 (DL-0441)**, with the whitelist's opening for the mention span.

## B-043 — Three controls drawn out of proportion

**Idea.** Three controls are drawn at a size that does not fit what they hold: *Create a document* in a box several lines tall beside the organisation's name; the change summary on the finishing screen a short single-line field, so the drafted summary is cut off; the freeze's reason field too narrow for its own placeholder. Each is a rule of the shell's stylesheet.

**Why it is parked.** None of them blocks an act; they are fixed together, with the look of the pages they sit on.

**What has to be true before it is taken up.** The next pass over the interface's look, before release 0.1 is accepted in Ukrainian.

## B-044 — The sending settings reaching an installation's own machines

**Idea.** An organisation's sending address, and *Send a test email*, connect to whatever server its administrator enters, and a failed test shows what answered: an organisation's administrator can probe the installation's own network from that page. Restricting an organisation's sender to public addresses, checked at every connection, and showing a fixed sentence where something other than a mail server answers, would close it.

**Why it is parked.** One organisation operates an installation in release 0.1, so its administrators are trusted with that network (DL-0391).

**What has to be true before it is taken up.** A second organisation, unrelated to the operator, on one installation.

## B-045 — Credential links through the platform's sender alone

**Idea.** Queue every email that carries a credential link — an invitation's, a reset's — in the shared outbox through the platform's sender, whatever organisation it is for, so no organisation's administrator runs the server a link to another person's account passes through (T-22). The organisation is still named in the email, and the link still opens on its domain.

**Why it is parked.** One organisation operates an installation in release 0.1, and its administrators are trusted with it (DL-0404).

**What has to be true before it is taken up.** A second organisation, unrelated to the operator, on one installation.

## B-046 — Telling a person their password changed

**Idea.** When a link — an invitation's or a reset's — sets a person's password, an email through the platform's sender tells them it changed and how to recover if it was not them.

**Why it is parked.** The controls on the link come first in release 0.1: single use, a short life, its token not kept once sent (DL-0405).

**What has to be true before it is taken up.** B-045 taken up, or a person reporting an account changed without them.

## B-047 — Moving a folder

**Idea.** An administrator moves a folder, with everything beneath it, under another folder.

**Why it is parked.** Release 0.1 moves documents between folders only (DL-0453); moving a folder changes every path beneath it, and the folder tree is presentation, so nothing yet needs it.

**What has to be true before it is taken up.** An organisation reorganises its tree and moving documents one by one is the cost it names.

## B-048 — Several stylesheets per organisation

**Idea.** An organisation keeps more than one export stylesheet — a policy look and a form look — and each document selects one.

**Why it is parked.** Release 0.1 has one stylesheet per organisation, used by every document (DL-0465); a selection needs a field the record does not have and a reviewer's view of the choice.

**What has to be true before it is taken up.** An organisation asks for two looks for two kinds of document.

## B-049 — The organisation's logo on the title page

**Idea.** The title page carries the organisation's logo as its first detail, as the interface's drawing shows.

**Why it is parked.** Release 0.1's title-page details need no file (DL-0462, DL-0467); a logo needs an upload, a store and the renderers reading it.

**What has to be true before it is taken up.** Images are uploaded and checked in documents; the upload on the template page reuses those checks.

## B-050 — Bringing a retired document type back into use

**Idea.** A retired type offers *bring back into use*, audited, so a type retired by mistake returns under its own label.

**Why it is parked.** Release 0.1 adds, renames, retires and deletes types (DL-0235); labels stay unique with retired ones included, so a type retired by mistake cannot be added again under its label until this exists.

**What has to be true before it is taken up.** An organisation retires a type it still needs.

## B-051 — Relabelling or removing an entity from the *Mark* picker

**Idea.** The picker that declares an entity also relabels one, and removes one marked nowhere in the document.

**Why it is parked.** Release 0.1's picker picks or declares (ST-0026); the review surface already lists an entity relabelled or removed, so adding the controls later redoes nothing.

**What has to be true before it is taken up.** Authors meet entities declared with a wrong label, or left unused, often enough to ask for a way to correct them.

## B-11-001 — An export's images, or a draft's, held to a budget

**Idea.** An export reads every image it shows before any writer runs, and holds them in memory together; a draft stages images each under the upload maximum, with no cap on how many. Either the images could be read to disk in the export's scratch folder as they are found, so a worker holds one at a time, or a draft and a document could carry an image budget — a total size, named in configuration — refused at the upload that would pass it.

**Why it is parked.** Reading every image first is what lets a job fail with its reason when a draft's image is gone, which a writer's own fetch could not say; the documents the platform is built for hold few images, and no measurement yet shows an export near a worker's memory.

**What has to be true before it is taken up.** An export comes near a worker's memory limit, or a document's images together pass a size an installation names as its ceiling.


## B-052 — Pasting an image onto a selected image replaces it

**Idea.** With an image selected in the editor, pasting or dropping another image replaces it in place, as typing replaces selected text.

**Why it is parked.** Release 0.1 adds a pasted or dropped image as a paragraph of its own after the selection (DL-0232); replacing one takes deleting it first, and nothing is lost meanwhile.

**What has to be true before it is taken up.** Authors replace images often enough that the extra step is noticed.

## B-053 — *Edit* on an archived document for an administrator

**Idea.** The document page draws *Edit* by the right alone, so an administrator who holds *edit* through a group sees it on an archived document; it answers *Nothing to show here*, as every act on an archived document does (DL-0450). Draw it only where it opens, as the appendix page already does.

**Why it is parked.** Nothing is written or lost: the act refuses, and the archived tag says why; the mismatch is the page's, between a right and a state.

**What has to be true before it is taken up.** An administrator reports meeting the dead act, or the document page's acts are next changed.

**Taken up (DL-0518):** *Редагувати* is not drawn on an archived document, which is read-only to everyone (DL-0450).

## B-054 — The parts' screens laid out evenly

**Idea.** Six small layout faults seen walking the parts: the parts panel's two headings drawn at different sizes, and an attachment's title in heading type, larger than an appendix's; the editor's toolbar running past the centre column in an appendix's editor; a panel act taken from an appendix's page returning to the document's editor rather than the appendix; the finishing screen's part rows in number order rather than the list's order after a move, its summary field too narrow for the summary it drafts, and its *new* and *open* links in different columns; the reading view's panel bulleting appendices and not attachments; the compare page's appendix pickers wrapping in the panel.

**Why it is parked.** Each one reads; none blocks an act or hides one, and every act was walked through them.

**What has to be true before it is taken up.** The parts' screens are next changed, or a person reports one of them in use.

## B-055 — The editor on texts of extreme shape

**Idea.** Measure opening the editor on texts whose shape costs it most, and bring each within a budget: 30,000 one-line list items — 210 KB, under ASR-23's 300 KB but some six hundred pages against its hundred — take about 16 s to open as the whole document's editor on a developer's machine, against about 0.8 s for the forty-page corpus of 254 KB; a single paragraph near 300 KB, a table of many rows and a list nested to the editor's depth are the other shapes to measure.

**Why it is parked.** ASR-21 promises its times at forty pages, and the measured list lies beyond ASR-23's envelope by its length, where no promise is made without revising ASR-23 first (DL-0484); every document expected in the first release is far smaller.

**What has to be true before it is taken up.** A document near the limit is held by an organisation, or an editor reports a wait opening the editor on a long document.

## B-056 — Edit authors on the compare page

**Idea.** The *Show edit authors* checkbox on the page comparing two versions of a document: each line of the newer version named by whoever last wrote it, from the same on-demand rows as the historical page (DL-0266), so a reader stepping across several edits by several people sees whose each change is. A line edited twice inside the range names the later editor; a removed line names nobody.

**Why it is parked.** The review page already names the authors of the run awaiting acceptance, and the historical page those of any version a reader opens; the comparison across a longer range is a use nobody has yet asked for in practice.

**What has to be true before it is taken up.** A reviewer or an administrator asks who made the changes between two editions, and stepping through the historical pages does not answer it.

**Taken up in release 0.1 (DL-0528):** a comparison of two versions carries *Show edit authors*, the names worked out on request for spans of up to a hundred versions.

## B-057 — No invisible format character in a title or an entity's label

**Idea.** DL-0490 applied: a document's title, an appendix's and an attachment's title, and an entity's label refuse every format character but the two joiners, as a reason and the title-page text do (DL-0483) — the marks that reorder text with them.

**Why it is parked.** Decided after release 0.1's stories were built; a title or a label carrying such a character has to be typed or pasted on purpose, and its reviewer sees the title in every list.

**What has to be true before it is taken up.** The next epic that changes a document's details, its parts or the entity picker takes it as a story; or a title is found displaying otherwise than it is stored.

## B-058 — An earlier version holding a reordering mark, exported

**Idea.** A version stored before the marks that reorder text were refused (DL-0486) is exported with each such mark shown visibly, rather than refused by the export's check.

**Why it is parked.** Every export now passes the same check as new text, so a stored version holding a reordering mark can no longer be exported; until real documents are stored, none is expected to hold one.

**What has to be true before it is taken up.** A stored version is found holding a reordering mark.

## B-059 — Content-policy violations reported by the browser

**Idea.** The content policy (DL-0493) names a route of the platform to which a reader's browser reports each violation, so a page the policy breaks in a browser no test opened is seen by an operator rather than met by its reader.

**Why it is parked.** The route parses whatever any client sends and needs a home for what it receives — a new surface with a security reader of its own — while the browser tests and the walks already exercise every page under the policy.

**What has to be true before it is taken up.** A page is found broken by the policy in a reader's browser, or the policy is to be tightened and its effect on real browsers measured first.

## B-060 — A person's page, opened from their name

**Idea.** A page of each person that the people of their organisations may open — their display name and what need to know allows beside it — with the display name, wherever a page draws it, a link to that page. Two members who share a name are then told apart by their pages, and the refusal of an identical name (DL-0523, DL-0537) can be revisited.

**Why it is parked.** Release 0.1 names people by a display name alone and keeps names unique within each organisation instead (DL-0538); a person's page is part of the profile that stays a later design (DL-0499).

**What has to be true before it is taken up.** The user profile is designed, or an organisation finds the refusal of a name its member really bears a burden.

## B-061 — What a platform administrator sees of an organisation's own controls

**Idea.** Settle whether a platform administrator who does not administer an organisation is shown that organisation's administrator controls on a document page — *More*, and *Groups* beneath it — and draw the rule from what the role's other pages show.

**Why it is parked.** Release 0.1 has one platform administrator, who also administers the organisation, so the two cases cannot be told apart in use, and the walk that met the question could not observe either.

**What has to be true before it is taken up.** A second platform administrator exists, or one who does not administer an organisation opens its documents.

## B-062 — The editor's outline following the text

**Idea.** The outline beside the editor follows edits as they are made: a heading added, renamed or turned into a paragraph changes its entry at once, not at the next opening.

**Why it is parked.** The outline is drawn when the edit tab opens; it is a navigation aid, and a person who changes headings sees it right again on reopening.

**What has to be true before it is taken up.** A person is seen relying on an outline that has fallen out of date with the text they are editing.

## B-063 — A hole in the archive, found before recovery

**Idea.** Before a restore, list the archive's segment names in the store and report a segment missing between two that are present, with the moment the continuous range ends, so the plan names the hole instead of PostgreSQL stopping at it (DL-0545).

**Why it is parked.** `pgbackrest verify` does not report such a hole; recovery stops at it and the restore runs again to the end of the archive (DL-0314), and a full base backup taken at once after a store outage starts the archive again beyond it.

**What has to be true before it is taken up.** A restore meets a hole the operator did not expect, or an archive is found with a hole older than the newest base backup that a restore to a point before that backup would need.

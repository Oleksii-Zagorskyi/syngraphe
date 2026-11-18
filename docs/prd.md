---
tags:
  - prd
aliases:
  - Syngraphē PRD
status: active
date: 2026-09-21
---

# PRD — Syngraphē

## Goal

An enterprise collaborative authoring platform where teams of human and AI editors create, review, approve and maintain authoritative documents. One cycle, end to end: **edit → commit → review → accept → edition → canonical → read and export.** Git is the substrate and is invisible; the interface has its own vocabulary, in Ukrainian and in English, each person choosing which they see (DL-0498).

## Target users

Staff of a tenant organisation revising the tenant's own authoritative documents — enterprise policies and technical instructions first, later marketing material, decision records and contracts. Nobody is expected to know git.

## What a document is

**A body, its appendices and its attachments**, in one repository of its own (DL-0165, DL-0166). `document.md` carries the title, the language and the list of parts in its frontmatter, and the main text as its body. **Appendices** are texts of the same kind, reviewed, accepted and frozen with the body. **Attachments** are files the platform keeps and never opens — a form, a spreadsheet template — each with a title and every change to it reviewed. Beside them sit the entity definitions, the images, and a **passport** recording review and approval decisions (DL-0041).

A new document starts from the organisation's **template** (DL-0169). An optional **title page** is generated at export from the document's metadata and is never typed (DL-0164).

**A section is a heading.** Structure is the heading hierarchy, and restructuring a document is editing its text.

Concretely (DL-0046):

```
tenant-N/document-M/          # repository root, one per document (DL-0111, ADR-0008)
├── document.md       # frontmatter: title, language, parts · body: the main text
├── appendices/       # one Markdown file per appendix
├── attachments/      # one opaque file per attachment
├── entities.yaml     # role, action and term definitions
├── images/           # uploaded binary assets the text embeds
├── analysis/         # reserved; release 0.2 commits no analysis (DL-0567)
└── passport.md       # review and approval decisions (DL-0041)
```

The stored form is a constrained **Markdown** subset. Entities are marked with attributed spans — `[CMO]{.role #cmo}` — never backticks, which mean *code* to every parser and export path; the editor never shows the syntax. Heading numbers are a render rule derived from depth, never stored, so moving a section renumbers everything and breaks nothing.

## Roles

Named by the action performed, never by corporate title (DL-0017). A person holds a role through the groups they belong to (ADR-0007).

| Role | Stance | Scope |
|---|---|---|
| reader | reads | canonical documents |
| editor | edits, commits; with *reserve for editing*, keeps a document for weeks | whole document |
| reviewer | accepts changes; edits, and corrects before accepting, including their own (ADR-0016) | whole document |
| decider *(later — EP-0002)* | rules on Statement entries, choosing the surviving wording | document |
| approver | makes an accepted document canonical, frozen or not (DL-0515) | document |
| pending edits viewer | sees committed, unaccepted changes | whole document |
| tenant administrator | users, document sets, role assignments, the document template and its title page layout, the organisation's stylesheet (DL-0169, DL-0230, DL-0462, DL-0464); from release 0.2, which companion actions and side-document types each document carries, and the organisation's default set of them, which a new document receives and which is applied to chosen existing documents in one act (DL-0565) — never the heuristics beneath them (DL-0049) | tenant |
| platform administrator | the platform; from release 0.2, the heuristic catalogue as loaded from `prompts/` — read, a heuristic switched off at need, never edited in place (DL-0567) | platform |

Board approval is recorded by one designated person; quorum and voting happen outside the software (DL-0017).

From stage 2, two AI actors, not roles a person holds. The **companion** runs actions for the holder of the draft and nobody else (DL-0571 (8)), is edit-scoped, and reads the document being edited and no other (DL-0567). The **reviewer agent** runs when a document is sent for review; in release 0.2 its analysis holds findings from the document alone and from the neighbours the reviewer put in scope — each itself a document assigned an analysis (DL-0571 (1)) — and the run's authors see it on the document's review state as soon as it is computed, each finding filtered by what its reader may read — there is no release act (DL-0568, DL-0021). *Later, with the confidential guidance (backlog B-079):* the reviewer agent produces two artefacts from **two separate runs** — a reviewer-eyes-only analysis from a run that reads the guidance, and an editor-facing analysis from a run whose context never contains it (DL-0007, DL-0095).

**Access is data** (DL-0051). Groups, their rights, their members and their links to documents are rows with a full change history carrying timestamp and actor (ADR-0007); only a tenant or platform administrator may edit them. Confidential guidance is **an ordinary document with restricted rows** — authored, edited and reviewed like any other — not a separate mechanism.

## Editing is linear

One editing sequence per document. No branches, no forks, no merges, and therefore no conflicts (ADR-0003).

1. An editor **takes the document** for editing. Nobody else edits it meanwhile. *Edit* opens the whole document in the editor at once — there is no section editor (DL-0517) — and the editor writes into the one draft. Formatted text is the default; a Markdown source view is always available.
2. Edits are **captured continuously** — there is no Save control. The draft persists so a closed laptop loses nothing; it is not yet a version and nobody else can see it.
3. **Undo** works within the editing session.
4. From release 0.2, at any point the holder of the draft may **call companion actions** (DL-0571 (8)) — individually, not all of them — to answer *"what do my changes introduce so far?"*. Results are cached against the content, so asking twice about unchanged text costs nothing. An action asked while the editor is open first captures what is typed, as *finish editing* does, and runs on it (DL-0569).
5. **There is no Save button.** In its place is *finish editing*. Pressing it shows the holder's changes, the part operations and the change summary, which starts from a mechanical draft naming the sections touched (DL-0261) — the companion analyses join them in release 0.2 — and its choices: **continue editing**, **send for review** — or, for a holder of *accept*, **accept as N.M** and **create version N.M-X** — and **discard my edits**, which asks for confirmation and throws the whole draft away — from release 0.2, the text a companion action read stays in the operator's traces (ADR-0024).
6. **Send for review commits** (DL-0054). From release 0.2, the version records which analyses travelled with it; the analyses themselves stay in the platform and are never committed, so one marked *not right* can be hidden from every view (DL-0567). The run's reviewers and authors read them on the review page (DL-0571 (4)).
7. Versions accumulate, attributed, until a reviewer accepts a run of them.

Going back is only ever forward: an unwanted change in the pending run is undone by a reviewer — one version, or all of one author's — into the reviewer's draft, and committed as the reviewer's version; sentences a later version changed are left for the reviewer to edit (ADR-0015). History is never erased.

An ordinary **hold is released after a period without activity**, once its holder has been asked whether they are still working, and can be released by the tenant administrator; the interrupted draft is kept, not discarded (ADR-0006). Everyone who may read the document sees that it is held; holders of *edit* or *accept* on it, and administrators, see by whom, for every hold (DL-0516). Holds cover the whole document — there is no smaller unit (DL-0091).

**A holder may reserve the document for editing** to mature it over days or weeks (ADR-0009): the reservation is the same hold without the inactivity release, taken by a member of a group holding *reserve for editing*, and ended by finishing, discarding, cancelling, or an administrator breaking the glass with a stated reason. As for any hold, the document cannot be frozen or re-linked meanwhile, and a reservation also keeps others from reviewing it; readers see that it is reserved and since when, and holders of *edit* or *accept* on it, and administrators, see by whom. When to end it is agreed between people, outside the platform. A holder who also holds *accept* finishes in one act — *accept as N.M* — or leaves the version pending — *create version N.M-X*; for a document accepted at 2.3, *accept as 2.4* and *create version 2.3-1* (DL-0222).

## Rights and administration

Three application roles (DL-0079). A **platform administrator** does everything a tenant administrator can, in every tenant, and creates tenants, blocks them and grants platform administration. A **tenant administrator** invites users by email, blocks them in tenants they administer, manages groups and links them to documents, manages folders, archives and restores documents, and from stage 2 assigns side-document types and companion actions (ADR-0007). A **user** does what the rights of their groups allow — creating documents included, through *create and edit*. The list is indicative rather than exhaustive — ordinary surfaces such as editing one's own profile are not enumerated and are not thereby forbidden.

**Rights are held by groups, and groups are linked to documents** (ADR-0007); a person holds the union of the rights of their groups linked to a document. The rights: a viewing ladder — view canonical, view accepted, view pending, edit, create and edit; history — view previous canonical versions, view all history; acts — accept, freeze and unfreeze, and reserve for editing, each including edit (ADR-0016), and make canonical, with the accepted view (DL-0234); and rights over appendices and attachments. A new or copied document reaches only its author until the tenant administrator links groups. In this release both administrators read every document in their scope; separating administering from reading is EP-0001. Comment is deferred with the rest of the annotation surface (backlog B-013, DL-0083).

**There are no section-scoped roles and no code owners** (DL-0091). A right is held over a document or not at all.

**No segregation of duties is enforced by default** (DL-0092). A reviewer may edit and then accept their own work. The control is the record rather than the prevention: every version is attributed, authorship is visible, and the audit history answers who did what (ASR-18).

**One optional check, per tenant, off by default** (DL-0101, DL-0115): an edition cannot be approved by anyone who accepted a run since the previous canonical edition. One comparison at the single transition where text becomes authoritative — enough to give a tenant a second pair of eyes to show an auditor, without slowing everyday editing.

**A new document starts author-only until the first linked group: its creator holds edit, and of the part rights only upload and replace attachment** (ADR-0007, DL-0445): the creator can carry the document's forms from its first draft, while creating and deleting its parts wait for a linked group's rights. The tenant administrator is notified that it was created and grants the rest. Until a reviewer exists the document reads *no reviewer assigned*, and acceptance is blocked with that stated reason rather than silently.

**Archiving** is visible to administrators only (DL-0084). An archived document's links stop resolving anywhere, including where its name appears in another document's prose; its group links stay, are listed and can be changed by an administrator while it is archived, and apply as they then stand on restore (DL-0548).

**Cross-tenant, nothing.** No links, no analyses, no searches. A user with several memberships switches tenant; a user with one sees the tenant name and no switcher. A tenant administrator adding a user by email learns nothing about that user's existence elsewhere (ASR-17).

**Every change is attributable and authorisation is reconstructible** (DL-0082, ASR-18). Every row carries who created it and whether the actor was a person, the system, or an agent; membership and access changes carry typed append-only history, so *who could read this document on the day that edition was approved* is a query rather than an inference.

## Notifications

**No notification carries document text** (DL-0113) — in the application or by email. Email carries the event and a link; a correction notice renders the two wordings from the document, under the reader's current rights.

Three surfaces (DL-0070). A **notifications section** in the application; **email** for the same events, sent from the tenant's own address or the platform's (DL-0202); and the **document list**, which shows each document's current state — so a reviewer seeing *pending edits* decides whether to review now or wait for more to arrive. The list is the quiet one and probably the most used: it turns notification from a stream of events into a standing picture of what is waiting.

## Types, folders and links

**Document types** are each tenant's own list, maintained by its tenant administrator — a new tenant starts with one type, *document* — assigned per document and used as filters in the document list (DL-0057, DL-0235). A document needs no relatives: a technical instruction about changing a serial number in the ERP stands alone.

Worth keeping apart: a **controls document** is authored, with its own editing and review pipeline; the controls **view** generated from a policy only reports what that policy already says. Same subject, different artefacts.

**Folders exist in the interface, not in storage.** Each document is its own repository, `tenant-N/document-M/`, in a flat directory under its tenant (DL-0111, ADR-0008); the interface shows folders with unlimited nesting, held as metadata (DL-0058). Moving a document changes nothing on disk, breaks no link, and orphans no history.

**Links.** A mention of another document becomes a link **when the reader may access it**, and renders as plain text otherwise — a link is never allowed to disclose that a document exists (DL-0060, ASR-16). Each document carries an auto-generated **see also** listing what it links to, filtered the same way. Together with types and folders, this is what makes the document set a wiki: everything in one place, browsable and cross-linked.

**Numbering and navigation.** Clauses — each paragraph of text — are numbered within their section: `1.1-3` is section 1, subsection 1, clause 3; `4.3.2-6` is section 4, subsection 3, subsection 2, clause 6 — with the hyphen separating the heading path from the clause index. Each appendix numbers its own headings from 1. Heading depth is capped at four. Numbers are derived at render, never stored, and appear in the PDF, the DOCX and the reading view; a heading carries its number in the heading, and clause numbers sit in a non-editable gutter beside the text, the editor included (DL-0065, DL-0363); the Markdown export numbers its headings only. Every document also carries an **outline** of its sections and subsections as navigation links.

**Images** live in the document's `images/` folder. A changed image is flagged in review and shown before-and-after, because a text diff cannot show it and a reviewer must not accept a change they could not see (DL-0059). **Attachments** are reviewed the same way: every one added, replaced or removed is listed with its title, each version downloadable, and the reviewer may revert the change (DL-0168).

**Changes read like tracked changes** — marked word by word inside the formatted text, not as source lines (DL-0170).

## Stances

English names are canonical; every translation, the Ukrainian interface names included, is in [`glossary.md`](glossary.md) (DL-0047, DL-0176).

| Stance | Shows |
| --- | --- |
| **Canonical version** | the last edition approved as authoritative |
| **Accepted edits** | the last revision a reviewer accepted |
| **Pending edits** | everything committed since, attributed and unaccepted |
| **My edits** | the holder's own uncommitted session |
| **My edits in review** | what the editor has sent — not drawn in release 0.1 (DL-0549) |

**Four of the five are *edits*, not document states.** The user is not switching between five documents; there is one document and a filter over which layers of edits are shown, with authorship toggled on top. That is how the tool being replaced works, and the interface follows it rather than the substrate.

**Authorship is visible to everyone**, behind a *Show edit authors* checkbox so a diff can be read without it; ticked, it names each changed paragraph's author in the margin beside it (DL-0040, DL-0504). A **time machine** steps through versions with a visual boundary between accepted history and pending edits.

## Acceptance

The reviewer reads the difference between the **last accepted revision** and the current one — with an agent's analysis of it from release 0.2. Accepting makes the current revision the new accepted baseline, and is recorded as a commit to the document's **passport** — so an acceptance always leaves a trace even when no text changes (DL-0041).

Where the reviewer wants corrections, they edit: a correction is a version of the run, committed with *accept as* or left pending with *create version* (DL-0222), or an undo applied to the reviewer's draft (ADR-0015). The acceptance commit itself touches only the passport.

**In stage 1** the platform generates a **correction notice** at acceptance for each author whose lines of the run a version by a holder of *accept* replaced or removed, or whose appendix or attachment operation it reversed — one notice per author, listing what they wrote, what was accepted and who changed it (ADR-0014) — delivered through the notification surface. Generated rather than authored, so the reviewer has no discretion about whether the author finds out. The reviewer may instead **return the run without accepting it**, with a reason — recorded as a passport commit like an acceptance, so the decision travels with the document (DL-0114). The next send presents the whole run since the last acceptance, returned versions included.

*Later, with disputes (EP-0002, not in release 0.2 — DL-0550), at low fidelity:* the notice becomes a durable **rejection record** the editor may escalate into the **Statement of Disagreements**, settled by agreement between editor and reviewer, or by the **decider** on deadlock (DL-0026, DL-0076).

Acceptance is a **document-level act** covering the whole run since the last accepted version (DL-0090). Accepting only part of a run is a backlog refinement.

## Editions

**Making a document canonical** makes its latest accepted version the next **edition**, while nobody holds it and nothing committed since that acceptance awaits review; it needs no freeze first (DL-0515). A document is **frozen** while something outside it is resolved — an approval that takes time, a discussion with whoever approves, work elsewhere — and only its reviewers may edit it meanwhile (DL-0189). The freeze ends by making the document canonical, or by unfreezing it. Once disputes arrive (EP-0002), a document cannot be made canonical while any Statement entry is open (DL-0010, deferred with the register, DL-0076, DL-0550); until then nothing gates it but the approver and the checks above. A new editing cycle may start against a canonical document at any time.

## What the agents look for

Three levels, and only the platform administrator sees the bottom one (DL-0049).

| | What it is | Platform administrator | Tenant administrator | Editor |
|---|---|---|---|---|
| **heuristic** | one focused piece of prompt text | reads it as loaded; may switch it off at once; never edits it in place (DL-0567) | cannot see | cannot see |
| **companion action** | a set of heuristics producing a user-facing analysis | creates, edits | sees title and description; assigns to a document | calls it |
| **side-document type** | a set of heuristics producing and maintaining a generated view | creates, edits | sees title and description; assigns to a document | reads the view |

The tenant's lever is the composed action, not its ingredients. Keeping prompt text out of reach of anyone who could write to the test is the point. **No heuristic is edited in place in the platform**: a heuristic changes only through `prompts/`, its evals and the load, and the hotfix is to switch it off (DL-0567). Release 0.2 has three side-document types, one per standing list — *contradictions*, *ambiguities*, *blind spots* — and the reviewer agent runs the heuristics of what is assigned to the document (DL-0567). For every document assigned any analysis it also runs D01, and the cross-document heuristics B01, B02, B03 and B05 for each neighbour in the reviewer's scope; these belong to no action and no type (DL-0571 (2)). A heuristic switched off runs in no new call; its stored results stay readable, and an analysis already running completes (DL-0571 (15)).

The catalogue of what the heuristics look for is [`review-findings.md`](review-findings.md). Every run records the heuristics and versions it used; every finding names the heuristic that produced it.

**Release 0.2 carries the catalogue's first cut** (DL-0555, DL-0568, DL-0571): contradiction, ambiguity, a gap inside the declared scope, one term with two meanings, circular authority and an obligation nobody owns, inside the document (A01 to A06); contradiction with another document, an override of a matter another document governs, a broken outbound reference and a term collision across the base (B01, B02, B03, B05); and what the run changes in a role's obligations (D01). The conflict with the confidential guidance (C01) is later: release 0.2 sends no guidance to a model (DL-0568, backlog B-079). A citation of a superseded edition (C03) is later too: the document alone cannot tell that a cited edition is superseded (DL-0571 (3), backlog B-081). **Where a deterministic check answers a heuristic exactly, no model is called** (DL-0551); in 0.2 none does, since marking roles, actions and terms is done by hand and optional, and the model reads them from the text (ADR-0022). Each finding quotes the passages it rests on, and a quote the platform cannot find in the text withholds the finding. A finding offered with no quote is a suggestion: the reviewer agent's analysis shows suggestions in a group of their own, unsorted, and the companion shows none (DL-0571 (9)). **A heuristic ships only at its eval target** (DL-0554).

### How a user reaches an agent

Three rules (DL-0056, ASR-11, ASR-12):

- **No conversation.** A user calls predefined actions; nobody composes a prompt.
- **No repeat for unchanged content.** Once an action has answered for a content state, the same action on the same content returns the stored answer — the source has not moved, so neither has the answer. What is stored and reused is each model call, one per heuristic, keyed by its prompt version and the content it read (DL-0567). **An analysis is the set of calls made for one purpose** — a companion action on a content state, the reviewer agent's analysis of a run, a standing set of an accepted state; a call that fails fails its part, the rest is shown, and *run again* repeats the failed calls (DL-0571 (4)).
- **Keyed to content, not to a session.** An action may run mid-edit; its result is stored against a hash of the document tree, so a commit is simply one content state among others (DL-0056). The hash leaves out `passport.md` and `analysis/`, and a companion call's key also holds the draft's base commit (DL-0571 (5)). The send-for-review screen shows what was already computed rather than recomputing it.

From release 0.2, on sending for review the editor sees the analyses that will travel with the version and confirms them.

**Audience (DL-0021):** a finding reaches a recipient if and only if it is derivable from material that recipient may already read — computed per recipient, never by the prompt. A finding's sources are the documents its call read (ADR-0022); a finding whose sources cannot be established is withheld from everyone and counted as an error (DL-0571 (13)). **What leaves for the model provider is controlled by the assignment alone**: a document may be put in a review's scope as a neighbour only if it is itself assigned at least one analysis (DL-0560, DL-0571 (1)).

**Scope (DL-0032):** the companion reports only what this editor is introducing. The reviewer agent reports introduced, pre-existing, resolved and aggravated findings, separated; a finding drawn on another document is only ever introduced or pre-existing (DL-0567). Its analysis starts at *send for review* with the findings within the document and grows as the reviewer adds neighbours (DL-0571 (4)); without a standing set, findings sort by position only — introduced or pre-existing — and the analysis says so (DL-0571 (6)).

### When an analysis is not right

Each analysis carries one control, ***not right*** (DL-0554). It **informs the developer that the software got it wrong** — a signal about the analysis, never about the document's sense or a disagreement with its prose. It marks the whole analysis, never one finding: a person says whether the output is right, and judging each heuristic's work is the developer's job, done in the developer's own tooling. In release 0.2 the mark also **hides the analysis from every view, for everyone**, as a safety valve while the prompts are new; the analysis is kept where it is stored, and the mark names who set it and when. Only the hiding is temporary: the mark stays as the measure of how often real analyses are wrong, and when the hiding ends is decided from the traces.

**The control is offered only to the person an analysis was made for, while it is the current analysis for its content** (DL-0570): the editor who called a companion action; the run's reviewers — holders of *accept* — for the reviewer agent's analysis; holders of *accept* on the document for its standing lists. Nobody else sees the control, and a mark cannot be withdrawn. The standing lists take one mark per list, which hides that list for everyone until the next accepted state's list and is offered only on the current accepted state's lists (DL-0571 (7)). A mark speaks for the reader the analysis was written for; were it every reader's, anyone could silence a list for all.

### Every run is traced

Every model call is recorded against the exact prompt version it ran and that version's eval results (ADR-0024, DL-0554). A trace holds references, not the text of committed documents — each document by its repository and the commit it was read at — and keeps as text only an uncommitted draft, which has no history to point to. The output is referenced where the platform stores it. Traces are read by whoever operates the installation, from the command line on its host; no role in the web interface reads them.

## Generated views

Maintained by nobody who writes documents. Release 0.1 has two — the role directory and *see also* — which the platform derives from the version shown each time it is read (DL-0448). The rest are maintained by the agent and by nobody else (DL-0044). Two classes (DL-0063):

**Mandatory:**

- **Directory of roles** — rights and obligations per role, with links back to the sections they come from. Derived at render since release 0.1.
- **Contradictions**, **ambiguities**, **blind spots** — release 0.2. Document-wide standing lists, a working backlog editors and reviewers act against, not a per-commit report. They are **the standing findings set shown as lists**, computed once per accepted state and refreshed when that state changes, and holding only findings derived from the document alone, so every reader of the document sees the same lists (DL-0032, DL-0555). Each list is a side-document type of its own, computed only for a document it is assigned to (DL-0567); a reader sees the lists of the latest accepted state at or before the version they read, behind the *Analysis* icon, their one home (DL-0569).
- **Directory of controls** — what the document says is controlled, and how. *Not in release 0.2* (DL-0555).

**Voluntary** — generated on request; *not in release 0.2* (DL-0555). A **job description** carrying a role's rights and obligations is the example. A voluntary view may also **seed an authored document**: the platform drafts it, a human takes it over, and from then on it is an ordinary document with its own pipeline. The view stays agent-only; what is seeded is a copy under human authorship, never an edited view.

The directories can render beside the document or be embedded in an export. Scope starts per document and extends to the whole repository later, since two policies can regulate one role. For a holder of the guidance grant, each list may later carry an **addendum** computed against the confidential requirements, visible only to them — *not in release 0.2* (DL-0555).

## Document ADRs

*Not in release 0.2* (DL-0555). When a person changes the *logic* rather than the wording, a decision record is generated beside the document: who decided, when, why, and what the alternatives were (DL-0045). The agent pre-authors it; the person edits it or leaves it. One record covers one decision however many passages it touches — changing who approves a budget may rewrite fifteen of them.

## Staging

**Stage 1 — editor, diff viewer, versions, review and acceptance.** A working editor users can use the next morning.
**Stage 2 — the agents and the generated views.**
Stage 1 is release 0.1; stage 2 begins with release 0.2, which carries its findings and leaves its other generated artefacts for later (DL-0555).
Architecture is designed for both now so stage 2 does not rebuild stage 1 (DL-0043, ASR-11).

## Scope

**In, release 0.1:** multi-tenancy with schema isolation; the linear cycle above; the interface in Ukrainian or English per person (DL-0498), and per-document language; entities marked by people, with the role directory and *see also* derived from them; manual cross-document links; canonical documents readable as wiki pages; appendices and attachments; export to Markdown, PDF and DOCX, composed by scope and view and written in the document's language (DL-0172, DL-0502); stances, history, holds shown to readers, the edit-authors checkbox.

**In, release 0.2 — the AI reader** (DL-0555, DL-0558, DL-0568): companion actions, mid-edit and reporting only what the editor introduces; the reviewer agent at send for review, with introduced, pre-existing, resolved and aggravated findings over the standing findings set, its analysis shown to the run's authors as to its reviewers; the catalogue's first cut; the contradiction, ambiguity and blind-spot lists; the catalogue's administration — heuristics, companion actions and side-document types for the platform administrator, their assignment to documents by the tenant administrator; prompts under version control with their evals, the traces, the model jobs and the *not right* mark. And three items that are not AI (DL-0556): the data retention and erasure procedure (B-017), the Platform part of Administration drawn only on a platform host (B-067), and the guide for the people who use the platform daily (B-016).

**Out:** everything in [`backlog.md`](backlog.md) — Word import, automatic review of connected documents, repository-scope views, style linting, tenant-authored heuristics, the MCP server, work items derived from the views, comments, and disputes (DL-0550). From the stage-2 design, not in release 0.2 (DL-0555, DL-0568, DL-0571): the confidential guidance and its heuristic C01 (B-079), the citation of a superseded edition, C03 (B-081), the control directory, voluntary views and the seeding of an authored document, document ADRs, entities proposed by the agent, and the companion's draft of the change summary. Visual design and interface polish. Plus per-tenant role-set configuration and board voting.

## Success criteria

**Release 0.1:** a reviewer and an editor who have never seen git complete one full cycle on a policy without meeting git vocabulary, and the canonical edition exports naming its version, with its acceptances and approval traceable in the platform's history.

**Release 0.2** (DL-0554), all four:

1. Every heuristic that ships is at its eval target, with its results dated and committed.
2. An editor and a reviewer complete a full cycle with the analyses on the send-for-review screen and in review, without meeting prompt, model or heuristic vocabulary.
3. In production, the share of analyses marked *not right* stays under the ceiling the evaluation strategy sets for each kind of analysis — each companion action, the reviewer agent's analysis, each standing list — read from the traces (DL-0571 (10)).
4. Every model call in production traces to its prompt version and that version's eval results.

## Publication

Apache License 2.0, published while in development (DL-0162). Repository layout and secret handling follow from the first commit.

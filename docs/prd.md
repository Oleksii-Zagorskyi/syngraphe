---
tags:
  - prd
aliases:
  - Syngraphē PRD
status: draft
date: 2026-09-21
---

# PRD — Syngraphē

> [!note] Walking skeleton
> Structurally complete, thin where grounding is thin. Sections resting on an open question name it inline.

## Goal

An enterprise collaborative authoring platform where teams of human and AI editors create, review, approve and maintain authoritative documents. One cycle, end to end: **edit → commit → review → accept → edition → canonical → read and export.** Git is the substrate and is invisible; the interface has its own vocabulary in Ukrainian.

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
├── analysis/         # editor-facing companion analyses (stage 2)
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
| decider *(stage 2)* | rules on Statement entries, choosing the surviving wording | document |
| approver | makes a frozen document canonical | document |
| pending edits viewer | sees committed, unaccepted changes | whole document |
| tenant administrator | users, document sets, role assignments, heuristic selection, the export stylesheet (DL-0230) | tenant |
| platform administrator | the platform, the seeded heuristic catalogue, the base prompts | platform |

Board approval is recorded by one designated person; quorum and voting happen outside the software (DL-0017).

Two AI actors, not roles a person holds. The **companion** runs actions for the editor, is edit-scoped, and never reads a document the editor cannot read. The **reviewer agent** runs when a document is sent for review and produces two artefacts from **two separate runs**: a reviewer-eyes-only analysis from a run that reads the guidance, and an editor-facing analysis from a run whose context never contains it (DL-0007, DL-0095).

**Access is data** (DL-0051). Groups, their rights, their members and their links to documents are rows with a full change history carrying timestamp and actor (ADR-0007); only a tenant or platform administrator may edit them. Confidential guidance is **an ordinary document with restricted rows** — authored, edited and reviewed like any other — not a separate mechanism.

## Editing is linear

One editing sequence per document. No branches, no forks, no merges, and therefore no conflicts (ADR-0003).

1. An editor **takes the document** for editing. Nobody else edits it meanwhile. They edit it whole, or open an editor on any section — several at once — and every editor writes into the one draft (DL-0167). Formatted text is the default; a Markdown source view is always available.
2. Edits are **captured continuously** — there is no Save control. The draft persists so a closed laptop loses nothing; it is not yet a version and nobody else can see it.
3. **Undo** works within the editing session.
4. From release 0.2, at any point the editor may **call companion actions** — individually, not all of them — to answer *"what do my changes introduce so far?"*. Results are cached against the content, so asking twice about unchanged text costs nothing.
5. **There is no Save button.** In its place is *finish editing*. Pressing it shows the holder's changes, the part operations and the change summary, which starts from a mechanical draft naming the sections touched (DL-0261) — the companion analyses join them in release 0.2 — and its choices: **continue editing**, **send for review** — or, for a holder of *accept*, **accept as N.M** and **create version N.M-X** — and **discard my edits**, which asks for confirmation and throws the whole draft away.
6. **Send for review commits** (DL-0054). From release 0.2, the analyses are written into the same commit as the content, so no identifier has to be resolved after the fact — they are part of the tree, and they are what the reviewer reads as the change's description.
7. Versions accumulate, attributed, until a reviewer accepts a run of them.

Going back is only ever forward: an unwanted change in the pending run is undone by a reviewer — one version, or all of one author's — into the reviewer's draft, and committed as the reviewer's version; sentences a later version changed are left for the reviewer to edit (ADR-0015). History is never erased.

An ordinary **hold is released after a period without activity**, once its holder has been asked whether they are still working, and can be released by the tenant administrator; the interrupted draft is kept, not discarded (ADR-0006). Everyone sees that a document is held; for an ordinary hold only the tenant administrator sees by whom. Holds cover the whole document — there is no smaller unit (DL-0091).

**A holder may reserve the document for editing** to mature it over days or weeks (ADR-0009): the reservation is the same hold without the inactivity release, taken by a member of a group holding *reserve for editing*, and ended by finishing, discarding, cancelling, or an administrator breaking the glass with a stated reason. As for any hold, the document cannot be frozen or re-linked meanwhile, and a reservation also keeps others from reviewing it; readers see that it is reserved and since when, and holders of *edit* or *accept* on it, and administrators, see by whom. When to end it is agreed between people, outside the platform. A holder who also holds *accept* finishes in one act — *accept as N.M* — or leaves the version pending — *create version N.M-X*; for a document accepted at 2.3, *accept as 2.4* and *create version 2.3-1* (DL-0222).

## Rights and administration

Three application roles (DL-0079). A **platform administrator** does everything a tenant administrator can, in every tenant, and creates tenants, blocks them and grants platform administration. A **tenant administrator** invites users by email, blocks them in tenants they administer, manages groups and links them to documents, manages folders, archives and restores documents, and assigns side-document types and companion actions (ADR-0007). A **user** does what the rights of their groups allow — creating documents included, through *create and edit*. The list is indicative rather than exhaustive — ordinary surfaces such as editing one's own profile are not enumerated and are not thereby forbidden.

**Rights are held by groups, and groups are linked to documents** (ADR-0007); a person holds the union of the rights of their groups linked to a document. The rights: a viewing ladder — view canonical, view accepted, view pending, edit, create and edit; history — view previous canonical versions, view all history; acts — accept, freeze and unfreeze, and reserve for editing, each including edit (ADR-0016), and make canonical, with the accepted view (DL-0234); and rights over appendices and attachments. A new or copied document reaches only its author until the tenant administrator links groups. In this release both administrators read every document in their scope; separating administering from reading is EP-0001. Comment is stage 2 with the rest of the annotation surface.

**There are no section-scoped roles and no code owners** (DL-0091). A right is held over a document or not at all.

**No segregation of duties is enforced by default** (DL-0092). A reviewer may edit and then accept their own work. The control is the record rather than the prevention: every version is attributed, authorship is visible, and the audit history answers who did what (ASR-18).

**One optional check, per tenant, off by default** (DL-0101, DL-0115): an edition cannot be approved by anyone who accepted a run since the previous canonical edition. One comparison at the single transition where text becomes authoritative — enough to give a tenant a second pair of eyes to show an auditor, without slowing everyday editing.

**A new document starts with its creator holding edit, and nothing else** (DL-0089). The tenant administrator is notified that it was created and grants the rest. Until a reviewer exists the document reads *no reviewer assigned*, and acceptance is blocked with that stated reason rather than silently.

**Archiving** is visible to administrators only (DL-0084). An archived document's links stop resolving anywhere, including where its name appears in another document's prose; its access rights are archived with it, vanish from the administration panel, and **resurrect unchanged** on restore.

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
| **My edits in review** | what the editor has sent |

**Four of the five are *edits*, not document states.** The user is not switching between five documents; there is one document and a filter over which layers of edits are shown, with authorship toggled on top. That is how the tool being replaced works, and the interface follows it rather than the substrate.

**Authorship is visible to everyone**, behind a *show author* toggle so a diff can be read without it (DL-0040). A **time machine** steps through versions with a visual boundary between accepted history and pending edits.

## Acceptance

The reviewer reads the difference between the **last accepted revision** and the current one — with an agent's analysis of it from release 0.2. Accepting makes the current revision the new accepted baseline, and is recorded as a commit to the document's **passport** — so an acceptance always leaves a trace even when no text changes (DL-0041).

Where the reviewer wants corrections, they edit: a correction is a version of the run, committed with *accept as* or left pending with *create version* (DL-0222), or an undo applied to the reviewer's draft (ADR-0015). The acceptance commit itself touches only the passport.

**In stage 1** the platform generates a **correction notice** at acceptance for each author whose lines of the run a version by a holder of *accept* replaced or removed — one notice per author, listing what they wrote, what was accepted and who changed it (ADR-0014) — delivered through the notification surface. Generated rather than authored, so the reviewer has no discretion about whether the author finds out. The reviewer may instead **return the run without accepting it**, with a reason — recorded as a passport commit like an acceptance, so the decision travels with the document (DL-0114). The next send presents the whole run since the last acceptance, returned versions included.

*Stage 2, at low fidelity:* the notice becomes a durable **rejection record** the editor may escalate into the **Statement of Disagreements**, settled by agreement between editor and reviewer, or by the **decider** on deadlock (DL-0026, DL-0076).

Acceptance is a **document-level act** covering the whole run since the last accepted version (DL-0090). Accepting only part of a run is a backlog refinement.

## Editions

A document is **frozen** while something outside it is resolved — an approval, a discussion with whoever approves, work elsewhere — and only its reviewers may edit it meanwhile (DL-0189). The freeze ends by **making it canonical**, which makes the latest accepted version the next **edition**, or by unfreezing it. A frozen document cannot be made canonical while any Statement entry is open (DL-0010). A new editing cycle may start against a canonical document at any time.

## What the agents look for

Three levels, and only the platform administrator sees the bottom one (DL-0049).

| | What it is | Platform administrator | Tenant administrator | Editor |
|---|---|---|---|---|
| **heuristic** | one focused piece of prompt text | creates, edits | cannot see | cannot see |
| **companion action** | a set of heuristics producing a user-facing analysis | creates, edits | sees title and description; attaches to a document | calls it |
| **side-document type** | a set of heuristics producing and maintaining a generated view | creates, edits | sees title and description; attaches to a document | reads the view |

The tenant's lever is the composed action, not its ingredients. Keeping prompt text out of reach of anyone who could write to the test is the point.

The catalogue of what the heuristics look for is [`review-findings.md`](review-findings.md). Every run records the heuristics and versions it used; every finding names the heuristic that produced it.

### How a user reaches an agent

Three rules (DL-0050, ASR-11, ASR-12):

- **No conversation.** A user calls predefined actions; nobody composes a prompt.
- **No repeat for an unchanged version.** Once an action has answered for a version, the stored answer is returned — the source has not moved, so neither has the answer.
- **Keyed to content, not to a session.** An action may run mid-edit; its result is stored against a hash of the document tree, so a commit is simply one content state among others (DL-0056). The send-for-review screen shows what was already computed rather than recomputing it.

On sending for review the editor sees the analyses that will travel with the commit and confirms them.

**Audience (DL-0021):** a finding reaches a recipient if and only if it is derivable from material that recipient may already read — computed per recipient, never by the prompt. An untagged finding is confidential.

**Scope (DL-0032):** the companion reports only what this editor is introducing. The reviewer agent reports introduced, pre-existing, resolved and aggravated findings, separated.

## Generated views

Maintained by the agent and by nobody else, each with its own history (DL-0044). Two classes (DL-0063):

**Mandatory** — recompiled on every commit:

- **Directory of roles** — rights and obligations per role, with links back to the sections they come from.
- **Directory of controls** — what the document says is controlled, and how.
- **Contradictions**, **ambiguities**, **blind spots** — document-wide standing lists, a working backlog editors and reviewers act against, not a per-commit report.

**Voluntary** — generated on request. A **job description** carrying a role's rights and obligations is the example. A voluntary view may also **seed an authored document**: the platform drafts it, a human takes it over, and from then on it is an ordinary document with its own pipeline. The view stays agent-only; what is seeded is a copy under human authorship, never an edited view.

Both directories can render beside the document or be embedded in an export. Scope starts per document and extends to the whole repository later, since two policies can regulate one role. For a holder of the guidance grant, each list carries an **addendum** computed against the confidential requirements, visible only to them.

## Document ADRs

When a person changes the *logic* rather than the wording, a decision record is generated beside the document: who decided, when, why, and what the alternatives were (DL-0045). The agent pre-authors it; the person edits it or leaves it. One record covers one decision however many passages it touches — changing who approves a budget may rewrite fifteen of them.

## Staging

**Stage 1 — editor, diff viewer, versions, review and acceptance.** A working editor users can use the next morning.
**Stage 2 — the agents and the generated views.**
Architecture is designed for both now so stage 2 does not rebuild stage 1 (DL-0043, ASR-11).

## Scope

**In:** multi-tenancy with schema isolation; the linear cycle above on dummy documents; Ukrainian interface and per-document language; the entity layer, AI-proposed and human-confirmed, with read-only derived views; manual cross-document links; canonical documents readable as wiki pages; appendices and attachments; section editing; export to Markdown, PDF and DOCX, composed by scope and view (DL-0172); heuristics and both agents; stances, time machine, presence, author toggle.

**Out:** everything in [`backlog.md`](backlog.md) — Word import, automatic review of connected documents, repository-scope views, style linting, tenant-authored heuristics, the MCP server, and work items derived from the views. Plus per-tenant role-set configuration and board voting.

## Success criteria

A reviewer and an editor who have never seen git complete one full cycle on a dummy policy without meeting git vocabulary, and the canonical edition exports with its versions, reviews, disputes and approval traceable.

## Publication

Apache License 2.0, published while in development (DL-0162). Repository layout and secret handling follow from the first commit.

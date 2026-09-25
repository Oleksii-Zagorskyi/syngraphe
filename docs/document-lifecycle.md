---
tags:
  - technical-design
aliases:
  - Syngraphē document lifecycle
status: draft
date: 2026-09-21
---

# Document Lifecycle — states and the actions that move them

Three diagrams, each small enough to hold in one look. Written against the linear edit model (ADR-0003).

## The document

```mermaid
stateDiagram-v2
    [*] --> Available: create document
    Available --> Held: open an editor
    Held --> Available: discard my edits
    Held --> Pending: send for review (commits)
    Pending --> Held: take again
    Pending --> Accepted: reviewer accepts the run
    Pending --> Pending: reviewer corrects, then accepts
    Accepted --> Held: open an editor
    Accepted --> Frozen: freeze
    Frozen --> Frozen: a reviewer edits and accepts
    Frozen --> Accepted: unfreeze
    Frozen --> Canonical: make canonical
    Canonical --> Held: open an editor
```

**Pending** means committed but not yet accepted — several editors' versions stack there, each attributed. **My edits in review** is the same set filtered to one author; it is a view, not a state, because *send for review* **is** the commit (DL-0054). **Accepted edits** is the last revision a reviewer accepted. **Canonical** is the last approved edition — a ref, not a mood, and the document keeps moving past it. The interface names of the stances, in every language, are in [`glossary.md`](glossary.md).

Disputes are stage 2 (DL-0076), so nothing gates `Frozen --> Canonical` in stage 1 but the approver — and, where a tenant has switched it on, the rule that whoever makes it canonical accepted none of the runs since the previous canonical edition (DL-0101, DL-0115). The disagreement guard returns with the register.

> [!important] A freeze locks the document, not a version
> A document is frozen only when nobody holds it. While frozen, editors cannot open an editor; people holding both *accept* and *edit* can, and their commits and acceptances continue the numbering — `1.3+1`, then `1.4` (DL-0189). No version ever changes. *Make canonical* turns the latest accepted version into the next edition and is refused while commits since it are unaccepted; *unfreeze* returns to ordinary editing at the current number. The stances are derived from `ACCEPTANCE`, `FREEZE` and `EDITION` rows, with no state column for them to disagree with.

## An editing session

```mermaid
stateDiagram-v2
    [*] --> Drafting: open an editor
    Drafting --> Drafting: open and close editors, type, undo, add or change parts
    Drafting --> Reviewing: press send for review, every editor closed
    Reviewing --> Drafting: continue editing
    Reviewing --> Committed: send for review
    Reviewing --> [*]: discard my edits, confirmed
    Drafting --> [*]: discard my edits, draft discarded
    Drafting --> Released: inactive past the timeout, or forced
    Released --> [*]: draft preserved, document freed
    Committed --> [*]
```

There is no Save control. The draft persists server-side so a closed laptop loses nothing, but it is not a version and no one else can see it. Returning the document produces exactly one version, carrying a change summary the editor writes, starting from a mechanical one; from 0.2 the companion drafts it (DL-0035).

**Editors are views over the one draft** (DL-0167). The holder opens the whole-document editor, or one editor per section — several at once, across tabs if they like — and each captures into the draft over its own range; an editor whose range changed underneath it stops and shows its unsaved text as changes. Adding, replacing, removing, renaming or reordering an appendix or attachment is part of the same draft (DL-0168). *Send for review* needs every editor closed.

**Companion actions run at any point**, individually, keyed to the content rather than to a commit (DL-0056). The *Reviewing* state is the send-for-review screen: it shows the analyses for the current content — mostly already computed — and the editor either goes back to editing or commits. Committing writes the analyses into the same commit as the text (DL-0055).

## A disagreement

```mermaid
stateDiagram-v2
    [*] --> Open: dispute raised, or rejection escalated
    Open --> Agreed: editor and reviewer converge
    Open --> Escalated: deadlock
    Escalated --> Decided: decider rules
    Agreed --> [*]: one wording survives
    Decided --> [*]: one wording survives
```

Entries arrive two ways: a reviewer marks a passage disputed, or an editor escalates a rejection record generated when a reviewer rewrote their wording (ADR-0001). While an entry is open the document holds the latest committed wording and the register holds the competing one.

## Who may do what

| Action | Role | Precondition | Effect |
|---|---|---|---|
| open an editor | editor | document not held, or held by this user | takes the hold if free; draft opens (ADR-0006) |
| call a companion action | the holder, or any editor of the document | this action has not run against this exact content | stored analysis, or one model call; available during a hold once every editor is closed (ADR-0006) |
| open an editor — whole document, or one per section | the holder | the whole-document editor needs no section editor open | captures into the draft over its range (DL-0167) |
| add, replace, remove, rename or reorder an appendix or attachment | the holder | an attachment within the tenant's size cap | staged in the draft; committed with the text (DL-0168, DL-0175) |
| send for review | the holder | draft differs from the current text or stages a file operation; no editor open | the commit; analyses written into it; document becomes Pending |
| discard my edits | the holder | confirmed | draft discarded, staged file operations included; document Available |
| force release | tenant administrator | holder inactive or unreachable | draft preserved; document freed |
| correct before accepting | reviewer | document Pending | commit touching content and passport, including reverting an appendix or attachment operation; a correction notice generated for every author whose text changed |
| accept the run | reviewer | a reviewer is assigned; versions exist since the last acceptance | commit to the passport; document becomes Accepted; a correction notice goes to every author whose text the reviewer changed |
| return without accepting | reviewer | versions exist since the last acceptance | run stays pending; authors notified with the reviewer's reason (ADR-0001) |
| revert a contribution | reviewer, editor | — | new commit undoing it; never a history rewrite |
| freeze | holder of freeze | document not frozen, and nobody holds it | document Frozen; editors locked out, holders of *accept* and *edit* may still edit (DL-0189) |
| unfreeze | holder of freeze | document Frozen | ordinary editing resumes at the current accepted number |
| make canonical | holder of make canonical | document Frozen; no unaccepted commits since the latest acceptance | latest accepted version becomes the next edition, `N+1.0`; freeze ends |
| read | holder of a viewing right | — | *view canonical* sees Canonical; *view accepted* adds Accepted; *view pending* adds Pending; history rights add earlier versions (ADR-0007) |
| follow a link to another document | any reader | the reader may access the target | otherwise the mention renders as plain text and is absent from *see also* (ASR-16) |
| move a document between folders | tenant administrator | — | metadata only; no repository path changes, no access change (ASR-15) |
| copy a document | holder of create and edit | may see the chosen version | new author-only document with that text, chosen appendices, no attachments, no history (ADR-0007) |
| set a document's type | tenant administrator | the type exists in the platform table | changes list filtering only |
| toggle show author | anyone who can see a diff | — | attribution shown or hidden (DL-0040) |
| download an attachment | anyone who may read the version it belongs to | — | the stored file, under its original name |
| export | anyone who may read the chosen view | at least one scope and one format chosen | an export job (DL-0172) |
| edit the document template | tenant administrator | — | applies to documents created afterwards (DL-0169) |

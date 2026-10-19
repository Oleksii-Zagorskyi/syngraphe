---
tags:
  - interface
aliases:
  - Syngraphē page wireframes
status: draft
date: 2026-09-27
---

# Pages

The pages of release 0.1: what each holds, which right each control needs, the stories each region carries, and the release and epic each region belongs to. **They are a design input, not a story:** several epics build from them. The epics are release planning and are not published; the *Built by* column names the one that builds each region.

**[`mockup.html`](mockup.html) draws them** — an HTML mockup with synthetic content, opened in a browser. It shows arrangement, not visual style. A bar across its top chooses **whom the pages are drawn for** — a reader, an editor, an editor who also accepts, a reviewer, an approver, a tenant or a platform administrator — and **the state of the example document**: who holds it, whether a run is pending or returned, frozen, archived. Where the mockup and this file differ, this file wins. [`coverage.md`](coverage.md) lists every story with the regions that carry it.

**Every region carries the release it belongs to.** A region marked for a later release is drawn in the mockup as an empty, labelled placeholder, so the layout keeps its room — **nothing is built for it in 0.1**: no empty frame, no disabled slot (DL-0228).

| Marker | Meaning |
|---|---|
| **0.1** | built in release 0.1, by the epic named |
| **0.2** | the AI half, release 0.2 |
| **later** | after 0.1, not yet assigned to a release |

**Rights decide what renders.** A control a user may not use is never drawn for them (ADR-0004, ADR-0007). A page or item the user may not see answers exactly as one that does not exist (ADR-0008). **A column, filter or choice that can never hold anything for this person is not drawn** (DL-0233, DL-0236).

**A blocked control explains itself.** A control its user holds the right to, but cannot use now, is drawn disabled with the reason beside it — whatever blocks it: someone's hold, a reservation, a missing precondition. It is never hidden from a holder of its right, and never refuses only on click (DL-0223, DL-0233).

**A document's state shows as a tag beside its title** — in lists and on the document page — and, where it stops people acting, **as a coloured band across the top of the page** (DL-0233, DL-0236).

**Content is at most 1,440 px wide**, centred (DL-0197).

## Page inventory

| Page | URL | Stories | Release |
|---|---|---|---|
| [Shell](#shell) | on every page | ST-0007, ST-0013, ST-0014, ST-0019, ST-0047, ST-0066, ST-0069 | **0.1** |
| [Sign-in pages](#sign-in-pages) | — | ST-0008, ST-0054, ST-0055, ST-0057 | **0.1** |
| [Document list](#document-list) | `/folder/7/`; `/` opens the root, `/folder/1/` | ST-0009, ST-0012, ST-0013, ST-0014, ST-0018, ST-0051, ST-0052, ST-0064 | **0.1** |
| [In edit, In review](#in-edit-in-review) | `/in-edit/`, `/in-review/` | ST-0013, ST-0014 | **0.1** |
| [Search results](#search-results) | `/search/?q=…&type=…` | ST-0013 | **0.1** |
| [Document page](#document-page) | `/document/12/` and one segment per tab | ST-0005, ST-0010, ST-0014, ST-0015, ST-0016, ST-0017, ST-0018, ST-0019, ST-0020, ST-0021, ST-0022, ST-0023, ST-0024, ST-0026, ST-0027, ST-0028, ST-0029, ST-0030, ST-0031, ST-0032, ST-0033, ST-0034, ST-0035, ST-0036, ST-0037, ST-0038, ST-0039, ST-0040, ST-0041, ST-0042, ST-0043, ST-0044, ST-0045, ST-0051, ST-0052, ST-0053, ST-0059, ST-0060, ST-0061, ST-0062, ST-0063, ST-0064, ST-0067, ST-0069, ST-0070 | **0.1** |
| [Appendix page](#appendix-page) | `/document/12/appendix/3/` | ST-0023, ST-0061 | **0.1** |
| [Historical page](#historical-page) | `/document/12/version/2.0/` | ST-0027, ST-0032, ST-0041, ST-0044, ST-0061, ST-0064 | **0.1** |
| [Compare](#compare) | `/document/12/compare/?from=2.0&to=2.3-1` | ST-0033, ST-0041, ST-0064 | **0.1** |
| [Send-for-review screen](#send-for-review-screen) | within the edit tab, opened by *finish editing* | ST-0022, ST-0029, ST-0035 | **0.1** |
| [Export](#export) | a dialog | ST-0045 | **0.1** |
| [Create or copy a document](#create-or-copy-a-document) | a dialog | ST-0009, ST-0067 | **0.1** |
| [Notifications](#notifications) | `/notifications/` | ST-0004, ST-0030, ST-0035, ST-0036, ST-0047, ST-0048, ST-0051, ST-0052, ST-0070 | **0.1** |
| [Help](#help) | `/help/…` | ST-0002, ST-0003, ST-0004, ST-0007, ST-0012, ST-0013, ST-0015, ST-0016, ST-0019, ST-0026, ST-0027, ST-0028, ST-0043, ST-0044, ST-0045, ST-0054, ST-0055, ST-0060, ST-0064, ST-0065, ST-0066, ST-0067 | **0.1** |
| [Nothing to show here](#nothing-to-show-here) | any address that may not be seen | ST-0015 | **0.1** |
| [Administration](#administration) | `/administration/platform/…`, `/administration/tenant/…` | ST-0001, ST-0002, ST-0003, ST-0004, ST-0005, ST-0006, ST-0011, ST-0012, ST-0015, ST-0016, ST-0030, ST-0046, ST-0048, ST-0049, ST-0050, ST-0051, ST-0053, ST-0058, ST-0062, ST-0065, ST-0066, ST-0068, ST-0071, ST-0072 | **0.1** |
| User profile | — | — | **later** — not yet designed; the user menu carries what 0.1 needs |

## Shell

```
+------------------------------------------------------------------------------+
| logo | All documents | In edit | In review | Help | Administration | (!3) | tenant ▾ | me ▾ |
+------------------------------------------------------------------------------+
```

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| *All documents* | **0.1** | — | ST-0013 | Epic 3 |
| *In edit* — documents the user may edit that have versions after their latest canonical edition | **0.1** — shown to holders of *edit* on any document, disabled when empty, no count (DL-0197) | *edit* | ST-0013 | Epics 14, 10 |
| *In review* — documents awaiting review the user may accept; a returned run leaves it until a version is sent after the return (DL-0420) | **0.1** — likewise | *accept* | ST-0014 | Epics 14, 15, 10 |
| *Help* | **0.1** | — | ST-0019 | Epic 4 |
| *Administration* | **0.1** | tenant or platform administrator | — | Epic 2 |
| notifications — unread count, opening the notifications page | **0.1** | — | ST-0047 | Epic 14 |
| tenant switcher — only with several memberships; on a tenant's own domain, switching moves to the other tenant's domain, or to the platform's host, where the choice is confirmed (ADR-0008) | **0.1** | — | ST-0007 | Epic 8; the tenant's name Epic 2 |
| user menu — *My reservations*, each document the person may still read with its start date, drawn only for a holder of *reserve for editing* (DL-0241); *block my account…*, confirmed, never offered to a person whose account is blocked; *sign out* | **0.1** | — | ST-0066, ST-0069 | Epic 2; self-block Epic 8; reservations Epic 9 |

## Sign-in pages

Sign in, accept an invitation, reset a password: small forms without navigation, each answering identically whether or not an address is known (ASR-17). On a tenant's own domain, signing in lands in that tenant.

**The first-run page** creates the first platform administrator. It accepts only the one-time token the install command `setup_token` prints, then the administrator's email address and password; the token is single-use and expires, and once a platform administrator exists the page answers as an address that does not exist (DL-0231, T-19).

| Region | Release | Stories | Built by |
|---|---|---|---|
| the three forms | **0.1** | ST-0008, ST-0054, ST-0055 | Epic 2; invitation and reset Epic 8 |
| the first-run page | **0.1** | ST-0057 | Epic 2 |

## Document list

```
+--------------+---+-----------------------------------------------------------------+
| ▾ Example Org|   | [ search titles of documents and appendices ] [All types ▾] [+ create] [Folders ▾] |
|  ▾ Policies  | ↔ | #   Title ▲                        Type    Canonical  Latest  Parts  ✎ |
|   ▸ **HR**   |   | 12  Annual leave, sick leave and…  policy  2.0        2.3-1   A  F   ✎ |
|   ▸ Finance  |   |     [reserved for editing, since 12 Sep] [awaiting review]       |
|  ▸ Procedures|   | 7   Travel rules                   policy  1.0                a  f   ✎ |
+--------------+---+-----------------------------------------------------------------+
```

*Titles are synthetic examples.* `↔` a draggable edge · `A` / `a` appendices present / absent · `F` / `f` attachments present / absent — drawn as dark and faint icons.

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| folder tree — no heading; ▸ ▾ to collapse; root named after the tenant; the selected folder in bold; always a folder selected (DL-0197) | **0.1** | — | ST-0012, ST-0013 | Epic 10 |
| folder visibility — only folders holding, at any depth, a document the user may read; administrators see all; alphabetical (DL-0206) | **0.1** | — | ST-0012 | Epic 10 |
| draggable pane edge; the width kept in the user's preferences (DL-0195) | **0.1** | — | — | Epic 10 |
| *Folders ▾* — new, rename, delete an empty folder, move documents | **0.1** | tenant administrator | ST-0012 | Epic 10 |
| search box — titles of documents and appendices only, never text | **0.1** | — | ST-0013 | Epic 10 |
| filter by type — beside the search box: *All types*, then the types of the active documents the user may open, retired ones included; **not drawn when those documents carry fewer than two types** (DL-0236); choosing one opens search results for that type across every folder, with the words in the box (DL-0197) | **0.1** | — | ST-0013 | Epic 10 |
| *create* | **0.1** | *create and edit* | ST-0009 | Epic 3 |
| *Compare documents…* — two document numbers, opening their comparison | **0.1** | a viewing right on each | ST-0064 | Epic 10 |
| `#` — the document's number (ADR-0008) | **0.1** | — | ST-0013 | Epic 3 |
| title — takes the free width; opens the reading view | **0.1** | — | ST-0013 | Epics 3, 4 |
| state tags after the title — *held* (DL-0262), the fact and never the person except to administrators — a tenant administrator, or a platform administrator acting in the organisation (ADR-0006, DL-0079); *reserved for editing, since* its date, with who to holders of *edit* or *accept* and to administrators (DL-0226); *frozen* first, then the hold's tag; *awaiting review* and *returned* to those who may see pending edits (DL-0233); *no reviewer assigned* to those, and to administrators | **0.1** | — | ST-0014, ST-0018, ST-0051, ST-0052 | Epics 5, 6, 9, 15 |
| sorting — by `#` or title, ascending or descending; title A to Z by default | **0.1** | — | ST-0013 | Epic 10 |
| *Canonical* — the canonical number, linking to the edition's historical page (DL-0208, DL-0352) | **0.1** | — | ST-0013 | Epics 6, 15 |
| *Latest* — the latest version the user may see beyond canonical, else empty; links where the title does (DL-0208, DL-0209). **Drawn only for someone who may see beyond canonical text on at least one document** (DL-0233) | **0.1** | — | ST-0013, ST-0014 | Epic 6 |
| part markers — presence, not count | **0.1** | — | ST-0013 | Epic 3 |
| ✎ — opens the edit tab | **0.1** | *edit* | ST-0013 | Epics 4, 10 |

An archived document leaves the list for everyone, administrators included; they reach it through Administration › Archive (DL-0233).

## In edit, In review

The document list's shape, each a page of its own reached from the menu, without the type filter — choosing a type opens search across every folder, which would leave the view: matching documents grouped under a heading per folder path, the groups alphabetical, sorting within each group; the folder tree shows only folders holding matches (DL-0197, DL-0207). An empty view reads *No documents here.*; to anyone the menu does not offer it, its address answers *Nothing to show here*.

| Region | Release | Stories | Built by |
|---|---|---|---|
| grouped list, filtered tree | **0.1** | ST-0013, ST-0014 | Epics 14, 10 |

## Search results

As *In edit*: results grouped under a heading per folder path, alphabetical groups, sorting within each group, the tree cut to *folders with found documents*. A group left empty by the reader's rights, and its folder, are not drawn.

| Region | Release | Stories | Built by |
|---|---|---|---|
| grouped results, filtered tree | **0.1** | ST-0013 | Epic 10 |
| search box — keeps the words searched; the note *Searched in titles of documents and of their appendices, not in text.* | **0.1** | ST-0013 | Epic 10 |
| filter by type — as on the document list; alone it lists every document of the type the user may open, with words it narrows them | **0.1** | ST-0013 | Epic 10 |
| nothing found — *No documents here.* | **0.1** | ST-0013 | Epic 10 |

## Document page

```
+------------------------------------------------------------------------------+
| [Reserved for editing since 12 Sep by Author A. Accepting, returning, …]     |
| Policies / Human resources /                                                 |
| #12 Annual leave, sick leave and parental leave: how employees…  2.3-1 [reserved …] |
| [Export] [Copy] [Freeze] [Make canonical] [Groups] [Archive] [More ▾]         |
+-----------+---+-------------------------------------------+---+--------------+
| OUTLINE ⇤ |   | View  Edit  My edits  Pending edits       |   | [P][G][C]  ⇥ |
| ▾ 1       | ↔ | History  Analysis  Info                   | ↔ |              |
|   1.1     |   | Viewing the 2.3-1 version · open canonical 2.0 ↗ |   | parts,       |
| ▾ 3       |   |                                           |   | generated    |
|   ▾ 3.1   |   | tab content                               |   | views or     |
|     3.1.1 |   |                                           |   | comments     |
+-----------+---+-------------------------------------------+---+--------------+
```

`[P][G][C]` — the icon row switching the panel between parts, generated views and comments; the panel opens on parts.

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| **bands** across the top — *reserved for editing* since its date, with who to holders of *edit* or *accept* and administrators, and what waits until it ends; *reserved for editing by you*, to its holder; *frozen* with its reason, and the name of who froze it to holders of a history right and administrators (DL-0236); *your editing of this document was ended*, to the holder of a kept draft — ended by an administrator, by inactivity or by a block — leading to the edit tab, which says who, when and why and offers *take the document back* when nothing was committed since (DL-0225) | **0.1** | — | ST-0018, ST-0038, ST-0069, ST-0070 | Epics 9, 6 |
| the notice after *send for review* — *Sent for review — the version waits as 2.3-2*, to the one who sent it (DL-0322) | **0.1** | — | ST-0029 | Epic 4 |
| breadcrumb, `#12`, title, the **latest version the reader may see** — never a version beyond their rights (DL-0209) | **0.1** | — | ST-0042 | Epics 3, 6 |
| state tags, as in the list; *archived* to administrators only — to everyone else an archived document does not exist | **0.1** | — | ST-0014, ST-0015, ST-0018, ST-0051, ST-0052 | Epics 5, 6, 9, 10, 15 |
| *Export*, *Copy* — *Copy* drawn disabled with *archived — restore it first* on an archived document (DL-0233) | **0.1** | any viewing right; *create and edit* | ST-0045, ST-0067 | Epics 7, 10 |
| *Freeze* / *Unfreeze* — disabled with its reason while anyone holds or has reserved the document (DL-0223) | **0.1** | *freeze* | ST-0038, ST-0040 | Epic 6 |
| *Make canonical* — disabled with its reason until the document is frozen, and while changes are unaccepted; to someone who may not see pending edits the reason names no pending number | **0.1** | *make canonical* | ST-0039, ST-0053 | Epic 6 |
| *Groups* — locked, with who holds the document, while it is held or reserved | **0.1** | tenant administrator | ST-0005 | Epic 8 |
| *Archive* / *Restore*; *More ▾* holds *force release* for an ordinary hold and *end the reservation…* for a reserved one, never offered to the holder; *end the reservation…* opens a page naming the reservation, its holder and its date, with the reason, required (DL-0225, DL-0415); *force release* names the hold the page showed, so a newer one is never forced | **0.1** | tenant or platform administrator | ST-0015, ST-0016, ST-0030 | Epics 10, 9 |
| *Compare with another document* — opens the picker, *from* the version shown | **0.1** | any viewing right | ST-0064 | Epic 10 |
| outline — every heading level, ▸ ▾, no appendices; collapsible and resizable; on the *View* tab (DL-0356) | **0.1** | — | ST-0024 | Epic 7 |
| the text — a heading's number part of the heading, set as the heading is; each clause's number in the gutter beside it in a light grey, never selected with the text; the same in the editor and the exports (DL-0363) | **0.1** | — | ST-0042 | Epic 7 |
| right panel — the icon row; collapsible and resizable; widths kept per user (DL-0194, DL-0195) | **0.1** — *parts* and *generated views*; comments **later** (B-013) and the agents' views **0.2**, not drawn until built (DL-0228, DL-0356) | — | — | Epics 3, 4, 7, 11 |
| parts — the version's appendices in their order, each opening its page; its attachments with title, file name, size and download — read only: the changing controls are the edit tab's own panel, beside the draft (DL-0442) | **0.1** | any viewing right | ST-0061, ST-0062 | Epic 13; its thinnest form — the attachments with title, file name, size and download, in the panel's parts tab (DL-0349, DL-0356) — Epics 18, 7 |
| generated views — the **role directory**: each declared role by label, in the order the document declares them, with every heading or clause marking it, its number linked to its place and its text as it reads under the reader's own rights — a long clause its opening words; a role in a table cell listed under the heading or clause the table follows, *(table)* after its number, and a table before any of them as *(table)* alone; a role marked nowhere *no clauses*; then a role marked with an undeclared key, grouped by it, and one marked without a key, grouped by its words, *(not declared)* beside them (DL-11-011); *No role is marked in this version* where none is — then **see also**: each document the text mentions, once, in order of first mention, the document itself left out — its number and title, linked, where the reader may read it, the first mention's words as plain text where not (DL-0437); *This version mentions no other document* where none is; then *Generated by the system from the version shown* (DL-0448); on the View tab and the historical page, at the version shown | **0.1**; contradictions, ambiguities, blind spots **0.2** | any viewing right | ST-0027, ST-0044 | Epic 11 |

### The tabs

| Tab | URL segment | Shows | Release | Needs | Stories |
|---|---|---|---|---|---|
| View | — | the latest version the reader may see, with *Viewing the 2.3-1 version · open canonical 2.0* (DL-0209), or *Viewing canonical 2.0* when the version shown is the latest edition — always, to a reader of canonical text only; *open canonical 2.0* links to the edition's historical page (DL-0352); to such a reader a document with no canonical edition yet does not exist; before any acceptance, with nothing pending, *Viewing the 0.0 version*, the document's first (DL-0358); clause numbers in the gutter; entities in their own formatting; the outline and the panel beside it (DL-0356) | **0.1** | any viewing right | ST-0023, ST-0026, ST-0042 |
| View, mentions | — | a mention of another document as a link to it where the reader may read it while it is active; its words alone where not — an archived document, one the reader may not read, a number that names none — with no title, no mark and no message (DL-0084, ASR-16); the same on every page that draws the text — the historical page, compare, pending edits, *my edits*, the send-for-review screen, the edit tab's drawn text, a kept draft, the stopped editor, a correction notice; PDF and DOCX carry the words alone for every reader, the Markdown export the mention as written | **0.1** | any viewing right | ST-0043 |
| Edit | `edit/` | below | **0.1** | *edit* — which *accept*, *freeze* and *reserve for editing* include (ADR-0016); while frozen, *accept* | ST-0017, ST-0019 to ST-0022, ST-0028, ST-0035, ST-0059, ST-0060, ST-0069, ST-0070 |
| My edits | `my-edits/` | the holder's draft: the whole document, the draft's changes marked in place; the roles, actions and terms it adds, relabels or removes, those its marked words declare with the version included (DL-0440) | **0.1** | the holder | ST-0031 |
| Pending edits | `pending/` | the whole document, every change since the last acceptance marked in place and attributed; formatting-only changes marked; **a changed image before and after, side by side**, each captioned with its side, its version's number and its description, *open both full size* below them (DL-0439, DL-11-002); the run's versions with their change summaries; **each appendix the run changed**, after the body, its changes marked as the body's are; **every part operation** — added, replaced, renamed, reordered, deleted — with each file's versions to download and, for a reviewer, *revert*, which puts the part back as the last acceptance had it, takes the document and joins the correction, needing *accept* alone (DL-0446); while a revert waits in a draft, *Accept the run* is disabled with its reason, and the run is accepted with that draft's *Accept as*; **the roles, actions and terms added, relabelled or removed in the run** (DL-0073); *Show edit authors* (DL-0040, DL-0489); *Correct*, *Accept the run* (confirmed, naming the versions accepted and the number that results), *Return without accepting* (confirmed, the reason required: one line of at most 500 characters, DL-0378, DL-0424) — each disabled with its reason while the document is reserved, the holder's own reservation included — a holder of *accept* accepts through *accept as* on the send-for-review screen (DL-0222, DL-0224); *Correct* also while an author holds the document | **0.1** | *view pending*; *accept* for the acts | ST-0031, ST-0034, ST-0035, ST-0036, ST-0052, ST-0063 |
| History | `history/` | per version, newest first: number, event (edit, a reviewer's version, acceptance, return, canonisation), who, when — and the freezes and unfreezes between them; *open* — in a new window as a historical page; the accepted boundary, to a reader of accepted text (DL-0209); to a holder of *view previous canonical versions* only, the editions alone; to a holder of *accept* without a history right, the pending run alone (DL-0251); *compare* from each version's historical page. On the pending run, for a reviewer: **undo this edit** on each version and **undo all of this author's edits since N.M** on each author's newest — the reversal of the body and of each appendix the run touched goes into the reviewer's draft, which opens — an appendix's places listed under its title; a title or part the undone edits changed — an appendix they created or deleted among them — is listed, to be changed with the parts' own controls (DL-0447); what a later version or the draft changed is left as it stands and listed above the editor for editing by hand (ADR-0015, DL-0380); disabled with the reason while reserved, held by another, or a kept draft of the reviewer's waits; while the undo waits in the draft, *Accept the run* is disabled with its reason, and the reviewer accepts it with *Accept as* (DL-0427) | **0.1** | *view all history*; *view previous canonical versions* for editions only; *accept* for the pending run and to undo | ST-0032, ST-0033, ST-0037, ST-0041, ST-0064 |
| Analysis | `analysis/` | the agents' analyses, drawn as a placeholder; release 0.1 has no analyses of its own (DL-0261) | **0.2**, drawn, not built (DL-0228) | *edit* | — |
| Info | `info/` | number, title, language, type — a choice for administrators — folder, canonical version, state, title page — *Yes* or *No* for the version the reader is shown — style — *The organisation's stylesheet* or *The platform's default* (DL-0463, DL-0465) — linked groups (administrators), created; *Copied from* (administrators, a copy alone) — the source's number, linked where the reader may open it, its version, the commit's first twelve characters, the date and who copied it (DL-0455) | **0.1** | any viewing right | ST-0010 |

### The edit tab

| Region | Release | Stories | Built by |
|---|---|---|---|
| the draft drawn as text, no editor until one is chosen; *edit* beside each `#` heading, at any depth, several open at once — a section sharing any line with another open editor, other than the same section, refused, five at most (DL-0418); the text before the first heading, and a draft the whitelist refuses, open only in the whole-document editor; *edit the whole document* only when none is open — disabled with its reason otherwise; after a capture adds or removes a heading, the other *edit* controls disabled with the reason until the tab is drawn again | **0.1** | ST-0059 | Epic 9 |
| a section editor opened in place, the rest rendered around it; toolbar exactly the whitelist — *quote* among it (DL-0238) — *undo* and *redo* (DL-0241), *mark* for entities — a picker beside the toolbar: the kind, this document's declared ones of that kind by label, *declare a new one* with its label; picking or declaring wraps the selection, words already marked taking the new one; only this document's own are offered (DL-0073) — *mention* — a document's number typed into the toolbar as a link's address is, Enter wrapping the selection in a mention of it, anything but a number refused on the notice line, nothing looked up — each control an icon with its word as tooltip and accessible name; a mention drawn in a link's colour with a dotted underline, apart from entities and links; *rich / markdown* | **0.1** | ST-0019, ST-0021, ST-0026, ST-0043, ST-0060 | Epic 4, *undo* and *redo* included; *mark* and *mention* Epic 11 |
| paste refusal — the lines named, the converted text previewed, *paste converted*, a link to help; an image left out of a paste with a one-line notice (DL-0232) | **0.1** | ST-0019, ST-0028 | Epic 4 |
| image refusal — the format or the size. A pasted or dropped image becomes an upload and a paragraph of its own; an image that is only a web address is left out of the paste, with a one-line notice to copy the image itself and paste it, which blocks nothing (DL-0232, DL-11-005) | **0.1** | ST-0019, ST-0028 | Epic 11 |
| capture indicator — no Save control | **0.1** | ST-0020 | Epic 4 |
| the **parts panel**, on the right while holding the document — the draft's appendices and attachments, each appendix opening its page's *Edit* tab; *Add* (an appendix by its title, an attachment by its title and file), *rename*, *replace* an attachment's file, *delete* (confirmed), ↑ *Move up* and ↓ *Move down*, the download arrow for the draft's file — each as the person's rights allow: *create appendix*, *delete appendix*, *upload attachment*, *replace attachment*, *delete attachment*; renaming and moving *edit* alone; a part the draft added withdrawn with the right that added it (DL-0473); the author of a document no group is linked to may upload and replace (DL-0445); a file above the organisation's limit, a name a file system refuses or that changes how it reads, refused with the reason; each form waits for the open editors to close; an appendix with an editor open is not deleted (DL-0442) | **0.1** | ST-0061, ST-0062 | Epic 13 |
| the **title page**, to the holder, in the panel below the parts — the switch *Title page* and *Title page text* (plain text, at most 500 characters and 8 lines, line breaks kept) with *Apply* — never *Save*, a word the product does not use (DL-0222); each a draft change committed with the run, the run's changes reading *Title page switched on* or *off*, *Title page text: …*, or *Title page text removed*; refused with the edit tab's reasons to anyone else (DL-0463, DL-0476) | **0.1** | ST-0058 | Epic 16 |
| *Start editing* — when the tab was reached from another site, so a link elsewhere never takes the hold; opened from the application or typed in, the tab takes it as it opens (DL-0319, DL-0325) | **0.1** | ST-0017 | Epic 4 |
| a stopped editor — read-only, what was typed and not captured as changes against its range as it now stands, *back to the edit tab*; *close this editor* on a section editor, the tab drawn again only when no other editor holds text | **0.1** | ST-0059 | Epic 9 |
| inactivity prompt — *are you still working?* with *I am still working*, shown while the hold is idle past the organisation's timeout, released ten minutes later (DL-0377); never for a reserved hold (DL-0221); the *released* notice in a stopped editor once a hold has been ended | **0.1** | ST-0017, ST-0030 | Epic 9 |
| *Finish editing* — opens the send-for-review screen; disabled with its reason while an editor is open | **0.1** | ST-0029 | Epic 4 |
| *Reserve for editing*, to a holder with the right — disabled with its reason while frozen (DL-0252); then *Cancel the reservation* (DL-0218, DL-0219, DL-0223) | **0.1** | ST-0069 | Epic 9 |
| *Discard my edits* whenever the user holds the document, confirmed in a box saying the whole draft — text and files — is thrown away and a reservation ends with it; the page closes its editors first (DL-0237) | **0.1** | ST-0022 | Epic 9 |
| to a reviewer correcting a pending run: that their changes become their own version; after an undo, above the editor, the places left for their hand with the wording before the undone edits and now — an appendix's under *In the appendix “{title}”* — or that everything was undone; that the roles, actions and terms the undone edits declared or relabelled stay as they stand (ADR-0015, DL-0380) | **0.1** | ST-0035, ST-0037 | Epics 5, 15; the appendix's places, Epic 13 |
| the holder's kept draft — after an administrator ended their reservation or forced their hold, an inactivity release or a block — offered back before any new hold: *take the document back* while nothing was committed since; otherwise read-only, as changes against the current text or another version the holder's rights reach, a history right's included (DL-0225, DL-0417); *discard this draft*, confirmed (DL-0381) | **0.1** | ST-0070 | Epic 9 |
| the tab while someone else holds or has reserved the document, or it is frozen and the user lacks *accept* | **0.1** — says so, offers nothing | ST-0017, ST-0038 | Epic 4 |

## Appendix page

The document page's frame for one appendix. The title reads **#12 Annual leave… › {the appendix's title, as its editor typed it} 2.3-1**, the document's number and title linking back to it; the appendix's own number appears only in its URL (ADR-0008); the appendix's own outline; its text numbered from 1, nothing in front; **View** and **Edit** scoped to the appendix — *Edit* opening its editors as the document's edit tab does, *edit the whole appendix* among them — and *Pending edits*, *History* and *My edits* leading to the document's (DL-0443); the right panel's parts and the whole document's generated views, an appendix's places named by its title (DL-0444). **No document actions** — no copy, freeze, make canonical, archive or groups (DL-0207).

| Region | Release | Stories | Built by |
|---|---|---|---|
| the page | **0.1** | ST-0023, ST-0061 | Epic 13 |

## Historical page

One version, opened in a new window: a **banner** across the top — *Historical version 2.0 — read only*, with a link to the current document; the reading view with a collapsible outline; the generated views of that version, as the View tab's; the attachments as that version listed them, each downloadable at that version — `/document/12/version/2.0/attachment/3/` (DL-0421); the appendices as that version listed them, each opening at that version — `/document/12/version/2.0/appendix/2/`, the appendix page's frame under the same banner, without tabs, its places in the generated views linking there; *Export* of that version alone, marked by the chain of the stance it reached where the reader may see its baseline (DL-0426), re-checked against the reader's ceiling when it runs (DL-0423); *compare with* any other version the reader may see, the latest included — not drawn when there is none (two documents are compared from the History tab, DL-0488). Never editable (DL-0195, DL-0208). The versions a reader may open: the current version of each stance their viewing right includes, every version of the pending run with *view pending*, every edition with *view previous canonical versions*, every version up to their highest stance with *view all history* (ADR-0007, DL-0286).

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| the page | **0.1** | the reader's ceiling: a viewing right, widened by a history right | ST-0032, ST-0041 | Epic 15 |
| the generated views of that version — the role directory and *see also*, as the View tab's | **0.1** | as the page | ST-0027, ST-0044 | Epic 11 |
| the appendices at that version, each on its own page | **0.1** | as the page | ST-0032, ST-0061 | Epic 13 |
| *Show edit authors* — the pending tab's toggle, one preference for both (DL-0489): each line of the body names its edit author; while a past version's authors are being worked out, the text without them and a line asking for a reload; worked out on demand and kept for a day (DL-0266) | **0.1** | as the page | ST-0032 | Epic 12 |

## Compare

A **banner** across the top in the historical page's style — *Comparing 2.0 with 2.3-1 — read only* — each version a link to it (DL-0233). Below it, *from* and *to*, chosen among the versions the reader may see, and a *Compare* button that opens the chosen pair as a new page. The newer version in full, with the changes against the older marked in place. A side panel lists the parts in both versions: **appendices** — pick one from each side and *compare appendices*, which opens a page of the same shape for the pair, `/document/12/compare/appendix/?from=2.0:2&to=2.3-1:2`: the banner *Comparing appendices of 2.0 with 2.3-1 — read only*, each side's version and title with a link to the appendix at that version, the newer appendix whole with its changes against the older marked, whichever order was asked, and *Back to the comparison*; **attachments** — each with its file in both versions and whether it was added, changed — its file, title or file name — removed or unchanged; attachments are not compared (DL-0208). On two versions that follow each other among those the reader may see, *previous* and *next* move the pair one version back or forward, skipping the others, disabled at the ends (DL-0361). One version asked against itself opens its historical page. A reader who may see only one version is offered no comparison.

**Comparing two documents** has the same shape. The banner reads *Comparing #12 2.0 with #7 1.0 — read only*, each number linking to its document and each version to its historical page; the heading names both documents. Below it, *from* among the first document's versions the reader may see, *with document* — a number — and *to* among the second's, then *Compare*. The second document's whole text, with its changes against the first's marked in place; the order is the reader's. Each version is one its own document's reader may see; a document the reader may not open, or a version beyond their rights, answers *Nothing to show here*, and a document compared with itself opens its own comparison. Without a *to*, the second document's newest version the reader may see. **The picker**: *with document* empty and no text drawn, opened by *Compare with another document*. The side panel lists **each document's attachments** under its number and version, each downloadable at that version, the two lists not paired (DL-0452), and its **appendices**: one of each document's to compare as a pair — `?from=2.0:2&with=7&to=1.0:1`, the second document's appendix marked against the first's — its *Back to the comparison* returning to the two documents. No *previous* and *next* across documents. It starts from the document page, the historical page and the document list.

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| version comparison, *previous* and *next*, attachment list; appendix comparison | **0.1** | the viewing right for both versions | ST-0033, ST-0041 | Epic 15; appendix comparison Epic 13 |
| comparing two documents — the banner, *from*, *with document* and *to*, the second document's text marked against the first's, each document's attachments; the picker (DL-0452) | **0.1** | a viewing right on each | ST-0064 | Epic 10; the appendices, Epic 13 |

## Send-for-review screen

Within the edit tab, opened by *finish editing* for every holder (DL-0222): the holder's changes, as *my edits*; the change summary — for the reviewer, and kept with the version — drafted mechanically with the sections touched, and editable; the part operations in the draft; the roles, actions and terms the draft adds, relabels or removes — those the commit will declare from marked words included (DL-0440); nothing else in 0.1, the agents' analyses from 0.2 (DL-0261); *finishing ends your reservation* when the document is reserved. Then the choices, each naming what it produces, with the number computed for this document:

| The holder holds | Choices besides *continue editing* and *discard my edits* |
|---|---|
| *edit* | *send for review* — the version waits as `2.3-2` |
| *accept*, which includes *edit* (ADR-0016) — correcting included | *accept as 2.4* — the version is made and the whole run since the last acceptance accepted, other editors' versions named, with the correction notices the acceptance sends (ADR-0014) · *create version 2.3-2* — the version waits in pending edits |

| Region | Release | Stories | Built by |
|---|---|---|---|
| the screen | **0.1**; change summary drafted by the companion **0.2** | ST-0022, ST-0029, ST-0035 | Epic 4; the choices of a holder of *accept* Epic 5; *discard my edits* Epic 9 |

## Export

```
+--------------------------------------------+
| Export — #12                               |
|  What ?   [x] Document                     |
|           [x] Appendices                   |
|               (•) embedded  ( ) separate   |
|           [x] Attachments                  |
|  Format ? (•) PDF  ( ) DOCX  ( ) Markdown  |
|  View ?   (•) Canonical 2.0 ↗              |
|           ( ) Accepted 2.3 ↗               |
|           ( ) Pending edits 2.3-1 ↗        |
|           ( ) My edits — your draft        |
|  Changes ? ( ) marked against 1.0          |
|            (•) clean text                  |
|  Delivered as one zip.        [Export]     |
+--------------------------------------------+
```

| Region | Release | Stories | Built by |
|---|---|---|---|
| *What* checkboxes, all checked by default; parts the document lacks not offered (DL-0236) | **0.1** | ST-0045 | Epic 7; the appendices, Epic 13 |
| *embedded / separate* — disabled unless the document is checked; *Format* — disabled unless the document or appendices are (DL-0207) | **0.1** | ST-0045 | Epic 7; the appendices, Epic 13 |
| *View* — canonical, accepted, pending edits, my edits, as the user's rights allow; each version linking to that version in a new window; a single view is named as text, not offered as a choice (DL-0236) | **0.1** | ST-0045 | Epic 7 |
| *Changes* — *marked against* the previous version in the chain, named: a canonical edition against the previous edition, an accepted version against the current canonical edition, pending edits against the last acceptance, the draft against the current text; or *clean text*. Clean by default for a canonical edition, marked for every other. Not drawn when marks are impossible — a canonical edition for someone with no history right (DL-0241) | **0.1** | ST-0045 | Epic 7 |
| what will be delivered — one file or one zip | **0.1** | ST-0045 | Epic 7; the appendices, Epic 13 |
| *Export* — disabled while nothing is chosen; a message when a chosen part is not in the chosen version, or nothing is left to export (DL-0208) | **0.1** | ST-0045 | Epic 7; the appendices, Epic 13 |
| *?* beside each section's heading — a box of help above the dialog, closed by a click anywhere else; no help text in the layout (DL-0233) | **0.1** | ST-0045 | Epic 7 |
| file names — `<title>_—_<version>_—_<stance>.<ext>`, the stance in the interface's language; a marked export ends in `-позначено` (`-marked`), `<stance>-позначено.<ext>`, and a clean one has none (DL-0359); the title cut at eighty characters; several files a zip of the same name (DL-0275) | **0.1** | ST-0045 | Epic 7 |
| the file's pages — the page number at the foot and no header, the title, version and stance standing in the file's name, and on the title page where the document has one (DL-0182, DL-0362); headings numbered in their text and clause numbers in a light-grey gutter — in DOCX at the start of the paragraph, Word having no gutter — a change of formatting alone marked by its colour; a Markdown file's headings carry their numbers and its clauses none (DL-0363) | **0.1** | ST-0045 | Epic 7 |

## Create or copy a document

Title, language, type — each named in words, never by its code — folder (the root allowed). A **copy** adds the source version — canonical, accepted or pending, among those the user may see — the appendices to take (none, all, chosen), and the notice that attachments are not copied. The new document is reachable only by its author until groups are linked.

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| create | **0.1** | *create and edit* | ST-0009 | Epic 3 |
| copy — opened by *Copy* on the document page: the title prefilled with the source's; the language the source's, shown as text; type and folder as in create; the version — *Pending edits*, *Accepted*, *Canonical* among those the user may see, pending by default, a single one named as text; the appendices — *None*, *All* or *Chosen*, renumbered from 1 in the source's order; *Attachments are not copied.* | **0.1** | *create and edit*, and the source version's viewing right | ST-0067 | Epic 10 |

## Notifications

Two tabs (DL-0204). **Document** — each entry linking to the document at the version concerned, for every event ST-0047 lists; among them a version sent for review; a run returned, with the reason while its reader may still read the pending edits (DL-0369); a **correction notice** — one per acceptance, however many of the author's lines changed (ADR-0014), listed as one line with its counts, *— 1 line and 2 parts changed*, the rest on its own page (DL-0480) — which opens to show, for each, what the author wrote, what was accepted and who changed it, marked, with a link to the passage, and for each part another author's version of the run added, replaced, renamed or removed and a reviewer's version changed, what each did — *You added this attachment in 1.1-1; Reviewer R removed it in 1.1-2* — the part by its title as the author left it, with *open* where the accepted version still holds it; *your reservation was ended*, with who and when, and why beneath it — the reason read here, never in the email (DL-0369); *your editing will soon end for inactivity*, once per idle spell (DL-0377). **Administrative** — users, groups, access, blocks, failed mail, documents without groups, reservations started — with filters, *mark all as read*, and marking one read. Filters and entries for events a person never receives are not drawn: a non-administrator sees their own group changes, each leading to the document list; an administrator's leads to the group. A failed email leads to the outbox that holds it (DL-0385). An entry whose document its reader can no longer open is not drawn and not counted (DL-0386). Opening a notification marks it read.

| Region | Release | Stories | Built by |
|---|---|---|---|
| both tabs | **0.1** | ST-0004, ST-0030, ST-0035, ST-0036, ST-0047, ST-0048, ST-0051, ST-0052, ST-0070 | Epic 14; the correction notice's part entries and counted line, Epic 13 |
| levels a person chooses; a read-and-act workflow | **later** — B-028, B-029 | — | — |

## Help

Pages rendered from Markdown files shipped with the application (DL-0195), `/help/` opening on *reading a document* with the list beside it: how a document moves, versions and their numbers, reviewing and accepting, freezing and editions, history, comparing and undoing, editing, editing together, the allowed Markdown — generated from the same specification as the editor and the parser — reading a document, exporting, appendices and attachments, notifications, mail, people and access, and finding and organising documents. Linked from every paste refusal.

| Region | Release | Stories | Built by |
|---|---|---|---|
| the pages and the allowed-Markdown list — what is accepted and how it is written, and what is refused with the conversion each gets, built from the specification: its limits, entities and callout types, and every refusal with its conversion | **0.1**; the guide's full content B-016 | ST-0019, ST-0060 | Epic 4 |
| *Reading a document* — the version shown, clause numbers, the outline, the parts, *Info*; *Exporting* — the dialog's choices, the file's name, delivery and failures | **0.1** | ST-0045 | Epic 7 |
| *Editing* — *Images*, *Roles, actions and terms*, *Mentions*; *Reading a document* — *Mentions and generated views*; *Exporting* — *Images* | **0.1** | ST-0026, ST-0027, ST-0028, ST-0043, ST-0044 | Epic 11 |
| *Finding and organising documents* — folders and the list, search and the type filter, copying, comparing two documents; for administrators, document types, folders, archive and restore; *Reading a document* — *Comparing two documents*, a pointer here | **0.1** | ST-0012, ST-0013, ST-0015, ST-0016, ST-0064, ST-0067 | Epic 10 |
| *Appendices and attachments* — reading them, the edit tab's parts panel and the rights each act needs, review and *revert*, the correction notice, exporting; the parts' sections of *Exporting*, *History, comparing and undoing*, *Reading a document* and *Reviewing and accepting* | **0.1** | ST-0061, ST-0062, ST-0063 | Epic 13 |
| *People and access* — inviting, a forgotten password, blocking a member and one's own account and lifting a block, several organisations, and the platform administrator's acts | **0.1** | ST-0002, ST-0003, ST-0004, ST-0007, ST-0054, ST-0055, ST-0065, ST-0066 | Epic 8 |
| *Template and styles* — the document template, the title page layout, the stylesheet and what it may hold, the Word files' styles, the sample; the title page's sections of *Editing* and *Exporting* | **0.1** | ST-0046, ST-0058 | Epic 16 |

## Nothing to show here

The one response for a document or folder that does not exist, may not be seen, is archived — to anyone but an administrator — or belongs to another tenant — same status, page and timing (ADR-0008): *Nothing to show here. The link may be incomplete or out of date. Check it, or ask whoever sent it.* — with a way back to the document list.

| Region | Release | Stories | Built by |
|---|---|---|---|
| the page | **0.1** | ST-0015 | Epic 2 |

## Administration

One area with two parts in a left pane: **Platform**, for platform administrators, and **Organisation** — the tenant part — with an organisation selector for platform administrators — active and blocked organisations, a blocked one marked, never one being set up (DL-0376); a tenant administrator sees only that part, for their own organisation. The interface says *organisation* throughout; *tenant* stays in the URLs (ADR-0008). Django's own administration interface is not part of it (DL-0210).

| Section | URL | Holds | Release | Stories | Built by |
|---|---|---|---|---|---|
| hosts | `/administration/platform/hosts/` | the platform's hosts and each tenant's, host with optional port, one default per set; every change audited (ADR-0008) | **0.1** | — | Epic 2 |
| organisations | `…/platform/tenants/` | the organisations with their state and administrators; *block…* confirmed; nothing on one being set up (DL-0291) | **0.1** | ST-0065 | the list Epic 2; *block* Epic 8 |
| organisations — forms | `…/platform/tenants/` | create with a first administrator, lift a block, appoint an administrator | **0.1** | ST-0001, ST-0071 | create Epic 2 — a registered person only; anyone else is invited from the organisation's users page afterwards; lift a block and appoint Epic 8 |
| platform administrators | `…/platform/administrators/` | *grant to* a registered person by address; *revoke* per row; the last one cannot be removed or blocked, the act drawn disabled with its reason (DL-0315) | **0.1** | ST-0002 | the list Epic 2; grant and revoke Epic 8 |
| mail and outbox | `…/platform/mail/` | the platform's sender, the password write-only and asked for again when the server, port, connection or user name changes (DL-0390), a user name refused on an unencrypted connection but to the same machine (DL-0388), *Send a test email*, one at a time; the outbox, its newest 200, with each email's status and attempts (DL-0202, DL-0203, DL-0392) | **0.1** | ST-0048, ST-0049 | Epic 14 |
| audit log | `…/platform/audit/` | what people, the system and agents did | **0.1** | ST-0050 | Epic 12 |
| heuristics | `…/platform/heuristics/` | the catalogue | **0.2** — drawn as a placeholder | — | — |
| users | `/administration/tenant/users/` | each membership by its address alone, never a display name (DL-0403); *invite by email*, with groups to join, answering alike for a known and an unknown address (ASR-17); *block…*, asking which of the organisations one administers; the last active administrator's *block* disabled with its reason; *lift the block* on a membership; a membership's own state alone — a person's own block is shown on no organisation's page, so an invitation of a self-blocked address draws the row a new one does (DL-0398); lifting a self-block is not in 0.1 (DL-0254, B-033) | **0.1** | ST-0003, ST-0004, ST-0066, ST-0072 | Epic 8 |
| groups | `…/tenant/groups/` | a grid of each group's rights — the viewing ladder, history, *accept*, *freeze*, *make canonical*, *reserve for editing*, the part rights; a right included by another shown as a faint tick — *edit* and the views under *accept*, *freeze* and *reserve for editing* (ADR-0016), *view accepted* under *make canonical* (DL-0234); *members…* per group | **0.1** | ST-0005 | Epics 2, 8 |
| document links | `…/tenant/document-links/` | which groups reach which document, as removable chips and *link a group*; locked while held or reserved, with who, and *force the release* or *end the reservation…*; author-only documents with who created them; an archived document's links, which take effect on restore | **0.1** | ST-0005, ST-0015, ST-0030, ST-0051 | Epics 3, 8, 9; the holder Epic 8, the two acts Epic 9 |
| reservations | `…/tenant/reservations/` | every reservation in the organisation: document, holder, since when; *end the reservation…*, to its page, a reason required and told to the holder in the application, never by email (DL-0225, DL-0227, DL-0369, DL-0415) | **0.1** | ST-0030 | Epic 9 |
| folders | `…/tenant/folders/` | the tree with each folder's documents; new, rename; *delete* disabled with its reason when a folder holds anything; *move documents…* — which, and where to | **0.1** | ST-0012 | Epic 10 |
| document types | `…/tenant/document-types/` | this organisation's own list, seeded with *document*; add, rename, retire; delete only a type no document uses, never the seeded one; the last type not retired is neither retired nor deleted (DL-0235, DL-10-001, DL-10-002) | **0.1** | ST-0011 | Epic 10 |
| template | `…/tenant/template/` | the headings and starting text new documents start from, checked against the editor's allowed set and beginning with a `#` heading; the title page switch; *last changed by*; *title page layout…*, a link to its page | **0.1** | ST-0058 | Epic 16 |
| template — title page layout | `…/tenant/template/title-page/` | which details the title page shows — title, number, type, edition, approver, approval date, the document's own title-page text — each shown or not, with its position; the approval line always shown, its position chosen; left or centred; *Reset to the default form*; no logo (DL-0462, DL-0467, DL-0475, DL-0476) | **0.1** | ST-0058 | Epic 16 |
| settings | `…/tenant/settings/` | attachment size cap, inactivity timeout, the distinct-approver check | **0.1** | ST-0030, ST-0053, ST-0062 | Epic 12 |
| sending address | `…/tenant/sending-address/` | the tenant's own sender or none; the password write-only and asked for again when the server, port, connection or user name changes (DL-0390); a user name refused on an unencrypted connection but to the same machine (DL-0388); *Send a test email* — to the address itself, with the step results, one at a time; the DNS note; the organisation's outbox, its newest 200, with each email's status and attempts (DL-0385, DL-0392) — a reset's email listed to a platform administrator alone (DL-0410) | **0.1** | ST-0068 | Epics 14, 8 |
| archive | `…/tenant/archive/` | archived documents, newest archived first, each with the date it was archived: *restore*, *export*; *No document is archived.* when there is none | **0.1** | ST-0015, ST-0016 | Epic 10 |
| styles | `…/tenant/styles/` | the organisation's stylesheet, *used by every document of the organisation*; *apply* checks it against the allowlist, each refusal with its line; the installed fonts; *not carried into Word files*, with lines; *export a sample PDF* and *export a sample Word file* of the text in the box, one at a time, with its progress and link; *last changed by* (DL-0230, DL-0464, DL-0465, DL-0466) | **0.1** | ST-0046 | Epic 16 |
| access history | `…/tenant/access-history/` | a document, or *any document* (every access change up to then, the newest 200), and a date — the end of that day in the installation's timezone — or, for a document, one of its editions, answering at the moment it was approved (DL-0461): which groups could read it then, each linked and each right granted with who did it and when, and its members that day by the membership's own state, each with who added them and when; a line each for a document not yet created, archived, the organisation blocked, no canonical edition yet; the changes to access that led there. People by address (DL-0434) | **0.1** | ST-0006 | Epic 12 |
| actions and side-document types | `…/tenant/actions/` | which are attached to which documents | **0.2** — drawn as a placeholder | — | — |

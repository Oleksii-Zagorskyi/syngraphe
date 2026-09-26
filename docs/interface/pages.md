---
tags:
  - interface
aliases:
  - Syngraphē page wireframes
status: draft
date: 2026-09-26
---

# Pages

The pages of release 0.1: what each holds, which right each control needs, and the release and epic each region belongs to. **They are a design input, not a story:** several epics build from them, and each of those epics links here.

**[`mockup.html`](mockup.html) draws them** — an HTML mockup with synthetic content, opened in a browser. It shows arrangement, not visual style. Where the mockup and this file differ, this file wins.

**Every region carries the release it belongs to.** A region marked for a later release is drawn so the layout has room for it — **it is not built in 0.1**, and an implementer who meets one builds the space, not the feature.

| Marker | Meaning |
|---|---|
| **0.1** | built in release 0.1, by the epic named |
| **0.2** | the AI half, release 0.2 |
| **later** | after 0.1, not yet assigned to a release |

**Rights decide what renders.** A control a user may not use is never drawn for them (ADR-0004, ADR-0007). A page or item the user may not see answers exactly as one that does not exist (ADR-0008).

**Content is at most 1,440 px wide**, centred (DL-0197).

## Page inventory

| Page | URL | Stories | Release |
|---|---|---|---|
| [Shell](#shell) | on every page | ST-0007, ST-0047 | **0.1** |
| [Sign-in pages](#sign-in-pages) | — | ST-0008, ST-0054, ST-0055 | **0.1** |
| [Document list](#document-list) | `/folder/7/`; `/` opens the root, `/folder/1/` | ST-0009, ST-0012 to ST-0014, ST-0018 | **0.1** |
| [In edit, In review](#in-edit-in-review) | own views | ST-0014 | **0.1** |
| [Search results](#search-results) | `/search/?q=…` | ST-0013 | **0.1** |
| [Document page](#document-page) | `/document/12/` and one segment per tab | ST-0017 to ST-0045, ST-0059 to ST-0064 | **0.1** |
| [Appendix page](#appendix-page) | `/document/12/appendix/3/` | ST-0061 | **0.1** |
| [Historical page](#historical-page) | `/document/12/version/2.0/` | ST-0032, ST-0041 | **0.1** |
| [Compare](#compare) | `/document/12/compare/?from=2.0&to=2.3-1` | ST-0033, ST-0041, ST-0064 | **0.1** |
| [Send for review](#send-for-review) | within the edit tab | ST-0022, ST-0029 | **0.1** |
| [Export](#export) | a dialog | ST-0045 | **0.1** |
| [Create or copy a document](#create-or-copy-a-document) | a dialog | ST-0009, ST-0067 | **0.1** |
| [Notifications](#notifications) | `/notifications/` | ST-0047 | **0.1** |
| [Help](#help) | `/help/…` | ST-0019, ST-0060 | **0.1** |
| [Nothing to show here](#nothing-to-show-here) | any address that may not be seen | — | **0.1** |
| [Administration](#administration) | `/administration/platform/…`, `/administration/tenant/…` | ST-0001 to ST-0006, ST-0010, ST-0011, ST-0015, ST-0016, ST-0030, ST-0049, ST-0050, ST-0053, ST-0058, ST-0065, ST-0068 | **0.1** |
| User profile | — | — | **later** — not yet designed |

## Shell

```
+------------------------------------------------------------------------------+
| logo | All documents | In edit | In review | Help | Administration | (!3) | tenant ▾ | me ▾ |
+------------------------------------------------------------------------------+
```

| Region | Release | Needs | Built by |
|---|---|---|---|
| *All documents* | **0.1** | — | Epic 3 |
| *In edit* — documents the user may edit that have versions after their latest canonical edition | **0.1** — shown to holders of *edit* on any document, disabled when empty, no count (DL-0197) | *edit* | Epic 9 |
| *In review* — documents with pending edits the user may accept | **0.1** — likewise | *accept* | Epic 9 |
| *Help* | **0.1** | — | Epic 7 |
| *Administration* | **0.1** | tenant or platform administrator | Epic 8 |
| notifications — unread count, opening the notifications page | **0.1** | — | Epic 8 |
| tenant switcher — only with several memberships; on a tenant's own domain, switching moves to the other tenant's domain (ADR-0008) | **0.1** | — | Epic 2 |
| user menu — sign out, *block my account* (confirmed) | **0.1** | — | Epic 2; self-block Epic 8 |

## Sign-in pages

Sign in, accept an invitation, reset a password: small forms without navigation, each answering identically whether or not an address is known (ASR-17). On a tenant's own domain, signing in lands in that tenant.

| Region | Release | Built by |
|---|---|---|
| the three forms | **0.1** | Epic 2; invitation and reset Epic 8 |

## Document list

```
+--------------+---+-----------------------------------------------------------------+
| ▾ Example Org|   | [ search titles of documents and appendices ] [+ create] [Folders ▾] |
|  ▾ Policies  | ↔ | #   Title ▲                        Type    Canonical  Latest  Parts  ✎ |
|   ▸ **HR**   |   | 12  Annual leave, sick leave and…  policy  2.0        2.3-1   A  F   ✎ |
|   ▸ Finance  |   |     [being edited]                                               |
|  ▸ Procedures|   | 7   Travel rules                   policy  1.0                a  f   ✎ |
+--------------+---+-----------------------------------------------------------------+
```

*Titles are synthetic examples.* `↔` a draggable edge · `A` / `a` appendices present / absent · `F` / `f` attachments present / absent — drawn as dark and faint icons.

| Region | Release | Needs | Built by |
|---|---|---|---|
| folder tree — no heading; ▸ ▾ to collapse; root named after the tenant; the selected folder in bold; always a folder selected (DL-0197) | **0.1** | — | Epic 10 |
| folder visibility — only folders holding, at any depth, a document the user may read; administrators see all; alphabetical (DL-0206) | **0.1** | — | Epic 10 |
| draggable pane edge; the width kept in the user's preferences (DL-0195) | **0.1** | — | Epic 10 |
| *Folders ▾* — new, rename, delete an empty folder, move documents | **0.1** | tenant administrator | Epic 10 |
| search box — titles of documents and appendices only, never text | **0.1** | — | Epic 10 |
| *create* | **0.1** | *create and edit* | Epic 3 |
| `#` — the document's number (ADR-0008) | **0.1** | — | Epic 3 |
| title — takes the free width; *being edited* after it, the fact and never the person; opens the reading view | **0.1** | — | Epics 3, 4 |
| sorting — by `#` or title, ascending or descending; title A to Z by default | **0.1** | — | Epic 10 |
| *Canonical* — the canonical number, linking to that version | **0.1** | — | Epic 6 |
| *Latest* — the latest version the user may see beyond canonical, else empty; links where the title does (DL-0208, DL-0209) | **0.1** | — | Epic 6 |
| part markers — presence, not count | **0.1** | — | Epic 3 |
| ✎ — opens the edit tab | **0.1** | *edit* | Epic 4 |

## In edit, In review

The document list's shape, reached from the menu: matching documents grouped under a heading per folder path, the groups alphabetical, sorting within each group; the folder tree shows only folders holding matches (DL-0197, DL-0207).

| Region | Release | Built by |
|---|---|---|
| grouped list, filtered tree | **0.1** | Epic 9 |

## Search results

As *In edit*: results grouped under a heading per folder path, alphabetical groups, sorting within each group, the tree cut to *folders with found documents*.

| Region | Release | Built by |
|---|---|---|
| grouped results, filtered tree | **0.1** | Epic 10 |

## Document page

```
+------------------------------------------------------------------------------+
| Policies / Human resources /                                                 |
| #12 Annual leave, sick leave and parental leave: how employees…  2.3-1 [being edited] |
| [Export] [Copy] [Freeze] [Make canonical] [Groups] [Archive] [More ▾]         |
+-----------+---+-------------------------------------------+---+--------------+
| OUTLINE ⇤ |   | View  Edit  My edits  Pending edits       |   | [P][G][C]  ⇥ |
| ▾ 1       | ↔ | History  Analysis  Info                   | ↔ |              |
|   1.1     |   | Viewing the 2.3-1 version · open canonical 2.0 ↗ |   | comments,    |
| ▾ 3       |   |                                           |   | parts or     |
|   ▾ 3.1   |   | tab content                               |   | generated    |
|     3.1.1 |   |                                           |   | views        |
+-----------+---+-------------------------------------------+---+--------------+
```

`[P][G][C]` — the icon row switching the panel between parts, generated views and comments.

| Region | Release | Needs | Built by |
|---|---|---|---|
| breadcrumb, `#12`, title, the **latest version the reader may see** — never a version beyond their rights (DL-0209) | **0.1** | — | Epic 4 |
| state badges — *being edited* (the tenant administrator sees who), *frozen* with its reason, *archived* (administrators only; to everyone else an archived document does not exist) | **0.1** | — | Epics 4, 6 |
| *Export*, *Copy* | **0.1** | any viewing right; *create and edit* | Epics 7, 10 |
| *Freeze* / *Unfreeze* — refused while anyone is editing | **0.1** | *freeze* | Epic 6 |
| *Make canonical* — while frozen, no unaccepted commits | **0.1** | *make canonical* | Epic 6 |
| *Groups* — locked while anyone is editing | **0.1** | tenant administrator | Epic 8 |
| *Archive* / *Restore*; *More ▾* holds *force release* | **0.1** | tenant administrator | Epics 8, 9 |
| outline — every heading level, ▸ ▾, no appendices; collapsible and resizable | **0.1** | — | Epic 7 |
| right panel — the icon row; collapsible and resizable; widths kept per user (DL-0194, DL-0195) | **0.1**; comments **later** (B-013); the agents' views **0.2** | — | Epics 3, 4, 7 |
| parts — appendices in their order, *add*, rename, reorder, delete; attachments with download, *add*, replace, rename, reorder, delete | **0.1** | *edit*; the part rights (ADR-0007) | Epics 3, 4 |
| generated views — role directory, see also | **0.1**; contradictions, ambiguities, blind spots **0.2** | — | Epics 11, 10 |

### The tabs

| Tab | URL segment | Shows | Release | Needs |
|---|---|---|---|---|
| View | — | the latest version the reader may see, with *Viewing the 2.3-1 version · open canonical 2.0* (DL-0209); to a reader who may see only canonical text, a document with no canonical edition yet does not exist; clause numbers in the gutter; entities in their own formatting | **0.1** | any viewing right |
| Edit | `edit/` | below | **0.1** | *edit*; while frozen, *accept* and *edit* |
| My edits | `my-edits/` | the holder's draft: the whole document, the draft's changes marked in place | **0.1** | the holder |
| Pending edits | `pending/` | the whole document, every change since the last acceptance marked in place and attributed; formatting-only changes marked; part operations with both versions; *show author*, hiding or showing who made each change (DL-0040); the change summary, for the reviewer; *Correct*, *Accept the run*, *Return with a reason* | **0.1** | *view pending*; *accept* for the acts |
| History | `history/` | per version: number, event (edit, acceptance, return, freeze, canonisation), who, when, *open* — in a new window as a historical page; the accepted boundary; *compare two versions*, *compare with another document* | **0.1** | *view all history*; *view previous canonical versions* for editions only |
| Analysis | `analysis/` | the mechanical analyses; the agents' from 0.2 | **0.1**; agents **0.2** | *edit* |
| Info | `info/` | number, title, language, type, folder, canonical version, state, title page, style, linked groups (administrators), created | **0.1** | any viewing right |

### The edit tab

| Region | Release | Built by |
|---|---|---|
| *edit* beside each `#` section, several open at once; *edit whole document* only when none is open | **0.1** | Epic 4 |
| a section editor opened in place, the rest rendered around it; toolbar exactly the whitelist, *mark* for entities; *rich / markdown* | **0.1**; *mark* Epic 11 | Epic 4 |
| paste refusal — the lines named, a previewed conversion, a link to help | **0.1** | Epic 4 |
| capture indicator — no Save control | **0.1** | Epic 4 |
| a stopped editor — read-only, its unsaved text as changes against the draft | **0.1** | Epic 4 |
| inactivity prompt — *are you still working?* | **0.1** | Epic 4 |
| *Send for review* — refused while an editor is open | **0.1** | Epic 4 |
| the tab while someone else holds the document, or it is frozen and the user lacks *accept* | **0.1** — says so, offers nothing | Epic 4 |

## Appendix page

The document page's frame for one appendix. The title reads **#12 Annual leave… › {the appendix's title, as its editor typed it} 2.3-1**, the document's number and title linking back to it; the appendix's own number appears only in its URL (ADR-0008); the appendix's own outline; the same tabs and right panel. **No document actions** — no copy, freeze, make canonical, archive or groups (DL-0207).

| Region | Release | Built by |
|---|---|---|
| the page | **0.1** | Epics 3, 4 |

## Historical page

One version, opened in a new window: a **banner** across the top — *Historical version 2.0 — read only*, with a link to the current document; the reading view with a collapsible outline; *Export*; *compare with* any other version, the latest included. Never editable (DL-0195, DL-0208).

| Region | Release | Needs | Built by |
|---|---|---|---|
| the page | **0.1** | the version's viewing right | Epic 6 |

## Compare

*From* and *to*, chosen among the versions the reader may see, each linking to its version; *swap*. The newer version in full, with the changes against the older marked in place. A side panel lists the parts in both versions: **appendices** — pick one from each side and *compare appendices*, which opens a page of the same shape for the pair; **attachments** — each with its file in both versions and whether it was added, changed or unchanged; attachments are not compared (DL-0208). Comparing with another document works the same way.

| Region | Release | Needs | Built by |
|---|---|---|---|
| version comparison, appendix comparison, attachment list | **0.1** | the viewing right for both versions | Epic 6; across documents Epic 10 |

## Send for review

Within the edit tab: the change summary — for the reviewer, and the commit message; the part operations in the draft; *continue editing*, *send for review*, *discard my edits* (confirmed); the mechanical analyses, the agents' from 0.2.

| Region | Release | Built by |
|---|---|---|
| the screen | **0.1**; change summary drafted by the companion **0.2** | Epic 4 |

## Export

```
+--------------------------------------------+
| Export — #12                            ?  |
|  What    [x] Document                      |
|          [x] Appendices                    |
|              (•) embedded  ( ) separate    |
|          [x] Attachments                   |
|  Format  (•) PDF  ( ) DOCX  ( ) Markdown   |
|  View    (•) Canonical 2.0 ↗               |
|          ( ) Accepted 2.3 ↗                |
|          ( ) Pending edits 2.3-1 ↗         |
|          ( ) My edits, marked | clean      |
|  Delivered as one zip.        [Export]     |
+--------------------------------------------+
```

| Region | Release | Built by |
|---|---|---|
| *What* checkboxes, all checked by default; parts the document lacks not offered | **0.1** | Epic 7 |
| *embedded / separate* — disabled unless the document is checked; *Format* — disabled unless the document or appendices are (DL-0207) | **0.1** | Epic 7 |
| view choices — canonical, accepted, pending edits, my edits marked or clean, as the user's rights allow; each version linking to that version in a new window | **0.1** | Epic 7 |
| what will be delivered — one file or one zip | **0.1** | Epic 7 |
| *Export* — disabled while nothing is chosen; a message when a chosen part is not in the chosen version, or nothing is left to export (DL-0208) | **0.1** | Epic 7 |
| *?* — help on the choices | **0.1** | Epic 7 |
| file names | **0.1** — to be decided | Epic 7 |

## Create or copy a document

Title, language, type, folder (the root allowed). A **copy** adds the source version — canonical, accepted or pending, among those the user may see — the appendices to take (none, all, chosen), and the notice that attachments are not copied. The new document is reachable only by its author until groups are linked.

| Region | Release | Needs | Built by |
|---|---|---|---|
| create | **0.1** | *create and edit* | Epic 3 |
| copy | **0.1** | *create and edit*, and the source version's viewing right | Epic 10 |

## Notifications

Two tabs (DL-0204). **Document** — each entry linking to the document at the version concerned. **Administrative** — users, groups, access, blocks, failed mail, documents without groups — with filters, *mark all as read*, and marking one read. Opening a notification marks it read.

| Region | Release | Built by |
|---|---|---|
| both tabs | **0.1** | Epic 8 |
| levels a person chooses; a read-and-act workflow | **later** — B-028, B-029 | — |

## Help

Pages rendered from Markdown files shipped with the application (DL-0195): how a document moves, versions and their numbers, editing whole documents and sections, parts, the allowed Markdown — generated from the same specification as the editor and the parser — and exporting. Linked from every paste refusal and from the export dialog's *?*.

| Region | Release | Built by |
|---|---|---|
| the pages and the allowed-Markdown list | **0.1**; the guide's full content B-016 | Epics 4, 7 |

## Nothing to show here

The one response for a document or folder that does not exist, may not be seen, is archived, or belongs to another tenant — same status, page and timing (ADR-0008): *Nothing to show here. The link may be incomplete or out of date. Check it, or ask whoever sent it.* — with a way back to the document list.

| Region | Release | Built by |
|---|---|---|
| the page | **0.1** | Epic 2 |

## Administration

One area with two parts in a left pane: **Platform**, for platform administrators, and **Tenant**, with a tenant selector for platform administrators; a tenant administrator sees only the tenant part, for their own tenant. Django's own administration interface is not part of it (DL-0210). The tenant sections are drawn at outline level; their detail is not yet designed.

| Section | URL | Holds | Release | Built by |
|---|---|---|---|---|
| hosts | `/administration/platform/hosts/` | the platform's hosts and each tenant's, host with optional port, one default per set; every change audited (ADR-0008) | **0.1** | Epic 2 |
| tenants | `…/platform/tenants/` | create with a first administrator, block, appoint an administrator | **0.1** | Epic 2 |
| platform administrators | `…/platform/administrators/` | grant; the last one cannot be removed or blocked | **0.1** | Epic 2 |
| document types | `…/platform/document-types/` | the platform-wide list | **0.1** | Epic 10 |
| mail and outbox | `…/platform/mail/` | the platform's sender, the password write-only, *Send a test email*; the outbox with each email's status and attempts (DL-0202, DL-0203) | **0.1** | Epic 8 |
| audit log | `…/platform/audit/` | what people, the system and agents did | **0.1** | Epic 12 |
| users | `/administration/tenant/users/` | invite by email; block, asked which of one's tenants | **0.1** | Epic 8 |
| groups | `…/tenant/groups/` | a grid of each group's rights; members | **0.1** | Epic 8 |
| document links | `…/tenant/document-links/` | which groups reach which document; locked while held; author-only documents | **0.1** | Epic 8 |
| folders | `…/tenant/folders/` | the tree; new, rename, delete when empty | **0.1** | Epic 10 |
| template | `…/tenant/template/` | the outline new documents start from; the title page switch and layout | **0.1** | Epic 3; title page Epic 7 |
| settings | `…/tenant/settings/` | attachment size cap, inactivity timeout, the distinct-approver check | **0.1** | Epic 8 |
| sending address | `…/tenant/sending-address/` | the tenant's own sender or none; the password write-only; *Send a test email* — to the address itself, with the step results; the DNS note | **0.1** | Epic 8 |
| archive | `…/tenant/archive/` | archived documents: restore, export | **0.1** | Epic 10 |
| access history | `…/tenant/access-history/` | who could read what on a given date | **0.1** | Epic 12 |
| styles | `…/tenant/styles/` | the export stylesheet and which document uses which (ST-0046) | **0.1** | Epic 7 |
| actions and side-document types | `…/tenant/actions/` | which are attached to which documents | **0.2** | — |
| heuristics | `…/platform/heuristics/` | the catalogue | **0.2** | — |

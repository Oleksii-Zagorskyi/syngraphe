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
| [Document list](#document-list) | `/folder/7/`; `/` opens the root, `/folder/1/` | ST-0009, ST-0012, ST-0013, ST-0014, ST-0018, ST-0051, ST-0052 | **0.1** |
| [In edit, In review](#in-edit-in-review) | `/in-edit/`, `/in-review/` | ST-0013, ST-0014 | **0.1** |
| [Search results](#search-results) | `/search/?q=…` | ST-0013 | **0.1** |
| [Document page](#document-page) | `/document/12/` and one segment per tab | ST-0005, ST-0010, ST-0014, ST-0015, ST-0016, ST-0017, ST-0018, ST-0019, ST-0020, ST-0021, ST-0022, ST-0023, ST-0024, ST-0026, ST-0027, ST-0028, ST-0029, ST-0030, ST-0031, ST-0032, ST-0033, ST-0034, ST-0035, ST-0036, ST-0037, ST-0038, ST-0039, ST-0040, ST-0041, ST-0042, ST-0043, ST-0044, ST-0045, ST-0051, ST-0052, ST-0053, ST-0059, ST-0060, ST-0061, ST-0062, ST-0063, ST-0064, ST-0067, ST-0069, ST-0070 | **0.1** |
| [Appendix page](#appendix-page) | `/document/12/appendix/3/` | ST-0023, ST-0061 | **0.1** |
| [Historical page](#historical-page) | `/document/12/version/2.0/` | ST-0032, ST-0041 | **0.1** |
| [Compare](#compare) | `/document/12/compare/?from=2.0&to=2.3-1` | ST-0033, ST-0041, ST-0064 | **0.1** |
| [Send-for-review screen](#send-for-review-screen) | within the edit tab, opened by *finish editing* | ST-0022, ST-0029, ST-0035 | **0.1** |
| [Export](#export) | a dialog | ST-0045 | **0.1** |
| [Create or copy a document](#create-or-copy-a-document) | a dialog | ST-0009, ST-0067 | **0.1** |
| [Notifications](#notifications) | `/notifications/` | ST-0004, ST-0030, ST-0035, ST-0036, ST-0047, ST-0048, ST-0051, ST-0052, ST-0070 | **0.1** |
| [Help](#help) | `/help/…` | ST-0019, ST-0060 | **0.1** |
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
| *In review* — documents with pending edits the user may accept, returned runs included | **0.1** — likewise | *accept* | ST-0014 | Epics 14, 10 |
| *Help* | **0.1** | — | ST-0019 | Epic 4 |
| *Administration* | **0.1** | tenant or platform administrator | — | Epic 2 |
| notifications — unread count, opening the notifications page | **0.1** | — | ST-0047 | Epic 14 |
| tenant switcher — only with several memberships; on a tenant's own domain, switching moves to the other tenant's domain (ADR-0008) | **0.1** | — | ST-0007 | Epic 8; the tenant's name Epic 2 |
| user menu — *My reservations*, each document with its start date, drawn only for a holder of *reserve for editing* (DL-0241); *block my account…*, confirmed; *sign out* | **0.1** | — | ST-0066, ST-0069 | Epic 2; self-block Epic 8; reservations Epic 9 |

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
| ▾ Example Org|   | [ search titles of documents and appendices ] [+ create] [Folders ▾] |
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
| filter by type | **0.1** — not yet drawn | — | ST-0013 | Epic 10 |
| *create* | **0.1** | *create and edit* | ST-0009 | Epic 3 |
| `#` — the document's number (ADR-0008) | **0.1** | — | ST-0013 | Epic 3 |
| title — takes the free width; opens the reading view | **0.1** | — | ST-0013 | Epics 3, 4 |
| state tags after the title — *held* (DL-0262), the fact and never the person except to a tenant administrator (ADR-0006); *reserved for editing, since* its date, with who to holders of *edit* or *accept* and to administrators (DL-0226); *frozen*; *awaiting review* and *returned* to those who may see pending edits (DL-0233); *no reviewer assigned* to those, and to administrators | **0.1** | — | ST-0014, ST-0018, ST-0051, ST-0052 | Epics 5, 6, 9, 15 |
| sorting — by `#` or title, ascending or descending; title A to Z by default | **0.1** | — | ST-0013 | Epic 10 |
| *Canonical* — the canonical number, linking to that version | **0.1** | — | ST-0013 | Epic 6 |
| *Latest* — the latest version the user may see beyond canonical, else empty; links where the title does (DL-0208, DL-0209). **Drawn only for someone who may see beyond canonical text on at least one document** (DL-0233) | **0.1** | — | ST-0013, ST-0014 | Epic 6 |
| part markers — presence, not count | **0.1** | — | ST-0013 | Epic 3 |
| ✎ — opens the edit tab | **0.1** | *edit* | ST-0013 | Epic 4 |

An archived document leaves the list for everyone, administrators included; they reach it through Administration › Archive (DL-0233).

## In edit, In review

The document list's shape, each a page of its own reached from the menu: matching documents grouped under a heading per folder path, the groups alphabetical, sorting within each group; the folder tree shows only folders holding matches (DL-0197, DL-0207).

| Region | Release | Stories | Built by |
|---|---|---|---|
| grouped list, filtered tree | **0.1** | ST-0013, ST-0014 | Epics 14, 10 |

## Search results

As *In edit*: results grouped under a heading per folder path, alphabetical groups, sorting within each group, the tree cut to *folders with found documents*. A group left empty by the reader's rights, and its folder, are not drawn.

| Region | Release | Stories | Built by |
|---|---|---|---|
| grouped results, filtered tree | **0.1** | ST-0013 | Epic 10 |

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
| **bands** across the top — *reserved for editing* since its date, with who to holders of *edit* or *accept* and administrators, and what waits until it ends; *reserved for editing by you*, to its holder; *frozen* with its reason, and the name of who froze it to holders of a history right and administrators (DL-0236); *your reservation was ended*, to its holder, with who, when and why, and *take the document back* when nothing was committed since (DL-0225) | **0.1** | — | ST-0018, ST-0038, ST-0069, ST-0070 | Epics 9, 6 |
| the notice after *send for review* — *Sent for review — the version waits as 2.3-2*, to the one who sent it (DL-0322) | **0.1** | — | ST-0029 | Epic 4 |
| breadcrumb, `#12`, title, the **latest version the reader may see** — never a version beyond their rights (DL-0209) | **0.1** | — | ST-0042 | Epics 3, 6 |
| state tags, as in the list; *archived* to administrators only — to everyone else an archived document does not exist | **0.1** | — | ST-0014, ST-0015, ST-0018, ST-0051, ST-0052 | Epics 5, 6, 9, 10, 15 |
| *Export*, *Copy* | **0.1** | any viewing right; *create and edit* | ST-0045, ST-0067 | Epics 7, 10 |
| *Freeze* / *Unfreeze* — disabled with its reason while anyone holds or has reserved the document (DL-0223) | **0.1** | *freeze* | ST-0038, ST-0040 | Epic 6 |
| *Make canonical* — disabled with its reason until the document is frozen, and while changes are unaccepted; to someone who may not see pending edits the reason names no pending number | **0.1** | *make canonical* | ST-0039, ST-0053 | Epic 6 |
| *Groups* — locked, with who holds the document, while it is held or reserved | **0.1** | tenant administrator | ST-0005 | Epic 8 |
| *Archive* / *Restore*; *More ▾* holds *force release* for an ordinary hold and *end the reservation…* for a reserved one, a reason required (DL-0225) | **0.1** | tenant administrator | ST-0015, ST-0016, ST-0030 | Epics 10, 9 |
| outline — every heading level, ▸ ▾, no appendices; collapsible and resizable | **0.1** | — | ST-0024 | Epic 7 |
| right panel — the icon row; collapsible and resizable; widths kept per user (DL-0194, DL-0195) | **0.1**; comments **later** (B-013), drawn as a placeholder; the agents' views **0.2**, likewise | — | — | Epics 3, 4, 7 |
| parts — appendices in their order, *add*, rename, reorder, delete; attachments with download, *add*, replace, rename, reorder, delete — the changing controls only while holding the document; a file above the organisation's limit refused with the limit | **0.1** | any viewing right for the list and downloads; *edit* and the part rights for the changing controls (ADR-0007) | ST-0061, ST-0062 | Epic 13; its thinnest form — the attachments with title, file name, size and download, in an *Attachments* section of the *View* tab until the panel exists — Epic 18 (DL-0349) |
| generated views — role directory, see also | **0.1** — their content not yet drawn; contradictions, ambiguities, blind spots **0.2** | — | ST-0027, ST-0044 | Epic 11 |

### The tabs

| Tab | URL segment | Shows | Release | Needs | Stories |
|---|---|---|---|---|---|
| View | — | the latest version the reader may see, with *Viewing the 2.3-1 version · open canonical 2.0* (DL-0209), or *Viewing canonical 2.0* to a reader of canonical text only; to such a reader a document with no canonical edition yet does not exist; clause numbers in the gutter; entities in their own formatting. Until editions exist, the view shows the latest accepted version to a holder of *view accepted*, headed *Accepted version 0.1* and without a number before any acceptance, with clause numbers inline, no outline, and an *Attachments* section above the text (DL-0348, DL-0349) | **0.1** | any viewing right | ST-0023, ST-0026, ST-0042 |
| View, mentions | — | a mention of another document as a link where the reader may open it, as plain text where not | **0.1** — not yet drawn | any viewing right | ST-0043 |
| Edit | `edit/` | below | **0.1** | *edit* — which *accept*, *freeze* and *reserve for editing* include (ADR-0016); while frozen, *accept* | ST-0017, ST-0019 to ST-0022, ST-0028, ST-0035, ST-0059, ST-0060, ST-0069, ST-0070 |
| My edits | `my-edits/` | the holder's draft: the whole document, the draft's changes marked in place | **0.1** | the holder | ST-0031 |
| Pending edits | `pending/` | the whole document, every change since the last acceptance marked in place and attributed; formatting-only changes marked; **a changed image before and after, side by side**; the run's versions with their change summaries; **every part operation** — added, replaced, renamed, reordered, deleted — with each file's versions to download and, for a reviewer, *revert*, which takes the document and joins the correction; *show author* (DL-0040); *Correct*, *Accept the run* (confirmed, naming the versions accepted and the number that results), *Return with a reason* (the reason required) — each disabled with its reason while the document is reserved, the holder's own reservation included — a holder of *accept* accepts through *accept as* on the send-for-review screen (DL-0222, DL-0224); *Correct* also while an author holds the document | **0.1** | *view pending*; *accept* for the acts | ST-0031, ST-0034, ST-0035, ST-0036, ST-0052, ST-0063 |
| History | `history/` | per version: number, event (edit, a reviewer's version, acceptance, return, canonisation), who, when — and the freezes and unfreezes between them; *open* — in a new window as a historical page; the accepted boundary; to a holder of *view previous canonical versions* only, the editions alone; to a holder of *accept* without a history right, the pending run alone (DL-0251); *compare two versions*, *compare with another document*. On the pending run, for a reviewer: **undo this edit** and **undo all of this author's edits since the acceptance** — the reversal goes into the reviewer's draft, which opens; what reverted is listed, and what a later version changed is left for editing by hand (ADR-0015) | **0.1** | *view all history*; *view previous canonical versions* for editions only; *accept* for the pending run and to undo | ST-0032, ST-0033, ST-0037, ST-0041, ST-0064 |
| Analysis | `analysis/` | the agents' analyses, drawn as a placeholder; release 0.1 has no analyses of its own (DL-0261) | **0.2**, drawn, not built (DL-0228) | *edit* | — |
| Info | `info/` | number, title, language, type — a choice for administrators — folder, canonical version, state, title page, style, linked groups (administrators), created | **0.1** | any viewing right | ST-0010 |

### The edit tab

| Region | Release | Stories | Built by |
|---|---|---|---|
| *edit* beside each `#` section, several open at once; *edit whole document* only when none is open — disabled with its reason otherwise | **0.1** | ST-0059 | Epic 9 |
| a section editor opened in place, the rest rendered around it; toolbar exactly the whitelist — *quote* among it (DL-0238) — *undo* and *redo* (DL-0241), *mark* for entities; *rich / markdown* | **0.1** | ST-0019, ST-0021, ST-0026, ST-0060 | Epics 4, 9; *mark* Epic 11 |
| paste refusal — the lines named, the converted text previewed, *paste converted*, a link to help; an image left out of a paste with a one-line notice (DL-0232) | **0.1** | ST-0019, ST-0028 | Epic 4 |
| image refusal — the format or the size. A pasted or dropped image becomes an upload and a paragraph of its own; an image that is only a web address is left out of the paste, with a one-line notice to save it and paste the file, which blocks nothing (DL-0232) | **0.1** | ST-0019, ST-0028 | Epic 11 |
| capture indicator — no Save control | **0.1** | ST-0020 | Epic 4 |
| *Start editing* — when the tab was reached from another site, so a link elsewhere never takes the hold; opened from the application or typed in, the tab takes it as it opens (DL-0319, DL-0325) | **0.1** | ST-0017 | Epic 4 |
| a stopped editor — read-only, its unsaved text as changes against the draft | **0.1** | ST-0059 | Epic 9 |
| inactivity prompt — *are you still working?*; never for a reserved hold (DL-0221) | **0.1** | ST-0017, ST-0030 | Epic 9 |
| *Finish editing* — opens the send-for-review screen; disabled with its reason while an editor is open | **0.1** | ST-0029 | Epic 4 |
| *Reserve for editing*, to a holder with the right — disabled with its reason while frozen (DL-0252); then *Cancel the reservation* (DL-0218, DL-0219, DL-0223) | **0.1** | ST-0069 | Epic 9 |
| *Discard my edits* whenever the user holds the document, confirmed in a box saying the whole draft is thrown away and a reservation ends with it (DL-0237) | **0.1** | ST-0022 | Epic 9 |
| to a reviewer correcting a pending run: that their changes become their own version; after an undo, what reverted and what is left for them (ADR-0015) | **0.1** | ST-0035, ST-0037 | Epics 5, 15 |
| the holder's draft after an administrator ended their reservation and someone committed since — read-only, as changes against the current text or any version they choose (DL-0225) | **0.1** | ST-0070 | Epic 9 |
| the tab while someone else holds or has reserved the document, or it is frozen and the user lacks *accept* | **0.1** — says so, offers nothing | ST-0017, ST-0038 | Epic 4 |

## Appendix page

The document page's frame for one appendix. The title reads **#12 Annual leave… › {the appendix's title, as its editor typed it} 2.3-1**, the document's number and title linking back to it; the appendix's own number appears only in its URL (ADR-0008); the appendix's own outline; the same tabs and right panel. **No document actions** — no copy, freeze, make canonical, archive or groups (DL-0207).

| Region | Release | Stories | Built by |
|---|---|---|---|
| the page | **0.1** | ST-0023, ST-0061 | Epic 13 |

## Historical page

One version, opened in a new window: a **banner** across the top — *Historical version 2.0 — read only*, with a link to the current document; the reading view with a collapsible outline; *Export*; *compare with* any other version the reader may see, the latest included — not drawn when there is none. Never editable (DL-0195, DL-0208).

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| the page | **0.1** | the version's viewing right | ST-0032, ST-0041 | Epic 15 |

## Compare

A **banner** across the top in the historical page's style — *Comparing 2.0 with 2.3-1 — read only* — each version a link to it (DL-0233). Below it, *from* and *to*, chosen among the versions the reader may see, and a *Compare* button that opens the chosen pair as a new page. The newer version in full, with the changes against the older marked in place. A side panel lists the parts in both versions: **appendices** — pick one from each side and *compare appendices*, which opens a page of the same shape for the pair; **attachments** — each with its file in both versions and whether it was added, changed or unchanged; attachments are not compared (DL-0208). Comparing with another document works the same way. A reader who may see only one version is offered no comparison.

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| version comparison, appendix comparison, attachment list | **0.1** | the viewing right for both versions | ST-0033, ST-0041 | Epic 15 |
| comparing two documents — the document picker, and the start from the document list | **0.1** — not yet drawn | a viewing right on each | ST-0064 | Epic 10 |

## Send-for-review screen

Within the edit tab, opened by *finish editing* for every holder (DL-0222): the holder's changes, as *my edits*; the change summary — for the reviewer, and kept with the version — drafted mechanically with the sections touched, and editable; the part operations in the draft; nothing else in 0.1, the agents' analyses from 0.2 (DL-0261); *finishing ends your reservation* when the document is reserved. Then the choices, each naming what it produces, with the number computed for this document:

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
| *What* checkboxes, all checked by default; parts the document lacks not offered (DL-0236) | **0.1** | ST-0045 | Epic 7 |
| *embedded / separate* — disabled unless the document is checked; *Format* — disabled unless the document or appendices are (DL-0207) | **0.1** | ST-0045 | Epic 7 |
| *View* — canonical, accepted, pending edits, my edits, as the user's rights allow; each version linking to that version in a new window; a single view is named as text, not offered as a choice (DL-0236) | **0.1** | ST-0045 | Epic 7 |
| *Changes* — *marked against* the previous version in the chain, named: a canonical edition against the previous edition, an accepted version against the current canonical edition, pending edits against the last acceptance, the draft against the current text; or *clean text*. Clean by default for a canonical edition, marked for every other. Not drawn when marks are impossible — a canonical edition for someone with no history right (DL-0241) | **0.1** | ST-0045 | Epic 7 |
| what will be delivered — one file or one zip | **0.1** | ST-0045 | Epic 7 |
| *Export* — disabled while nothing is chosen; a message when a chosen part is not in the chosen version, or nothing is left to export (DL-0208) | **0.1** | ST-0045 | Epic 7 |
| *?* beside each section's heading — a box of help above the dialog, closed by a click anywhere else; no help text in the layout (DL-0233) | **0.1** | ST-0045 | Epic 7 |
| file names — `<title>_—_<version>_—_<stance>.<ext>`, the stance in the interface's language; a marked export ends in a suffix naming the marks, in the same language, `<stance>-<marks>.<ext>`, and a clean one has none; several files a zip of the same name (DL-0275) | **0.1** | ST-0045 | Epic 7 |

## Create or copy a document

Title, language, type, folder (the root allowed). A **copy** adds the source version — canonical, accepted or pending, among those the user may see — the appendices to take (none, all, chosen), and the notice that attachments are not copied. The new document is reachable only by its author until groups are linked.

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| create | **0.1** | *create and edit* | ST-0009 | Epic 3 |
| copy | **0.1** — not yet drawn | *create and edit*, and the source version's viewing right | ST-0067 | Epic 10 |

## Notifications

Two tabs (DL-0204). **Document** — each entry linking to the document at the version concerned, for every event ST-0047 lists; among them a version sent for review; a run returned, with the reason; a **correction notice** — one per acceptance, however many of the author's lines changed (ADR-0014) — which opens to show, for each, what the author wrote, what was accepted and who changed it, marked, with a link to the passage; *your reservation was ended*, with who, when and why. **Administrative** — users, groups, access, blocks, failed mail, documents without groups, reservations started — with filters, *mark all as read*, and marking one read. Filters and entries for events a person never receives are not drawn: a non-administrator sees their own group changes. Opening a notification marks it read.

| Region | Release | Stories | Built by |
|---|---|---|---|
| both tabs | **0.1** | ST-0004, ST-0030, ST-0035, ST-0036, ST-0047, ST-0048, ST-0051, ST-0052, ST-0070 | Epic 14 |
| levels a person chooses; a read-and-act workflow | **later** — B-028, B-029 | — | — |

## Help

Pages rendered from Markdown files shipped with the application (DL-0195): how a document moves, versions and their numbers, editing whole documents and sections, parts, the allowed Markdown — generated from the same specification as the editor and the parser — and exporting. Linked from every paste refusal.

| Region | Release | Stories | Built by |
|---|---|---|---|
| the pages and the allowed-Markdown list — what is accepted and how it is written, and what is refused with the conversion each gets, built from the specification: its limits, entities and callout types, and every refusal with its conversion | **0.1**; the guide's full content B-016 | ST-0019, ST-0060 | Epic 4 |

## Nothing to show here

The one response for a document or folder that does not exist, may not be seen, is archived — to anyone but an administrator — or belongs to another tenant — same status, page and timing (ADR-0008): *Nothing to show here. The link may be incomplete or out of date. Check it, or ask whoever sent it.* — with a way back to the document list.

| Region | Release | Stories | Built by |
|---|---|---|---|
| the page | **0.1** | ST-0015 | Epic 2 |

## Administration

One area with two parts in a left pane: **Platform**, for platform administrators, and **Organisation** — the tenant part — with an organisation selector for platform administrators; a tenant administrator sees only that part, for their own organisation. The interface says *organisation* throughout; *tenant* stays in the URLs (ADR-0008). Django's own administration interface is not part of it (DL-0210).

| Section | URL | Holds | Release | Stories | Built by |
|---|---|---|---|---|---|
| hosts | `/administration/platform/hosts/` | the platform's hosts and each tenant's, host with optional port, one default per set; every change audited (ADR-0008) | **0.1** | — | Epic 2 |
| organisations | `…/platform/tenants/` | the organisations with their state and administrators; *block* | **0.1** | ST-0065 | the list Epic 2; *block* Epic 8 |
| organisations — forms | `…/platform/tenants/` | create with a first administrator, lift a block, appoint an administrator | **0.1** | ST-0001, ST-0071 | create Epic 2 — a registered person only, the invitation of an unregistered address with Epic 8; lift a block and appoint Epic 8 |
| platform administrators | `…/platform/administrators/` | grant; the last one cannot be removed or blocked | **0.1** | ST-0002 | the list Epic 2; grant Epic 8 |
| mail and outbox | `…/platform/mail/` | the platform's sender, the password write-only, *Send a test email*; the outbox with each email's status and attempts (DL-0202, DL-0203) | **0.1** | ST-0048, ST-0049 | Epic 14 |
| audit log | `…/platform/audit/` | what people, the system and agents did | **0.1** | ST-0050 | Epic 12 |
| heuristics | `…/platform/heuristics/` | the catalogue | **0.2** — drawn as a placeholder | — | — |
| users | `/administration/tenant/users/` | *invite by email*, with groups to join, answering alike for a known and an unknown address (ASR-17); *block…*, asking which of the organisations one administers; the last active administrator's *block* disabled with its reason; *lift the block* on a membership; a self-blocked account shown as blocked, with no *lift the block* — lifting it is not in 0.1 (DL-0254, B-033) | **0.1** | ST-0003, ST-0004, ST-0066, ST-0072 | Epic 8 |
| groups | `…/tenant/groups/` | a grid of each group's rights — the viewing ladder, history, *accept*, *freeze*, *make canonical*, *reserve for editing*, the part rights; a right included by another shown as a faint tick — *edit* and the views under *accept*, *freeze* and *reserve for editing* (ADR-0016), *view accepted* under *make canonical* (DL-0234); *members…* per group | **0.1** | ST-0005 | Epics 2, 8 |
| document links | `…/tenant/document-links/` | which groups reach which document, as removable chips and *link a group*; locked while held or reserved, with who, and *force the release* or *end the reservation…*; author-only documents with who created them; an archived document's links, which take effect on restore | **0.1** | ST-0005, ST-0015, ST-0030, ST-0051 | Epics 3, 8 |
| reservations | `…/tenant/reservations/` | every reservation in the organisation: document, holder, since when; *end the reservation…*, a reason required and sent to the holder (DL-0225, DL-0227) | **0.1** | ST-0030 | Epic 9 |
| folders | `…/tenant/folders/` | the tree with each folder's documents; new, rename; *delete* disabled with its reason when a folder holds anything; *move documents…* — which, and where to | **0.1** | ST-0012 | Epic 10 |
| document types | `…/tenant/document-types/` | this organisation's own list, seeded with *document*; add, rename, retire; delete only a type no document uses (DL-0235) | **0.1** | ST-0011 | Epic 10 |
| template | `…/tenant/template/` | the headings and starting text new documents start from; the title page switch and *title page layout…* — which details, in which order | **0.1** | ST-0058 | Epic 16 |
| settings | `…/tenant/settings/` | attachment size cap, inactivity timeout, the distinct-approver check | **0.1** | ST-0030, ST-0053, ST-0062 | Epic 12 |
| sending address | `…/tenant/sending-address/` | the tenant's own sender or none; the password write-only; *Send a test email* — to the address itself, with the step results; the DNS note | **0.1** | ST-0068 | Epic 14 |
| archive | `…/tenant/archive/` | archived documents: restore, export | **0.1** | ST-0015, ST-0016 | Epic 10 |
| styles | `…/tenant/styles/` | the organisation's export stylesheet and which documents use it, *apply*, *export a sample PDF* (DL-0230) | **0.1** | ST-0046 | Epic 16 |
| access history | `…/tenant/access-history/` | a document and a date: which groups could read it then, each with its members that day; the changes to access that led there | **0.1** | ST-0006 | Epic 12 |
| actions and side-document types | `…/tenant/actions/` | which are attached to which documents | **0.2** — drawn as a placeholder | — | — |

---
tags:
  - interface
aliases:
  - Syngraphē page wireframes
status: active
date: 2026-09-27
---

# Pages

The pages of release 0.1: what each holds, which right each control needs, the stories each region carries, and the release and epic each region belongs to. **They are a design input, not a story:** several epics build from them. The epics are release planning and are not published; the *Built by* column names the one that builds each region.

**[`mockup.html`](mockup.html) draws them** — an HTML mockup with synthetic content, opened in a browser. It shows arrangement, not visual style. A bar across its top chooses **whom the pages are drawn for** — a reader, an editor, an editor who also accepts, a reviewer, an approver, a tenant or a platform administrator — and **the state of the example document**: who holds it, whether a run is pending or returned, frozen, archived. Where the mockup and this file differ, this file wins. [`coverage.md`](coverage.md) lists every story with the regions that carry it. A region marked *not yet drawn* is settled here and awaits the mockup.

**Every region carries the release it belongs to.** A region marked for a later release is drawn in the mockup as an empty, labelled placeholder, so the layout keeps its room — **nothing is built for it in 0.1**: no empty frame, no disabled slot (DL-0228).

| Marker | Meaning |
|---|---|
| **0.1** | built in release 0.1, by the epic named |
| **0.2** | the AI reader, release 0.2 |
| **later** | after 0.1, not yet assigned to a release |

**Rights decide what renders.** A control a user may not use is never drawn for them (ADR-0004, ADR-0007). A page or item the user may not see answers exactly as one that does not exist (ADR-0008). **A column, filter or choice that can never hold anything for this person is not drawn** (DL-0233, DL-0236), and a point of the document's path with nothing to show is not offered (DL-0518).

**A blocked control explains itself.** A control its user holds the right to, but cannot use now, is drawn disabled with the reason beside it — whatever blocks it: someone's hold, a reservation, a missing precondition. It is never hidden from a holder of its right, and never refuses only on click (DL-0223, DL-0233).

**A document's state shows as a tag beside its title** — in lists and on the document page — and, where it stops people acting, **as a coloured band across the top of the page** (DL-0233, DL-0236).

**Content is at most 1,440 px wide**, centred (DL-0197).

**Three backgrounds on screen** — the page, the document's text and the editor, so a reader tells them apart at a glance: the page `#f4f4f4`; the text `#ffffff` within a thin border, on every page that draws it; the editor `#fffdf3`. Exports stay on white paper. An organisation's stylesheet may set the text's background, never the editor's (DL-0503, DL-0464).

**Dates and times take one form everywhere**, the long one — *30 вересня 2026, 13:53* (DL-0511).

**The interface is in the person's own language**, Ukrainian or English, chosen on their account page; without a choice, the installation's default. A document's text, numbering and exports are in the document's language and never follow it (DL-0498, DL-0501).

## Page inventory

| Page | URL | Stories | Release |
|---|---|---|---|
| [Shell](#shell) | on every page | ST-0007, ST-0013, ST-0014, ST-0019, ST-0047, ST-0069, ST-0076, ST-0078 | **0.1** |
| [Sign-in pages](#sign-in-pages) | `/signin/`, `/setup/`, `/reset/`, `/reset/<token>/`, `/invitation/<token>/` | ST-0007, ST-0008, ST-0054, ST-0055, ST-0057 | **0.1** |
| [Account page](#account-page) | `/account/` | ST-0066, ST-0076, ST-0078 | **0.1** |
| [Document list](#document-list) | `/folder/7/`; `/` opens the root, `/folder/1/` | ST-0009, ST-0012, ST-0013, ST-0014, ST-0018, ST-0051, ST-0052, ST-0064, ST-0067 | **0.1** |
| [Being edited, In review](#being-edited-in-review) | `/in-edit/`, `/in-review/` | ST-0013, ST-0014 | **0.1** |
| [Search results](#search-results) | `/search/?q=…&type=…` | ST-0013 | **0.1** |
| [Document page](#document-page) | `/document/12/` — the latest version the reader may see; beneath it `edit/` the draft's page, `pending/` the review page, `history/`, `info/`, `my-edits/` (DL-0522) | ST-0005, ST-0010, ST-0014, ST-0015, ST-0016, ST-0017, ST-0018, ST-0019, ST-0020, ST-0021, ST-0022, ST-0023, ST-0024, ST-0026, ST-0027, ST-0028, ST-0029, ST-0030, ST-0031, ST-0032, ST-0033, ST-0034, ST-0035, ST-0036, ST-0037, ST-0038, ST-0039, ST-0040, ST-0041, ST-0042, ST-0043, ST-0044, ST-0051, ST-0052, ST-0053, ST-0058, ST-0060, ST-0061, ST-0062, ST-0063, ST-0069, ST-0070, ST-0075, ST-0079 | **0.1** |
| [Appendix page](#appendix-page) | `/document/12/appendix/3/` | ST-0023, ST-0061 | **0.1** |
| [Historical page](#historical-page) | `/document/12/version/2.0/` | ST-0027, ST-0032, ST-0041, ST-0044, ST-0061, ST-0075 | **0.1** |
| [Compare](#compare) | `/document/12/compare/?from=2.0&to=2.3-1` | ST-0033, ST-0041, ST-0064 | **0.1** |
| [Send-for-review screen](#send-for-review-screen) | `/document/12/edit/finish/`, inside the document's frame, opened by *Завершити редагування* | ST-0022, ST-0029, ST-0035 | **0.1** |
| [Export](#export) | `/document/12/export/`; a version's, `/document/12/version/2.0/export/`; the export's own page, `/document/12/export/<job>/` | ST-0045 | **0.1** |
| [Create or copy a document](#create-or-copy-a-document) | `/document/new/`; `/document/12/copy/` | ST-0009, ST-0067 | **0.1** |
| [Notifications](#notifications) | `/notifications/` | ST-0004, ST-0030, ST-0035, ST-0036, ST-0047, ST-0048, ST-0051, ST-0052, ST-0070 | **0.1** |
| [Help](#help) | `/help/…` | ST-0002, ST-0003, ST-0004, ST-0006, ST-0007, ST-0012, ST-0013, ST-0015, ST-0016, ST-0019, ST-0026, ST-0027, ST-0028, ST-0030, ST-0043, ST-0044, ST-0045, ST-0046, ST-0050, ST-0053, ST-0054, ST-0055, ST-0058, ST-0060, ST-0061, ST-0062, ST-0063, ST-0064, ST-0065, ST-0066, ST-0067, ST-0076, ST-0077 | **0.1** |
| [Nothing to show here](#nothing-to-show-here) | any address that may not be seen | ST-0015 | **0.1** |
| [Administration](#administration) | `/administration/platform/…`, `/administration/tenant/…` | ST-0001, ST-0002, ST-0003, ST-0004, ST-0005, ST-0006, ST-0011, ST-0012, ST-0015, ST-0016, ST-0030, ST-0046, ST-0048, ST-0049, ST-0050, ST-0051, ST-0053, ST-0058, ST-0062, ST-0065, ST-0066, ST-0068, ST-0071, ST-0072, ST-0077, ST-0080 | **0.1** |
| My reservations | `/my-reservations/` | ST-0069 | **0.1** |
| User profile | — | — | **later** — not yet designed; the account page carries what 0.1 needs, without the rest of a profile (DL-0499) |

## Shell

```
+------------------------------------------------------------------------------+
| logo | All documents | Being edited | In review | My reservations | Help | Administration | (!3) | Organisation | 👤 |
+------------------------------------------------------------------------------+
```

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| *All documents* | **0.1** | — | ST-0013 | Epic 3 |
| *Being edited* — documents the user may edit that have versions after their latest canonical edition | **0.1** — shown to holders of *edit* on any document, disabled when empty, no count (DL-0197) | *edit* | ST-0013 | Epics 14, 10 |
| *In review* — documents awaiting review the user may accept; a returned run leaves it until a version is sent after the return (DL-0420) | **0.1** — likewise | *accept* | ST-0014 | Epics 14, 15, 10 |
| *My reservations* — the person's reservations, each document they may still read with its start date; drawn only while they hold one (DL-0241, DL-0525) — a page of its own, `/my-reservations/`: each document with its number, title and start date | **0.1** | — | ST-0069 | Epic 9; in the row Epic 22 |
| *Help* | **0.1** | — | ST-0019 | Epic 4 |
| *Administration* | **0.1** | tenant or platform administrator | — | Epic 2 |
| notifications — unread count, opening the notifications page | **0.1** | — | ST-0047 | Epic 14 |
| the organisation — its name, plain with one active membership; with two or more, a link opening a window that lists the person's organisations, each a POST that switches, and a page of its own, `/organisation/`, with the same list when no script runs; on a tenant's own domain, switching answers with a page carrying the link to the other tenant's domain, or to the platform's host, where the choice is confirmed (ADR-0008, DL-0497, DL-0525) | **0.1** | — | ST-0007 | Epic 8; the tenant's name Epic 2; the link and its list Epic 22 |
| the person icon ending the row, the link to their account page, where their own settings, *Sign out* and *Block my account…* live; their display name — their address while they have none — its tooltip and accessible label, never its text (DL-0499, DL-0500, DL-0523, DL-0525, DL-0541) | **0.1** | — | ST-0076, ST-0078 | Epic 2; the account page Epic 20; the name and the one row Epic 22 |

## Sign-in pages

Sign in, accept an invitation, reset a password: small forms without navigation, each answering identically whether or not an address is known (ASR-17). On a tenant's own domain, signing in lands in that tenant. Before sign-in the pages are in the installation's default language, except a reset or invitation page opened from its link, which is in the language of the person the link belongs to (DL-0501). A member of several organisations who signs in with none chosen lands on a page asking which (DL-0511).

**The first-run page** creates the first platform administrator. It accepts only the one-time token the install command `setup_token` prints, then the administrator's email address and password; the token is single-use and expires, and once a platform administrator exists the page answers as an address that does not exist (DL-0231, T-19).

| Region | Release | Stories | Built by |
|---|---|---|---|
| the three forms | **0.1** | ST-0008, ST-0054, ST-0055 | Epic 2; invitation and reset Epic 8 |
| the first-run page | **0.1** | ST-0057 | Epic 2 |
| the choice of an organisation — to a member of several who signs in with none chosen (DL-0511) | **0.1** | ST-0007 | Epic 20 |

## Account page

`/account/`, reached from the person icon at the end of the menu row: the person's own settings and no more; the rest of a profile stays a later design (DL-0499, DL-0500, DL-0525, DL-0541).

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| the person's email address, read-only | **0.1** | — | ST-0076 | Epic 20 |
| the person's display name, with *Apply* — required, at most 200 characters, so a name once given is changed, never cleared (DL-0539); refused when another member of one of the person's organisations uses it, whatever its case or spaces, the refusal naming no organisation (DL-0523, DL-0537) | **0.1** | — | ST-0078 | Epic 22 |
| the interface's language — Ukrainian or English, with *Apply*; kept as the person's own preference and applied to every page they open; without a choice, the installation's default; emails go in their recipient's language, an invitation in the installation's default; a version's change summary stays as its writer left it (DL-0498, DL-0501) | **0.1** | — | ST-0076 | Epic 20 |
| *Sign out* · *Вийти* — a POST, here and nowhere else (DL-0525) | **0.1** | — | ST-0076 | Epic 22 |
| *Block my account…*, apart at the page's foot — leading to the confirmation; to the last platform administrator drawn disabled with its reason (DL-0315, DL-0233, DL-0500) | **0.1** | — | ST-0066 | Epic 20 |

## Document list

```
+--------------+---+-----------------------------------------------------------------+
| ▾ Example Org|   | [ search titles of documents and appendices ] [All types ▾] [+ create] [Folders ▾] |
|  ▾ Policies  | ↔ | #   Title ▲                        Type    Canonical  Latest  Parts  ✎  ⧉ |
|   ▸ **HR**   |   | 12  Annual leave, sick leave and…  policy  2.0        2.3-1   A  F   ✎  ⧉ |
|   ▸ Finance  |   |     [reserved for editing, since 12 Sep] [awaiting review]       |
|  ▸ Procedures|   | 7   Travel rules                   policy  1.0                a  f   ✎  ⧉ |
+--------------+---+-----------------------------------------------------------------+
```

*Titles are synthetic examples.* `↔` a draggable edge · `A` / `a` appendices present / absent · `F` / `f` attachments present / absent — drawn as dark and faint icons · `⧉` *Копіювати*.

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| folder tree — no heading; ▸ ▾ to collapse; root named after the tenant; the selected folder in bold; always a folder selected (DL-0197) | **0.1** | — | ST-0012, ST-0013 | Epic 10 |
| folder visibility — only folders holding, at any depth, a document the user may read; administrators see all; alphabetical (DL-0206) | **0.1** | — | ST-0012 | Epic 10 |
| draggable pane edge; the width kept in the user's preferences (DL-0195) | **0.1** | — | — | Epic 10 |
| *Folders ▾* — new, rename, delete an empty folder, move documents | **0.1** | tenant administrator | ST-0012 | Epic 10 |
| search box — titles of documents and appendices only, never text | **0.1** | — | ST-0013 | Epic 10 |
| filter by type — beside the search box: *All types*, then the types of the active documents the user may open, retired ones included; **not drawn when those documents carry fewer than two types** (DL-0236); choosing one opens search results for that type across every folder, with the words in the box (DL-0197) | **0.1** | — | ST-0013 | Epic 10 |
| *create* | **0.1** | *create and edit* | ST-0009 | Epic 3 |
| *Compare documents…* — two document numbers, opening their comparison; the one place two documents are compared from (DL-0520) | **0.1** | a viewing right on each | ST-0064 | Epic 10 |
| `#` — the document's number (ADR-0008) | **0.1** | — | ST-0013 | Epic 3 |
| title — takes the free width; opens the reading view | **0.1** | — | ST-0013 | Epics 3, 4 |
| state tags after the title — *held* (DL-0262): the fact to everyone who may read the document, and who holds it to holders of *edit* or *accept* and to administrators — a tenant administrator, or a platform administrator acting in the organisation (ADR-0006, DL-0079, DL-0516); *reserved for editing, since* its date, with who to the same people (DL-0516); *frozen* first, then the hold's tag; *awaiting review* and *returned* to those who may see pending edits (DL-0233); *no reviewer assigned* to those, and to administrators | **0.1** | — | ST-0014, ST-0018, ST-0051, ST-0052 | Epics 5, 6, 9, 15; the holder named Epic 21 |
| sorting — by `#` or title, ascending or descending; title A to Z by default | **0.1** | — | ST-0013 | Epic 10 |
| *Canonical* — the canonical number, linking to the edition's historical page (DL-0208, DL-0352) | **0.1** | — | ST-0013 | Epics 6, 15 |
| *Latest* — the latest version the user may see beyond canonical, else empty; links where the title does (DL-0208, DL-0209). **Drawn only for someone who may see beyond canonical text on at least one document** (DL-0233) | **0.1** | — | ST-0013, ST-0014 | Epic 6 |
| part markers — presence, not count | **0.1** | — | ST-0013 | Epic 3 |
| ✎ — opens the draft's page | **0.1** | *edit* | ST-0013 | Epics 4, 10 |
| *Копіювати* — on each row, opening the copy form with its version choice; the one place a document is copied from (DL-0520) | **0.1** | *create and edit*, and a viewing right on the source | ST-0067 | Epic 21 |

An archived document leaves the list for everyone, administrators included; they reach it through Administration › Archive (DL-0233).

## Being edited, In review

The document list's shape, each a page of its own reached from the menu, without the type filter — choosing a type opens search across every folder, which would leave the view: matching documents grouped under a heading per folder path, the groups alphabetical, sorting within each group; the folder tree shows only folders holding matches (DL-0197, DL-0207). An empty view reads *No documents here.*; to anyone the menu does not offer it, its address answers *Nothing to show here*.

| Region | Release | Stories | Built by |
|---|---|---|---|
| grouped list, filtered tree | **0.1** | ST-0013, ST-0014 | Epics 14, 10 |

## Search results

As *Being edited*: results grouped under a heading per folder path, alphabetical groups, sorting within each group, the tree cut to *folders with found documents*. A group left empty by the reader's rights, and its folder, are not drawn.

| Region | Release | Stories | Built by |
|---|---|---|---|
| grouped results, filtered tree | **0.1** | ST-0013 | Epic 10 |
| search box — keeps the words searched; the note *Searches the titles of documents and their appendices — not the text.* | **0.1** | ST-0013 | Epic 10 |
| filter by type — as on the document list; alone it lists every document of the type the user may open, with words it narrows them | **0.1** | ST-0013 | Epic 10 |
| nothing found — *No documents here.*; *not yet drawn* | **0.1** | ST-0013 | Epic 10 |

## Document page

```
+------------------------------------------------------------------------------+
| Policies / Human resources /                                                 |
| #12 Annual leave, sick leave and parental leave: how employees…  2.3-1       |
| [awaiting review]                           [Export] [History] [Info] [⋯]    |
|                                                                              |
|   ● 2.0 ──── edits ──── ● 2.3 ──── edits ──── ● 2.3-1 ┄┄┄┄ ○ 2.3-2           |
|   canonical        latest accepted        latest        your draft · або 2.4 |
|        Завершити редагування · Відкинути мої правки… · Зарезервувати … ? ┘ |
+-----------+---+-------------------------------------------+---+--------------+
| OUTLINE ⇤ |   | the version's text                        |   | ▾ Parts    ⇥ |
| ▾ 1       | ↔ |                                           | ↔ |              |
|   1.1     |   |                                           |   | parts,       |
| ▾ 3       |   |                                           |   | generated    |
|   ▾ 3.1   |   |                                           |   | views or     |
|     3.1.1 |   |                                           |   | comments     |
+-----------+---+-------------------------------------------+---+--------------+
```

Drawn for a holder of *accept* and *freeze* who holds the document with a draft of their own while a run is pending, the draft chosen: the acts on the line are the chosen version's alone, hung from it; choosing 2.3 would show *Затвердити як 3.0…* and *Заморозити* there instead, choosing 2.3-1 *Розглянути*. `●` a version · `○` the draft · `────` an arc of edits · `┄┄┄┄` the draft's edits so far · `[⋯]` *Більше*, to tenant or platform administrators (DL-0533) · `▾ Parts` — the panel's sections standing one under another, parts, then generated views, comments when they come, each under its name, which collapses it (DL-0536).

**A path of versions** shows where the document stands and puts each act beside the version it changes (DL-0518). Its points are the canonical version, the latest accepted version, the latest version and, to its holder alone, the draft in progress, numbered as the version it will become; between them two arcs of edits — canonical to the latest accepted, the latest accepted to the latest. **Every point and arc has a page and an address of its own** (DL-0522): a version's point opens that version to read — the latest version the reader may see at `/document/12/`, any other at its historical page, `/document/12/version/2.0/`; the first arc opens the comparison of its two versions, `/document/12/compare/?from=2.0&to=2.3`, and the run's arc the review page, `pending/`; the draft opens at `edit/`, History at `history/` and Info at `info/` — so a link in a notification or an email answers. **Each person sees only what their rights reach**: a reader of the canonical version alone sees no path — the path alone is withheld, the state tags stay. **The version shown stands in the heading on every page that reads a version**; History and Info show none. The outline and the right panel stay on every page that reads a version; leaving the draft for another point keeps the draft and the hold, as a hold already does.

**In a window too narrow for the text and the open panes** — the text's own minimum, 560 px, plus each open pane's kept width — the panes are drawn collapsed, and one opens over the text, the text keeping its width, a click outside closing it again; that collapse is the window's, never kept as the person's (DL-0526). **In a window wider than the text**, panes collapsed or not, the text keeps its measure and stands centred in its column, the edit authors' margin counted with it (DL-0540).

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| **bands** across the top — *reserved for editing* since its date, with who to holders of *edit* or *accept* and administrators, and what waits until it ends; *reserved for editing by you*, to its holder; *frozen* — with its reason where the freeze carries one, which only `make_canonical --reason` gives (DL-0549, B-066) — and the name of who froze it to holders of a history right and administrators (DL-0236); *your editing of this document was ended*, to the holder of a kept draft — ended by an administrator, by inactivity or by a block — leading to their draft point, which says who, when and why and offers *Забрати документ назад* when nothing was committed since (DL-0225, DL-0522) | **0.1** | — | ST-0018, ST-0038, ST-0069, ST-0070 | Epics 9, 6; the draft point Epic 21 |
| the notice after *send for review* — *Sent for review — the version waits as 2.3-2*, to the one who sent it (DL-0322) | **0.1** | — | ST-0029 | Epic 4 |
| breadcrumb, `#12`, title, and **the version shown, in the heading of every page that reads a version** — History and Info show none (DL-0518) — on `/document/12/` the **latest version the reader may see**, never one beyond their rights (DL-0209): *2.3-1*; *2.0*, the latest edition, to a reader of canonical text only — to whom a document with no canonical edition yet does not exist (DL-0352); *0.0*, the document's first, before any acceptance with nothing pending (DL-0358); on every other page of the document, the version that page shows | **0.1** | — | ST-0042 | Epics 3, 6; the heading Epic 21 |
| state tags, as in the list; *archived* to administrators only — to everyone else an archived document does not exist | **0.1** | — | ST-0014, ST-0015, ST-0018, ST-0051, ST-0052 | Epics 5, 6, 9, 10, 15; the holder named Epic 21 |
| **the icons** in the heading — *Export*, opening the export page; *History* and *Info*, each opening its page (DL-0518, DL-0519); *Більше* (⋯), to tenant or platform administrators — a platform administrator acting in the organisation as its administrators do (DL-0522, DL-0533) | **0.1** | any viewing right; *Більше*, tenant or platform administrator | — | Epic 21 |
| the agents' *Analysis* — an icon of its own when release 0.2 brings it; nothing is drawn for it in 0.1 (DL-0228, DL-0261, DL-0518) | **0.2** | *edit* | — | — |
| **the path** — its points: the canonical version; the latest accepted version; the latest version; to its holder alone, the draft in progress, numbered as the version it will become — the pending number, *N.M-X*, with *або N.M+1* beside it for a holder of *accept* — or the holder's kept draft, marked *залишена* (DL-0522); two points that name one version are drawn once; a point with nothing to show is not offered, and the run's arc is absent while nothing is pending (DL-0518); its arcs: canonical to the latest accepted, opening their comparison, with *‹* and *›* there (DL-0508) and History for any other pair; the latest accepted to the latest — the run's arc — opening the review page, `pending/`: to a holder of *accept* with its acts, to everyone else who may see pending edits the run's text with its change authors in the margin, a changed image before and after side by side and the run's part operations, read-only, the review page without its acts (DL-0522); a point opens its version to read; each person sees only the points and arcs their rights reach, and a reader of the canonical version alone sees no path (DL-0518) | **0.1** | any viewing right; an arc, the viewing right for both its versions | ST-0032, ST-0033, ST-0042 | Epic 21 |
| **the acts**, on one line beneath the version they apply to, hung from it by a line (DL-0518): on the latest version *Редагувати*, opening the whole document's editor (DL-0517) — disabled with its reason while someone else holds or has reserved the document, the holder named to holders of *edit* or *accept* and administrators (DL-0516), and while frozen to everyone but a holder of *accept*; not drawn on an archived document, which is read-only to everyone (DL-0450, DL-0518); a holder of *accept* who edits while a run is pending makes their own version, and there is no separate *Correct* (DL-0521); to a holder of *accept* with a run pending, *Розглянути*, opening the review page; on the draft, the draft's acts, below; on the latest accepted version, the next two rows | **0.1** | *edit* — which *accept*, *freeze* and *reserve for editing* include (ADR-0016); while frozen, *accept*; *Розглянути*, *accept* | ST-0017, ST-0035 | Epic 21 |
| *Затвердити як N.0…* on the latest accepted version — the canonical point while nothing was accepted since it, where it is disabled with *nothing accepted* (DL-0518) — confirmed in a window over the page naming the version, the edition it becomes and that it cannot be undone, with *Затвердити як N.0* and *Скасувати* (DL-0513); frozen or not (DL-0515); disabled with its reason while anyone holds or has reserved the document (DL-0419) and while a content version since that acceptance is unaccepted (DL-0267) — to someone who may not see pending edits the reason names no pending number; the distinct-approver check where the organisation has it on (DL-0115) | **0.1** | *make canonical* | ST-0039, ST-0053 | Epic 6; the window Epic 21, the freeze optional Epic 20 |
| *Заморозити* / *Розморозити* on the latest accepted version — the canonical point while nothing was accepted since it (DL-0518) — one toggle; disabled with its reason while anyone holds or has reserved the document (DL-0223); a freeze is a state of the document in which nobody but a holder of *accept* starts editing, ended by *Розморозити* or by *make canonical* (DL-0189, DL-0515) | **0.1** | *freeze* | ST-0038, ST-0040 | Epic 6; on the path Epic 21 |
| **the hold and the freeze marks**, under the latest version — *редагує {name}*, for a reservation *зарезервував {name}*, to holders of *edit* or *accept* and to administrators, for every hold, ordinary or reserved; the fact alone to everyone else who may read the document (DL-0516); *frozen*, with who froze it to holders of a history right or *accept* and administrators (DL-0236, DL-0549) | **0.1** | — | ST-0018, ST-0038, ST-0069 | Epic 21 |
| *Більше* (⋯), the administrator's acts (DL-0522) — *Групи*, locked, with who holds the document, while it is held or reserved; *Архівувати* / *Відновити*; *Звільнити документ примусово* for an ordinary hold and *Завершити резервування…* for a reserved one, never offered to the holder — the latter a page of its own inside the frame, the path above it, naming the reservation, its holder and its date, with the reason, required (DL-0225, DL-0415); the former names the hold the page showed, so a newer one is never forced | **0.1** | tenant or platform administrator (DL-0533) | ST-0005, ST-0015, ST-0016, ST-0030 | Epics 8, 10, 9; behind the icon Epic 21 |
| outline — every heading level, ▸ ▾, no appendices; resizable; on every page that draws a document's text — a version, the review page, the editor, both comparisons — each heading scrolling the text to its place (DL-0518, DL-0527); collapsed, a strip with its control, the text taking the width, the collapse kept per person (DL-0526) | **0.1** | — | ST-0024 | Epic 7; on every page that reads a version Epic 21; on every text page and the strip Epic 22 |
| the text — a heading's number part of the heading, set as the heading is; each clause's number in the gutter beside it in a light grey, never selected with the text; the same in the editor and the exports (DL-0363); on its own background, within a thin border (DL-0503) | **0.1** | — | ST-0042 | Epic 7; the background Epic 20 |
| right panel — its sections one under another, each under its name, which collapses and opens it; every section collapsed, or the panel's own control, narrows it to a strip naming its sections, a name opening it on that section; resizable, its width and its collapse kept per person (DL-0194, DL-0195, DL-0526, DL-0536); on every page that reads a version, on the review page, where it holds the run's versions, and on the comparisons (DL-0509, DL-0518) | **0.1** — *parts* and *generated views*; comments **later** (B-013) and the agents' views **0.2**, not drawn until built (DL-0228, DL-0356) | — | — | Epics 3, 4, 7, 11; on every page Epic 21 |
| parts — the version's appendices in their order, each opening its page; its attachments with title, file name, size and download — read only: the changing controls are the draft page's own panel, beside the editor (DL-0442) | **0.1** | any viewing right | ST-0061, ST-0062, ST-0075 | Epic 13; its thinnest form — the attachments with title, file name, size and download, in the panel's parts section (DL-0349, DL-0356) — Epics 18, 7 |
| generated views — the **role directory**: each declared role by label, in the order the document declares them, with every heading or clause marking it, its number linked to its place and its text as it reads under the reader's own rights — a long clause its opening words; a role in a table cell listed under the heading or clause the table follows, *(table)* after its number, and a table before any of them as *(table)* alone; a role marked nowhere *no clauses*; then a role marked with an undeclared key, grouped by it, and one marked without a key, grouped by its words, *(not declared)* beside them (DL-11-011); *No role is marked in this version* where none is — then **see also**: each document the text mentions, once, in order of first mention, the document itself left out — its number and title, linked, where the reader may read it, the first mention's words as plain text where not (DL-0437); *This version mentions no other document* where none is; then *Generated by the system from the version shown* (DL-0448); on a version's page and the historical page, at the version shown | **0.1**; contradictions, ambiguities, blind spots **0.2** | any viewing right | ST-0027, ST-0044 | Epic 11 |

### Where the tabs' content lives

An earlier design put the document's content under tabs; the decision log carries it (DL-0518). Each has one place on the path, and the addresses the tabs had still answer (DL-0522):

| Former tab | Where its content lives |
|---|---|
| View | the version points: a point opens its version to read — the latest at `/document/12/`, any other at its historical page |
| Edit | the draft's page, `edit/` — § The draft's page |
| My edits | a switch inside the editor; its address, `my-edits/`, answers as built (DL-0514) |
| Pending edits | the review page, `pending/`, which the run's arc — the latest accepted version to the latest — opens: to a holder of *accept* with a run pending, with its acts; to everyone else who may see pending edits, the run's change authors, a changed image before and after side by side and the run's part operations, read-only, the review page without its acts (DL-0522) |
| History | the History icon, opening `history/` — § History and Info |
| Info | the Info icon, opening `info/` |
| Analysis | nothing drawn in 0.1; an icon of its own in release 0.2 (DL-0228) |

### A version's page

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| the version's text — the version in the heading (DL-0518); clause numbers in the gutter; entities in their own formatting; the outline and the panel beside it (DL-0356) | **0.1** | any viewing right | ST-0023, ST-0026, ST-0042 | Epic 7; the heading Epic 21 |
| mentions — a mention of another document as a link to it where the reader may read it while it is active; its words alone where not — an archived document, one the reader may not read, a number that names none — with no title, no mark and no message (DL-0084, ASR-16); the same on every page that draws the text — the historical page, compare, the review page, the editor's drawn text and its *my edits* switch, the send-for-review screen, a kept draft, the stopped editor, a correction notice; PDF and DOCX carry the words alone for every reader, the Markdown export the mention as written | **0.1** | any viewing right | ST-0043 | Epic 11 |

### The draft's page

`edit/`, the holder's draft point. Opened from the application or typed in, the page takes the hold as it opens (DL-0319, DL-0325) and shows the whole document's editor at once: a document is shown either to be read or to be edited, with no third way of editing one section (DL-0517). The draft, its capture and the hold are as the lifecycle describes them.

| Region | Release | Stories | Built by |
|---|---|---|---|
| the editor, the whole document in it, open on arrival (DL-0517) — as wide as the document's text on its version's page, on the editor's own background (DL-0503, DL-0513); toolbar exactly the whitelist — *quote* among it (DL-0238) — led by *undo*, *redo* and *Clear formatting*, which leaves the selection or the cursor's line plain paragraphs of the same words, its roles, actions, terms and mentions kept (DL-0241, DL-0531), *mark* for entities — a picker beside the toolbar: the kind, this document's declared ones of that kind by label, *declare a new one* with its label; picking or declaring wraps the selection, words already marked taking the new one; only this document's own are offered (DL-0073) — *mention* — a document's number typed into the toolbar as a link's address is, Enter wrapping the selection in a mention of it, anything but a number refused on the notice line, nothing looked up — each control an icon with its word as tooltip and accessible name; a mention drawn in a link's colour with a dotted underline, apart from entities and links; *rich / markdown*; a draft the whitelist refuses opens in it as text | **0.1** | ST-0019, ST-0021, ST-0026, ST-0043, ST-0060, ST-0079 | Epic 4, *undo* and *redo* included; *mark* and *mention* Epic 11; the whole editor on arrival and its width Epic 21; the toolbar's order and *Clear formatting* Epic 22 |
| paste refusal — the lines named, the converted text previewed, *paste converted*, a link to help; an image left out of a paste with a one-line notice (DL-0232) | **0.1** | ST-0019, ST-0028 | Epic 4 |
| image refusal — the format or the size. A pasted or dropped image becomes an upload and a paragraph of its own; an image that is only a web address is left out of the paste, with a one-line notice to copy the image itself and paste it, which blocks nothing (DL-0232, DL-11-005) | **0.1** | ST-0019, ST-0028 | Epic 11 |
| capture indicator — no Save control | **0.1** | ST-0020 | Epic 4 |
| *My edits*, a switch inside the editor (DL-0518) — the whole document with the draft's changes marked in place; the roles, actions and terms it adds, relabels or removes, those its marked words declare with the version included (DL-0440); dimmed and disabled, its reason as a tooltip, while the person has no edits (DL-0518) | **0.1** | ST-0031 | Epic 21 |
| the **parts panel**, on the right while holding the document — the draft's appendices and attachments, each appendix opening its page's editor; *Add* (an appendix by its title, an attachment by its title and file), *rename*, *replace* an attachment's file, *delete* (confirmed), ↑ *Move up* and ↓ *Move down*, the download arrow for the draft's file — each as the person's rights allow: *create appendix*, *delete appendix*, *upload attachment*, *replace attachment*, *delete attachment*; renaming and moving *edit* alone; a part the draft added withdrawn with the right that added it (DL-0473); the author of a document no group is linked to may upload and replace (DL-0445); a file above the organisation's limit, a name a file system refuses or that changes how it reads, refused with the reason (DL-0442) | **0.1** | ST-0061, ST-0062 | Epic 13 |
| the **title page**, to the holder, in the panel below the parts — the switch *Title page* and *Title page text* (plain text, at most 500 characters and 8 lines, line breaks kept) with *Apply* — never *Save*, a word the product does not use (DL-0222); each a draft change committed with the run, the run's changes reading *Title page switched on* or *off*, *Title page text: …*, or *Title page text removed*; refused with the draft page's reasons to anyone else (DL-0463, DL-0476) | **0.1** | ST-0058 | Epic 16 |
| *Start editing* — when the page was reached from another site, so a link elsewhere never takes the hold; opened from the application or typed in, the page takes it as it opens (DL-0319, DL-0325); *not yet drawn* | **0.1** | ST-0017 | Epic 4 |
| **the draft's acts**, on one line beneath its point (DL-0518): *Завершити редагування*, opening the send-for-review screen, disabled with its reason while nothing is edited (DL-0233, DL-0510); *Звільнити документ* while nothing is edited — no captured text, no part operation, no title page change — releasing the hold without confirmation, unless a reservation would end with it, and *Відкинути мої правки…* after the first edit (DL-0510), confirmed in a window over the page saying the whole draft, text and files, is thrown away and this cannot be undone, with *Discard my edits* and *Back to editing* · *Повернутись до редагування* (DL-0513) — a reservation ends with the discard; *Зарезервувати для редагування*, beside *Завершити редагування*, its explanation behind *?* (DL-0511), to a holder of the right — disabled with its reason while frozen (DL-0252); then *Cancel the reservation* (DL-0218, DL-0219, DL-0223) | **0.1** | ST-0022, ST-0029, ST-0069 | Epic 21 |
| a stopped editor — read-only, what was typed and not captured as changes against the draft as it now stands; the *released* notice once the hold has been ended | **0.1** | ST-0017, ST-0030 | Epic 9; the one editor Epic 21 |
| inactivity prompt — *are you still working?* with *I am still working*, shown while the hold is idle past the organisation's timeout, released ten minutes later (DL-0377); never for a reserved hold (DL-0221) | **0.1** | ST-0017, ST-0030 | Epic 9 |
| to a holder of *accept* editing while a run is pending — that their changes become their own version, offered *accept as* on finishing (DL-0521); after an undo, above the editor, the places left for their hand with the wording before the undone edits and now — an appendix's under *In the appendix “{title}”* — or that everything was undone; that the roles, actions and terms the undone edits declared or relabelled stay as they stand (ADR-0015, DL-0380) | **0.1** | ST-0035, ST-0037 | Epics 5, 15; the appendix's places, Epic 13; one act for every holder Epic 20 |
| the holder's kept draft — their draft point, marked *залишена*, after an administrator ended their reservation or forced their hold, an inactivity release or a block; offered back before any new hold: *Забрати документ назад* while nothing was committed since; read-only once the document has moved on, as changes against the current text or another version the holder's rights reach, a history right's included (DL-0225, DL-0318, DL-0417, DL-0522); on a frozen document read-only as well (DL-0511); *Відкинути цю чернетку…*, confirmed in the window (DL-0381, DL-0513); a hold with no edits keeps nothing when it ends — no band, no point, nothing to take back (DL-0514) | **0.1** | ST-0070 | Epic 9; the draft point Epic 21 |
| the address while someone else holds or has reserved the document, or it is frozen and the user lacks *accept* | **0.1** — says so, names the holder to holders of *edit* or *accept* and administrators (DL-0516), offers nothing | ST-0017, ST-0038 | Epic 4; the name Epic 21 |

### The review page

`pending/`, *сторінка розгляду*: to a holder of *accept* while a run is pending, opened by *Розглянути* on the latest version, the path above it and the outline beside it (DL-0518, DL-0522). It opens while someone else holds the document, its acts disabled with their reasons as the lifecycle's preconditions say. Everyone else who may see pending edits reads the run on its arc's page — the change authors, the images side by side and the part operations as below, read-only, without the acts; `pending/` answers them with it (DL-0522).

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| the run's text — the whole document, every change since the last acceptance marked in place; formatting-only changes marked; **a changed image before and after, side by side**, each captioned with its side, its version's number and its description, *open both full size* below them (DL-0439, DL-11-002); **each appendix the run changed**, after the body, its changes marked as the body's are; **the roles, actions and terms added, relabelled or removed in the run** (DL-0073) | **0.1** | *accept* | ST-0031, ST-0034 | as built; on the review page Epic 21 |
| **change authors** — each name in the right margin beside its paragraph, in small grey text, the text itself without an underline, only beside a paragraph the run changed against the last acceptance; a paragraph whose sentences have several authors names each at its sentence's end; the checkbox *Show edit authors* at the top of the names' column as its title, one preference with the historical page's (DL-0489) — ticking it saves the preference and draws the page again (DL-0504) | **0.1** | *accept* | ST-0031 | Epic 20 |
| **the panel** — the run's versions, a bulleted list, each with its number linking that version's page in the same window, its change summary whole, author and date, a blank line between entries; resizable and collapsible as the others are (DL-0509, DL-0526, DL-0530); on each version **undo this edit** and on each author's newest **undo all of this author's edits since N.M** (DL-0522) — the reversal of the body and of each appendix the run touched goes into the reviewer's draft, which opens — an appendix's places listed under its title; a title or part the undone edits changed — an appendix they created or deleted among them — is listed, to be changed with the parts' own controls (DL-0447); what a later version or the draft changed is left as it stands and listed above the editor for editing by hand (ADR-0015, DL-0380); disabled with the reason while reserved, held by another, or a kept draft of the reviewer's waits; while the undo waits in the draft, *Погодити* is disabled with its reason, and the reviewer accepts it with *accept as* (DL-0427); comments stay a later feature with their own place in the panel (B-013) | **0.1** | *accept* | ST-0031, ST-0037 | Epic 21 |
| **every part operation** — added, replaced, renamed, reordered, deleted — with each file's versions to download and *revert*, which puts the part back as the last acceptance had it, takes the document and joins the reviewer's own version, needing *accept* alone (DL-0446); while a revert waits in a draft, *Погодити* is disabled with its reason, and the run is accepted with that draft's *accept as* | **0.1** | *accept* | ST-0063 | Epic 13; on the review page Epic 21 |
| *Погодити N — стане M* — confirmed on a page of its own inside the frame, naming the versions accepted and the number that results; *Повернути без погодження…* — confirmed the same way, the reason required: one line of at most 500 characters (DL-0378, DL-0424, DL-0522); each disabled with its reason while the document is reserved, the holder's own reservation included — a holder of *accept* who holds the document accepts through *accept as* on the send-for-review screen (DL-0222, DL-0224); *Редагувати* stands here as well, for a reviewer who may edit, as on the latest version (DL-0518, DL-0521) | **0.1** | *accept* | ST-0036, ST-0052 | Epic 21 |
| *Заморозити* / *Розморозити* — the latest accepted version's toggle, here as well (DL-0518) | **0.1** | *freeze* | ST-0038, ST-0040 | Epic 21 |

### History and Info

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| **History**, `history/`, from its icon — per version, newest first: number, event (created, edit, a reviewer's version, acceptance, return, made canonical), who, when — and the freezes and unfreezes between them, a freeze recorded with an approval not drawn (DL-0515); *open* — in a new window as a historical page; *compare* from each version's historical page, so any pair is reached from here (DL-0518); the accepted boundary, to a reader of accepted text (DL-0209); to a holder of *view previous canonical versions* only, the editions alone; to a holder of *edit* without *view all history* — *accept*, *freeze* and *reserve for editing* include it — every entry from the latest canonical edition's approval up — while the document has no edition, every version — the freezes left out; a note says what the list reaches (DL-0524, DL-0534). It lists, opens and compares; the undo controls stand on the review page (DL-0522) | **0.1** | *view all history*; *view previous canonical versions* for editions only; *edit* from the latest edition | ST-0032, ST-0033, ST-0041 | as built; the icon and the undo's place Epic 21 |
| **Info**, `info/`, from its icon — number, title, language, type — a choice for administrators — folder, canonical version, state, title page — *Yes* or *No* for the version the reader is shown — style — *The organisation's stylesheet* or *The platform's default* (DL-0463, DL-0465) — linked groups (administrators), created; *Copied from* (administrators, a copy alone) — the source's number, linked where the reader may open it, its version, the commit's first twelve characters, the date and who copied it (DL-0455) | **0.1** | any viewing right | ST-0010 | as built; the icon Epic 21 |

## Appendix page

The document page's frame for one appendix. The title reads **#12 Annual leave… › {the appendix's title, as its editor typed it} 2.3-1**, the document's number and title linking back to it; the appendix's own number appears only in its URL (ADR-0008); **the document's path above it** — a point opens the appendix at that version, `/document/12/version/2.0/appendix/2/`, and *Редагувати* opens the appendix's editor, the whole appendix in it (DL-0517, DL-0522); the appendix's own outline; its text numbered from 1, nothing in front; the review page, History and the editor's *my edits* switch are the document's (DL-0443); the right panel's parts and the whole document's generated views, an appendix's places named by its title (DL-0444). **The path here offers editing alone** — no *Затвердити як*, no freeze, no *Розглянути* and no *Більше* (DL-0207).

| Region | Release | Stories | Built by |
|---|---|---|---|
| the page | **0.1** | ST-0023, ST-0061 | Epic 13; the path and the whole appendix's editor Epic 21 |

## Historical page

One version — its point on the path, opening it in the same window, or *open* from History in a new one: **the path stands above it**, the point outlined (DL-0522); a **banner** across the top — *Historical version 2.0 — read only*, with a link to the current document — and under it the version's change summary, whole (DL-0532); the reading view with the outline and the right panel, as on every page that reads a version (DL-0518); the generated views of that version, as a version's page's; the attachments as that version listed them, each downloadable at that version — `/document/12/version/2.0/attachment/3/` (DL-0421); the appendices as that version listed them, each opening at that version — `/document/12/version/2.0/appendix/2/`, the appendix page's frame under the same banner, its places in the generated views linking there; the heading's *Export* icon exporting that version alone, opening the export page at that version with the version in its heading (DL-0519), marked by the chain of the stance it reached where the reader may see its baseline (DL-0426), re-checked against the reader's ceiling when it runs (DL-0423); *compare with* any other version the reader may see, the latest included — not drawn when there is none (two documents are compared from the document list, DL-0520). Never editable (DL-0195, DL-0208). The versions a reader may open: the current version of each stance their viewing right includes, every version of the pending run with *view pending*, every edition with *view previous canonical versions*, every version up to their highest stance with *view all history* (ADR-0007, DL-0286).

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| the page | **0.1** | the reader's ceiling: a viewing right, widened by a history right | ST-0032, ST-0041, ST-0075 | Epic 15 |
| the generated views of that version — the role directory and *see also*, as a version's page's | **0.1** | as the page | ST-0027, ST-0044 | Epic 11 |
| the appendices at that version, each on its own page | **0.1** | as the page | ST-0032, ST-0061 | Epic 13 |
| *Show edit authors* — the checkbox at the top of the names' column, one preference with the review page's (DL-0489): each paragraph the version changed against the version before it within the reader's reach names its edit author in the right margin — the first version within reach, with none before it, names every paragraph — the text left without marks, a paragraph with several authors each at its sentence's end (DL-0504); while a past version's authors are being worked out, the text without them and a line asking for a reload; worked out on demand and kept for a day (DL-0266) | **0.1** | as the page | ST-0032 | Epic 12; the margin and the checkbox Epic 20 |

## Compare

A **banner** across the top in the historical page's style — *Comparing 2.0 with 2.3-1 — read only* — each version a link to it (DL-0233). Below it, one row — *From ‹ {version} to › {version} Compare* — the versions chosen among those the reader may see, each step beside the version it moves, drawn as an icon (DL-0528), and *Compare* opening the chosen pair as a new page. The newer version in full, with the changes against the older marked in place, the newer text's outline beside it (DL-0527); *Show edit authors* names who last edited each changed paragraph between the two versions, a line the older version held naming nobody, across a hundred versions at most, past which the page says the names are not shown (DL-0528). The panes are the document page's (DL-0526). The right panel lists the parts in both versions: **appendices** — pick one from each side and *compare appendices*, which opens a page of the same shape for the pair, `/document/12/compare/appendix/?from=2.0:2&to=2.3-1:2`: the banner *Comparing appendices of 2.0 with 2.3-1 — read only*, each side's version and title with a link to the appendix at that version, the newer appendix whole with its changes against the older marked, whichever order was asked, and *Back to the comparison*; **attachments** — each with its file in both versions and whether it was added, changed — its file, title or file name — removed or unchanged; attachments are not compared (DL-0208). **On every comparison of two versions, *‹* and *›*** — in the choosers' row — with *previous* and *next* as their tooltips and accessible names: comparing X with Y, *‹* opens the version before X against X, and *›* opens Y against the version after Y; a version the reader may not see is skipped (DL-0209); each is disabled when no such version exists (DL-0508). One version asked against itself opens its historical page. A reader who may see only one version is offered no comparison. The path's first arc — the canonical version to the latest accepted — opens here with its two versions (DL-0518); the run's arc opens the review page instead, which draws what a comparison does not — the run's change authors, a changed image before and after side by side and the run's part operations (DL-0522); the pair of the latest accepted version with the latest is reached here by *›* and from History.

**Comparing two documents** has the same shape, under the first document's frame and path: the heading reads *#12 Annual leave… 2.0 → #7 1.0* (DL-0522). The banner reads *Comparing #12 2.0 with #7 1.0 — read only*, each number linking to its document and each version to its historical page, the second document's *archived* tag beside its number when it is archived. Below it, *from* among the first document's versions the reader may see, *with #* — a number — and *to* among the second's, then *Compare*. The second document's whole text, with its changes against the first's marked in place, its outline beside it; no edit authors; the order is the reader's. Each version is one its own document's reader may see; a document the reader may not open, or a version beyond their rights, answers *Nothing to show here*, and a document compared with itself opens its own comparison. Without a *to*, the second document's newest version the reader may see; both numbers are asked by the list's *Compare documents…*, and there is no picker on the page — an address naming no second document answers *Nothing to show here* (DL-0520). The side panel lists **each document's attachments** under its number and version, each downloadable at that version, the two lists not paired (DL-0452), and its **appendices**: one of each document's to compare as a pair — `?from=2.0:2&with=7&to=1.0:1`, the second document's appendix marked against the first's — its *Back to the comparison* returning to the two documents. No *‹* and *›* across documents (DL-0508). It starts from the document list's *Compare documents…*, and from nowhere on the document page (DL-0520).

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| version comparison, *‹* and *›*, attachment list; appendix comparison | **0.1** | the viewing right for both versions | ST-0033, ST-0041 | Epic 15; appendix comparison Epic 13; *‹* and *›* on every pair Epic 20; in the row, the outline and edit authors Epic 22 |
| comparing two documents — the banner, *from*, *with #* and *to*, the second document's text marked against the first's, each document's attachments (DL-0452) | **0.1** | a viewing right on each | ST-0064 | Epic 10; the appendices, Epic 13; from the list alone Epic 21 |

## Send-for-review screen

A page of its own inside the document's frame, the path above it (DL-0522), opened by *Завершити редагування* for every holder (DL-0222): first the change summary and the choices below; then the holder's changes, as *my edits* (DL-0532). The change summary — for the reviewer, and kept with the version — is plain text of several lines in a field the editor's width and ten lines high, drafted mechanically with the sections touched, and editable: its first line, at most 500 characters and not beginning like a trailer, is the commit's subject and what every list shows; the rest is the commit's body, no line of it shaped like a trailer; the whole at most 5,000 characters (DL-0532, DL-0535); the part operations in the draft; the roles, actions and terms the draft adds, relabels or removes — those the commit will declare from marked words included (DL-0440); nothing else in 0.1, the agents' analyses from 0.2 (DL-0261). Then the choices, each naming what it produces, with the number computed for this document:

| The holder holds | Choices besides *continue editing* and *Відкинути мої правки…*, confirmed in the window (DL-0513) |
|---|---|
| *edit* | *send for review* — the version waits as `2.3-2` |
| *accept*, which includes *edit* (ADR-0016) — a holder of *accept* who edited while a run was pending included (DL-0521) | *accept as 2.4* — the version is made and the whole run since the last acceptance accepted, other editors' versions named, with the correction notices the acceptance sends (ADR-0014) · *create version 2.3-2* — the version waits for review |

| Region | Release | Stories | Built by |
|---|---|---|---|
| the screen | **0.1**; change summary drafted by the companion **0.2** | ST-0022, ST-0029, ST-0035 | Epic 4; the choices of a holder of *accept* Epic 5; *discard my edits* Epic 9; the frame and the window Epic 21 |

## Export

```
+------------------------------------------------------+
| #12 Annual leave…  2.0      [Export] [History] [Info] |
|   ● 2.0 ──── edits ──── ● 2.3 ──── edits ──── ● 2.3-1 |
|                                                      |
| Export                                               |
|  What ?    [x] Document                              |
|            [x] Appendices                            |
|                (•) embedded  ( ) separate            |
|            [x] Attachments                           |
|  Format ?  (•) PDF  ( ) DOCX  ( ) Markdown           |
|  View ?    (•) Canonical 2.0                         |
|              Changes: ( ) marked against 1.0         |
|                       (•) clean text                 |
|            ( ) Accepted 2.3                          |
|            ( ) Pending edits 2.3-1                   |
|            ( ) My edits — your draft                 |
|  Delivered as one zip.                      [Export] |
+------------------------------------------------------+
```

A page of the document's own, `/document/12/export/`, opened by the Export icon, and `/document/12/version/2.0/export/` from a historical page; **it starts on what the person was reading** — a version's page and a comparison's newer version, that version; the draft's page, *My edits*; the latest version's page, the newest view the person may export; the choice carried in the icon's link, a view not offered falling back to the first (DL-0529); **its heading names the version that will be exported**, following the view chosen (DL-0519). **Everything in the file is in the document's language** — its name, the zip's entries, the title page's words and the attachment list — whoever asked for it and whatever the installation's language; words the catalogue does not hold in that language fall back to English (DL-0502).

| Region | Release | Stories | Built by |
|---|---|---|---|
| the page — opened by the Export icon, the version that will be exported in its heading, following the view chosen (DL-0519) | **0.1** | ST-0045 | Epic 21 |
| *What* checkboxes, all checked by default; parts the document lacks not offered (DL-0236) | **0.1** | ST-0045 | Epic 7; the appendices, Epic 13 |
| *embedded / separate* — disabled unless the document is checked; *Format* — disabled unless the document or appendices are (DL-0207) | **0.1** | ST-0045 | Epic 7; the appendices, Epic 13 |
| *View* — canonical, accepted, pending edits, my edits, as the user's rights allow, each naming its version (DL-0549); a single view is named as text, not offered as a choice (DL-0236) | **0.1** | ST-0045 | Epic 7 |
| *Changes* — beside each view that has a baseline, with no heading of its own (DL-0549): *marked against* the previous version in the chain, named: a canonical edition against the previous edition, an accepted version against the current canonical edition, pending edits against the last acceptance, the draft against the current text; or *clean text*. Clean by default for a canonical edition, marked for every other. Not drawn when marks are impossible — a canonical edition for someone with no history right (DL-0241) | **0.1** | ST-0045 | Epic 7 |
| what will be delivered — one file or one zip | **0.1** | ST-0045 | Epic 7; the appendices, Epic 13 |
| *Export* — disabled while nothing is chosen; a message when a chosen part is not in the chosen version, or nothing is left to export (DL-0208) | **0.1** | ST-0045 | Epic 7; the appendices, Epic 13 |
| *?* beside each section's heading — a box of help above the page, closed by a click anywhere else; no help text in the layout (DL-0233) | **0.1** | ST-0045 | Epic 7 |
| file names — `<title>_—_<version>_—_<stance>.<ext>`, the stance in the document's language, as are the zip's entries (DL-0502); a marked export ends in `-позначено` (`-marked`), `<stance>-позначено.<ext>`, and a clean one has none (DL-0359); the title cut at eighty characters; several files a zip of the same name (DL-0275) | **0.1** | ST-0045 | Epic 7; the document's language Epic 20 |
| the file's pages — the page number at the foot and no header, the title, version and stance standing in the file's name, and on the title page where the document has one (DL-0182, DL-0362); headings numbered in their text and clause numbers in a light-grey gutter — in DOCX at the start of the paragraph, Word having no gutter — a change of formatting alone marked by its colour; a Markdown file's headings carry their numbers and its clauses none (DL-0363); *not yet drawn* | **0.1** | ST-0045 | Epic 7 |

## Create or copy a document

Title, language, type — each named in words, never by its code — folder (the root allowed). A **copy** adds the source version — canonical, accepted or pending, among those the user may see — the appendices to take (none, all, chosen), and the notice that attachments are not copied. The new document is reachable only by its author until groups are linked.

| Region | Release | Needs | Stories | Built by |
|---|---|---|---|---|
| create — the language offered first is the installation's default, until the organisation has a language of its own, which then takes its place; the other seeded languages beside it; neither the person's interface language nor the list's order decides it (DL-0512) | **0.1** | *create and edit* | ST-0009 | Epic 3; the default language Epic 20 |
| copy — opened by *Копіювати* on the document's row of the document list (DL-0520): the title prefilled with the source's; the language the source's, shown as text; type and folder as in create; the version — *Pending edits*, *Accepted*, *Canonical* among those the user may see, pending by default, a single one named as text; the appendices — *None*, *All* or *Chosen*, renumbered from 1 in the source's order; *Attachments are not copied.* | **0.1** | *create and edit*, and the source version's viewing right | ST-0067 | Epic 10; from the list Epic 21 |

## Notifications

Two tabs (DL-0204). **Document** — each entry linking to the document at the version concerned, for every event ST-0047 lists; among them a version sent for review; a run returned, with the reason while its reader may still read the pending edits (DL-0369); a **correction notice** — one per acceptance, however many of the author's lines changed (ADR-0014), listed as one line with its counts, *— 1 line and 2 parts changed*, the rest on its own page (DL-0480) — which opens to show, for each, what the author wrote, what was accepted and who changed it, marked, with a link to the passage, and for each part another author's version of the run added, replaced, renamed or removed and a reviewer's version changed, what each did — *You added this attachment in 1.1-1; Reviewer R removed it in 1.1-2* — the part by its title as the author left it, with *open* where the accepted version still holds it; *your reservation was ended*, with who and when, and why beneath it — the reason read here, never in the email (DL-0369); *your editing will soon end for inactivity*, once per idle spell (DL-0377). **Administrative** — being added to a group, documents created or copied and not yet linked, failed mail, reservations started; to a platform administrator also a person blocked in one organisation and active in another, an organisation left without an administrator, and the backup's condition, which opens the health address — with filters and *mark all as read*. Filters and entries for events a person never receives are not drawn: a non-administrator sees their own group changes, each leading to the document list; an administrator's leads to the group. A failed email leads to the outbox that holds it (DL-0385). An entry whose document its reader can no longer open is not drawn and not counted (DL-0386). Opening a notification marks it read. An email goes in its recipient's language, fixed when it is queued (DL-0501).

| Region | Release | Stories | Built by |
|---|---|---|---|
| both tabs | **0.1** | ST-0004, ST-0030, ST-0035, ST-0036, ST-0047, ST-0048, ST-0051, ST-0052, ST-0070 | Epic 14; the correction notice's part entries and counted line, Epic 13 |
| levels a person chooses; a read-and-act workflow | **later** — B-028, B-029 | — | — |

## Help

Pages rendered from Markdown files shipped with the application (DL-0195), `/help/` opening on *reading a document* with the list beside it: how a document moves, versions and their numbers, reviewing and accepting, freezing and editions, history, comparing and undoing, editing, editing together, what the editor accepts — generated from the same specification as the editor and the parser — reading a document, exporting, template and styles, appendices and attachments, notifications, mail, people and access, finding and organising documents, and settings, access history and the audit log. Linked from every paste refusal. An installation may switch every help page to the heading and the one message *Work in progress* (`HELP_WORK_IN_PROGRESS`, off by default; DL-0344).

| Region | Release | Stories | Built by |
|---|---|---|---|
| the pages and the allowed-Markdown list — what is accepted and how it is written, and what is refused with the conversion each gets, built from the specification: its limits, entities and callout types, and every refusal with its conversion | **0.1**; the guide's full content B-016 | ST-0019, ST-0060 | Epic 4 |
| *Reading a document* — the version shown, clause numbers, the outline, the parts, *Info*; *Exporting* — the page's choices, the file's name, delivery and failures; *not yet drawn* | **0.1** | ST-0045 | Epic 7 |
| *Editing* — *Images*, *Roles, actions and terms*, *Mentions*; *Reading a document* — *Mentions and generated views*; *Exporting* — *Images*; *not yet drawn* | **0.1** | ST-0026, ST-0027, ST-0028, ST-0043, ST-0044 | Epic 11 |
| *Finding and organising documents* — folders and the list, search and the type filter, copying, comparing two documents; for administrators, document types, folders, archive and restore; *Reading a document* — *Comparing two documents*, a pointer here; *not yet drawn* | **0.1** | ST-0012, ST-0013, ST-0015, ST-0016, ST-0064, ST-0067 | Epic 10 |
| *Appendices and attachments* — reading them, the editor's parts panel and the rights each act needs, review and *revert*, the correction notice, exporting; the parts' sections of *Exporting*, *History, comparing and undoing*, *Reading a document* and *Reviewing and accepting*; *not yet drawn* | **0.1** | ST-0061, ST-0062, ST-0063 | Epic 13 |
| *People and access* — inviting, a forgotten password, blocking a member and one's own account and lifting a block, several organisations, the platform administrator's acts, a member's page, and the account page with the display name and the interface language; *not yet drawn* | **0.1** | ST-0002, ST-0003, ST-0004, ST-0007, ST-0054, ST-0055, ST-0065, ST-0066, ST-0076, ST-0077 | Epic 8; a member's page and *My account* Epic 20 |
| *Template and styles* — the document template, the title page layout, the stylesheet and what it may hold, the Word files' styles, the sample; the title page's sections of *Editing* and *Exporting*; *not yet drawn* | **0.1** | ST-0046, ST-0058 | Epic 16 |
| *Settings, access history and the audit log* — the organisation's three settings and their bounds, the distinct-approver check's rule; who could read a document at a day's end or an edition's approval; the platform's audit log; a past version's edit authors; *Show edit authors* in *Reviewing and accepting*; *not yet drawn* | **0.1** | ST-0006, ST-0030, ST-0050, ST-0053 | Epic 12 |

## Nothing to show here

The one response for a document or folder that does not exist, may not be seen, is archived — to anyone but an administrator — or belongs to another tenant — same status, page and timing (ADR-0008): *Nothing to show here. The link may be incomplete or out of date. Check it, or ask whoever sent it.* — with a way back to the document list.

| Region | Release | Stories | Built by |
|---|---|---|---|
| the page | **0.1** | ST-0015 | Epic 2 |

## Administration

One area with two parts in a left pane: **Platform**, for platform administrators, and **Organisation** — the tenant part — with an organisation selector for platform administrators — active and blocked organisations, a blocked one marked, never one being set up (DL-0376); a tenant administrator sees only that part, for their own organisation. The interface says *organisation* throughout; *tenant* stays in the URLs (ADR-0008). Django's own administration interface is not part of it (DL-0210).

| Section | URL | Holds | Release | Stories | Built by |
|---|---|---|---|---|---|
| the landing | `/administration/` | opens the first section the person may use (DL-0511) | **0.1** | — | Epic 20 |
| hosts | `/administration/platform/hosts/` | the platform's hosts and each tenant's, host with optional port, one default per set; every change audited (ADR-0008) | **0.1** | ST-0080 | Epic 2 |
| organisations | `…/platform/tenants/`, `…/platform/tenants/<n>/block/` | the organisations with their state and administrators; *block…* confirmed; nothing on one being set up (DL-0291) | **0.1** | ST-0065 | the list Epic 2; *block* Epic 8 |
| organisations — forms | `…/platform/tenants/new/`, `…/platform/tenants/<n>/lift/`, `…/platform/tenants/<n>/appoint/` | create with a first administrator, lift a block, appoint an administrator | **0.1** | ST-0001, ST-0071 | create Epic 2 — a registered person only; anyone else is invited from the organisation's users page afterwards; lift a block and appoint Epic 8 |
| platform administrators | `…/platform/administrators/` | each by address (DL-0434); *grant to* a registered person by address; *revoke* per row; the last one cannot be removed or blocked, the act drawn disabled with its reason (DL-0315) | **0.1** | ST-0002 | the list Epic 2; grant and revoke Epic 8 |
| mail and outbox | `…/platform/mail/` | the platform's sender, the password write-only and asked for again when the server, port, connection or user name changes (DL-0390), a user name refused on an unencrypted connection but to the same machine (DL-0388), *Send a test email*, one at a time; the outbox, its newest 200, with each email's status and attempts (DL-0202, DL-0203, DL-0392) | **0.1** | ST-0048, ST-0049 | Epic 14 |
| audit log | `…/platform/audit/` | what people, the system and agents did, newest first: when, who by address, which kind of actor, the organisation or the platform, the act's code, its object and what changed, from the event's own record; filtered by organisation or the platform, by the kind of actor, by the start of an act's code and by a period in the installation's timezone; the newest 200 matching, the page saying so | **0.1** | ST-0050 | Epic 12 |
| heuristics | `…/platform/heuristics/` | the catalogue | **0.2** — drawn as a placeholder | — | — |
| users | `/administration/tenant/users/` | each membership by its address alone, never a display name (DL-0403), the address opening the member's page (DL-0505); *invite by email*, with groups to join, answering alike for a known and an unknown address (ASR-17) — the invitation's email worded to fit a person with an account and one without, telling neither apart (DL-0511), and sent in the installation's default language (DL-0501); *block…*, asking which of the organisations one administers; the last active administrator's *block* disabled with its reason; *lift the block* on a membership; a membership's own state alone — a person's own block is shown on no organisation's page, so an invitation of a self-blocked address draws the row a new one does (DL-0398); lifting a self-block is not in 0.1 (DL-0254, B-033) | **0.1** | ST-0003, ST-0004, ST-0066, ST-0072 | Epic 8; the member's address as a link Epic 20 |
| a member's page | `…/tenant/users/<membership>/`, from the member's address on the users page, as its block and lift acts are addressed | the member's groups, changed here with the same acts as *members…*; a read-only table of documents per folder with the rights held; the membership's own state, never the person's own block (DL-0398); for an administrator, one line, *Administrator: reads every document in the organisation*, in place of the rows; an author-only document listed for the person who created it, noted *(author)*; an archived document left out, its links taking effect only on restore; a blocked member's page shows their state and groups, they may be taken out of a group and not added to one, and the table stands under *blocked: none of this applies now*; no new right and nothing stored (DL-0505) | **0.1** | ST-0077 | Epic 20 |
| groups | `…/tenant/groups/` | *New group* by its name; a grid of each group's rights — the viewing ladder, history, *accept*, *freeze*, *make canonical*, *reserve for editing*, the part rights; a right included by another shown as a faint tick — *edit* and the views under *accept*, *freeze* and *reserve for editing* (ADR-0016), *view accepted* under *make canonical* (DL-0234); *members…* per group, opening the group's members in a block embedded at the top of the section, with a close button — the page scrolls to it, and another group's *members…* replaces it (DL-0506) | **0.1** | ST-0005 | Epics 2, 8; the members block Epic 20 |
| document links | `…/tenant/document-links/` | which groups reach which document, as removable chips drawn inline and wrapping (DL-0511), and *link a group*; the document's title linking to the document, in the same tab, on every row — an archived one as an administrator reads it (DL-0507); locked while held or reserved, with who by address (DL-0434), and *force the release* or *end the reservation…*; author-only documents with who created them, by address; an archived document's links, which take effect on restore | **0.1** | ST-0005, ST-0015, ST-0030, ST-0051 | Epics 3, 8, 9; the holder Epic 8, the two acts Epic 9; the linked title and the chips Epic 20 |
| reservations | `…/tenant/reservations/` | every reservation in the organisation: document, holder by address (DL-0434), since when; *end the reservation…*, to its page, a reason required and told to the holder in the application, never by email (DL-0225, DL-0227, DL-0369, DL-0415) | **0.1** | ST-0030 | Epic 9 |
| folders | `…/tenant/folders/` | the tree with each folder's documents; new, rename; *delete* disabled with its reason when a folder holds anything; *move documents…* — which, and where to | **0.1** | ST-0012 | Epic 10 |
| document types | `…/tenant/document-types/` | this organisation's own list, seeded with *document*; add, rename, retire; delete only a type no document uses, never the seeded one; the last type not retired is neither retired nor deleted (DL-0235, DL-10-001, DL-10-002) | **0.1** | ST-0011 | Epic 10 |
| template | `…/tenant/template/` | the headings and starting text new documents start from, checked against the editor's allowed set and beginning with a `#` heading; the title page switch; *last changed by*; *title page layout…*, a link to its page | **0.1** | ST-0058 | Epic 16 |
| template — title page layout | `…/tenant/template/title-page/` | which details the title page shows — title, number, type, edition, approver, approval date, the document's own title-page text — each shown or not, with its position; the approval line always shown, its position chosen; left or centred; *Reset to the default form*; no logo (DL-0462, DL-0467, DL-0475, DL-0476) | **0.1** | ST-0058 | Epic 16 |
| settings | `…/tenant/settings/` | the attachment size cap in whole MB, from 1 to the platform's upload maximum; the inactivity timeout, from 5 to 480 minutes; the distinct-approver check — each bound named, a value outside it refused with its reason once, under the field (DL-0458, DL-0469, DL-0511); *Apply*, an applied change answering *Applied* (DL-0511); each change audited | **0.1** | ST-0030, ST-0053, ST-0062 | Epic 12; the refusal and *Applied* Epic 20 |
| sending address | `…/tenant/sending-address/` | the tenant's own sender or none; the password write-only and asked for again when the server, port, connection or user name changes (DL-0390); a user name refused on an unencrypted connection but to the same machine (DL-0388); *Send a test email* — to the address itself, with the step results, one at a time; the DNS note; the organisation's outbox, its newest 200, with each email's status and attempts (DL-0385, DL-0392) — a reset's email listed to a platform administrator alone (DL-0410) | **0.1** | ST-0068 | Epics 14, 8 |
| archive | `…/tenant/archive/` | archived documents, newest archived first, each with the date it was archived: *restore*, *export*; *No document is archived.* when there is none | **0.1** | ST-0015, ST-0016 | Epic 10 |
| styles | `…/tenant/styles/` | the organisation's stylesheet, *used by every document of the organisation*, its box taking the full width, as the template's does (DL-0511); *apply* checks it against the allowlist, each refusal with its line; the installed fonts; *not carried into Word files*, with lines; *export a sample PDF* and *export a sample Word file* of the text in the box, one at a time, with its progress and link; *last changed by* (DL-0230, DL-0464, DL-0465, DL-0466) | **0.1** | ST-0046 | Epic 16; the box's width Epic 20 |
| access history | `…/tenant/access-history/` | a document, or *any document* (every access change up to then, the newest 200), and a date — the end of that day in the installation's timezone — or, for a document, one of its editions, answering at the moment it was approved (DL-0461): which groups could read it then, each linked and each right granted with who did it and when, and its members that day by the membership's own state, each with who added them and when; a line each for a document not yet created, archived, the organisation blocked, no canonical edition yet; the changes to access that led there. People by address (DL-0434) | **0.1** | ST-0006 | Epic 12 |
| actions and side-document types | `…/tenant/actions/` | which are attached to which documents | **0.2** — drawn as a placeholder | — | — |

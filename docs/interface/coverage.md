---
tags:
  - interface
aliases:
  - Syngraphē story coverage
status: active
date: 2026-09-27
---

# Story coverage

Every release 0.1 story against the page regions that carry it, and whether [`mockup.html`](mockup.html) draws them yet. It answers the question [`pages.md`](pages.md) cannot answer of itself: which stories have no place on a page. ST-0073 and ST-0074 have none by design: each is a command the operator runs from the command line.

**Derived by `scripts/derive_coverage.py`** from the *Stories* column of each region table in `pages.md` and its *not yet drawn* marks, and from the stories of [`user-stories.md`](../user-stories.md) in their order — a withdrawn story and one outside release 0.1 left out; run it whenever either file changes. A region is named by its section — a page's heading, or the page and its subsection, as `Document page › The draft's page` — then the region cell up to its first ` — ` or `; `, emphasis removed, cut at 58 characters; a region named as its section is the section alone. A story's title stops before its *so that* or at its sentence's end. A story is **drawn** when every region carrying it is drawn, **partly drawn** when some are, **not yet drawn** when none are. A region for a later release carries no 0.1 story (DL-0228).

**76 stories:** 47 drawn · 27 partly drawn · 0 not yet drawn. Without a region: ST-0073, ST-0074.

| # | Story | Where | Drawn |
|---|---|---|---|
| ST-0057 | As the person standing the platform up, I create the first platform administrator | Sign-in pages — the first-run page | drawn |
| ST-0001 | As a platform administrator, I create a tenant | Administration — organisations | drawn |
| ST-0065 | As a platform administrator, I block a tenant | Help — People and access; Administration — organisations | partly drawn |
| ST-0071 | As a platform administrator, I lift a tenant's block | Administration — organisations | drawn |
| ST-0002 | As a platform administrator, I grant platform administration to another user | Help — People and access; Administration — platform administrators | partly drawn |
| ST-0003 | As a tenant administrator, I add a user to my tenant by email address | Help — People and access; Administration — users | partly drawn |
| ST-0004 | As a tenant administrator, I block a user | Notifications — both tabs; Help — People and access; Administration — users | partly drawn |
| ST-0072 | As a tenant administrator, I lift the block on a person's membership in my tenant | Administration — users | drawn |
| ST-0066 | As any user, I block my own account | Account page — Block my account…, apart at the page's foot; Help — People and access; Administration — users | partly drawn |
| ST-0076 | As any user, I choose the language of the interface I see, Ukrainian or English, on my account page | Shell — the person icon ending the row, the link to their account …; Account page — the person's email address, read-only; Account page — the interface's language; Account page — Sign out · Вийти; Help — People and access | partly drawn |
| ST-0078 | As any user, I set my own display name on my account page | Shell — the person icon ending the row, the link to their account …; Account page — the person's display name, with Apply | drawn |
| ST-0005 | As a tenant administrator, I manage groups — their rights, their members, and the documents they are linked to | Document page — Більше (⋯), the administrator's acts (DL-0522); Administration — groups; Administration — document links | drawn |
| ST-0077 | As a tenant administrator, I open a member's page | Help — People and access; Administration — a member's page | partly drawn |
| ST-0006 | As a tenant administrator, I read the history of access changes — memberships, a group's rights, a document's links | Help — Settings, access history and the audit log; Administration — access history | partly drawn |
| ST-0007 | As a user with memberships in several tenants, I switch between them | Shell — the organisation; Sign-in pages — the choice of an organisation; Help — People and access | partly drawn |
| ST-0008 | As a user, I sign in with an email address and a password | Sign-in pages — the three forms | drawn |
| ST-0054 | As an invited person, I accept an invitation and set a password | Sign-in pages — the three forms; Help — People and access | partly drawn |
| ST-0055 | As a user, I reset a forgotten password | Sign-in pages — the three forms; Help — People and access | partly drawn |
| ST-0009 | As a user holding *create and edit*, I create a document by giving it a title, a language, a type and a folder | Document list — create; Create or copy a document — create | drawn |
| ST-0058 | As a tenant administrator, I edit my organisation's document template and choose whether documents get a title page | Document page › The draft's page — the title page, to the holder, in the panel below the part…; Help — Template and styles; Administration — template | partly drawn |
| ST-0051 | As a tenant administrator, I am notified when a document is created or copied | Document list — state tags after the title; Document page — state tags, as in the list; Notifications — both tabs; Administration — document links | drawn |
| ST-0010 | As a tenant administrator, I change a document's type | Document page › History and Info — Info, info/, from its icon | drawn |
| ST-0011 | As a tenant administrator, I maintain my organisation's list of document types | Administration — document types | drawn |
| ST-0012 | As a tenant administrator, I create, rename and delete folders and move documents between them | Document list — folder tree; Document list — folder visibility; Document list — Folders ▾; Help — Finding and organising documents; Administration — folders | partly drawn |
| ST-0067 | As a user holding *create and edit*, I copy a document I can read into a new one | Document list — Копіювати; Create or copy a document — copy; Help — Finding and organising documents | partly drawn |
| ST-0013 | As a user, I browse the document list and filter it by type and by folder | Shell — All documents; Shell — Being edited; Document list — folder tree; Document list — search box; Document list — filter by type; Document list — #; Document list — title; Document list — sorting; Document list — Canonical; Document list — Latest; Document list — part markers; Document list — ✎; Being edited, In review — grouped list, filtered tree; Search results — grouped results, filtered tree; Search results — search box; Search results — filter by type; Search results — nothing found; Help — Finding and organising documents | partly drawn |
| ST-0014 | As a reviewer, I see each document's current state in the list | Shell — In review; Document list — state tags after the title; Document list — Latest; Being edited, In review — grouped list, filtered tree; Document page — state tags, as in the list | drawn |
| ST-0015 | As a tenant administrator, I archive a document | Document page — state tags, as in the list; Document page — Більше (⋯), the administrator's acts (DL-0522); Help — Finding and organising documents; Nothing to show here — the page; Administration — document links; Administration — archive | partly drawn |
| ST-0016 | As a tenant administrator, I restore an archived document | Document page — Більше (⋯), the administrator's acts (DL-0522); Help — Finding and organising documents; Administration — archive | partly drawn |
| ST-0017 | As an editor, I open an editor on a document and hold it | Document page — the acts, on one line beneath the version they apply to, h…; Document page › The draft's page — Start editing; Document page › The draft's page — a stopped editor; Document page › The draft's page — inactivity prompt; Document page › The draft's page — the address while someone else holds or has reserved the d… | partly drawn |
| ST-0018 | As any user of a document, I see that it is *held* · *зайнятий* — someone is editing it — in the document list and on the document | Document list — state tags after the title; Document page — bands across the top; Document page — state tags, as in the list; Document page — the hold and the freeze marks, under the latest version | drawn |
| ST-0069 | As an editor holding *reserve for editing*, which includes *edit* (ADR-0016), I reserve a document I am editing | Shell — My reservations; Document page — bands across the top; Document page — the hold and the freeze marks, under the latest version; Document page › The draft's page — the draft's acts, on one line beneath its point (DL-0518):… | drawn |
| ST-0070 | As an editor whose reservation an administrator ended, I learn who ended it, when and why, and keep my work | Document page — bands across the top; Document page › The draft's page — the holder's kept draft; Notifications — both tabs | drawn |
| ST-0019 | As an editor, I write and format text with headings, lists, bold, underline, italics, quotes, callouts and tables | Shell — Help; Document page › The draft's page — the editor, the whole document in it, open on arrival (DL-…; Document page › The draft's page — paste refusal; Document page › The draft's page — image refusal; Help — the pages and the allowed-Markdown list | drawn |
| ST-0020 | As an editor, I never need a Save button, because my work is captured as I type | Document page › The draft's page — capture indicator | drawn |
| ST-0060 | As an editor, I switch the editor to Markdown source and type or paste Markdown there | Document page › The draft's page — the editor, the whole document in it, open on arrival (DL-…; Help — the pages and the allowed-Markdown list | drawn |
| ST-0061 | As an editor, I add, rename, reorder and delete a document's appendices, as my groups' part rights allow | Document page — parts; Document page › The draft's page — the parts panel, on the right while holding the document; Appendix page — the page; Historical page — the appendices at that version, each on its own page; Help — Appendices and attachments | partly drawn |
| ST-0062 | As an editor, I attach files to a document — a form, a spreadsheet template — and replace, rename, reorder, download or delete them, as my groups' part rights allow | Document page — parts; Document page › The draft's page — the parts panel, on the right while holding the document; Help — Appendices and attachments; Administration — settings | partly drawn |
| ST-0021 | As an editor, I undo changes I have just made | Document page › The draft's page — the editor, the whole document in it, open on arrival (DL-… | drawn |
| ST-0079 | As an editor, I clear the formatting of a passage in one act | Document page › The draft's page — the editor, the whole document in it, open on arrival (DL-… | drawn |
| ST-0022 | As an editor, I discard my edits | Document page › The draft's page — the draft's acts, on one line beneath its point (DL-0518):…; Send-for-review screen — the screen | drawn |
| ST-0023 | As an editor, I see a clause number beside every paragraph | Document page › A version's page — the version's text; Appendix page — the page | drawn |
| ST-0024 | As any reader of a document, I navigate by an outline of its sections and subsections | Document page — outline | drawn |
| ST-0026 | As an editor, I mark a piece of text as a role, an action or a term | Document page › A version's page — the version's text; Document page › The draft's page — the editor, the whole document in it, open on arrival (DL-…; Help — Editing | drawn |
| ST-0027 | As any reader of a document, I see the directory of roles it declares, with each role's rights and obligations and the paragraphs they come from | Document page — generated views; Historical page — the generated views of that version; Help — Editing | drawn |
| ST-0028 | As an editor, I upload an image and place it in the text | Document page › The draft's page — paste refusal; Document page › The draft's page — image refusal; Help — Editing | drawn |
| ST-0029 | As an editor, I press *finish editing*, see what my changes introduce, and either continue editing or commit | Document page — the notice after send for review; Document page › The draft's page — the draft's acts, on one line beneath its point (DL-0518):…; Send-for-review screen — the screen | drawn |
| ST-0030 | As a tenant administrator, I release a document held by someone who has gone quiet | Document page — Більше (⋯), the administrator's acts (DL-0522); Document page › The draft's page — a stopped editor; Document page › The draft's page — inactivity prompt; Notifications — both tabs; Help — Settings, access history and the audit log; Administration — document links; Administration — reservations; Administration — settings | partly drawn |
| ST-0031 | As a reviewer, I read everything committed since the last acceptance, in order, with each change attributed to its author | Document page › The draft's page — My edits, a switch inside the editor (DL-0518); Document page › The review page — the run's text; Document page › The review page — change authors; Document page › The review page — the panel | drawn |
| ST-0032 | As a holder of a history right on a document, I step through its versions one at a time, with a visible boundary between what has been accepted and what has not | Document page — the path; Document page › History and Info — History, history/, from its icon; Historical page — the page; Historical page — the appendices at that version, each on its own page; Historical page — Show edit authors | drawn |
| ST-0033 | As a reviewer, I compare any two versions directly | Document page — the path; Document page › History and Info — History, history/, from its icon; Compare — version comparison, ‹ and ›, attachment list | drawn |
| ST-0034 | As a reviewer, I see that an image changed and view the old and new side by side | Document page › The review page — the run's text | drawn |
| ST-0063 | As a reviewer, I see every appendix and attachment that was added, replaced, renamed, reordered or removed, and can download each version of an attachment and revert the operation before accepting | Document page › The review page — every part operation; Help — Appendices and attachments | partly drawn |
| ST-0035 | As a reviewer, I correct wording I find unacceptable and accept the result | Document page — the acts, on one line beneath the version they apply to, h…; Document page › The draft's page — to a holder of accept editing while a run is pending; Send-for-review screen — the screen; Notifications — both tabs | drawn |
| ST-0036 | As a reviewer, I accept the run of versions since the last acceptance, making the current text the accepted baseline | Document page › The review page — Погодити N; Notifications — both tabs | drawn |
| ST-0052 | As a reviewer, I return a run without accepting it, giving a reason | Document list — state tags after the title; Document page — state tags, as in the list; Document page › The review page — Погодити N; Notifications — both tabs | drawn |
| ST-0053 | As a tenant administrator, I switch on a check that a document cannot be made canonical by anyone who accepted any of its runs since the previous canonical edition | Document page — Затвердити як N.0… on the latest accepted version; Help — Settings, access history and the audit log; Administration — settings | partly drawn |
| ST-0037 | As a reviewer, I undo one pending version, or everything one author contributed since the last acceptance | Document page › The draft's page — to a holder of accept editing while a run is pending; Document page › The review page — the panel | drawn |
| ST-0038 | As a holder of the freeze right, I freeze a document | Document page — bands across the top; Document page — Заморозити / Розморозити on the latest accepted version; Document page — the hold and the freeze marks, under the latest version; Document page › The draft's page — the address while someone else holds or has reserved the d…; Document page › The review page — Заморозити / Розморозити | drawn |
| ST-0039 | As a holder of the make-canonical right, I make a document canonical | Document page — Затвердити як N.0… on the latest accepted version | drawn |
| ST-0064 | As any reader, I compare two different documents — a version of each that I may read | Document list — Compare documents…; Compare — comparing two documents; Help — Finding and organising documents | partly drawn |
| ST-0040 | As a holder of the freeze right, I unfreeze a document | Document page — Заморозити / Розморозити on the latest accepted version; Document page › The review page — Заморозити / Розморозити | drawn |
| ST-0041 | As a holder of *view previous canonical versions*, I see the list of canonical editions and compare any two | Document page › History and Info — History, history/, from its icon; Historical page — the page; Compare — version comparison, ‹ and ›, attachment list | drawn |
| ST-0042 | As a reader, I read a document, with its numbering and outline, and always know which version I am reading | Document page — breadcrumb, #12, title, and the version shown, in the head…; Document page — the path; Document page — the text; Document page › A version's page — the version's text | drawn |
| ST-0043 | As a reader, I follow a mention of another document as a link when I have access to it | Document page › A version's page — mentions; Document page › The draft's page — the editor, the whole document in it, open on arrival (DL-…; Help — Editing | drawn |
| ST-0044 | As any reader of a document, I see an automatically maintained *see also* listing the documents it links to, filtered the same way | Document page — generated views; Historical page — the generated views of that version; Help — Editing | drawn |
| ST-0045 | As a reader, I export a stated version to PDF, to Word or to Markdown | Export — the page; Export — What checkboxes, all checked by default; Export — embedded / separate; Export — View; Export — Changes; Export — what will be delivered; Export; Export — ? beside each section's heading; Export — file names; Export — the file's pages; Help — Reading a document | partly drawn |
| ST-0046 | As a tenant administrator, I edit the stylesheet the exports are rendered with | Help — Template and styles; Administration — styles | partly drawn |
| ST-0075 | As a reader, I download a file attached to the version of a document I may read | Document page — parts; Historical page — the page | drawn |
| ST-0047 | As any user, I see in the application what is waiting for me | Shell — notifications; Notifications — both tabs | drawn |
| ST-0048 | As any user, I receive an email for the same events | Notifications — both tabs; Administration — mail and outbox | drawn |
| ST-0068 | As a tenant administrator, I configure my organisation's own sending address | Administration — sending address | drawn |
| ST-0049 | As a platform administrator, I configure the sending address and its credentials | Administration — mail and outbox | drawn |
| ST-0050 | As a platform administrator, I read a log of what people did | Help — Settings, access history and the audit log; Administration — audit log | partly drawn |

## Not in release 0.1

Parts of a 0.1 story that the release leaves out, so no region carries them:

| # | Left out | Where it went |
|---|---|---|
| ST-0066 | lifting a self-blocked account — the database is the recovery path | DL-0254, backlog B-033 |

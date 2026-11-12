---
tags:
  - story
aliases:
  - Syngraphē user stories
status: active
date: 2026-09-21
---

# User Stories

Release 0.1 — the editor and the exporter (DL-0043, DL-0081) — then, after its boundary, the first stories of release 0.2, the AI reader (§ Release 0.2 — the AI reader), with that release's own boundary at its end.

**Reading this file.** One story per line, with acceptance criteria only where they carry something the story does not. Stories marked *(skeleton)* form the thinnest end-to-end path — one person taking a document, editing it, committing, having it accepted, frozen, approved and exported. If only those were built, the product would work for one user doing one thing, which is the point of a walking skeleton.

---

## Access and tenancy

**ST-0057** — As the person standing the platform up, I create the first platform administrator, so that there is somebody who can do everything else. *(skeleton)*
- The install command prints a one-time setup token; a first-run page accepts only that token, then the administrator's email address and password (DL-0231).
- The token is single-use and expires. Once a platform administrator exists, the page answers as an address that does not exist (ADR-0008). Every other story assumes it has happened.

**ST-0001** — As a platform administrator, I create a tenant, so that an organisation can have its own independent workspace. *(skeleton)*
- The tenant is created with its first tenant administrator, a person already registered on the platform; anyone else is invited from the tenant's users page afterwards (DL-0412).
- An active tenant always has at least one active tenant administrator.
- Later tenant administrators are appointed by a platform administrator from the organisations page, among the organisation's active members.

**ST-0080** — As a platform administrator, I list the names the platform answers on and each organisation's domains, add and remove them, and choose the default of each set, so that links and mail carry the right name (ADR-0008).
- A name is a host with an optional port; each set has one default; every change is audited.

**ST-0073** — As the operator of an installation, I add a person to a tenant from the command line, so that people can sign in before invitations exist.
- The command creates the person if the email address is new and gives them an active membership in the named tenant; it never makes a tenant administrator.
- It generates a password that meets DL-0284 and prints it once; a password is never a command argument, so it never reaches a shell's history. The person receives it from the operator by hand.
- Groups and document links are made on the tenant's own pages, as for anyone else.

**ST-0065** — As a platform administrator, I block a tenant, so that nobody but platform administrators can reach it.
- A blocked tenant may have no users at all.
- The block ends every hold and reservation in the tenant; drafts with edits are kept (DL-0256, DL-0514).

**ST-0071** — As a platform administrator, I lift a tenant's block, so that an organisation blocked by mistake or for a settled reason can work again.
- Its memberships, groups and links apply as they stood; nothing is rebuilt by hand. The change is typed history, like the block.

**ST-0002** — As a platform administrator, I grant platform administration to another user, so that I am not the only person who can operate the platform.
- The last platform administrator cannot be blocked or lose the role; the command line and the database are the recovery path.

**ST-0003** — As a tenant administrator, I add a user to my tenant by email address, so that they can work on our documents.
- The email is the platform identifier, so a person already registered elsewhere is added, not created.
- What I see is identical either way: same screens, same wording, same timestamp. I learn nothing about their existence elsewhere (ASR-17).

**ST-0004** — As a tenant administrator, I block a user, so that they lose access to our documents without losing access to other organisations they work with.
- Blocking sets the membership state; nothing about the person changes.
- If I administer several tenants the person belongs to, I am asked which of them to block them in. I never see or touch tenants I do not administer; a platform administrator is notified when the person stays active elsewhere.
- I cannot block a tenant's last active administrator. If that is me, I can block myself only when I am also its last active user.
- The block ends every hold and reservation the person has on our documents; their drafts with edits are kept, and each release is recorded with the block as its cause (DL-0256, DL-0514).

**ST-0072** — As a tenant administrator, I lift the block on a person's membership in my tenant, so that someone who returns regains access through the groups they were in.
- Their group memberships apply as they stood. A self-blocked account (ST-0066) stays blocked: only a platform administrator lifts that.

**ST-0066** — As any user, I block my own account, so that nobody can use it while I cannot.
- *Block my account…* stands apart at the foot of my account page (ST-0076), confirmed before it acts; the menu row does not offer it (DL-0499, DL-0500). To the last platform administrator the control is drawn disabled with its reason (DL-0315, DL-0233).
- It blocks every membership I hold; only a platform administrator can lift it, and not through the interface in this release — the database is the recovery path (DL-0254, backlog B-033). There is no deleting an account (backlog B-022).
- Blocking myself ends my holds and reservations; my drafts with edits are kept (DL-0256, DL-0514).

**ST-0076** — As any user, I choose the language of the interface I see, Ukrainian or English, on my account page, so that I meet the platform in my own language.
- My account page is `/account/`, reached from the person icon at the end of the menu row, which names me — by my display name, my address while I have none — when I point at it (DL-0525, DL-0541); *Sign out* · *Вийти* stands there and nowhere else. It shows my email address, read-only; the interface's language with *Apply*; and, apart at its foot, *Block my account…* (ST-0066) — nothing more of a profile (DL-0499, DL-0500).
- The choice is stored as my own preference and applies to every page I open; until I choose, I see the installation's default language (DL-0498, DL-0501).
- Pages before sign-in use the installation's default, except a reset or invitation page opened from its link, which uses the preference of the person the link belongs to (DL-0501).
- An email to me goes in my language, fixed when it is queued; an invitation goes in the installation's default (DL-0501, ASR-17). A version's change summary stays in the language its writer left it in (DL-0321).
- A document's own language — its text, its numbering, its exports — is the document's and does not follow my choice (DL-0498, DL-0502).

**ST-0078** — As any user, I set my own display name on my account page, so that colleagues know me by the name I chose wherever the organisation's pages name a person (DL-0523).
- My account page shows my display name with *Apply*: required, at most 200 characters, spaces at either end dropped. Edit authors, holders, histories and notifications name me by it; administration pages keep naming me by my address (DL-0434).
- A name another active or blocked member of any of my organisations uses is refused, whatever its case or its spaces — *Another member already uses this name*, naming no organisation; nothing is saved. A name used only in an organisation I do not belong to is mine to take (DL-0537).
- `create_member` checks a new person's name the same way. A person invited is created without a name and names themselves here; until then pages name them *anonymous editor* (DL-0339).
- Joining an organisation keeps its names unique: an invitation, or `create_member`, that would bring me in while my name is used there is refused, without my name; I change it here first (DL-0537).
- My account stays my address: there is no separate username.

**ST-0005** — As a tenant administrator, I manage groups — their rights, their members, and the documents they are linked to — so that people see and do exactly what their job requires (ADR-0007).
- Rights: a viewing ladder (view canonical, view accepted, view pending, edit, create and edit), history rights (view previous canonical versions, view all history), acts (accept, freeze and unfreeze, and reserve for editing, each of which includes edit (ADR-0016); make canonical, which includes the accepted view it approves), and part rights (create or delete appendices; upload, replace or delete attachments).
- A person holds the union of the rights of their groups linked to a document; nothing is granted to a person directly.
- I cannot change a document's links while someone is editing it; I see who it is and ask them to finish, or force the release as a last resort (ST-0030); for a reserved document, I end the reservation with a reason (ST-0070).
- *Synthetic example:* a finance policy linked to *Accountants* (view canonical), *Finance reviewers* (accept) and *Executives* (make canonical).

**ST-0077** — As a tenant administrator, I open a member's page, so that I see in one place which groups they are in and what they may do on each document.
- Reached from the member's address on the users page, which names them by the address alone (DL-0403, DL-0505). Nothing new is stored and no right is added: the page reads what the groups and links already say.
- It lists the member's groups, which I change there with the same acts as a group's *members…*, and a read-only table of documents per folder with the rights held. An archived document is left out, its links taking effect only on restore; an author-only document is listed for the person who created it, noted *author*.
- For an administrator it shows one line, *Administrator: reads every document in the organisation*, in place of the rows (ADR-0007).
- It shows the membership's own state, never the person's own block (DL-0398). A blocked member's page shows their state and groups; I may take them out of a group and not add them to one, and the table stands under *blocked: none of this applies now*.

**ST-0006** — As a tenant administrator, I read the history of access changes — memberships, a group's rights, a document's links — so that I can answer who could see a document at any past date and who granted that.
- The answer is retrievable for a date in the past, not only for now (ASR-18).

**ST-0007** — As a user with memberships in several tenants, I switch between them, so that I work in one organisation at a time.
- A user with one membership sees the tenant's name, plain. With two or more active memberships the name is a link: it opens a window listing my organisations, each one a switch, and a page of its own with the same list when no script runs; the switch itself is a POST (DL-0525, DL-0497).
- Nothing is visible, searchable or linkable across the boundary.

**ST-0008** — As a user, I sign in with an email address and a password, so that the platform knows which rights I hold. *(skeleton)*
- Repeated failures are **throttled with a growing delay**, never a hard lock — a lock answers differently from an unknown address, and anyone who knows my address could otherwise shut me out (DL-0116). Sessions expire.
- The response is the same whether or not the address is known.

**ST-0054** — As an invited person, I accept an invitation and set a password, so that I can start work.
- The link is single-use and expires. There is no self-registration — a person exists because a tenant administrator invited them.

**ST-0055** — As a user, I reset a forgotten password, so that losing it does not need an administrator.
- The response is the same whether or not the address is known, and the link is single-use and expiring.

**ST-0056** — As a person exercising a right to erasure, I have my name and address removed, so that the platform no longer holds them. *Not in stage 1 — backlog B-017 (DL-0186).*
- What I did remains in the record, attributed to a *former user*. The identifier stays; the person does not (DL-0108).

---

## Documents and organisation

**ST-0009** — As a user holding *create and edit*, I create a document by giving it a title, a language, a type and a folder, so that work can begin on it. *(skeleton)*
- Language comes from a fixed list; a document carries exactly one. The form offers the installation's default language first, until my organisation has a language of its own; it follows neither my interface language nor the list's order (DL-0512). The folder may be the root.
- Only I can reach it until the tenant administrator links groups to it, who is notified; from the first link I reach it through my groups (ADR-0007).
- The new document's text is the organisation's document template: its section headings and any starting text (DL-0169).

**ST-0058** — As a tenant administrator, I edit my organisation's document template and choose whether documents get a title page, so that every new document starts with the structure we expect.
- One template per organisation: Markdown in the editor's allowed set, beginning with a `#` heading, holding no image, at most 20,000 bytes (DL-0481); each refusal named by its line. Editing it changes documents created afterwards, each starting from it in the platform's form for its language, never existing ones; the page says who last changed it and when (DL-0482).
- *New documents get a title page* sets the switch a new document starts with; each document's own switch is changed by its holder as a draft change, committed with the run and shown to the reviewer (DL-0463).
- The title page is generated at export from the document's metadata through a layout I configure — which of title, number, type, edition, approver, approval date and the document's own text it shows, in which order, left or centred, the approval line always present (DL-0462, DL-0475); nobody types it as a page (DL-0164). One detail is the document's own title-page text — an internal code, a register entry — written by its holder as a draft change, as the title is (DL-0476).

**ST-0051** — As a tenant administrator, I am notified when a document is created or copied, so that I link its groups while only its author can reach it.
- Until a linked group holds accept, the document reads *no reviewer assigned* and acceptance is refused with that reason rather than failing quietly.

**ST-0010** — As a tenant administrator, I change a document's type, so that it is filed correctly as its purpose becomes clear.

**ST-0011** — As a tenant administrator, I maintain my organisation's list of document types, so that documents are classified the way we work (DL-0235).
- A new tenant starts with one type, *document*. I add, rename and retire types; a type still assigned to a document can be retired, never deleted.
- *Synthetic example:* policy, controls, technical instruction.

**ST-0012** — As a tenant administrator, I create, rename and delete folders and move documents between them, so that a growing set stays navigable.
- Folders nest without limit and are presentation only; moving a document changes nothing about the document itself or who may read it (ASR-15).
- A folder holding a document or a subfolder cannot be deleted.
- People see only folders holding, at any depth, a document they may read; administrators see all (DL-0206). Folders sort alphabetically.

**ST-0067** — As a user holding *create and edit*, I copy a document I can read into a new one, so that a similar policy starts from existing text.
- I start it from the document list — *Copy* · *Копіювати* on the document's row — not from the document's page (DL-0520).
- I choose the version: canonical, accepted, or pending edits (the default), among those I may see. The copy starts with that text and no history, no accepted or canonical version.
- I choose which appendices to copy — none, all, or some. Attachments are never copied, and I am told so.
- The copy is author-only until groups are linked, like any new document. Administrators see where it came from: source, version number, commit, time and who copied it.

**ST-0013** — As a user, I browse the document list and filter it by type and by folder, so that I find what I need in a corpus that grows.
- A search box finds documents by their titles and their appendices' titles, never by text; results are grouped by full folder path, and the folder pane shows only folders with results.
- I always browse inside a folder, the organisation's root included (DL-0197). *Being edited* · *У редагуванні* and *In review* are views of their own, showing only the folders that hold matching documents.
- Each row starts with the document's number, `#7`.
- Each row shows the canonical version, linking to it, and the latest version I may see beyond it, linking where the title does (DL-0208); icons for appendices and attachments; the title opens the reading view, the pencil the editor. Export is on the document page, not the list.
- Copying a document and comparing two documents start from the list: *Copy* on each row, *Compare documents…* for the pair (DL-0520, ST-0067, ST-0064).
- With *create and edit*, the list offers *create document*.

**ST-0014** — As a reviewer, I see each document's current state in the list, so that I decide whether to review now or wait for more edits to arrive.
- The state distinguishes canonical, accepted, and pending edits awaiting review.

**ST-0015** — As a tenant administrator, I archive a document, so that material that is no longer current stops appearing in the corpus.
- Its links stop resolving everywhere, including where its name is written in another document's text.
- Only administrators see it. It enters no analysis scope, and administrators can still export it.
- Its group links stay; I can change them while it is archived, and they apply as they then stand when it is restored.

**ST-0016** — As a tenant administrator, I restore an archived document, so that material put away by mistake or revived by circumstance comes back exactly as it was.
- Its group links apply as they stand; nothing is rebuilt by hand (DL-0084).

---

**ST-0074** — As the operator of an installation, I load a hand-prepared document with its attachments from a folder as its first accepted version, so that documents written outside the platform can be read in it (DL-0080, DL-0348). Readers of canonical text read it once it is made canonical by the operator's `make_canonical` (DL-0350).
- The document is created as any other, then its text and every attachment are committed together as one version by a named member, who accepts it as `0.1` through the same act the interface performs — refused unless that member holds *create and edit* and *accept* through a group.
- A folder whose document is already loaded is skipped, so the same command can be run again after a refusal.
- The text passes the whitelist and the normalizer the editor's commit passes; a refused construct, or an attachment over the tenant's size limit, is named, and nothing is written for that document.

## Editing

**ST-0017** — As an editor, I open an editor on a document and hold it, so that I can change it without anyone else changing it underneath me. *(skeleton)*
- *Edit* · *Редагувати* on the latest version opens the whole document's editor (DL-0517, DL-0518) and takes the hold when nobody holds the document — the page sends it as it mounts the editor (DL-0319); there is no separate button for it (ADR-0006), except when the editor is reached from another site, which shows *Start editing* (DL-0325).
- While I hold it, nobody else can open its editor. Holds are over the whole document.
- My draft in progress is a point of the document's path, numbered as the version it will become, shown to me alone; leaving it for another version keeps the draft and the hold (DL-0518).

**ST-0018** — As any user of a document, I see that it is *held* · *зайнятий* — someone is editing it — in the document list and on the document, so that I know to wait (DL-0262).
- If I hold *edit* or *accept* on it, or administer the organisation, I see who holds it, for every hold, ordinary or reserved — *редагує {name}* under the latest version, and as the reason beside a disabled *Edit* — so I know whom to ask; anyone else who may read it sees the fact alone (DL-0516).
- A reserved document reads *reserved for editing, since* its date (DL-0226).
- The content of the edits is never visible until a version is committed.

**ST-0069** — As an editor holding *reserve for editing*, which includes *edit* (ADR-0016), I reserve a document I am editing, so that I can mature the next iteration over days or weeks and let peers see it only when it is ready.
- I reserve from an editing session I already have; while someone else holds the document there is nothing to reserve, so reservations are never contested (DL-0218, DL-0219).
- While it is reserved it is not released for inactivity; my draft waits between sittings, and I finish it once, producing one version (DL-0213).
- I may cancel the reservation, which makes it an ordinary hold again.
- I cannot reserve a frozen document (DL-0223). I may hold several reservations; each document is on its own, and *My reservations* in the menu row, drawn only while I hold one, lists them with their start dates (DL-0227, DL-0241, DL-0525).
- While it is reserved, as while any hold lasts, nobody can freeze it or change its groups — and nobody else can review it; that is agreed with me outside the platform, or an administrator ends my reservation (DL-0223, DL-0224).

**ST-0070** — As an editor whose reservation an administrator ended, I learn who ended it, when and why, and keep my work, so that weeks of editing are never lost.
- The notification and the notice on the document carry the administrator's reason (DL-0225).
- If nobody committed since, I take the document back and may reserve it again; otherwise my draft opens read-only as changes against the current text, and I can switch the comparison to any version I may see.
- A draft I will not carry over I discard from that view, confirmed, and the document opens for editing as usual (DL-0381).

**ST-0019** — As an editor, I write and format text with headings, lists, bold, underline, italics, quotes, callouts and tables, so that a policy reads as a policy. *(skeleton)*
- Nothing outside that set is available, and anything pasted that falls outside it is refused at the moment of pasting, never silently dropped. The refusal names the offending lines and offers a conversion, shown before it is applied, and links to a help page listing what is allowed (DL-0171).
- Tables are plain: one row per line, inline content only, **no merged cells**. A table needing merged cells is restructured — the constraint is stated to the business users rather than discovered by them.
- Inside a table the **row** is what a change is attributed to, not the sentence (DL-0100).
- A table stands at the top level of the document only — never inside a list, a quote or a callout; one placed there is refused with a message (DL-0239).

**ST-0020** — As an editor, I never need a Save button, because my work is captured as I type. *(skeleton)*
- Closing the browser, or losing it, loses nothing.
- Because a user arriving from Word **will** look for it, the interface states that the work is captured rather than leaving the absence to be inferred.

**ST-0059** — *withdrawn 2026-11-02 (DL-0517). Identifier retired, never reused.*

**ST-0060** — As an editor, I switch the editor to Markdown source and type or paste Markdown there, so that text I prepared elsewhere keeps its formatting.
- Formatted text is the default; the source view is always one step away.
- The source view shows each paragraph as one line, as I would write it; how the platform stores sentences is never visible.

**ST-0061** — As an editor, I add, rename, reorder and delete a document's appendices, as my groups' part rights allow, so that material that belongs with the policy is approved with it.
- An appendix has a title I type, including any number (DL-0165); the title names it in the interface and in an exported file and is never printed in the document.
- An appendix holds one `#` section, and I edit it with the same editor as the body.
- Creating and deleting need the part rights (ADR-0007); renaming and reordering need only *edit*.
- Appendices are listed in the order I added them until I reorder them.
- I change them in the editor's own parts panel while I hold the document, and type into an appendix from *Edit* on its own page; nothing changes in the document until I finish editing (DL-0442, DL-0443).
- An appendix I added and never sent, I can always delete again; one with an editor open is not deleted.

**ST-0062** — As an editor, I attach files to a document — a form, a spreadsheet template — and replace, rename, reorder, download or delete them, as my groups' part rights allow, so that the files people need sit beside the policy they belong to.
- Every attachment has a title. Files above the organisation's size limit — set by its administrators on the settings page, 5 MB by default and never above the platform's upload maximum — are refused with the limit stated (ADR-0005, DL-0432).
- The platform never opens an attachment; replacing it keeps the earlier version in the history.
- Every change to an attachment is part of my draft and is reviewed with my text (DL-0168); I download a file as my draft holds it.
- As the author of a document no group is linked to yet, I may upload and replace attachments (DL-0445).

**ST-0021** — As an editor, I undo changes I have just made, so that a wrong turn costs seconds.
- *Undo* and *redo* are buttons in the editor's toolbar as well as the usual keys, because people arriving from Word look for them (DL-0241); they are its first two controls, *Clear formatting* the third (DL-0531).

**ST-0079** — As an editor, I clear the formatting of a passage in one act, so that text I pasted or moved reads as plain paragraphs again.
- *Clear formatting* · *Очистити форматування* acts on my selection, or on the line my cursor stands in when nothing is selected: bold, italic, underline and links go; the lines leave lists, quotes and callouts; headings become paragraphs — the same words, plain (DL-0531).
- The roles, actions and terms I marked, and my mentions of other documents, stay: they say what the text declares, not how it looks. A table keeps its shape, its cells cleared of marks. One *undo* puts everything back.

**ST-0022** — As an editor, I discard my edits, so that work I have decided against does not reach the document.
- Offered among the acts beneath my draft whenever I hold the document (DL-0518), and on the send-for-review screen beside *continue editing* (DL-0237).
- While I have no edits — no captured text, no part operation, no title page change — the control reads *Release the document* · *Звільнити документ* and releases the hold without confirmation, unless a reservation would end with it; a hold with no edits keeps nothing when it ends. After the first edit it is *Discard my edits…* (DL-0510, DL-0514).
- *Discard my edits…* is confirmed in a window over the page, which says the whole draft, text and files, is thrown away and cannot be undone, with *Discard my edits* and *Back to editing* · *Повернутись до редагування*; a kept draft is discarded the same way (DL-0513).
- It discards everything in the draft: text, and any attachment or appendix added, replaced, reordered or deleted. A file I deleted and then discarded is still there.

**ST-0023** — As an editor, I see a clause number beside every paragraph, so that I can tell a colleague exactly which passage I mean.
- The form is `1.1-3` and `4.3.2-6`: the heading path, then the clause within it — each paragraph of text is one clause.
- Inside an appendix the numbers start again from 1, with nothing in front; a reference from elsewhere names the appendix by its title in front, so *Approval matrix, 1.1-3* (a synthetic example) is unambiguous — the appendix's number is internal (DL-0444).
- The numbers are not part of the text and cannot be typed into: a heading's stands in the heading, a clause's in a gutter beside it (DL-0363).

**ST-0024** — As any reader of a document, I navigate by an outline of its sections and subsections, so that a forty-page policy is usable.

**ST-0025** — *withdrawn 2026-09-22 (DL-0126). Identifier retired, never reused.*

**ST-0026** — As an editor, I mark a piece of text as a role, an action or a term, so that the platform knows what the document is talking about.
- Marking picks an entity that already exists in the document, or declares a new one.
- Wherever the text is rendered — the reading view, the editor, DOCX and PDF — marked text is set apart by its formatting, a shaded background for example, and the syntax is never shown. The source view and the Markdown export show the marks as written (DL-0184).

**ST-0027** — As any reader of a document, I see the directory of roles it declares, with each role's rights and obligations and the paragraphs they come from, so that I can check a role without reading the whole policy.
- Derived from the marks, with no agent involved (DL-0073).

**ST-0028** — As an editor, I upload an image and place it in the text, so that a technical instruction can show a screen rather than describe it.
- PNG, JPEG and GIF are accepted; HEIC is refused outright rather than converted (DL-0074).
- Images above the size limit — 10 MB, or the platform's upload maximum where that is lower, and 40 megapixels or 10,000 pixels a side — are refused with the limit stated.
- All metadata is removed on upload — no location, no device.
- Pasting or dropping an image is an upload like any other: an image already on the clipboard — a screenshot, a copied image, an image inside copied text — is stored and always placed as a paragraph of its own (DL-0232).
- An image typed inside a sentence in the source view is refused with its line named: an image always stands on its own line (DL-0253).
- An image that exists only as a web address is left out of the paste, the rest of the pasted text goes in, and a one-line notice says the image was not pasted and to copy the image itself and paste it (DL-0232, DL-11-005).

**ST-0029** — As an editor, I press *finish editing*, see what my changes introduce, and either continue editing or commit. *(skeleton)*
- The summary and the screen's buttons stand above my changes. The summary is plain text of several lines, in a field as wide as the editor and ten lines high: its first line is the commit's subject and what every list shows, the rest its body, drawn whole on the version's page and in the review page's panel; the first line is at most 500 characters, the whole at most 5,000, and no line may read as a trailer (DL-0532, DL-0535).
- The commit carries a summary I may edit before sending. It is for whoever reviews the run, and shows with the version in the review page's panel (DL-0509) — or, for a version I accepted in the same act, in its history entry (DL-0222).
- In release 0.1 the screen shows my changes, the part operations and the summary, which starts from a mechanical draft naming the sections I touched; the agent's analyses arrive in release 0.2 on the same screen (DL-0261).
- If I also hold *accept*, the screen offers *accept as N.M* — my version and the acceptance of the whole run, other editors' versions included, in one act — and *create version N.M-X*, which leaves it pending; each shows the number that results, such as *accept as 2.4* and *create version 2.3-1* on a document accepted at 2.3 (DL-0222).
- Finishing ends a reservation (DL-0220).

**ST-0030** — As a tenant administrator, I release a document held by someone who has gone quiet, so that work is not blocked by an absence.
- I see who holds it; so do holders of *edit* or *accept* on it, for every hold (DL-0516).
- I can also end a reservation, giving a reason; its holder is notified with who, when and why, and the act is audited (DL-0225, ST-0070).
- A hold is also released on its own after a period without activity — 30 minutes unless I set another for my organisation — once its holder has been asked whether they are still working and has not answered. A reserved hold is not (ADR-0009).
- I am notified when a reservation starts, and I can list every reservation with its holder and start date (DL-0226, DL-0227).
- The interrupted draft, if it holds edits, is kept, never discarded — unless a finish of the hold had stopped after its commit, which the release completes instead (DL-0414). If the document has not changed since the draft began — no new version and no acceptance — its holder takes it back and continues; otherwise it opens read-only as changes against the current text (DL-0318).

---

## Review and acceptance

**ST-0031** — As a reviewer, I read everything committed since the last acceptance, in order, with each change attributed to its author. *(skeleton)*
- I read it on the review page, reached by *Розглянути* on the latest version, offered to a holder of *accept* while a run is pending (DL-0518).
- Authorship shows behind a checkbox, *Show edit authors*, so the same diff can be read with or without it: each author's name stands in the right margin beside the paragraph they changed, and nothing beside a paragraph without changes (DL-0504).
- Changes are marked word by word inside the formatted text, the way a word processor tracks changes; a change to formatting alone is marked as such (DL-0170).
- As an editor I see my own draft the same way, as *my edits* — a switch inside the editor (DL-0518).
- Both views show the whole document with the changes marked in place (DL-0195).

**ST-0032** — As a holder of a history right on a document, I step through its versions one at a time, with a visible boundary between what has been accepted and what has not.
- Each entry shows the version, the event — edit, acceptance, return, freeze, canonisation — and who acted (DL-0197).
- Each version opens as a historical page — from here in a new window, from its point on the path in the same one, the path above it (DL-0522): the reading view and export, never editing, and *compare with* any other version, the latest included (DL-0195).
- As a holder of *edit* without a history right — *accept*, *freeze* and *reserve for editing* include it — I read History from the latest canonical edition up: the edition, the versions and acceptances since, each opening its historical page and comparing with the others; nothing older; before the first edition, every version (DL-0524, DL-0534). Freezes are listed to holders of *view all history*.
- The history opens from *History*, an icon in the document page's heading; the path of versions on the page opens the comparison of the canonical version with the latest accepted, and the review page for the run from the latest accepted to the latest (DL-0518, DL-0522).
- Every comparison of two versions offers *‹* and *›* — *previous* and *next* as their tooltips and accessible names: for a comparison of X and Y, *‹* opens the version before X against X, and *›* opens Y against the version after Y — so a long history is read edit by edit; a version the reader may not see is skipped (DL-0209), and each stands disabled when no such version exists (DL-0508).

**ST-0033** — As a reviewer, I compare any two versions directly, so that I am not forced to read a long run one step at a time.
- The comparison shows the newer version's whole text with the changes marked, links to both versions, appendices compared in pairs I pick, and each attachment with both files and whether it changed (DL-0208).
- It carries *‹* and *›* like every comparison of two versions, so from any pair I step to the neighbouring ones (DL-0508); any other pair I open from *History* (DL-0518). They stand inside the choosers' row as icons — *From ‹ {version} to › {version} Compare* — each beside the version it steps (DL-0528).
- *Show edit authors*, the same preference as the review page's and a version's page's, names each changed paragraph of the newer text by who last edited it between the two versions, in the right margin (DL-0504, DL-0528); across more than a hundred versions the names are not drawn, and the page says so. Two documents compared carry no authors.

**ST-0034** — As a reviewer, I see that an image changed and view the old and new side by side, so that I never accept a change I could not see.

**ST-0063** — As a reviewer, I see every appendix and attachment that was added, replaced, renamed, reordered or removed, and can download each version of an attachment and revert the operation before accepting, so that a form never becomes part of an approved document unseen (DL-0168).
- Each appendix the run changed is shown after the body, its changes marked; each version's part changes are listed under it.
- *Revert* needs *accept* alone; it takes the document and joins my correction, and while it waits the run is accepted only through my draft's *accept as* (DL-0446).
- The author whose part operation I reversed is told in their correction notice (ADR-0014).

**ST-0035** — As a reviewer, I correct wording I find unacceptable and accept the result, so that a single sentence does not cost a round trip. *(skeleton)*
- I correct through *Edit* · *Редагувати*, as any editor does; there is no act of its own for it. Finishing, I am offered *accept as* on my own version (DL-0521, ST-0029).
- My correction is committed as mine and is visible as such.
- I hold the document's fate, so introducing an edit and accepting it are both mine to do.
- My correction is never silent: the acceptance that makes it authoritative — mine, or another reviewer's — generates a **correction notice** for every author whose lines I replaced or removed, one per author listing all of them, and I have no discretion over it (ADR-0001, ADR-0014). The durable rejection record the notice later feeds arrives in stage 2 (DL-0076).

**ST-0036** — As a reviewer, I accept the run of versions since the last acceptance, making the current text the accepted baseline. *(skeleton)*
- The acceptance is recorded in the document's passport, so it travels with the document and needs no second system to be believed; an export does not carry it (backlog B-038).
- Acceptance covers the whole document. Accepting only part of a run is a backlog refinement.
- I may accept work I wrote myself; the record, not a rule, is what makes that accountable (DL-0092). Finishing my own session, I can do both in one act (ST-0029).
- I cannot accept or return while the document is reserved; the screen says it is reserved and by whom (DL-0224). An ordinary hold leaves both open; it disables *Edit* and the undo, naming the holder (DL-0516).
- Every author whose lines of the run a reviewer's version replaced or removed, or whose appendix or attachment operation it reversed, receives one **correction notice** for the acceptance — their text, the accepted text, and who changed it (ADR-0014).

**ST-0052** — As a reviewer, I return a run without accepting it, giving a reason, so that I can decline work that needs rework instead of holding it or unpicking it sentence by sentence.
- The run stays pending and its authors are notified with my reason (ADR-0001).
- The return is recorded in the document's passport, like an acceptance; an export does not carry it (backlog B-038). The document list says *returned* rather than *awaiting review* (DL-0114).

**ST-0053** — As a tenant administrator, I switch on a check that a document cannot be made canonical by anyone who accepted any of its runs since the previous canonical edition, so that my organisation can show an auditor a second pair of eyes.
- Off by default. The approver must have accepted **none** of the runs since the previous canonical edition — not merely not the last one (DL-0115).

**ST-0037** — As a reviewer, I undo one pending version, or everything one author contributed since the last acceptance, so that work that should not have entered can be removed without retyping it (ADR-0015).
- I start it from the review page's panel, which lists the run's versions with their summaries: *undo this edit* on a version after the last acceptance, or *undo all of this author's edits* for an author of the run (DL-0518).
- The reversal is computed automatically and goes into my draft — the one I have open, or a new one that takes the document. It becomes my version when I finish editing, and each author whose text I removed receives a correction notice at the acceptance (ADR-0014). Nothing disappears from the history (ASR-02).
- A sentence a later version changed is not reverted: it is left as it is and listed in my draft for me to edit by hand. Choosing sentence by sentence, or word by word, is ordinary editing.

---

## Editions and approval

**ST-0038** — As a holder of the freeze right, I freeze a document, so that it stays as accepted while something outside it is resolved — an approval, a discussion with whoever approves, work in another document. *(skeleton)*
- I can freeze it only when nobody is editing it; otherwise I ask the person editing, outside the platform, to finish, or wait for the inactivity release. A reserved document has no inactivity release: I ask its holder, or an administrator ends the reservation (DL-0223).
- I may say what it waits for. Editors cannot open an editor while it is frozen; holders of *accept* can, and accept their fixes as the next number, *1.4* (DL-0189, ADR-0016).
- The freeze right includes *edit*, so I read what I freeze and may work on it like any editor before I freeze it (ADR-0016).

**ST-0039** — As a holder of the make-canonical right, I make a document canonical, so that its latest accepted version becomes the next edition — *2.0*. *(skeleton)*
- The document need not be frozen first: a freeze is for an approval that takes time, and ends by this act or by *unfreeze* (DL-0515, DL-0189).
- Refused while anybody holds the document (DL-0419) or content versions since the latest acceptance are unaccepted (DL-0267).
- *Make canonical as N.0…* · *Затвердити як N.0…* stands beneath the latest accepted version on the document page and is confirmed in a window naming the version, the edition it becomes and that it cannot be undone, with *Затвердити як N.0* and *Скасувати* (DL-0513, DL-0518).
- One person records the decision; the approving body's own procedure — a board, for example — happens outside the platform.
- The person who froze the document may be the person who makes it canonical. With the check in ST-0053 switched on, the approver must have accepted none of the runs since the previous edition (DL-0115).

**ST-0064** — As any reader, I compare two different documents — a version of each that I may read — so that I can see how a copy or a sibling policy differs from the original (DL-0187).
- Started from the document list's *Compare documents…*, not from either document's page (DL-0520); the comparison is the same word-level view as between versions, without *‹* and *›* (DL-0508).
- To compare appendices I pick one from each document myself; the platform never pairs them.

**ST-0040** — As a holder of the freeze right, I unfreeze a document, so that editing resumes once what it waited for is resolved without an approval.
- The document stays at its accepted number — *1.3* stays *1.3*; the next commit is *1.3-1*.

**ST-0041** — As a holder of *view previous canonical versions*, I see the list of canonical editions and compare any two, so that I can answer what changed between version 1.0 and version 2.0.
- This is the question the previous tool could not answer, and it is why editions are a first-class thing rather than a note in the margin.
- Met by *History*, an icon in the document page's heading, which lists the editions alone for this right, an edition's historical page and the compare page; no separate list or picker (DL-0245, DL-0518).

---

## Reading and export

**ST-0042** — As a reader, I read a document, with its numbering and outline, and always know which version I am reading. *(skeleton)*
- I see the latest version my rights allow — canonical, accepted or pending — named in the page's heading; the path's canonical point opens the latest canonical version (DL-0209, DL-0518), and no line above the text repeats either. *Export* starts on the version I am reading (DL-0529). A reader who may see only canonical text never sees pending edits or diffs, and sees no path of versions.

**ST-0043** — As a reader, I follow a mention of another document as a link when I have access to it.
- When I do not, the mention reads as ordinary text and offers no way through (ASR-16).

**ST-0044** — As any reader of a document, I see an automatically maintained *see also* listing the documents it links to, filtered the same way.

**ST-0045** — As a reader, I export a stated version to PDF, to Word or to Markdown, so that I can circulate it outside the platform. *(skeleton)*
- Export is a page of the document's own, opened by the *Export* icon in the heading; its heading shows the version that will be exported, following the view I choose (DL-0519).
- The export names the version it is of.
- Everything of the export's own is in the document's language, not mine and not the installation's: the file's name, its stance and suffix, the zip's entries, the title page's words and the attachment list; a word the catalogue lacks in that language falls back to English (DL-0502).
- Numbering, structure and images survive into all three formats.
- I choose one format, and what to include — the document, its appendices (embedded or as separate files), its attachments — all included by default; parts the document lacks are not offered. Several files come as one zip. The view: canonical, accepted, pending edits, or my edits with or without marks, as my rights allow (DL-0193, DL-0209).
- The title page and a table of the attachments — title, file name, hash — are generated; attachments themselves never go inside a text export.
- Paragraphs read as paragraphs in every format, Markdown included; the document's frontmatter is never exported.
- DOCX and PDF carry the page number in the footer and no header; the file's name carries the title, the version number and the stance exported (DL-0362).

**ST-0046** — As a tenant administrator, I edit the stylesheet the exports are rendered with, so that documents look the way the organisation expects.
- One stylesheet per organisation, used by every document; the platform's default while it has none (DL-0465).
- Checked against an allowlist, each refusal named by its line (DL-0464); tried first as a sample PDF or Word file of an invented text (DL-0466); carried into Word files through Word's own styles, what cannot be carried listed (DL-0465).

---

**ST-0075** — As a reader, I download a file attached to the version of a document I may read, so that the forms that belong with a policy reach me with it.
- Only the attachments listed in the version my rights show me are offered; any other number answers as an address that does not exist.
- The file is served under its original name and never opened by the platform; every download is recorded.

## Notifications and audit

**ST-0047** — As any user, I see in the application what is waiting for me, so that I do not have to go looking.
- Two tabs: *Document*, each entry linking to the document at the version concerned, and *Administrative*, with filters and *mark all as read*. Opening a notification marks it read (DL-0204).
- Committed versions awaiting my review, acceptances of work I wrote, a run of mine returned with the reviewer's reason, a correction notice listing my lines and parts a reviewer's version changed (ADR-0014), frozen documents awaiting a decision, a hold of mine about to be released for inactivity, a reservation of mine ended by an administrator (ST-0070), a hold of mine released because the document was archived, a document I may read frozen, unfrozen or made canonical, groups I was added to; for a tenant administrator also a document created or copied and not yet linked to any group, a reservation started (ST-0030) and an email that failed (ST-0048); for a platform administrator a person blocked in one organisation and active in another (ST-0004), an organisation left without an administrator, and a change in the backup's state.

**ST-0048** — As any user, I receive an email for the same events, so that I notice them without visiting the platform.
- It names the document, versions, people and the event, and links to the platform; it never contains text of the document (DL-0205). It is written in my interface language, fixed when it is queued (DL-0501).
- Sent from my organisation's own address if it has one, otherwise the platform's; with neither configured, no email is sent (DL-0202, DL-0203).
- Each email is queued, tried up to three times five minutes apart, and logged; a final failure notifies the administrators in the application.

**ST-0068** — As a tenant administrator, I configure my organisation's own sending address, so that notifications carry our name.
- One address or none; with none, the platform's address sends.
- *Send a test email* sends from the address to itself — *Test message*, *Test email from {host}, sent at {time}* — and reports connected, signed in, sent (DL-0202).
- The password can be replaced, never shown.

**ST-0049** — As a platform administrator, I configure the sending address and its credentials, so that notification email leaves from an address we control.
- The credential can be replaced but never read back.

**ST-0050** — As a platform administrator, I read a log of what people did, so that an unexpected change has an author and a time.
- Every record carries who created it and whether the actor was a person, the system or an agent (ASR-18).

---

## The walking skeleton

The stories marked *(skeleton)* in order: bootstrap the first administrator → create a tenant → sign in → create a document → open an editor → write text → work captured without saving → send for review and commit → read the pending changes → correct and accept → accept the run → make it canonical → read it → export it.

They carry one document through the whole cycle for one person. Everything else thickens that path: more people, more rights, more organisation, more ways to look at the same history.

## Not in stage 1

Named here so the boundary is explicit rather than inferred from absence.

| Area | Where it went |
|---|---|
| Companion actions and the reviewer agent | stage 2 (DL-0043) |
| Heuristics, companion actions, side-document types and their administration | stage 2 (DL-0049) |
| Generated views — contradictions, ambiguities, blind spots, control directory | stage 2 (DL-0044) |
| Document ADRs | stage 2 (DL-0045) |
| Comments and the annotation surface | backlog B-013 (DL-0083) |
| Disputes, the Statement of Disagreements, the decider, rejection records | EP-0002, from backlog B-010 (DL-0076) |
| Importing a Word document | backlog B-006 (DL-0080) |
| Erasure of a person's name and address (ST-0056) | backlog B-017 (DL-0186) |
| Deleting a user | backlog B-022 |
| MCP server for external agents | backlog B-007 |
| Automatic review of connected documents | backlog B-002 |
| Tenant-wide entity registry | backlog B-012 |

The role directory and *see also* are the generated views that **are** in stage 1, because with human marking each is a parser rather than an agent (ST-0027, ST-0044, DL-0448).

---

## Release 0.2 — the AI reader

The first stories of release 0.2 (DL-0554 to DL-0556). The agents never compose a prompt from what a person types: each person calls a predefined action or reads what the platform computed (DL-0056, ASR-11). A finding is shown by its kind — *contradiction*, *ambiguity* — never by a heuristic's identifier, so nobody meets prompt, model or heuristic vocabulary (DL-0554).

### Editing with the companion

**ST-0081** — As an editor, while I edit, I call one of the document's companion actions and read what my changes introduce so far, so that I fix a problem before I send it (DL-0056, DL-0032).
- Only the actions assigned to the document are offered, each called on its own; there is no field to type a request into.
- The analysis reports only what this editor's changes introduce, never the document's standing problems.
- Each finding names its kind and cites the passage it rests on; one the agent cannot ground in a passage is labelled a suggestion (`review-findings.md § Rules`).
- The same action on unchanged content returns the stored answer at once, with no new model call (ASR-12).

**ST-0082** — As an editor, on the send-for-review screen I read the analyses that will travel with my version and confirm them, so that the reviewer reads what I read (DL-0049, DL-0054).
- What was already computed for this content is shown, not computed again.
- The editor-facing analysis is written into the same commit as the content (DL-0055).

### Reviewing with the reviewer agent

**ST-0083** — As a reviewer, I read the reviewer agent's analysis of the run beside its changes, so that I judge the run by what it breaks and what it fixes (DL-0032).
- Findings are grouped as introduced, pre-existing, resolved and aggravated.
- The analysis shows what the run changes in a role's obligations (D1), read from the text wherever the role appears, whether or not it is marked (DL-0559).
- The agent runs on the version *send for review* commits, never on a draft (DL-0054).

**ST-0084** — As a reviewer who holds the guidance grant, I read a second analysis of the run against the confidential guidance, which no editor ever sees, so that I can stop a change that conflicts with it without disclosing it (DL-0095, DL-0021).
- It comes from a run of its own; the run that writes the editor-facing analysis never holds the guidance.
- A finding without a provenance tag is shown to holders of the guidance grant only (`review-findings.md § Rules`).

**ST-0085** — As a reviewer, I choose which other documents go into a review's scope, among those I may read, so that the cross-document findings come from documents that matter to this one (DL-0077, DL-0078).
- The scope offers only documents the reviewer may read; an archived document is never offered.
- Two reviewers who choose the same scope share one result.
- The result is computed once for the scope, never once per person; each person it is shown to sees a cross-document finding only if they may read every document it draws on (DL-0021).

**ST-0086** — As a reviewer, I release the editor-facing analysis to the run's authors, so that they see what I decided to show them (`technical-design.md § The reviewer agent`).
- Nothing of the reviewer agent's work reaches an author before the release.

### The document's standing problems

**ST-0087** — As anyone who may read a document, I see its standing lists of contradictions, ambiguities and blind spots for the version I am reading, so that its known open problems are in view (DL-0044, DL-0555).
- The lists are computed once for each accepted state and refreshed when it changes, never on every commit (DL-0555).
- They hold only findings derived from the document alone, so every reader of the document sees the same lists; cross-document and guidance findings stay in the reviewer's analysis of a run (DL-0555).
- Their author is shown as the system, never a person and never a model's name, beside the version they were computed for — *for version 1.3* (DL-0448).

### When an analysis is not right

**ST-0088** — As a person reading an analysis, I mark it *not right* and so inform the developer, so that a wrong output leaves the screens and the developer learns the software got it wrong (DL-0554).
- The mark is about the analysis the software produced, never about the document's sense or the person's disagreement with its prose; the control says so where it is drawn.
- One mark covers the whole analysis.
- The mark hides the analysis from every view, for everyone; the analysis is kept where it is stored.
- The mark records who set it and when.

### The catalogue and its administration

**ST-0089** — As a platform administrator, I read the heuristic catalogue the platform was loaded with, each heuristic at its version, and compose companion actions and side-document types from it, so that organisations have analyses to attach (DL-0049, DL-0153).
- An edit to a heuristic in place is a divergence from its source, which the loading command reports.

**ST-0090** — As a tenant administrator, I assign companion actions and side-document types to documents by their title and description, so that each document carries the analyses that fit it (DL-0049, ADR-0007).
- The tenant administrator never sees a heuristic or its text.

### Operating and developing the AI workbench

**ST-0091** — As the operator, I load a release's prompts into the platform with one command that reports every row differing from its source, so that the running catalogue matches the repository (DL-0153).
- The command is idempotent and records, for each row, the source version it came from.

**ST-0092** — As the operator, I read a model run's trace from the command line on the host, so that any analysis can be explained later (DL-0552, DL-0553).
- The trace names the prompt version and its eval results, each committed document read by repository and commit, the draft's text for a run over a draft, and the stored result.
- No page of the web interface shows a trace.

**ST-0093** — As the developer, I run a prompt against its eval set from the command line and keep the dated results, marking each finding right or wrong, so that a prompt changes only against a measurement (DL-0554, `evaluation-strategy.md`).
- Every case is invented; no real document's text enters the repository.

**ST-0094** — As a person waiting for an analysis, I see that it is running, and when the model fails I am told so and can ask again, so that a failure never reads as an empty analysis (B-031).
- An analysis is reported done only when the provider's answer was received and parsed.

### Not AI, in release 0.2

**ST-0095** — As a platform administrator on an organisation's own domain, I am not shown the Platform part of Administration, which works only on a platform host, so that no control is drawn that cannot be used (B-067, DL-0556).

**ST-0096** — As the administrator who receives a person's erasure request, I follow a written procedure — who may ask, who decides, what is cleared, what is kept and for how long — so that the request is never answered by improvisation (B-017, DL-0556).
- The procedure covers the draft text a trace keeps (DL-0553).

**ST-0097** — As a colleague who edits, reviews or approves, I have a guide to the platform written from my own screens, so that I can work without asking how (B-016, DL-0556).
- Written once the analyses are on the screens.

### Not in release 0.2

| Area | Where it went |
|---|---|
| Disputes, the Statement of Disagreements, the decider, rejection records | EP-0002 (DL-0550) |
| Comments and the annotation surface | backlog B-013 (DL-0556) |
| The control directory | backlog B-068 (DL-0555) |
| Voluntary views and the seeding of an authored document | backlog B-069 (DL-0555) |
| Document ADRs | backlog B-070 (DL-0555) |
| Entities proposed by the agent | backlog B-071 (DL-0555) |
| The companion's draft of the change summary | backlog B-072 (DL-0555) |
| The standing lists' guidance addendum | backlog B-074 (DL-0555) |
| The accessibility position | backlog B-018 (DL-0556) |

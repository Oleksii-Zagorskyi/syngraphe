---
tags:
  - brief
aliases:
  - Syngraphē glossary
status: draft
date: 2026-09-21
language:
  - en
  - uk
---

# Glossary

Every term in both languages, because the interface is Ukrainian and the design is in English, so each concept exists twice from the first day and the two drift silently — nothing fails when they do.

**Format.** One line per term: **English** · Ukrainian · status — meaning. No tables, so nothing reformats itself between sessions.

**Status.** *fixed* — the owner has settled it. *proposed* — the agent's suggestion, awaiting the owner. A term the owner has not seen is never treated as settled.

**One term, one line.** A concept appears once. If a second name for it appears in a document, that is a finding, not a synonym.

---

## Documents and their parts

**document** · документ · *proposed* — an authoritative text: its body, its appendices and its attachments, with its entities, images and passport beside them, in one repository.

**body** · основний текст · *proposed* — the document's main text, `document.md`.

**appendix** · додаток · *proposed* — a text that belongs to a document and is reviewed, accepted and frozen with it. One `#` section, whose heading is what the finished document shows; its **appendix title** names it in the interface and in an exported file name. Has no appendices or attachments of its own.

**attachment** · вкладений файл · *proposed* — a file kept beside a document and never opened by the platform: a form, a spreadsheet template. Has a title; replacing it keeps earlier versions; changes to it are reviewed like text.

**part** · частина документа · *proposed* — the body, an appendix or an attachment, when a sentence has to speak of all three.

**title page** · титульна сторінка · *proposed* — an optional first page generated at export from the document's metadata. Never edited. Its switch, and one plain text of the document's own, are the holder's draft changes (DL-0463, DL-0476); which details it shows, and in which order, is the organisation's layout (DL-0462).

**document template** · шаблон документа · *proposed* — the outline a new document starts from, one per organisation, kept by the tenant administrator.

**attachment list** · перелік вкладених файлів · *proposed* — the table an export generates of a document's attachments: title, file name, hash.

**frontmatter** · заголовок файлу · *proposed* — the title, the language, the title-page switch, the title-page text (DL-0476) and the lists of appendices and attachments at the top of `document.md`. Never shown in the editor and never exported; it is what a restored repository recovers its identity from.

**section** · розділ · *proposed* — a top-level heading in a document.

**subsection** · підрозділ · *proposed* — a heading below a section. Depth is capped at four.

**clause** · пункт · *fixed* — the numbered unit inside a section: one paragraph of text. *Normative Ukrainian documents number розділ → підрозділ → пункт, which is exactly our `1.1-3`; **абзац** is the typographic word and is deliberately not used here.*

**clause number** · номер пункту · *fixed* — `1.1-3` reads as розділ 1, підрозділ 1, пункт 3. Derived when the document is rendered, never stored.

**passport** · паспорт документа · *proposed* — the file recording review and approval decisions, so that approvals travel with the document rather than living only in the application.

**entity** · позначка · *proposed* — a marked piece of text: a **role** (роль), an **action** (дія) or a **term** (термін). Set apart by its formatting wherever text is rendered; its syntax shows only in the source view and the Markdown export.

**callout** · врізка · *proposed* — a set-off block of one of the allowed types: a **note** (примітка), a **warning** (застереження) or an **example** (приклад). Written as a quote whose first line names its type.

**footnote** · виноска · *proposed* — a note referred to from the text and printed apart from it. Not accepted in a document; the source view's conversion puts its text in brackets where it was referred to.

**role directory** · довідник ролей · *proposed* — the list of roles a document declares or marks, each with every heading and clause marking it, linked to its place. Derived from the version shown each time it is read, with no store (DL-0073, DL-0448).

**outline** · зміст · *proposed* — the navigable list of a document's sections and subsections.

**see also** · див. також · *proposed* — the automatically maintained list of documents this one mentions — a link where the reader may follow it, plain text in the mention's own words where they may not (DL-0071, DL-0437).

**generated view** · супровідний документ · *fixed* — a document no person writes, shown as the **system**'s (система, DL-0448). In the first release the **role directory** and **see also**, derived from the version shown each time they are read; from stage 2 also the agent's: contradictions (суперечності), ambiguities (неоднозначності), blind spots (прогалини), the control directory.

**mention** · згадка · *proposed* — words in the text naming another document by its **document number** (номер документа), written `[words]{.document #12}`: a link where the reader may read that document, the words alone where not (DL-0436, ASR-16). Not an **entity**: a mention is never declared.

**declare** · оголосити · *proposed* — to add a role, an action or a term to a document's own list of entities, by its **kind** (вид) and its **label** (найменування — the name it is listed by, never *назва*, which is a document's title); words marked with a key the document lacks are declared at the commit, labelled with their words (DL-0073, DL-0440).

**document type** · тип документа · *proposed* — each tenant's own classification of its documents; a new tenant starts with one, *document* (документ) (DL-0235). *Synthetic examples:* policy (політика), controls (контролі), technical instruction (технічна інструкція).

**folder** · тека · *fixed* — where a document appears in the interface. Presentation only; storage is flat.

**style** · стиль · *proposed* — the organisation's rendering rules: one stylesheet, authored by its tenant administrator, that every document of the organisation is read and exported with — the platform's default look while it is empty; no document selects another (DL-0230, DL-0465).

**image** · зображення · *proposed* — an uploaded PNG, JPEG or GIF, at most 40 megapixels and 10,000 pixels a side, named by its content. HEIC is refused; metadata is stripped, but for a JPEG's orientation tag (DL-0439, DL-0472).

---

## States and what a reader sees

The five stances. The Ukrainian is the owner's own and is the authority; the English follows it.

**canonical version** · канонічна версія · *fixed* — the last edition approved as authoritative.

**accepted edits** · погоджені правки · *fixed* — the last revision a reviewer accepted.

**pending edits** · всі неприйняті правки · *fixed* — everything committed since, attributed and not yet accepted.

**my edits** · мої правки · *fixed* — the holder's own uncommitted session.

**my edits in review** · мої правки на розгляді · *fixed* — what this editor has sent.

**version number** · номер версії · *proposed* — `N.M` for an acceptance, N canonical editions before it and M acceptances since; `N.0` for a canonical edition; `1.3-2` for pending work on top of acceptance 1.3, counting content versions only, and `2.0-1` for the first after edition 2.0 — counted from the later of the latest edition and the latest acceptance (DL-0267); `0.0` for the document's first version, the text as created, and `0.0-1` for pending work before the first acceptance (DL-0272, DL-0358). Derived, never typed.

**edition** · редакція · *proposed* — a canonical version, numbered `N.0` from `1.0`. Never changes once made. *Редакція документа is the standard Ukrainian for a version of a normative document, which is exactly what this is.*

**version** · правка · *proposed* — one committed change-set, the thing that appears in *мої правки*. Deliberately the same word as the stance names, because it is the same object seen from a different angle. Where a screen names one version by its number, as the send-for-review screen does beside *create version N.M-X*, it reads *версія* (DL-0336).

**draft** · чернетка · *proposed* — typed but not yet committed. Held by the platform, visible to nobody else.

**held** · зайнятий · *fixed* — somebody has the document open for editing and nobody else can. The one name for the state, in the interface's tag as everywhere else (DL-0262); the claim itself is the *hold*.

**awaiting review** · очікує на розгляд · *proposed* — the tag of a document with pending edits that no reviewer has yet accepted or returned.

**returned** · повернено · *proposed* — the tag of a run a reviewer returned without accepting; it stays pending, with the reviewer's reason. Once a version is sent after the return, the run is *awaiting review* again (DL-0114).

**no reviewer assigned** · погоджувача не призначено · *proposed* — no group linked to the document holds *accept*; acceptance is refused with this reason.

**frozen** · заморожено · *proposed* — the tag of a frozen document; everyone who may read it sees it.

**archived** · заархівований · *proposed* — put away. Its links stop resolving; its access rights sleep and return unchanged on restore.

---

## What a user does

**take for editing** · взяти на редагування · *proposed* — what opening an editor does when nobody holds the document: it takes the hold. There is no button of that name (ADR-0006), except on a tab reached from another site, which shows *Start editing* (DL-0325).

**continue editing** · продовжити редагування · *fixed* — the button that returns from the send-for-review screen to the text.

**kept draft** · збережена чернетка · *proposed* — the draft of a hold someone else ended — an administrator, the inactivity release, a block — kept for the person who was editing: offered back in the edit tab before any new editing begins. A finish and a discard keep nothing (DL-0225).

**take the document back** · забрати документ назад · *proposed* — resume editing with the kept draft, offered while the document has not changed since the draft began (DL-0318).

**discard this draft** · відкинути цю чернетку · *proposed* — throw a kept draft away, after confirming; *discard my edits* applied to a kept draft (DL-0381).

**the person editing** · той, хто редагує · *proposed* — whoever has the document open for editing, and so holds it; in the interface never *holder* or *owner*.

**discard my edits** · відкинути мої правки · *proposed* — a button in the edit tab and on the send-for-review screen (DL-0237): throws away the whole draft, text and file operations alike, after the user confirms. The document is left as it was.

**finish editing** · завершити редагування · *proposed* — the control that closes an editing session and opens the send-for-review screen, for every holder (DL-0222).

**send for review** · відправити на розгляд · *fixed* — the button on the send-for-review screen that commits, for a holder of *edit* alone. There is no Save.

**create version N.M-X** · створити версію N.M-X · *proposed* — for a holder of *accept*: commits the draft as a version that waits in pending edits. The button carries the number the version gets — *create version 2.3-1* (DL-0222).

**accept as N.M** · погодити як N.M · *proposed* — for a holder of *accept*: commits the draft and accepts the whole run since the last acceptance in one act. The button carries the accepted number that results — *accept as 2.4* (DL-0222).

**my reservations** · мої резервування · *proposed* — the list of documents a person has reserved for editing, each with its start date; in the user menu (DL-0241).

**reserve for editing** · зарезервувати для редагування · *proposed* — keep the document one holds for days or weeks: the hold is no longer released for inactivity. Taken from an open editing session, by a member of a group holding the right of the same name (ADR-0009).

**reserved for editing** · зарезервовано для редагування · *proposed* — what others see on a reserved document, with the date it began; holders of *edit* or *accept* on it, and administrators, also see by whom.

**cancel the reservation** · скасувати резервування · *proposed* — return a reserved hold to an ordinary one, released again after inactivity.

**end the reservation** · завершити резервування · *proposed* — an administrator's act on someone else's reservation, with a reason the holder reads in their notifications: the hold ends, the holder's draft is kept for them (DL-0225, DL-0415).

**force release** · звільнити документ примусово · *proposed* — an administrator's act on someone else's ordinary hold: the hold ends, the holder's draft is kept for them, and the document is free (ADR-0006). A reserved hold is not forced; its reservation is ended, with a reason.

**accept the run** · погодити правки · *fixed* — make the current text the accepted baseline: every version of the run accepted in one act; the control's name (DL-0338).

**run** · правки після останнього погодження · *proposed* — every version committed since the last acceptance, which one acceptance decides on (DL-0090, DL-0338).

**anonymous editor** · анонімний редактор · *fixed* — how a page names a person who has no display name (DL-0339).

**edit author** · автор правки · *fixed* — the person whose edit last wrote a line; *Show edit authors* · *Показувати авторів правок* is the toggle that names one beside each line (DL-0040, DL-0489).

**formatting only** · лише форматування · *proposed* — the mark of a change that altered a sentence's look, not its words or what it points at (DL-0331).

**former user** · колишній користувач · *proposed* — how a page names an erased person (DL-0108).

**correct** · виправити · *proposed* — a reviewer's act on pending edits: take the document and change what they will not accept as it stands; the changes become the reviewer's own version (ADR-0014).

**return without accepting** · повернути без погодження · *proposed* — a reviewer's act: the run stays pending and its authors are notified with the reviewer's reason; recorded in the passport like an acceptance (DL-0114).

**revert** · повернути як було · *fixed* — a reviewer's act on one row of the run's part changes: that appendix or attachment is put back as the run's base had it, in the reviewer's draft, and committed as their version. The noun is *повернення як було*. Never *повернути* alone, the verb of *return without accepting* (DL-0446, DL-0479).

**correction notice** · сповіщення про виправлення · *proposed* — generated at acceptance for each author whose lines of the run a reviewer's version — or the acceptor's own — replaced or removed, or whose removal it undid, and each author of a part — an appendix or an attachment — whose addition, removal, file or title such a version changed; one per author, listing every such line and part (ADR-0014). Never authored, never optional.

**freeze** · заморозити · *proposed* — lock a document nobody is editing against editors while something outside it is resolved; holders of *accept* may still edit (ADR-0016). Ends by *make canonical* or *unfreeze*.

**unfreeze** · розморозити · *proposed* — end a freeze and return the document to ordinary editing at its current accepted number (DL-0189).

**distinct approver check** · перевірка окремого затверджувача · *proposed* — an organisation's setting: when on, nobody who accepted any run since the previous edition may make the next one canonical (DL-0101, DL-0115).

**make canonical** · затвердити · *proposed* — end a freeze by making the latest accepted version the next edition.

**author-only** · лише для автора · *proposed* — a document that has never had a group linked: only its creator reaches it, and administrators see it; the first linked group ends it (ADR-0007).

**copy a document** · копіювати документ · *proposed* — create a new document from a version of one you may read; no history, no attachments, author-only until groups are linked.

**undo a contribution** · скасувати правку · *proposed* — a reviewer's act on the pending run: the reversal of one version (*undo this edit*) or of one author's edits since the last acceptance, applied to the reviewer's draft and committed as their version. Sentences a later version changed are left for editing by hand. Nothing is erased (ADR-0015).

**undo this edit** · скасувати цю правку · *proposed* — the History tab's control for one version of the pending run (ADR-0015).

**undo all of this author's edits** · скасувати всі правки цього автора · *proposed* — the History tab's control for one author's versions in the pending run (ADR-0015).

**compare** · порівняти · *proposed* — show two versions of a document, or versions of two documents, word by word inside the rendered text (DL-0170, DL-0187).

**history** · історія · *proposed* — the tab listing a document's versions and events; how far back a reader sees depends on their history rights, and a holder of *accept* sees the pending run's versions there (DL-0251).

**archive / restore** · архівувати / відновити · *proposed* — put a document away, reached by administrators alone and read only, every act refused; restore makes it active again as it was (DL-0084, DL-0450).

**retire** (a document type) · вивести з ужитку · *proposed* — keep a type on the documents that carry it and stop offering it for a new document, a copy or a change of type (DL-0235, DL-10-001).

**export** · експортувати · *proposed* — to PDF, Word or Markdown, of a stated version, composed from a scope, formats and a view.

**embedded appendices** · додатки у документі · *proposed* — an export's appendices after the document's body and before its attachment list (DL-0193); in PDF each starts a page of its own. The dialog's choice reads *у документі*.

**separate appendices** · додатки окремими файлами · *proposed* — an export's appendices each as a file of its own in the zip, named by its number and title (DL-0193). The dialog's choice reads *окремими файлами*; appendices exported without the document always go so.

**edit the whole document** · редагувати весь документ · *proposed* — open one editor over the whole body or appendix.

**edit a section** · редагувати розділ · *proposed* — open an editor over one section: a `#` heading at any depth and the lines it leads, its subsections included; several may be open at once. Every editor writes into the same draft.

**inactivity prompt** · запитання про бездіяльність · *proposed* — *are you still working?*, asked in the editor of a hold idle past the organisation's timeout; unanswered, the hold is released ten minutes later, the draft kept (DL-0377). Never asked of a reserved hold.

**source view** · вихідний текст · *proposed* — the editor showing and accepting Markdown instead of formatted text. An editor, not an import.

**block / lift the block** · заблокувати / розблокувати · *proposed* — end access, and restore it as it stood, at one of three levels: a tenant administrator blocks a person's membership in their organisation and lifts that block (ST-0004, ST-0072); a platform administrator blocks a whole organisation and lifts that block (ST-0065, ST-0071); a person blocks their own account (ST-0066), a block nothing in the platform lifts in release 0.1: a platform administrator asks the installation's operator, who lifts it in the database (DL-0254). *Unblock* is not a second name for it.

**blocked** · заблоковано · *proposed* — the state of a blocked membership, account or tenant; of an organisation, *заблокована*.

**block my account** · заблокувати мій обліковий запис · *proposed* — a person's own block, from the user menu (ST-0066): every organisation closes to them; in release 0.1 nothing in the platform lifts it — a platform administrator asks the installation's operator, who lifts it in the database (DL-0254).

**account** · обліковий запис · *proposed* — a person's own sign-in to the platform, one per address, whatever organisations they belong to.

**invite by email** · запросити електронною поштою · *proposed* — how a person enters an organisation (DL-0107): an administrator gives an address and the groups to join; the person is a member at once and gets an **invitation**.

**invitation** · запрошення · *proposed* — the email with a single-use link of seven days that sets the person's password and signs them in; **accept the invitation** · прийняти запрошення · *proposed* — follow that link and set the password.

**reset the password** · скинути пароль · *proposed* — set a new password through *Forgot your password?* · *Забули пароль?*: an email with a single-use link of one hour.

**switch organisation** · перейти до іншої організації · *proposed* — choose, in the switcher beside the organisation's name, which of one's organisations to work in (ST-0007). The platform administrator's selector in the administration *chooses* the organisation its pane shows; the switcher changes where one works.

**being set up** · налаштовується · *proposed* — what the interface shows for a new organisation whose schema is not yet fully migrated, the state `migrating`: no request reaches it until the migration completes and it becomes active (DL-0280, DL-0287).

---

## Who does it

**reader** · читач · *proposed* — holds a viewing right: the canonical version, and more as the right allows (ADR-0007).

**editor** · редактор · *proposed* — edits and commits.

**reviewer** · погоджувач · *proposed* — accepts edits, and edits: may correct wording first, including their own (ADR-0016). *(Рецензент reads as academic; погоджувач is the corporate role.)*

**approver** · затверджувач · *proposed* — holds *make canonical*: ends a freeze by making the latest accepted version the next edition. The approving body's own procedure happens outside the platform.


**pending edits viewer** · переглядач неприйнятих правок · *proposed* — holds *view pending*: may see committed but unaccepted changes.

**tenant administrator** · адміністратор організації · *proposed*

**platform administrator** · адміністратор платформи · *proposed*

---

## Access and organisation

**organisation** · організація · *proposed* — what a user sees. The internal word is *tenant*, and it never appears in the interface.

**sign in / sign out** · увійти / вийти · *proposed* — the page is *вхід*.

**host** · хост · *proposed* — a name, with an optional port, the platform answers on: the platform's own, or an organisation's domain (ADR-0008).

**default** (host) · основний · *proposed* — the one host of a set that links and mail use.

**platform** · платформа · *proposed* — the installation as a whole, above every organisation; what a platform administrator administers.

**active** · активна · *proposed* — the state of an organisation people can use; with *blocked* (заблокована) and *being set up* (налаштовується), the three an organisation shows. Of a membership, *активне*, beside *заблоковано*.

**access right** · право доступу · *proposed* — something a group may do to the documents linked to it: view canonical, view accepted, view pending, edit, create and edit; view previous canonical versions, view all history; accept, freeze and unfreeze, make canonical, reserve for editing; create or delete appendices; upload, replace or delete attachments. Held over a whole document. Some include others: each viewing right the ones below it; *accept*, *freeze and unfreeze* and *reserve for editing* include *edit* (ADR-0016); *make canonical* includes *view accepted* (DL-0234).

**group** · група · *proposed* — a set of people in one organisation holding a set of access rights, linked to the documents those rights apply to. The only way a person holds a right on a document.

**access history** · історія доступу · *proposed* — who held what, when, granted by whom. Answerable for a past date.

**notification** · сповіщення · *proposed*

**sending address** · адреса надсилання · *proposed* — the address an installation's or an organisation's email leaves from, with the server that carries it (DL-0202).

**outbox** · вихідні листи · *proposed* — every email written before it is sent, and the record of what was sent (DL-0203).

**test email** · тестовий лист · *proposed* — a message from a sending address to itself, reporting the connection, the sign-in and the sending (DL-0202).

**sender's name** · ім’я відправника · *proposed* — the name an email is shown as coming from (DL-0368).

---

## The product and its releases

**release** · реліз · *fixed* — a numbered delivery of the platform: 0.1, then 0.2.

---

## Agent concepts — stage 2

Not in the first release. Listed so the vocabulary is settled before it is built.

**companion** · помічник · *proposed* — the agent that assists an editor. Sees only what that editor may read.

**reviewer agent** · агент-погоджувач · *proposed* — the agent that runs when a document is sent for review.

**heuristic** · евристика · *proposed* — one focused piece of prompt text. Visible only to the platform administrator.

**companion action** · дія помічника · *proposed* — a set of heuristics producing one analysis a user can ask for.

**side-document type** · тип супровідного документа · *proposed* — a set of heuristics producing and maintaining a generated view.

**finding** · зауваження · *proposed* — one thing an agent reports, tagged with the material it was derived from.

**review scope** · обсяг розгляду · *proposed* — the set of documents a reviewer puts in scope for one review. Neighbours are read at their accepted state unless the reviewer switches one to pending (DL-0104).

**dispute** · розбіжність · *proposed* — a recorded disagreement over a passage. Stage 2.

---

## Internal terms, never shown to a user

English only. If one of these reaches the interface, that is a defect.

**tenant** — an organisation's isolated workspace, one PostgreSQL schema.

**content state** — a hash of a document's tree, the key an analysis is cached against.

**provenance tag** — the set of sources a finding was derived from, which decides who may see it.

**review scope** — the ordered set of documents a reviewer put in scope, each at its content state, plus the heuristic set version. The key an analysis result is stored against.

**audit event** — a recorded action with its actor, object and time.

**hold** — the exclusive claim an editor has while editing. A reserved hold is not released for inactivity (ADR-0009).

**long hold** — the design name for a reserved hold, used in the decisions that led to it (DL-0212 to DL-0217).

**normal form** — one sentence per line, whitelisted constructs, applied before every commit.

---

## Words we never use

The substrate is invisible (ASR-06), so none of these appears anywhere a user can see, error messages included.

**commit · branch · merge · pull request · repository · ref · diff · blame · LaTeX**

Українською: коміт · гілк · репозитор · зберегт · збережіть · збережено

And one that is not a git word: **save**. There is no Save button, and calling anything "save" reintroduces the idea that work can be lost by not doing it.

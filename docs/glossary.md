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

**title page** · титульна сторінка · *proposed* — an optional first page generated at export from the document's metadata. Never edited.

**document template** · шаблон документа · *proposed* — the outline a new document starts from, one per organisation, kept by the tenant administrator.

**attachment list** · перелік вкладених файлів · *proposed* — the table an export generates of a document's attachments: title, file name, hash.

**frontmatter** · заголовок файлу · *proposed* — the title, the language, the title-page switch and the lists of appendices and attachments at the top of `document.md`. Never shown in the editor and never exported; it is what a restored repository recovers its identity from.

**section** · розділ · *proposed* — a top-level heading in a document.

**subsection** · підрозділ · *proposed* — a heading below a section. Depth is capped at four.

**clause** · пункт · *fixed* — the numbered unit inside a section: one paragraph of text. *Normative Ukrainian documents number розділ → підрозділ → пункт, which is exactly our `1.1-3`; **абзац** is the typographic word and is deliberately not used here.*

**clause number** · номер пункту · *fixed* — `1.1-3` reads as розділ 1, підрозділ 1, пункт 3. Derived when the document is rendered, never stored.

**passport** · паспорт документа · *proposed* — the file recording review and approval decisions, so that approvals travel with the document rather than living only in the application.

**entity** · позначка · *proposed* — a marked piece of text: a **role** (роль), an **action** (дія) or a **term** (термін). Set apart by its formatting wherever text is rendered; its syntax shows only in the source view and the Markdown export.

**role directory** · довідник ролей · *proposed* — the list of roles a document declares, with their rights, obligations and the paragraphs each comes from. Derived by parsing the marks.

**outline** · зміст · *proposed* — the navigable list of a document's sections and subsections.

**see also** · див. також · *proposed* — the automatically maintained list of documents this one links to, filtered to what the reader may reach.

**document type** · тип документа · *proposed* — policy (політика), controls (контролі), technical instruction (технічна інструкція), job description (посадова інструкція), notes (нотатки).

**folder** · тека · *fixed* — where a document appears in the interface. Presentation only; storage is flat.

**style** · стиль · *proposed* — the organisation's rendering rules, authored by a designer and selected per document.

**image** · зображення · *proposed* — an uploaded PNG, JPEG or GIF. HEIC is refused; metadata is stripped.

---

## States and what a reader sees

The five stances. The Ukrainian is the owner's own and is the authority; the English follows it.

**canonical version** · канонічна версія · *fixed* — the last edition approved as authoritative.

**accepted edits** · погоджені правки · *fixed* — the last revision a reviewer accepted.

**pending edits** · всі неприйняті правки · *fixed* — everything committed since, attributed and not yet accepted.

**my edits** · мої правки · *fixed* — the holder's own uncommitted session.

**my edits in review** · мої правки на розгляді · *fixed* — what this editor has sent.

**version number** · номер версії · *proposed* — `N.M` for an acceptance, N canonical editions before it and M acceptances since; `N.0` for a canonical edition; `1.3-2` for pending work on top of acceptance 1.3. Derived, never typed.

**edition** · редакція · *proposed* — a canonical version, numbered `N.0`. Never changes once made. *Редакція документа is the standard Ukrainian for a version of a normative document, which is exactly what this is.*

**version** · правка · *proposed* — one committed change-set, the thing that appears in *мої правки*. Deliberately the same word as the stance names, because it is the same object seen from a different angle.

**draft** · чернетка · *proposed* — typed but not yet committed. Held by the platform, visible to nobody else.

**held** · зайнятий · *proposed* — somebody has the document open for editing and nobody else can.

**archived** · заархівований · *proposed* — put away. Its links stop resolving; its access rights sleep and return unchanged on restore.

---

## What a user does

**take for editing** · взяти на редагування · *proposed* — what opening an editor does when nobody holds the document: it takes the hold. There is no button of that name (ADR-0006).

**continue editing** · продовжити редагування · *fixed* — the button that returns from the send-for-review screen to the text.

**discard my edits** · відкинути мої правки · *proposed* — the third button on the send-for-review screen: throws away the whole draft, text and file operations alike, after the user confirms. The document is left as it was.

**send for review** · відправити на розгляд · *fixed* — the button that commits. There is no Save.

**accept edits** · погодити правки · *fixed* — make the current text the accepted baseline.

**freeze** · заморозити · *proposed* — lock a document nobody is editing against editors while something outside it is resolved; people holding *accept* and *edit* may still edit. Ends by *make canonical* or *unfreeze*.

**make canonical** · затвердити · *proposed* — end a freeze by making the latest accepted version the next edition.

**copy a document** · копіювати документ · *proposed* — create a new document from a version of one you may read; no history, no attachments, author-only until groups are linked.

**undo a contribution** · скасувати правку · *proposed* — a new version that reverses an earlier one. Nothing is erased.

**archive / restore** · архівувати / відновити · *proposed*

**export** · експортувати · *proposed* — to PDF, Word or Markdown, of a stated version, composed from a scope, formats and a view.

**edit the whole document** · редагувати весь документ · *proposed* — open one editor over the whole body or appendix.

**edit a section** · редагувати розділ · *proposed* — open an editor over one `#` section; several may be open at once. Every editor writes into the same draft.

**source view** · вихідний текст · *proposed* — the editor showing and accepting Markdown instead of formatted text. An editor, not an import.

---

## Who does it

**reader** · читач · *proposed* — holds a viewing right: the canonical version, and more as the right allows (ADR-0007).

**editor** · редактор · *proposed* — edits and commits.

**reviewer** · погоджувач · *proposed* — accepts edits, and may correct wording first, including their own. *(Рецензент reads as academic; погоджувач is the corporate role.)*

**approver** · затверджувач · *proposed* — holds *make canonical*: ends a freeze by making the latest accepted version the next edition. The approving body's own procedure happens outside the platform.

**designer** · дизайнер · *proposed* — authors the organisation's styles and selects them per document.

**pending edits viewer** · переглядач неприйнятих правок · *proposed* — holds *view pending*: may see committed but unaccepted changes.

**tenant administrator** · адміністратор організації · *proposed*

**platform administrator** · адміністратор платформи · *proposed*

---

## Access and organisation

**organisation** · організація · *proposed* — what a user sees. The internal word is *tenant*, and it never appears in the interface.

**access right** · право доступу · *proposed* — something a group may do to the documents linked to it: view canonical, view accepted, view pending, edit, create and edit; view previous canonical versions, view all history; accept, freeze, make canonical; create or delete appendices; upload, replace or delete attachments. Held over a whole document.

**group** · група · *proposed* — a set of people in one organisation holding a set of access rights, linked to the documents those rights apply to. The only way a person holds a right on a document.

**access history** · історія доступу · *proposed* — who held what, when, granted by whom. Answerable for a past date.

**notification** · сповіщення · *proposed*

---

## Agent concepts — stage 2

Not in the first release. Listed so the vocabulary is settled before it is built.

**companion** · помічник · *proposed* — the agent that assists an editor. Sees only what that editor may read.

**reviewer agent** · агент-погоджувач · *proposed* — the agent that runs when a document is sent for review.

**heuristic** · евристика · *proposed* — one focused piece of prompt text. Visible only to the platform administrator.

**companion action** · дія помічника · *proposed* — a set of heuristics producing one analysis a user can ask for.

**side-document type** · тип супровідного документа · *proposed* — a set of heuristics producing and maintaining a generated view.

**generated view** · супровідний документ · *fixed* — a document written by the agent and by nobody else: contradictions (суперечності), ambiguities (неоднозначності), blind spots (прогалини), the role and control directories.

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

**hold** — the exclusive claim an editor has while editing.

**normal form** — one sentence per line, whitelisted constructs, applied before every commit.

---

## Words we never use

The substrate is invisible (ASR-06), so none of these appears anywhere a user can see, error messages included.

**commit · branch · merge · pull request · repository · ref · diff · blame · LaTeX**

And one that is not a git word: **save**. There is no Save button, and calling anything "save" reintroduces the idea that work can be lost by not doing it.

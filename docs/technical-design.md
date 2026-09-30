---
tags:
  - technical-design
aliases:
  - Syngraphē Technical Design
status: draft
date: 2026-09-21
---

# Technical Design — Syngraphē

> [!note] Walking skeleton
> Structurally complete, deliberately thin. Sections resting on unanswered questions name the question inline.

## Stack

| Layer | Choice | Status |
|---|---|---|
| Application | Django, Python | Decided (seed) |
| Git access | pygit2 inside Django, on bare repositories it owns; the `git` binary in the image, for blame | Decided (DL-0030, DL-0042, ADR-0002, ADR-0011) |
| Database | PostgreSQL, schema per tenant | Decided (DL-0029) |
| Host | A single Linux host; the production target is chosen when the platform leaves development | Open (DL-0086, DL-0109, DL-0117) |
| Runtime | Containers: web, PostgreSQL, Redis, Celery worker | Decided (DL-0086, DL-0134) |
| Queue | **Celery over Redis**, Redis without persistence — every task has a database row behind it | Decided (DL-0134) |
| Markdown parser | markdown-it-py on the server and markdown-it in the editor, bound to the whitelist and configured from one specification file | Decided (ADR-0010) |
| Agent runtime | A plain model API behind a **provider interface**, in a container job the platform drives | Decided (DL-0120) |
| Identity and access control | Django (DL-0042, supersedes DL-0015) | Decided |
| Forgejo | **Dropped** (DL-0042) | Decided |
| Document format | Constrained **Markdown** subset, pipe tables included | Decided (DL-0046, DL-0100) |
| Editor | ProseMirror, used directly: a constrained rich editor over Markdown, with a Markdown source view; one instance per open editor | Decided (ADR-0010) |
| Interface | Django templates, htmx, the editor as the one client island | Decided (ADR-0004) |
| Rendering | One parse for every target: HTML from the server's parser with the organisation's stylesheet; weasyprint for PDF with fetch failures fatal; Pandoc over that HTML for DOCX with named Word styles | Decided (DL-0046, ADR-0013) |

## Architecture

**Django owns the workflow. Git is a library, not a service.** Rationale, consequences and rejected alternatives: [`ADR-0002`](adr/ADR-0002-django-owns-the-workflow.md).

```
Browser (Ukrainian UI)
   └── Django — the only authorisation surface
        ├── workflow: holds, versions, acceptance, disputes, editions, rejections,
        │             comments, entities, findings, heuristics, roles, tenants
        ├── pygit2 on bare repositories: init, commit, read, diff, revert, tag; the git binary for blame (ADR-0011)
        └── agent jobs: sandboxed containers the platform starts
```

Forgejo is gone (DL-0042). Edits accumulate in the application and are committed on a user's behalf, so a forge could never authenticate per commit; once identity leaves and the events that start agent runs are the platform's own, a forge has nothing left to offer. Git usage is init, commit, read, diff, blame, revert and tag — no branches, no merge (ADR-0003).

## Runtime

**Development** runs on a development host; **production** runs behind the operator's reverse proxy, which terminates the public TLS (DL-0281). Both are the same containers — web, PostgreSQL, Redis and a Celery worker — and the difference is where they run and what backs them up.

- **worker** from stage 1, not stage 2: PDF rendering is slow and does not belong in a request, and `EXPORT_JOB` already assumes it is asynchronous. It also computes per-line authorship after each commit into `LINE_AUTHORSHIP` rows, which the author view reads rather than blame (DL-0135, ADR-0011). **Three rules keep the cache off the interactive paths (ASR-21):** the pending run's own lines are attributed at render by a blame of the head bounded by the accepted version and never wait for the worker; older text whose version has no rows yet renders without an author, never blocking, and the reconciler asks the worker again for a kept version without rows; a bounded blame whose base version has no rows falls back to a cold blame. **Rows are kept for the head and the latest accepted version only**; an older version's authorship is computed on demand and kept for a limited time (DL-0266).
- **Redis** is the broker and result backend, and is **not in the backup set**. It runs without persistence on purpose: every queued task has a row behind it, so a lost entry is re-enqueued from its row by the reconciler. A broker that has to be restored is a second store holding state, which is the thing the write protocol exists to avoid.
- **git working area** — a volume holding the bare repositories Django owns, one per document.
- **Stage 2 agent runs** are ephemeral container jobs started by a dedicated runner service consuming the queue. The job assembles the context, makes one request through the **provider interface**, and parses a structured result — it does not decide what to read, because the review scope already did (DL-0120) — never by the web process, because a process that can start containers turns a web vulnerability into a host compromise. Each run mounts read-only exactly the repositories in its review scope and nothing else, and its egress is limited to the model endpoint.

**As built, the stack is five Compose services** at the repository root: `web` — gunicorn, which migrates every schema, seeds the language lists and collects the static files as it starts, then serves the application and its own static files (DL-0285); `worker` — Celery, with the periodic tasks' scheduler inside it; `db` — PostgreSQL 16, its log archived by pgBackRest; `backup` — the nightly base backup and the state the worker reads (ADR-0019); `redis`. Each receives only the configuration its job needs. `/health/` also reports the backup's state — the newest clean marker's age, whether any repository is failing (never which), the last segment archived and the log waiting — without letting it change the status code (DL-0295). Only `web` publishes a port, on the loopback, for the host's reverse proxy; the proxy's forwarded client, scheme and host are honoured only from `TRUSTED_PROXIES` (DL-0283, DL-0292). A production shape overrides the base file rather than editing it: `deploy/compose.prod.yaml` adds a sixth service, `front`, an nginx that terminates the installation's TLS on the one published port, buffers requests and forwards to `web`, which then publishes nothing; the data moves to bind mounts under one directory (DL-0281). The front is configured by two files in `deploy/front/` rather than one `nginx.conf`: a template the image renders at start, and a helper that turns the header the operator's proxy carries the client's address in — a per-installation value — into the nginx variable the template forwards as `X-Forwarded-For`. Gunicorn runs threaded workers, two workers of four threads each, so an idle connection holds a thread, not a worker (DL-0347). An attachment is downloaded at `/document/M/attachment/n/`, from the version the reader may see, through the document page's own gates (DL-0342).

Sizing is not driven by the agents — their work is mostly waiting on a model API. Memory for repository working copies and PDF rendering is the constraint.

**Off-host backup is a production requirement** (DL-0118): a copy of the database archive and of every repository has to leave the host, or the scope agreement's *nothing is ever lost* is true only until that host fails.

## The write protocol between git and PostgreSQL

Two stores, one record. Without these rules the crash states are undefined and the tamper detection T-07 relies on has nothing to compare (DL-0111).

**Git is the commit point.** The ref update is the moment a version, an acceptance, a return or an approval exists. Rows are **derived idempotently** — by the request that made the commit, and again by a **reconciler** that replays any commit lacking its row. A row is never the authority for something git holds.

**One repository per document**, at `tenant-N/document-M/` — the tenant's platform number and the document's number in its tenant (ADR-0008). Never by title: a directory named by title puts document titles, including a confidential guidance document's title, into filesystem listings, backup manifests and operator shells that the access table does not govern.

**A single-writer lock per document** covers every ref update: the file `tenant-N/document-M.lock` beside the repository, taken with `flock` by `web` and `worker` alike and by an operator's shell, always before any database row lock. It is almost uncontended, because the editor's hold already serialises human editors, but it still has to exist: acceptance and any stage 2 worker write are not covered by that hold; undoing a contribution is made inside the reviewer's own hold (ADR-0015).

**The passport wins over the row.** Where they disagree, the reconciler reports it and never changes the passport; the interface believes the passport.

**Document creation is the one two-store write.** The row is written in a `creating` state; the repository is initialised and receives its first commit, of kind `created` (DL-0268) — `document.md` built from the organisation's template (DL-0169); the row becomes `active`, reaching only its author until groups are linked (DL-0260). The reconciler **finishes** a creation that stopped and **recreates** the row of a repository without one, with no access — never deleting a repository.

**Backup never restores the database past the repositories** — the tooling and the restore are [`ADR-0018`](adr/ADR-0018-backup-and-restore.md) and [`ADR-0019`](adr/ADR-0019-backup-when-something-fails.md). The superset property holds per document: history is append-only and there is no cross-document commit, so each repository copied after the database's recovery point contains at least what the database knew about it. The repositories are bundled every ten minutes, and every run leaves a marker listing any repository that failed; a restore of the whole host takes the database to the time the newest run with no failure began, or to the last good moment if that is earlier, and to the end of its archive only when recovery cannot reach that time (DL-0294, DL-0296, DL-0314); markers are kept as long as the oldest chain any repository keeps (DL-0316); and a failure of the database alone, the repositories intact on the host, restores it to its latest archived point (DL-0276). Two hazards, neither about the number of repositories, and one rule:

- A repository copied **while it is being written** can yield a ref pointing at an object the copy missed. Each bundle is written **under the repository's writer lock** and verified and copied after the lock is released, so no commit waits on the store (DL-0301).
- A restore leaves git ahead of the database and the reconciler repairs that, but **database-only state after the recovery point is gone** — holds, access changes, and above all **drafts**, which ADR-0003 makes load-bearing because a session has no intermediate commits. The database therefore needs **continuous archiving with point-in-time recovery**, which ADR-0018 gives it.
- A repository restored **without its row** is recreated from `document.md`'s frontmatter — title, language, and the appendix and attachment lists — with **no access rows at all**, and the tenant administrator is notified. Fail closed, the same instinct as an untagged finding.

**Housekeeping for many small repositories.** Initialise from an empty template, or every repository carries a dozen sample hooks. Schedule a **nightly repack per repository under its lock**, before the base backup (DL-0313), because a library that writes commits does not repack and each version leaves loose objects; pruning removes only unreachable objects, and in an append-only linear history the only unreachable objects are debris from failed writes — so this does not touch ASR-02, and that sentence belongs beside the job or nobody will dare run it.

**What is given up, recorded rather than discovered.** There is no commit meaning *the corpus as of this moment*; nothing needs one, because an analysis is keyed by each document's own content state (DL-0078). And a cross-document generated view has no repository to live in — when B-003 is taken up it needs a per-tenant derived store, not a home inside any one document.

## Tenancy

A tenant is a fully independent group of users or a separate business (DL-0003). The tenancy mechanism as a whole — the schema per tenant, the one middleware that resolves it, the guard and the per-schema migrations — is [`ADR-0017`](adr/ADR-0017-schema-per-tenant-resolved-per-request.md). **A tenant is recognised from the host** when it has its own domain (`TENANT_DOMAIN`), and from the session on the application's main domain; a person signing in on a tenant's domain lands in that tenant, and switching tenant moves between domains and may need signing in again (ADR-0008). Tenants share nothing but the heuristic catalogue their copies are seeded from.

- **Database — schema per tenant** in PostgreSQL (DL-0029). Isolation is enforced by the database, not by application code: crossing it requires getting a whole request's `search_path` wrong rather than one query's `WHERE` clause. Migrations run per schema; platform-level tables live in a shared schema.
- **Repositories** — a directory per tenant holding one repository per document, pairing with schema-per-tenant. DL-0003's mapping of a tenant to a Forgejo organization lapses with DL-0042.

## Identity and authorisation

Both are Django's (DL-0042, superseding DL-0015). Groups holding rights, linked to documents, are the only permission model in the system (ADR-0007) — one authorisation surface, per ASR-07. The MCP contract, that an external agent holds exactly its user's rights, is a property of the same authorisation path the browser uses.

Principle of least privilege throughout: the burden is on expanding access, never on restricting it.

**Developers are not an application role** (DL-0210). Django's own administration interface is reachable only by operator accounts with its superuser flag, created from the command line; it is never linked from the application, is served only on the platform's main domain, sits at a non-default path, and every use is audited. Platform and tenant administration are the application's own pages.

## Who performs git operations

Django, through pygit2, on bare repositories it owns, with the `git` binary in the image for blame — pygit2 has no bounded blame, no excluded commits and no reverse walk (ADR-0011) — **Forgejo was dropped at DL-0042** (ADR-0002). The reasoning was the owner's: edits accumulate in the application and are committed on a user's behalf, so a forge cannot authenticate per commit and cannot hold the authorisation; and once the events that start agent runs are the platform's own, forge runners add nothing either.

The operation set is small because the model is linear (ADR-0003): **init, commit, read, diff, blame, revert, tag** — `init` because creating a document creates a repository (DL-0111). No branches, no merges, no conflict resolution.

**Commits carry no personal data** (DL-0088, DL-0093). The git author name is the Django user identifier; the author email is a per-user non-routable address, `{user-id}@users.noreply.syngraphe.local`, so authors stay distinct to any tool that keys on email. The domain is fixed here, once, because it is baked into every commit ever written and changing it later splits one author into two. The mapping to a person lives in PostgreSQL, and a deletion request is answered by removing that mapping rather than by rewriting history — which is what keeps ASR-02 and a person's right to erasure from colliding.

**A contributor map travels with an export, never with the history.** Identifier to display name, generated at export and backup time from the database and never committed. It answers the cost of pseudonymisation — a repository whose history reads as opaque identifiers is not portable evidence — without putting a name anywhere immutable. Erasure changes what the next export contains and nothing that already exists.

What was given up is the forge's web interface for inspecting a repository when something breaks. The replacement is the `git` command line on the host, plus read-only repository views for the platform administrator.

## Repositories and access

**One repository per document** (DL-0111), at `tenant-N/document-M/` (ADR-0008). Confidential guidance is an ordinary document with restricted access (DL-0051, superseding DL-0008). The granularity is what makes the agent's mount list *be* the review scope, so the editor-facing run has no guidance on its filesystem at all.

Access is **data with history** (ASR-08): groups, their rights, their members and their links to documents, every change carrying a timestamp and an actor, editable only by a tenant or platform administrator (ADR-0007). A confidential document is one linked to few groups; a new document is linked to none and reaches only its author.

The condition the old design relied on is now explicit rather than structural: **no user ever receives raw repository access, and every export is per document**. Both are enforced by the application because the application is the only path to the repository.

## Document storage and diff semantics

A document is **its body, zero or more appendices and zero or more attachments**, all in its own repository (DL-0165, DL-0166):

```
tenant-N/document-M/          # repository root, one per document (DL-0111, ADR-0008)
├── document.md       # frontmatter: title, language, appendix and attachment lists · body: the main text
├── appendices/       # one Markdown file per appendix, named by its number: 1.md, 2.md
├── attachments/      # one opaque file per attachment, named by its number
├── entities.yaml     # role, action and term definitions
├── images/           # uploaded binary assets the text embeds
├── analysis/         # editor-facing companion analyses (stage 2)
└── passport.md       # review and approval decisions (DL-0041)
```

### Appendices, attachments and the title page

- **`document.md`'s frontmatter lists the parts**: appendices in display order, each with its identifier and title; attachments in display order, each with its identifier, title, original file name and SHA-256 hash. Adding, removing, renaming, replacing or reordering a part is a change to the document, versioned and reviewed like any other (DL-0168), and a repository restored without its row recovers every part from this one file.
- **An appendix** is a Markdown file under the same whitelist as the body, holding **exactly one `#` section**, whose heading is what the finished document shows. Its title in the frontmatter names the appendix in the interface and its exported file, and is never rendered in DOCX or PDF. An appendix has no appendices or attachments of its own.
- **An attachment** is stored as uploaded and never parsed, rendered or read by an agent. Its size is capped per tenant, 5 MB by default. Replacing it writes a new blob at the same path, so earlier versions stay in history; a download serves the original file name.
- **The title page is not stored.** When a document has one, it is rendered at export from the document's metadata through the tenant's title-page template (DL-0164).

### The constrained Markdown subset

**This list is the whitelist.** It is normative and it is the only place the set is decided — `src/editing/whitelist/spec.json` is its machine-readable form, changed with it, and every test or harness reads the set through that file and never restates it, and a construct absent from it is absent from the product (DL-0046, DL-0100).

| Construct | Form | Note |
|---|---|---|
| Headings | `#` to `####` | Depth capped at four; numbering is a render rule |
| Paragraphs | blank-line separated | One sentence per line on disk, never visible |
| Lists | ordered and unordered, nesting to three levels | No task lists |
| Emphasis | `*italic*`, `**bold**` | |
| Underline | `[text]{.underline}` | An attributed span, not `<u>` |
| Entity spans | `[CMO]{.role #cmo}` and the other types | Defined in `entities.yaml` |
| Quotes | blockquote, `> text` | Paragraphs and lists inside; no nested quote, callout or table (DL-0238) |
| Callouts | typed blockquote, `> [!note]` | Types: note, warning, example; paragraphs and lists inside, no nested quote, callout or table; the marker stands alone on its line, and text written after it moves to the first paragraph (DL-0238) |
| Tables | pipe tables | At the top level only (DL-0239); no merged cells, no nested blocks; the row is the unit |
| Images | `![alt](images/name.png)` | Repository-local paths only; every image stands as a paragraph of its own, however it arrives — one inside a sentence is refused (DL-0232, DL-0253) |
| Links | `[text](url)` and repository-local paths | |

Everything else is outside the subset: raw HTML, scripts, footnotes, definition lists, headings below depth four, task lists, nested tables, merged cells, horizontal rules, code blocks, math, and any remote image or stylesheet reference. The editor offers exactly the set above and nothing else; anything outside it is **rejected at edit time with a message**, never silently dropped. Pasted Markdown that falls outside the set is refused with the offending lines named, and the user is offered a conversion — removing or rewriting what the set does not allow — previewed before it is applied (DL-0171). The message links to a help page listing the set, generated from the same specification as the editor schema and the parser configuration.
- **One specification, two parsers** (ADR-0010). The editor's markdown-it and the server's markdown-it-py are configured from one specification file; the span, callout and validation rules are written once per language, and a conformance suite in CI holds them in step — for those rules the weaker of the two controls V-04 weighed.
- **The whitelist binds the parser, not only the editor** (DL-0096): raw HTML disabled, no script, no remote image or stylesheet references, and no network for the PDF renderer. *Raw HTML disabled* means never rendered: the parser recognises raw HTML only to refuse it with a message, because left unrecognised it would pass through as literal text without a word (ADR-0010). Text arrives by paste and by import as well as by typing, so a rule that only the interface enforces protects nobody.
- **Tables** are pipe tables: one row per line, inline content only, no merged cells, no nested blocks (DL-0100). Inside a table the **row** is the unit of diff, authorship and per-author undo — a cell cannot hold a line break, so the sentence stops being addressable there. The normalizer gives every row exactly one spelling: one space inside each cell edge, no alignment padding, a delimiter row keeping only its alignment colons. Without that, padding from an editor, a paste or a prettifier rewrites every row when one cell changes, and each rewritten row is re-attributed to whoever touched one of them.
- **Entities** are attributed spans — `[CMO]{.role #cmo}` (a synthetic example), `[obliged to approve]{.action}`, `[10 days]{.term #timeout}`. Real Pandoc syntax, so it survives every render target and stays machine-readable. Definitions live in `entities.yaml`; the spans mark occurrences. The editor never shows the syntax: a user selects text and marks it. Wherever text is rendered — reading view, editor, DOCX, PDF — marked text carries a distinct formatting set by the stylesheet (DL-0184).
- **One spelling per construct** (DL-0240). Text inside the subset but spelled otherwise is accepted and rewritten by the normalizer: `-` bullets, `N.` ordered markers numbered in sequence (DL-0324), a nested list indented by its parent's marker width, `*italic*` and `**bold**`, an entity span outermost when marks nest, `#` headings without closing hashes, pipe tables with edge pipes, a callout marker alone on its line. A literal `<` is stored escaped, and so is an `&` that would begin an HTML entity, so text never reads as markup.
- **Normal form:** one sentence per line; a server-side normalizer runs before every commit (DL-0012). Paragraph boundaries are blank lines — Markdown's native rule, not a convention imposed on it — and the renderer joins the sentences between them into one paragraph. The user never sees or manages a line break — not in the reading view, the rich editor, the source view or any export. The source view and a Markdown export write each paragraph as one line, entity marks included exactly as stored (DL-0184) — a Markdown export is the source view saved to a file; the normalizer restores the stored breaks on the way back in (DL-0181).
- **A stored line is never re-normalised** (DL-0112, ASR-20). No normalizer rule — the splitter, quote and dash typography, Unicode composition, the canonical table row — is ever applied to a line its edit did not touch. *Touched* means the submitted line differs from the stored line **after canonicalising the submitted one**, so a prettifier that pads every table row produces rows that canonicalise back to the stored bytes and count as untouched.
- **Quote and dash typography** (DL-0273). Straight double quotes around a run of text become the document language's quotation marks — `«…»` for Ukrainian, `“…”` for English; a spaced hyphen between words becomes a spaced em dash; a doubled hyphen becomes an em dash; three dots become an ellipsis. It rewrites text content only, after the splitter's masking — never a link destination, an attribute block, image syntax or a table's delimiter row. It is the *typography* stage below, run on what *reuse* left to rewrite and before any boundary is placed, over every touched line, a heading and a table row's cells included, though the splitter divides neither; the parse-preservation check therefore compares the typeset text before and after the split.
- **What reaches the normalizer.** The rich editor submits each paragraph with a line break at every stored sentence boundary it kept (V-03); the source view and an outside paste submit each paragraph as one line. **The normalizer relies on neither**: it joins each submitted paragraph's lines and treats every path alike. The editor's breaks only make an untouched paragraph arrive byte-identical to its stored lines.
- **The normalizer is a function of two inputs**, the previous version and the submitted text. Within each paragraph it aligns the new text against the old, carries the old boundaries across unchanged spans, and runs the rules only over changed spans widened to the whole old lines they overlap — the alignment of the *reuse* stage below.
- **The normal form is therefore path-dependent.** The same text can legitimately be stored with different line breaks depending on its history. **The stored newline is the authority** — a check that re-runs the splitter over a file and compares is not valid, and the line structure cannot be rebuilt from the text, unlike the search and navigation indexes.
- **Normalisation preserves the parse** — an invariant checked on every write. A wrong boundary degrades granularity, not correctness: an over-split renders identically and anchors identically. The one way a boundary can be *wrong* is a break inside an inline construct, and this invariant is what catches it.
- **The splitter is the platform's own** (ADR-0012), rules parameterised by data. Before any rule runs, link destinations, attribute blocks and image syntax are masked, so no boundary can fall inside them. A boundary candidate is terminal punctuation (`.`, `!`, `?`, `…`) plus any closing quotation marks or brackets that follow, then whitespace. `!` and `?` always end a sentence; `…` only before a capitalised word. A full stop does not end a sentence before a lowercase letter or a digit, after a single capital letter (an initial), or after an abbreviation in the language's *never final* list; after an abbreviation in the *may be final* list it ends the sentence only before a capitalised word; otherwise it does. Each sentence inside a multi-sentence quotation is its own line, and the boundary after a quotation falls after its closing mark. The two lists are per-language data in the `LANGUAGE` table, seeded from the spike's fixtures and edited by the platform administrator; the rules do not change per language. Every boundary the splitter places is checked by the parse-preservation invariant above; a boundary that fails it is not written — the two sentences share a line — and the write proceeds. The normalizer version recorded per commit (below) names the rule set and the revision of the two lists it loaded, so a list edit is a new normalizer version and a line's split can always be traced to the lists that made it.
- **The normalizer version is recorded per commit**, not per document — one document holds lines split by several versions at once, so a per-document field would be untrue on the day of the first upgrade.
- **Moved text keeps its stored lines** (DL-0244). A paragraph cut and pasted elsewhere arrives as a deletion and an insertion. Before anything is split, in order: whole paragraphs equal to a stored paragraph anywhere in the file reuse its lines; other paragraphs are aligned in place (above); in what is still unmatched, the previous version's stored lines are found where they stand as sentences of their own — each end an edge of the paragraph or a sentence's end — longest first, and reuse their bytes, never out of the middle of a longer sentence (DL-0323); only the remainder is split. A stored line whose bytes change — a list item renumbered — is touched (DL-0324). Which author a tie between identical lines keeps is the authorship worker's (ADR-0011). **The stages, in order** (DL-0317): *canonicalise* each submitted paragraph and decide *touched*; *reuse* — whole paragraphs, alignment in place, stored lines standing as sentences; *typography*; *split*; *check* every new boundary by the parse-preservation invariant.
### Rendering, styles and layout

- **Heading numbering is a render rule** derived from depth: `#` is 1, `##` is 1.1, `###` is 1.1.1; a skipped level counts as 1, so a `###` directly under a `#` is 1.1.1 (DL-0327); a paragraph before the first heading carries its index alone, and a table or an image is not a clause (DL-0330). **Each appendix numbers its own headings from 1**, and a reference into one carries the appendix in front — *Appendix 2, 1.1-3*. Never stored, so moving a section renumbers everything and breaks nothing. Comments and findings anchor by quoted text (DL-0027). A prose reference such as *"as defined in clause 4.2"* is ordinary text; keeping it true as a document is restructured is a stage 2 heuristic, backlog B-015.
- **Styles are a stylesheet** the tenant administrator authors at organization level and selects from per document (DL-0020, DL-0230). The CSS analogy is no longer an analogy.
- **One parse for every target** (ADR-0013). The reading view is the HTML the server's parser renders — entity spans and callouts as classed elements the stylesheet addresses, sentences joined, clause and heading numbers attached as labels at render. PDF is weasyprint over that HTML with fetch failures fatal and a fetcher limited to repository files; DOCX is Pandoc over that HTML with the platform's classes mapped to named Word styles, their look given by a reference document authored from the stylesheet. The validator gates every export; a renderer's warning is never a pass. The renderer rules for spans, callouts, soft breaks and labels are a fourth piece of code beside the three ADR-0010 names, and exist server-side only — the editor renders through its own document model — so the conformance suite fixes their output rather than a twin.
- Hunks are classified **sense** or **style**. Style hunks **collapse** in the review surface and are accepted **with the run** — they do not auto-accept, because acceptance is a document-level act with no per-hunk step to skip, and a classifier deciding a change needs no human eyes would contradict ASR-04. A changed sentence is style when, formatting marks and the normalizer's typography set aside, its words and what it points at — link targets, images, entity spans — are unchanged; a sense change shows the new wording with its formatting, the inserted words marked inside it and the removed ones struck where they stood (DL-0331); two sentences at one place with less than half in common are shown as one removed and one inserted.
- **A section is a heading.** Structure is the heading hierarchy of `document.md` and of each appendix, and restructuring a document is editing its text. A section is a range of a file, never a file of its own.
- **Images** are ordinary git blobs — **no LFS** (DL-0066). PNG, JPEG and GIF are accepted and a per-image size cap is enforced on upload; HEIC and every other type are refused with a message, never converted; metadata is stripped (DL-0074, DL-0242). **An image pasted or dropped into the editor is an upload like any other** and always stands as a paragraph of its own; one known only by a web address is never fetched — it is left out of the paste with a one-line notice (DL-0232). A change to an image cannot be read as a diff, so the review surface flags it and renders before-and-after (ASR-04). Agents never read images (DL-0168). Revisit LFS only if a repository's size becomes a measured problem.
- **Clause numbering** is derived at render, never stored (DL-0065): `1.1-3` is section 1, subsection 1, clause 3 — each paragraph of text is one clause; the hyphen separates the heading path from the clause index, and heading depth is capped at four. In the editor the numbers render in a non-editable gutter outside the editable region, recomputed as the text changes. A finding or a comment anchors by **quoted text** (DL-0027) and displays the current number — the number is a label, never an address.
- **Storage layout is flat.** One repository per document under the tenant's directory; the nested tree a user sees is Django metadata, and a move never touches a path (DL-0058, DL-0111, ASR-15).

## Versions, holds and history

- **Taking the document** opens a draft. It persists server-side, is invisible to others, and is not a version. There is no Save control.
- **Editors are views over the draft** (DL-0167). The whole-document editor and a section editor per `#` section are the same editor over different ranges, and several section editors may be open at once; the whole-document editor opens only when no section editor is open. Every editor writes into the one draft of the one hold.
- **Captures are checked per range.** An editor remembers the text of the range it opened, and the server accepts its capture only while that range of the draft is unchanged since the editor last saw it — so editors over different sections never conflict, including across browser tabs. An editor whose range changed underneath it stops, turns read-only, and shows its unsaved text as changes against the current draft for the user to carry over by hand.
- **Open editors are known to the server** by heartbeat. Finishing and an analysis request are refused while any editor is open; an editor whose tab closed without closing it times out. An editor captures 750 ms after the last keystroke, and at once when it loses focus or its page is hidden; it beats every 30 seconds, and one silent for three minutes is closed by the worker, which looks every minute (ASR-22).
- **Uploads wait with the draft.** An image or attachment added, replaced or removed during a hold is held in the database beside the draft's text, covered by the same point-in-time recovery, and written to the repository in the commit that finishes the session.
- **There is no Save.** *Finish editing* opens the send-for-review screen (DL-0222). It presents the holder's changes (*my edits*), the part operations and the change summary, which starts from a mechanical draft naming the sections touched (DL-0261); the companion analyses join it in release 0.2. The editor continues editing, discards the draft after confirming, or commits — *send for review* for a holder of *edit* alone (DL-0054), *create version N.M-X* or *accept as N.M* for a holder of *accept*. A session that changed only attachments or appendix order ends the same ways; discarding it leaves every file as it was, a deletion included (DL-0180).
- **From release 0.2, the analyses are written into the same commit** as the content, in `analysis/` (DL-0055); release 0.1 writes none (DL-0261). This is why the commit identifier is never needed: the analysis is part of the tree rather than a pointer at it, both halves are known before the commit is made, and the reasoning travels into any clone or export.
- **Analysis files have fixed names and are overwritten on every commit** (DL-0067). Nothing is lost — the analysis as of any version is `git show {commit}:analysis/{name}`. Accumulating timestamped files would duplicate what history already gives.
- **Only the editor-facing artefact goes into the tree.** The reviewer-eyes-only analysis (DL-0007) must never be committed into the document folder, because anyone with read access to the document would read it. It lives outside the tree, reachable only through the access table. Committing it would breach ASR-03 by a storage decision rather than a delivery one.
- History is **linear and append-only** (ADR-0003, ASR-02). No branches, no merges, no rewriting. An unwanted change is undone by reverting it into the reviewer's draft — one version, or one author's versions since the last acceptance — computed from blame; lines a later version changed are left for the reviewer to edit by hand, and the draft is committed as the reviewer's version (ADR-0015).
- **`refs/proposals/{id}/head` is no longer needed** — nothing is squashed, so nothing needs retaining. ADR-0002's retention consequence lapses.
- **Acceptance** is a commit to the document's passport carrying the reviewer's decision, so approval history lives in the repository and travels with the document (DL-0041). **A reviewer's corrections are versions of the run**, never part of the acceptance commit: an editing session finished by *accept as* or *create version* (DL-0222), or an undo applied to the reviewer's draft (ADR-0015). A version committed by a holder of *accept* is marked so at commit (ADR-0014). An acceptance or a version stopped after its commit and before its rows is settled — its rows derived, an acceptance's from its passport section, its notices computed — by the next writer under the lock before its own commit, and by the reconciler, so a number is never given twice and nothing is written over a commit the rows do not know (DL-0111).
- **Version numbers are derived** (DL-0183): an acceptance is `N.M` — N canonical editions before it, M acceptances since the last — and making a frozen document canonical gives its latest accepted version `N+1.0`. The passport records them, so no user ever needs a commit hash. Pending work is shown as the later of the latest edition's and the latest accepted number, plus the content versions since it — `edit` and `reviewer_edit`, never a passport commit — `1.3-2`, and `2.0-1` for the first after edition `2.0` (DL-0267). Before the first acceptance the base is `0.0`, so a new document's first version reads `0.0-1`; `0.0` names no version and is never shown alone or linked (DL-0272).
- **Copying a document creates a new one** (ADR-0007): its first commit, of kind `created` (DL-0268), holds the chosen version's text — canonical, accepted or pending — with the chosen appendices, images and entity definitions, no attachments and no history. It is author-only until groups are linked, and records its source.
- **A freeze locks the document, not a version** (DL-0189). A document is frozen only when nobody holds it; while frozen, only holders of *accept* may take the hold (ADR-0016); their commits and acceptances continue the numbering. **Make canonical writes a passport commit** — the approver, the edition number and the accepted version it approves — **and tags it** as the next edition, then ends the freeze (DL-0260); *unfreeze* ends it without one. An approval stopped after its commit is finished — tag, rows, the freeze's end — by the next writer under the lock and by the reconciler, from its passport section, as an acceptance is. **Which version a person reads** is one function of their rights (DL-0209): the latest content version for *view pending*, the latest accepted for *view accepted*, the latest edition for *view canonical*, before whose first edition the document does not exist for that reader; the page, the list's *Canonical* and *Latest* columns and the attachment route all read it.
- **Acceptance is document-level** (DL-0090): one reviewer accepts the whole run since the last accepted version. No per-file ledger, no partially-approved state, no section owners (DL-0091).
- **Holds** are exclusive per document and taken by opening an editor (ADR-0006). A hold is released after a tenant-set period without activity — 30 minutes by default — once the holder has been asked whether they are still working and has not answered; a tenant administrator can force release, and blocking the holder releases it (DL-0256). The released draft is preserved: if nobody has committed since, its holder takes it back; otherwise it opens read-only as changes against the current text.
- **A reserved hold** carries `reserved_at` and is skipped by the inactivity release (ADR-0009); nothing else about the hold changes. As for any hold, freezing, group-link changes and correction are refused; while it is set, acceptance and return by anyone else are refused too, and the holder's own *accept as N.M* ends it. Starting, cancelling and ending it are audit events. An administrator ending it records a reason, an audit event and a notification. *Accept as N.M* runs the commit and the acceptance under the one single-writer lock, so no other ref update falls between them.

## The pending view

A plain read, not a computation over branches: the content versions since the last accepted revision, in order, attributed — the run's lines by a blame of the head bounded by the accepted version, the accepted text's from its kept rows. **The document's review state** is a function of the acceptances, the repository and the linked groups' rights — returns join them when they are built — never a stored column beside `DOCUMENT.state`'s lifecycle; a document whose linked groups hold no *accept* has no reviewer whatever else is true, and the tags that speak of pending work reach only holders of *view pending*. **Changes are shown word by word inside the rendered text** (DL-0170): the line diff finds the changed sentences, and only those are compared word by word; a change to formatting alone carries its own marker. Added, replaced and removed images and attachments are listed with their titles, each version viewable or downloadable. *My edits* uses the same presentation against the current text, and so does a comparison of two different documents, each at a version the reader may read (DL-0187). Sentence-per-line keeps attribution exact, so *show author* (DL-0040) resolves to a sentence rather than a paragraph, and a per-author revert is exact.

## Presence

Derived, never declared (DL-0036). That a document is held is shown to everyone, in the list and on the document; who holds it, only to the tenant administrator (ADR-0006) — and, for a reserved document, also to holders of *edit* or *accept* on it and administrators (ADR-0009). Content stays invisible until the version is committed.

## Rejection records

Rationale and rejected alternatives: [`ADR-0001`](adr/ADR-0001-reviewer-corrects-and-accepts.md).

Generated, not authored (ADR-0014). **At acceptance**, for every version of the accepted run committed by a holder of *accept* — a correction, an undo, a session finished by *accept as* — the platform diffs that version against its parent; each change of the pending run it replaced or reversed — a line written, a line removed and now restored, an appendix or attachment operation reverted — becomes an entry holding **references, never text** (DL-0113): the changing version and its author, the change's author and the version that made it, and the file with the line range in the author's version and in the accepted version, or the part for a file operation. **An author receives one notice per acceptance**, listing every entry for their lines. The acceptor's own versions in the run count as a reviewer's, whatever their stored kind. A line the move rule recognises as moved (ADR-0011) is neither replaced nor removed. Nobody is notified about their own lines. Other versions committed by editors without *accept*, a document's `created` commit (DL-0268), and lines already in the accepted text, generate nothing. Both wordings are rendered from git when the notice is opened, under the reader's **current** rights — so a revoked right or an archived document withdraws the text, which a stored copy would not.

**No notification carries document text**, in the application or by email. Email carries the event and a link. The editor may escalate a record into the Statement of Disagreements; editor and reviewer may settle an entry by agreement with exactly one wording surviving, and on deadlock the decider rules, and only the decider can (DL-0026).

## Comments

Threads anchored to a passage or to an edit, nested, closable, permanently recorded. Nothing is written into the document text: commenting must not require the right to edit, so no marker can be placed in the source to hold an anchor, and comment traffic would pollute the sense-versus-style classifier.

The thread store is in Django, with anchors modelled on the W3C Web Annotation Data Model — a quoted-text selector plus a position selector — resolved against the sentence-per-line source (DL-0027). When the anchored sentence later changes, the thread is flagged as attached to a superseded sentence and shown with both wordings rather than silently re-anchored. A snapshot exports into the document folder whenever an edition is frozen.

## Heuristics, actions and prompt composition

Three levels (DL-0049, refining DL-0031):

| Entity | Contents | Composed into |
|---|---|---|
| **heuristic** | one focused piece of prompt text | actions and side-document types |
| **companion action** | a set of heuristics | a user-facing analysis, run against one version |
| **side-document type** | a set of heuristics | a generated view, recompiled on every commit |

The **platform administrator** creates and edits all three. The **tenant administrator** sees titles and descriptions of actions and side-document types and attaches them to documents, and cannot see heuristics at all. The **editor** calls actions and reads views, and sees neither heuristics nor the sets. The taxonomy in [`review-findings.md`](review-findings.md) is the specification the catalogue's prompt text is written against; the text itself is source (§ Prompts are source).

**Run provenance is recorded** — every agent run stores the exact heuristic set and the version of each heuristic's text it used, and every finding carries the heuristic that produced it. A finding that shaped an approval has to remain explainable months later, which requires knowing the heuristic text as it was, not as it now is.

Inside the platform, prompt text is reachable only by the platform administrator: reading and configuring heuristics is that role's privilege, and a tenant administrator or a user has no need for it. The same text is source in this repository (§ Prompts are source), which is where it is reviewed and versioned.

## Prompts are source

**Heuristic prompt text is source code, and `prompts/` in this repository is canonical while the product is being built.** One directory per heuristic at the repository root, plain Markdown loaded by path — never packaged as module data, so it can be read and edited by someone who does not write Python. Its eval cases live beside it in `evals/` ([`evaluation-strategy.md`](evaluation-strategy.md)). A prompt enters `prompts/` when it has cases to be measured against.

- **A seed command derives the database copy.** The heuristic rows the platform administrator sees are loaded from `prompts/` — idempotent, re-runnable, each row recording the source version it came from. That source version is the *heuristic version* run provenance records, and the one a review scope's heuristic set version is built from.
- **An in-place edit is a divergence, not a new source of truth.** The platform administrator may edit a row as a hotfix. The seed command reports every row that differs from its source, and the edit is folded back into `prompts/` or overwritten — it is never left as the only copy.
- **Selection is data.** Which actions and side-document types a tenant enables, and on which documents, is ordinary configuration and lives only in the database.
- **When the platform's own versioning is mature, the canonical copy may move into it.** The repository then keeps a **published export of each released heuristic set**, generated at release by the same command. Without it the prompt work becomes invisible outside the running system — no diff, no review, no citable history.

## Agent scopes and finding lifecycle

The companion is **edit-scoped**; the reviewer agent reports both introduced and pre-existing findings, in separated groups (DL-0032).

The mechanism is a **standing findings set** per document, computed against the accepted state and refreshed when that state changes. A run's findings are computed against its latest version and diffed against the standing set, classifying each finding as **introduced**, **pre-existing**, **resolved** or **aggravated**. The standing set is computed once per accepted state and shared across every unaccepted run, so the cost does not scale with the number of open runs, and it doubles as the known-open-findings list on a canonical document.

## The reviewer agent

Runs when a document is **sent for review** (DL-0048) — never per version — as a sandboxed container job with read access to the document repository and the confidential guidance document, and write access only to its own two output artefacts.

It produces two artefacts from **two runs with different inputs** (DL-0095, refining DL-0007):

1. A **reviewer-eyes-only analysis** — a run that reads the guidance, free to cite it.
2. An **editor-facing analysis** — a run whose context **never contains the guidance at all**.

Only the second is publishable, and only when a human reviewer releases it. Two runs rather than two outputs of one run is the whole control: with the confidential material absent from the context that writes the publishable artefact, a prompt failure, a model error or an instruction injected into the document cannot carry it across (`threat-model.md` T-01, T-02).

## Findings and their audience

The agent tags each finding with the material it was derived from. The platform applies DL-0021: a finding reaches a recipient if and only if it is derivable from material that recipient may already read. Audience is computed **per recipient**, not per finding — a finding drawing on a neighbouring document is ordinary for a reviewer who may read both and confidential for an editor who may read only one. An untagged finding is treated as reviewer-only. The decision is the platform's, never the prompt's.

## The companion agent

Runs against the editor's session with its own interface. Sees the working document and the canonical documents its editor may read. Never sees the confidential guidance document. Also generates the length-limited change description the editor may accept or edit (DL-0035).

## Interfaces

- **Nothing to show** (ADR-0008): a document that does not exist, one the reader may not open, one archived and one in another tenant all get the same not-found response — status, page and timing — reading *Nothing to show here*, with no title, author, version or mention of access.
- **URLs** (ADR-0008), within the tenant the host or session names: `/document/12/` the reading view; `/document/12/edit/` and one segment per tab — `my-edits`, `pending`, `history`, `analysis`, `info`; `/document/12/version/2.3/`, `/document/12/version/2.3-1/`; `/document/12/compare/?from=2.0&to=2.3-1`; `/document/12/appendix/3/`; `/document/12/attachment/3/`; `/folder/7/`; `/search/?q=…`.
- **Help pages** are Markdown files shipped with the application and rendered by it, in the interface's language (DL-0195). They describe the product, belong to no tenant, and are not platform documents.
- **Web UI** — Ukrainian, all roles, five document stances (DL-0033). Server-rendered pages with the editor as the one client island (ADR-0004).
- **MCP server** — an external agent connects as a user and inherits exactly that user's rights. **Not in stage 1** — backlog B-007; the contract is recorded so the authorisation path is built once.

## Export

Markdown, PDF and DOCX, all from one parse (ADR-0013). The Markdown export is the source view saved to a file. PDF is weasyprint over the HTML the server's parser renders, with the organisation's stylesheet, fetch failures fatal and the fetcher limited to repository files. DOCX is Pandoc over that same HTML, the platform's classes mapped to named Word styles whose look a reference document authored from the stylesheet provides. The validator gates every export; a renderer's warning is never a pass. All three are in stage 1 — Markdown made the Word path cheap (DL-0046).

An export is composed from three choices (DL-0172, DL-0193):

- **What** — checkboxes, all checked by default: the document; its appendices, embedded in the document or as separate files; its attachments, as stored. A part the document does not have is not offered.
- **Format** — one of DOCX, PDF, Markdown.
- **View** — the canonical version; the *accepted* version; *pending edits*, marked against the last approved text; *my edits*, marked against the current text, or unmarked — each as the reader's rights allow (DL-0209). Change marks appear in DOCX and PDF only.

More than one file is always delivered as a zip. A single attachment is downloaded from the document page; there is no single-item export.

**An exported file is named `<title>_—_<version>_—_<stance>.<ext>`** (DL-0275) — the title as typed, the version number and the stance, every space an underscore and every character a filesystem refuses a hyphen; a zip takes the same name. A **marked** export adds a suffix naming the marks after the stance — `<stance>-<marks>.<ext>` — so a marked and a clean export of one version never share a name. The stance and the fixed words inside a zip — the document, each appendix, each attachment — are written in the interface's language with the glossary's terms.

The platform generates two parts no one authors: the **title page**, when the document has one, and the **attachment list** — title, file name and SHA-256 hash, on a page of its own in DOCX and PDF and as a final `#` section in Markdown. Attachment contents are never embedded in a text export.

**The frontmatter is never exported**, in any format: it is the platform's record of the document's parts and settings, not text anyone wrote for a reader (DL-0181).

**DOCX and PDF carry page furniture** (DL-0182): the page number in the footer; in the header, the document title with its version number beside it, and the stance the export shows — canonical version, accepted edits, pending edits or my edits. A *pending edits* or *my edits* export shows the last accepted number plus the content versions since it (DL-0267): *1.3-2 · pending edits*.

## Publication and secret handling

Apache License 2.0 (DL-0011, DL-0162). Carried from the first commit: no tenant data, credentials or confidential guidance in this repository's history, and configuration by environment rather than by committed file. These are properties of how the repository is built, not checks performed before a release.

## Analysis scope, storage and cost

The same edit yields different findings for different readers: an editor who can see one document, a finance director who can also see a neighbouring one, a chief executive who can also see the confidential guidance. Three rules keep that from multiplying into chaos.

**A review runs under the reviewer's own access** (DL-0077), over a **scope the reviewer selects** — access is not relevance. Findings are tagged with the sources they were derived from and filtered per recipient (DL-0021); the editor-facing artefact comes from a run that never held the confidential material at all (DL-0095), so the control is both the filter and the absence.

**Storage follows provenance, not the user (DL-0069).** A finding derived from the document alone — class P1 — is committed into that document's `analysis/`. Anything derived from other documents or from the guidance lives outside the tree; committing it into a document folder would hand it to everyone who can read that document.

**Keyed by review scope, not by user** (DL-0078). A scope is the ordered set of documents a reviewer put in scope, their content states, and the heuristic set version. Two reviewers with the same scope share one result; different scopes lose nothing. This answers "is it document analysis or user analysis": it is corpus analysis keyed to a scope, anchored to the document whose commit triggered it.

## Types, folders and links

- **Document types** are a table in each tenant's schema, maintained by its tenant administrator and seeded with one type, *document*; assigned per document, used as list filters (DL-0057, DL-0063, DL-0235).
- **Folders** are metadata with unlimited nesting; storage stays flat (ASR-15). A person sees only folders holding, at any depth, a document they may read; administrators see all (DL-0206).
- **Outline** — every document renders a navigation outline of its sections and subsections.
- **Links** resolve per reader: a mention becomes a link only if that reader may access the target, and renders as plain text otherwise (ASR-16). The generated **see also** applies the same filter. The filter runs at render time against the access table, never at authoring time.

## Generated views and document ADRs

Agent-maintained, no human editor (DL-0044, ASR-09). **Mandatory** views recompile on every commit; **voluntary** views are generated on request and may seed an authored document, which is then a copy under human authorship rather than an edited view (DL-0063). Mandatory set: the role directory, the control directory, and the standing contradictions, ambiguities and blind-spot lists. Each carries its own history. For a holder of the guidance grant, each list also carries an addendum computed against the confidential requirements and visible only to them.

Document ADRs (DL-0045) are generated when a person changes the document's logic rather than its wording: one record per decision, however many passages it rewrites, pre-authored by the agent and editable by the person.

## Agent invocation rules

- **No free-form channel.** A user calls a predefined action; nobody composes a prompt (ASR-11).
- **Actions may run at any time**, including mid-edit, and the editor picks which ones.
- **Results are keyed to a hash of the document tree**, not to a commit (DL-0056, ASR-12). One model call per action per content state; a repeat returns the stored result. A commit is one content state among others, which is why the send screen shows work already done.
- The reviewer agent runs on the commit that *send for review* produces, and reads the analyses committed alongside it.
- Each run mounts read-only exactly the repositories in its review scope. The editor-facing run's scope excludes the guidance, so DL-0095's containment is a mount table rather than a property of prompt assembly.

## Notifications

An in-application notifications section, email for the same events, and document-list state as the standing picture of what is waiting (DL-0070). A tenant may send from its own address, or from the platform's by default; every sending password is encrypted at rest under a key from the environment, decrypted only in the worker when sending, and write-only in the interface. *Send a test email* sends from the configured address to itself and reports each step (DL-0202). **Every email goes through an outbox** written before the first attempt: three attempts five minutes apart, then *failed* with an in-application notice to administrators; the outbox is the log of every email sent (DL-0203). Links in an email are built from the tenant's default host, or the platform's (ADR-0008). Notifications are shown in two tabs, *Document* and *Administrative* (DL-0204). A correction notice is one notification per author per acceptance, however many of their lines changed (ADR-0014). **No notification carries document text** (DL-0113, DL-0205): an email may carry the document's number and title, versions, people, the event and the state, and a link — never any text of the document or its appendices, and never the change summary.

## Open technical questions

None in the register. Items the architecture review left open are tracked as its findings until each is decided.

## Verification spikes

Claims this design rests on that have not been checked against running software live in [`verification-plan.md`](verification-plan.md), each with its test, its pass condition and what changes if it fails. This section points there and does not restate them.

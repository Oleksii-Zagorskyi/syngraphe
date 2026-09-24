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
| Git access | A git library inside Django, on bare repositories it owns | Decided (DL-0030, DL-0042, ADR-0002) |
| Database | PostgreSQL, schema per tenant | Decided (DL-0029) |
| Host | A single Linux host; the production target is chosen when the platform leaves development | Open (DL-0086, DL-0109, DL-0117) |
| Runtime | Containers: web, PostgreSQL, Redis, Celery worker | Decided (DL-0086, DL-0134) |
| Queue | **Celery over Redis**, Redis without persistence — every task has a database row behind it | Decided (DL-0134) |
| Markdown parser | A server-side parser bound to the whitelist, built from one specification file the editor schema also reads | Chosen in Epic 1 |
| Agent runtime | A plain model API behind a **provider interface**, in a container job the platform drives | Decided (DL-0120) |
| Identity and access control | Django (DL-0042, supersedes DL-0015) | Decided |
| Forgejo | **Dropped** (DL-0042) | Decided |
| Document format | Constrained **Markdown** subset, pipe tables included | Decided (DL-0046, DL-0100) |
| Editor | Constrained WYSIWYG over Markdown | Library not yet chosen |
| Rendering | HTML with a designer-authored stylesheet through weasyprint for PDF; pandoc for DOCX | Decided (DL-0046) |

## Architecture

**Django owns the workflow. Git is a library, not a service.** Rationale, consequences and rejected alternatives: [`ADR-0002`](adr/ADR-0002-django-owns-the-workflow.md).

```
Browser (Ukrainian UI)
   └── Django — the only authorisation surface
        ├── workflow: holds, versions, acceptance, disputes, editions, rejections,
        │             comments, entities, findings, heuristics, roles, tenants
        ├── git library on bare repositories: init, commit, read, diff, blame, revert, tag
        └── agent jobs: sandboxed containers the platform starts
```

Forgejo is gone (DL-0042). Edits accumulate in the application and are committed on a user's behalf, so a forge could never authenticate per commit; once identity leaves and the events that start agent runs are the platform's own, a forge has nothing left to offer. Git usage is init, commit, read, diff, blame, revert and tag — no branches, no merge (ADR-0003).

## Runtime

**Development** runs on a development host; **production** runs on existing facilities as Docker or a VDS, decided when the platform is ready to leave development (DL-0117). Both are the same containers — web, PostgreSQL, Redis and a Celery worker — and the difference is where they run and what backs them up.

- **worker** from stage 1, not stage 2: PDF rendering is slow and does not belong in a request, and `EXPORT_JOB` already assumes it is asynchronous. It also computes per-line authorship after each commit, which the author view reads from a cache rather than from blame (DL-0135).
- **Redis** is the broker and result backend, and is **not in the backup set**. It runs without persistence on purpose: every queued task has a row behind it, so a lost entry is re-enqueued from its row by the reconciler. A broker that has to be restored is a second store holding state, which is the thing the write protocol exists to avoid.
- **git working area** — a volume holding the bare repositories Django owns, one per document.
- **Stage 2 agent runs** are ephemeral container jobs started by a dedicated runner service consuming the queue. The job assembles the context, makes one request through the **provider interface**, and parses a structured result — it does not decide what to read, because the review scope already did (DL-0120) — never by the web process, because a process that can start containers turns a web vulnerability into a host compromise. Each run mounts read-only exactly the repositories in its review scope and nothing else, and its egress is limited to the model endpoint.

Sizing is not driven by the agents — their work is mostly waiting on a model API. Memory for repository working copies and PDF rendering is the constraint.

**Off-host backup is a production requirement** (DL-0118): a copy of the database archive and of every repository has to leave the host, or the scope agreement's *nothing is ever lost* is true only until that host fails.

## The write protocol between git and PostgreSQL

Two stores, one record. Without these rules the crash states are undefined and the tamper detection T-07 relies on has nothing to compare (DL-0111).

**Git is the commit point.** The ref update is the moment a version, an acceptance or a return exists. Rows are **derived idempotently** — by the request that made the commit, and again by a **reconciler** that replays any commit lacking its row. A row is never the authority for something git holds.

**One repository per document**, named by `DOCUMENT.id` rather than by slug — a directory named by slug puts document titles, including a confidential guidance document's title, into filesystem listings, backup manifests and operator shells that the access table does not govern.

**A single-writer lock per document** covers every ref update. It is almost uncontended, because the editor's hold already serialises human editors, but it still has to exist: acceptance, per-author undo and any stage 2 worker write are not covered by that hold.

**The passport wins over the row.** Where they disagree, the reconciler reports an audit event; the interface believes the passport.

**Document creation is the one two-store write.** The row is written in a `creating` state; the repository is initialised and receives the manifest commit; the row becomes `draft`. The reconciler **retries** a row without a repository and **reports** a repository without a row as an orphan — never deleting it.

**Backup takes the database first and the repositories second.** The superset property holds per document: history is append-only and there is no cross-document commit, so each repository copied later contains at least what the database knew about it. Two hazards, neither about the number of repositories:

- A repository copied **while it is being written** can yield a ref pointing at an object the copy missed. Use a filesystem snapshot of the repository root, or copy each repository **under its writer lock** — milliseconds, at this size.
- A restore leaves git ahead of the database and the reconciler repairs that, but **database-only state between the last dump and the failure is gone** — holds, access changes, and above all **drafts**, which ADR-0003 makes load-bearing because a session has no intermediate commits. The database therefore needs **continuous archiving with point-in-time recovery**; the tooling is a deployment detail, the requirement is not.
- A repository restored **without its row** is recreated from `document.md`'s frontmatter — title and language — with **no access rows at all**, and the tenant administrator is notified. Fail closed, the same instinct as an untagged finding.

**Housekeeping for many small repositories.** Initialise from an empty template, or every repository carries a dozen sample hooks. Schedule a **periodic repack per repository under its lock**, because a library that writes commits does not repack and each version leaves loose objects; pruning removes only unreachable objects, and in an append-only linear history the only unreachable objects are debris from failed writes — so this does not touch ASR-02, and that sentence belongs beside the job or nobody will dare run it.

**What is given up, recorded rather than discovered.** There is no commit meaning *the corpus as of this moment*; nothing needs one, because an analysis is keyed by each document's own content state (DL-0078). And a cross-document generated view has no repository to live in — when B-003 is taken up it needs a per-tenant derived store, not a home inside any one document.

## Tenancy

A tenant is a fully independent group of users or a separate business (DL-0003). Tenants share nothing but the heuristic catalogue their copies are seeded from.

- **Database — schema per tenant** in PostgreSQL (DL-0029). Isolation is enforced by the database, not by application code: crossing it requires getting a whole request's `search_path` wrong rather than one query's `WHERE` clause. Migrations run per schema; platform-level tables live in a shared schema.
- **Repositories** — a directory per tenant holding one repository per document, pairing with schema-per-tenant. DL-0003's mapping of a tenant to a Forgejo organization lapses with DL-0042.

## Identity and authorisation

Both are Django's (DL-0042, superseding DL-0015). Role assignments at document granularity are the only permission model in the system — one authorisation surface, per ASR-07. The MCP contract, that an external agent holds exactly its user's rights, is a property of the same authorisation path the browser uses.

Principle of least privilege throughout: the burden is on expanding access, never on restricting it.

## Who performs git operations

Django, through a git library, on bare repositories it owns — **Forgejo was dropped at DL-0042** (ADR-0002). The reasoning was the owner's: edits accumulate in the application and are committed on a user's behalf, so a forge cannot authenticate per commit and cannot hold the authorisation; and once the events that start agent runs are the platform's own, forge runners add nothing either.

The operation set is small because the model is linear (ADR-0003): **init, commit, read, diff, blame, revert, tag** — `init` because creating a document creates a repository (DL-0111). No branches, no merges, no conflict resolution.

**Commits carry no personal data** (DL-0088, DL-0093). The git author name is the Django user identifier; the author email is a per-user non-routable address, `{user-id}@users.noreply.syngraphe.local`, so authors stay distinct to any tool that keys on email. The domain is fixed here, once, because it is baked into every commit ever written and changing it later splits one author into two. The mapping to a person lives in PostgreSQL, and a deletion request is answered by removing that mapping rather than by rewriting history — which is what keeps ASR-02 and a person's right to erasure from colliding.

**A contributor map travels with an export, never with the history.** Identifier to display name, generated at export and backup time from the database and never committed. It answers the cost of pseudonymisation — a repository whose history reads as opaque identifiers is not portable evidence — without putting a name anywhere immutable. Erasure changes what the next export contains and nothing that already exists.

What was given up is the forge's web interface for inspecting a repository when something breaks. The replacement is the `git` command line on the host, plus read-only repository views for the platform administrator.

## Repositories and access

**One repository per document** (DL-0111), inside the tenant's directory, named by `DOCUMENT.id`. Confidential guidance is an ordinary document with restricted access (DL-0051, superseding DL-0008). The granularity is what makes the agent's mount list *be* the review scope, so the editor-facing run has no guidance on its filesystem at all.

Access is **data with history** (ASR-08): rows of `document, user, rights`, every change carrying a timestamp and an actor, editable only by a tenant or platform administrator. This is the same table the role assignments live in; a confidential document is one whose rows are few.

The condition the old design relied on is now explicit rather than structural: **no user ever receives raw repository access, and every export is per document**. Both are enforced by the application because the application is the only path to the repository.

## Document storage and diff semantics

A document is **one Markdown file** in its own repository:

```
{tenant}/{document-id}/        # repository root, one per document (DL-0111)
├── document.md       # frontmatter: title, language · body: the whole text
├── entities.yaml     # role, action and term definitions
├── images/           # uploaded binary assets the text embeds
├── analysis/         # editor-facing companion analyses (stage 2)
└── passport.md       # review and approval decisions (DL-0041)
```

### The constrained Markdown subset

**This list is the whitelist.** It is normative and it is the only place the set is enumerated — an epic, a story or a harness tests against it and never restates it, and a construct absent from it is absent from the product (DL-0046, DL-0100).

| Construct | Form | Note |
|---|---|---|
| Headings | `#` to `####` | Depth capped at four; numbering is a render rule |
| Paragraphs | blank-line separated | One sentence per line on disk, never visible |
| Lists | ordered and unordered, nesting to three levels | No task lists |
| Emphasis | `*italic*`, `**bold**` | |
| Underline | `[text]{.underline}` | An attributed span, not `<u>` |
| Entity spans | `[CMO]{.role #cmo}` and the other types | Defined in `entities.yaml` |
| Callouts | typed blockquote, `> [!note]` | Types: note, warning, example |
| Tables | pipe tables | No merged cells, no nested blocks; the row is the unit |
| Images | `![alt](images/name.png)` | Repository-local paths only |
| Links | `[text](url)` and repository-local paths | |

Everything else is outside the subset: raw HTML, scripts, footnotes, definition lists, headings below depth four, task lists, nested tables, merged cells, horizontal rules, code blocks, math, and any remote image or stylesheet reference. The editor offers exactly the set above and nothing else; anything outside it is **rejected at edit time with a message**, never silently dropped.
- **The whitelist binds the parser, not only the editor** (DL-0096): raw HTML disabled, no script, no remote image or stylesheet references, and no network for the PDF renderer. Text arrives by paste and by import as well as by typing, so a rule that only the interface enforces protects nobody.
- **Tables** are pipe tables: one row per line, inline content only, no merged cells, no nested blocks (DL-0100). Inside a table the **row** is the unit of diff, authorship and per-author undo — a cell cannot hold a line break, so the sentence stops being addressable there. The normalizer gives every row exactly one spelling: one space inside each cell edge, no alignment padding, a delimiter row keeping only its alignment colons. Without that, padding from an editor, a paste or a prettifier rewrites every row when one cell changes, and each rewritten row is re-attributed to whoever touched one of them.
- **Entities** are attributed spans — `[CMO]{.role #cmo}`, `[obliged to approve]{.action}`, `[10 days]{.term #timeout}`. Real Pandoc syntax, so it survives every render target and stays machine-readable. Definitions live in `entities.yaml`; the spans mark occurrences. The editor never shows the syntax: a user selects text and marks it.
- **Normal form:** one sentence per line; a server-side normalizer runs before every commit (DL-0012). Paragraph boundaries are blank lines — Markdown's native rule, not a convention imposed on it — and the renderer joins the sentences between them into one paragraph. The user never sees or manages a line break.
- **A stored line is never re-normalised** (DL-0112, ASR-20). No normalizer rule — the splitter, quote and dash typography, Unicode composition, the canonical table row — is ever applied to a line its edit did not touch. *Touched* means the submitted line differs from the stored line **after canonicalising the submitted one**, so a prettifier that pads every table row produces rows that canonicalise back to the stored bytes and count as untouched.
- **The normalizer is a function of two inputs**, the previous version and the submitted text, because the editor returns paragraph text rather than lines. Within each paragraph it aligns the new text against the old, carries the old boundaries across unchanged spans, and runs the rules only over changed spans widened to the whole old lines they overlap.
- **The normal form is therefore path-dependent.** The same text can legitimately be stored with different line breaks depending on its history. **The stored newline is the authority** — a check that re-runs the splitter over a file and compares is not valid, and the line structure cannot be rebuilt from the text, unlike the search and navigation indexes.
- **Normalisation preserves the parse** — an invariant checked on every write. A wrong boundary degrades granularity, not correctness: an over-split renders identically and anchors identically. The one way a boundary can be *wrong* is a break inside an inline construct, and this invariant is what catches it.
- **The normalizer version is recorded per commit**, not per document — one document holds lines split by several versions at once, so a per-document field would be untrue on the day of the first upgrade.
- **Moved text** is the case to watch: a paragraph cut and pasted elsewhere arrives as a deletion and an insertion. If alignment recognises the moved block and carries its bytes and boundaries unchanged, blame can still attribute it to its original author; if it is re-split, the author becomes whoever moved it.
### Rendering, styles and layout

- **Heading numbering is a render rule** derived from depth: `#` is 1, `##` is 1.1, `###` is 1.1.1. Never stored, so moving a section renumbers everything and breaks nothing. Comments and findings anchor by quoted text (DL-0027). A prose reference such as *«як визначено в п. 4.2»* is ordinary text; keeping it true as a document is restructured is a stage 2 heuristic, backlog B-015.
- **Styles are a stylesheet** the designer authors at organization level and selects from per document (DL-0020). The CSS analogy is no longer an analogy.
- Hunks are classified **sense** or **style**. Style hunks **collapse** in the review surface and are accepted **with the run** — they do not auto-accept, because acceptance is a document-level act with no per-hunk step to skip, and a classifier deciding a change needs no human eyes would contradict ASR-04.
- **A section is a heading.** Structure is the heading hierarchy of `document.md`, and restructuring a document is editing its text.
- **Images** are ordinary git blobs — **no LFS** (DL-0066). Allowed types and a per-image size cap are enforced on upload; anything not web-renderable is converted on the way in, which is not optional because no browser renders HEIC; metadata is stripped. A change to an image cannot be read as a diff, so the review surface flags it and renders before-and-after (ASR-04). Revisit LFS only if a repository's size becomes a measured problem.
- **Paragraph numbering** is derived at render, never stored (DL-0065): `1.1-3` is section 1, subsection 1, paragraph 3; the hyphen separates the heading path from the paragraph index, and heading depth is capped at four. In the editor the numbers render in a non-editable gutter outside the editable region, recomputed as the text changes. A finding or a comment anchors by **quoted text** (DL-0027) and displays the current number — the number is a label, never an address.
- **Storage layout is flat.** One repository per document under the tenant's directory; the nested tree a user sees is Django metadata, and a move never touches a path (DL-0058, DL-0111, ASR-15).

## Versions, holds and history

- **Taking the document** opens a draft. It persists server-side, is invisible to others, and is not a version. There is no Save control.
- **There is no Save.** *Send for review* is the commit (DL-0054). Pressing it presents the companion analyses for the current content, and the editor either continues editing or commits.
- **The analyses are written into the same commit** as the content, in `analysis/` (DL-0055). This is why the commit identifier is never needed: the analysis is part of the tree rather than a pointer at it, both halves are known before the commit is made, and the reasoning travels into any clone or export.
- **Analysis files have fixed names and are overwritten on every commit** (DL-0067). Nothing is lost — the analysis as of any version is `git show {commit}:analysis/{name}`. Accumulating timestamped files would duplicate what history already gives.
- **Only the editor-facing artefact goes into the tree.** The reviewer-eyes-only analysis (DL-0007) must never be committed into the document folder, because anyone with read access to the document would read it. It lives outside the tree, reachable only through the access table. Committing it would breach ASR-03 by a storage decision rather than a delivery one.
- History is **linear and append-only** (ADR-0003, ASR-02). No branches, no merges, no rewriting. An unwanted change is undone by a commit that reverts it, computed per sentence from blame, with the platform resolving the case where a later author built on top.
- **`refs/proposals/{id}/head` is no longer needed** — nothing is squashed, so nothing needs retaining. ADR-0002's retention consequence lapses.
- **Acceptance** is a commit to the document's passport carrying the reviewer's decision, so approval history lives in the repository and travels with the document (DL-0041). Corrective edits ride in the same commit.
- **Acceptance is document-level** (DL-0090): one reviewer accepts the whole run since the last accepted version. No per-file ledger, no partially-approved state, no section owners (DL-0091).
- **Holds** are exclusive per document. They expire; a tenant administrator can force release; the released draft is preserved, not discarded.

## The pending view

A plain read, not a computation over branches: the commits since the last accepted revision, in order, attributed. Sentence-per-line keeps attribution exact, so *show author* (DL-0040) resolves to a sentence rather than a paragraph, and a per-author revert is exact.

## Presence

Derived, never declared (DL-0036). Whoever holds the document is shown to everyone. Content stays invisible until the version is committed.

## Rejection records

Rationale and rejected alternatives: [`ADR-0001`](adr/ADR-0001-reviewer-corrects-and-accepts.md).

Generated, not authored. When a reviewer corrects text in the same commit that accepts it, the platform diffs the editor's version against the accepted result; each divergence becomes a record holding **references, never text** (DL-0113): the acceptance, the author, the author's version, and the file and line range in each. Both wordings are rendered from git when the notice is opened, under the reader's **current** rights — so a revoked right or an archived document withdraws the text, which a stored copy would not.

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

- **Web UI** — Ukrainian, all roles, five document stances (DL-0033).
- **MCP server** — an external agent connects as a user and inherits exactly that user's rights. **Not in stage 1** — backlog B-007; the contract is recorded so the authorisation path is built once.

## Export

Markdown, PDF and DOCX. PDF renders through HTML and the designer's stylesheet with weasyprint; DOCX through pandoc. All three are in stage 1 — Markdown made the Word path cheap (DL-0046).

## Publication and secret handling

Apache License 2.0 (DL-0011, DL-0162). Carried from the first commit: no tenant data, credentials or confidential guidance in this repository's history, and configuration by environment rather than by committed file. These are properties of how the repository is built, not checks performed before a release.

## Analysis scope, storage and cost

The same edit yields different findings for different readers: an editor who can see one document, a finance director who can also see a neighbouring one, a chief executive who can also see the confidential guidance. Three rules keep that from multiplying into chaos.

**A review runs under the reviewer's own access** (DL-0077), over a **scope the reviewer selects** — access is not relevance. Findings are tagged with the sources they were derived from and filtered per recipient (DL-0021); the editor-facing artefact comes from a run that never held the confidential material at all (DL-0095), so the control is both the filter and the absence.

**Storage follows provenance, not the user (DL-0069).** A finding derived from the document alone — class P1 — is committed into that document's `analysis/`. Anything derived from other documents or from the guidance lives outside the tree; committing it into a document folder would hand it to everyone who can read that document.

**Keyed by review scope, not by user** (DL-0078). A scope is the ordered set of documents a reviewer put in scope, their content states, and the heuristic set version. Two reviewers with the same scope share one result; different scopes lose nothing. This answers "is it document analysis or user analysis": it is corpus analysis keyed to a scope, anchored to the document whose commit triggered it.

## Types, folders and links

- **Document types** are a platform-managed table — policy, controls, technical instruction, job description, notes — assigned per document by the tenant administrator, used as list filters (DL-0057, DL-0063).
- **Folders** are metadata with unlimited nesting; storage stays flat (ASR-15).
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

An in-application notifications section, email for the same events, and document-list state as the standing picture of what is waiting (DL-0070). The sending identity is settled at DL-0072 — one platform address, credential encrypted at rest and write-only in the interface. Per-tenant sending domains are backlog B-009. **No notification carries document text** (DL-0113): email carries the event and a link.

## Open technical questions

None in the register. Items the architecture review left open are tracked as its findings until each is decided.

## Verification spikes

Claims this design rests on that have not been checked against running software live in [`verification-plan.md`](verification-plan.md), each with its test, its pass condition and what changes if it fails. This section points there and does not restate them.

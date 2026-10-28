---
tags:
  - verification
aliases:
  - Syngraphē verification plan
status: active
date: 2026-09-23
---

# Verification plan

Every claim the design rests on that has not yet been checked against running software — how it is tested, the number that decides it, and what changes if it fails. **This file is where those claims live.** The technical design points here rather than restating them, and an entry changes status here and nowhere else.

A failure consequence marked *proposed* is a planning proposal rather than a decision already recorded elsewhere, and is settled when the entry resolves. An entry is **open** until its test has run, then **proven**, **disproven** or **open with a reason**; an entry settled before its test runs is **accepted as a risk** or **deferred**, with the decision that did so. A disproven entry is a finished result, not a failure of the work: the design changes before anything is estimated against it.

## How the spikes run

Most entries are resolved by spikes in Epic 1. Three rules bind them.

**A spike that leaves a component behind has stopped being a spike** and has skipped review. Each harness is thrown away; what survives is the written finding and, where an alternative was genuinely weighed, an ADR. Where a question could only be answered by building something, the spike answers a narrower question instead and the finding says which.

**The time box is two working days per spike, three for the editor.** At the box the spike stops, and the finding records what was and was not proven. If a box is hit, what is dropped first is the incremental blame measurement, then the second candidate library, then the sentence-boundary-node test — in that order, because each refines an answer the spike has already produced.

**Every server-side library is measured on Python 3.12 on Debian**, the stack the platform pins. A result from a different interpreter is not a result, because what is being decided is what goes into that image.

## The editor

### V-01 — An existing editor library meets the editor's constraints

**Claim.** An existing library can be configured into the constrained editor the product needs. **The spike selects among existing libraries and does not build one** — writing an editor is a product of its own, and a hand-built one is the most expensive way to be wrong here.

**The binding requirement.** The editor carries sentence boundaries as invisible nodes through a round trip and returns **paragraphs rather than lines** (`technical-design.md § The constrained Markdown subset`: the normalizer is a function of the previous version and the submitted paragraph text). That rules out any library whose model is a string of text with formatting laid over it, and points at editors with **a real document tree whose serialisation the application controls**. Two further constraints: the library's licence permits redistribution in an Apache-2.0 product (ASR-13), and it can refuse input outside the whitelist at paste with a message.

**Requirements from the editing surface** (DL-0167, DL-0171, ADR-0004), measured on every candidate:

- **Several independent instances on one page** — one per open section editor — each loading, editing and returning its own range with no state shared between them.
- **Loading a range, not only a whole file** — a section's Markdown in, that section's paragraphs out, headings included, with a `#` typed inside it returned as a new heading.
- **A source view switchable in place** — formatted text to Markdown and back without leaving the editor; the round trip across the switch is V-02's.
- **Paste interception** — pasted Markdown or rich text reaches application code before it enters the document, so the refusal, the named lines and the conversion preview can be built on it.
- **Mounting without a client framework** — the library runs as an island in a server-rendered page, driven by plain JavaScript.

**Candidates to measure**, not a preference among them: ProseMirror used directly, Tiptap (on ProseMirror), Milkdown (ProseMirror with a Markdown pipeline), Lexical and Slate. The spike adds any candidate it finds that meets the constraints above, and records why each one is a candidate.

**Pass condition.** A library is selected only if it passes V-02 and V-03 in full and meets every requirement from the editing surface — three instances on one page editing three sections, and a source-view switch on each; among those that do, the spike records the trade-offs and an ADR records the choice, which also moves ADR-0004 from proposed to accepted or reopens it.

**If no candidate passes.** Tables fall back to a source-view editor for tables only, and ST-0019's acceptance criteria change before it is estimated. If sentence-boundary nodes are what fails, server-side alignment remains the control (V-03).

**Status.** Proven — 2026-09-27: ProseMirror, used directly, passes V-02 and V-03 in full; three instances on one page edit three sections independently, each with a source-view switch; ranges load and return as sections; paste reaches application code before it enters the document, where pasted images become uploaded files (DL-0232). Tiptap, Milkdown and Lexical were measured beside it and Slate screened out; the choice and the alternatives are ADR-0010, accepted with ADR-0004.

### V-02 — The constrained editor round-trips the whitelist losslessly, tables included

**Claim.** Every construct in the whitelist survives editor → Markdown → editor unchanged, and everything outside it is refused.

**Test.** A harness takes each row of the whitelist table through a round trip and compares the two sides **after canonicalisation by the normalizer's own rules** — no second notion of sameness. The refusal path is tested with raw HTML, a nested table, a merged cell, a fifth-level heading and a code block, pasted in.

**Pass condition.** **Zero differences** after canonicalisation across every whitelist row, images and links included; **every** refusal case refused at paste with a message and none silently dropped.

**If it fails.** As V-01: a table failure moves tables to a source-view editor; any other construct that cannot round-trip leaves the whitelist before a story is estimated against it.

**Status.** Proven — 2026-09-27, on ProseMirror direct with a markdown-it pipeline generated from one specification. Every whitelist row, tables, images and links included, round-trips with zero differences after canonicalisation through the editor, its DOM, its clipboard and the source view; every refusal case is refused at paste with the construct and its line named, in the source view and in the rich view. The tested set is the whitelist as amended by DL-0238 and DL-0239. Several spellings of one document are written back in a single canonical form, and the normalizer owns those rules (DL-0240).

### V-03 — Sentence boundaries survive the editor as invisible nodes

**Claim.** The editor can hold the stored sentence boundaries as nodes the user never sees, and return them unchanged in spans the user did not edit.

**Test.** Load a multi-paragraph document with known boundaries, edit one sentence, and compare the returned boundaries with the stored ones.

**Pass condition.** **Every** boundary outside the edited sentence comes back unchanged, and the editor returns paragraph units, never lines.

**If it fails.** Not a blocker: text also arrives by paste and import, so server-side alignment of the submitted paragraph against the previous version is the control either way. The loss is precision inside the editor, recorded in the finding.

**Status.** Proven — 2026-09-27, on ProseMirror direct: a stored boundary is an invisible inline node that renders as the space between sentences. After an edit made with real keys — a word inside a sentence, inside a bold span, a list item or a callout, a sentence joined, deleted or split, a sentence typed — every boundary outside the edited sentence comes back unchanged, and undo restores the text exactly. The serialiser writes a boundary only between two pieces of text, so deleting a sentence cannot turn into a paragraph break. No line break can exist inside a paragraph; the editor returns paragraphs.

### V-04 — One specification drives both the editor and the server-side parser

**Claim.** A single machine-readable specification of the whitelist can generate the editor's schema and the server-side parser's configuration, so the two cannot disagree (ASR-19: the parser is bound, not only the interface). The parser must also read attributed spans — `[CMO]{.role #cmo}` — which plain CommonMark does not.

**Test.** A throwaway specification file generates both; one conformance case list, each case marked accept or reject, runs against the editor and against the parser. Candidates for the parser are a CommonMark implementation admitting a custom inline rule, and a Pandoc-compatible parser.

**Pass condition.** **Identical verdicts on every conformance case.** A single divergence is the same defect as having no whitelist.

**If it fails** *(proposed during planning; no earlier document states it)*. Two specifications kept in step by the conformance suite in CI — a weaker control, recorded as such in the technical design.

**Status.** Proven for what the specification carries; the rest held by the fallback's control — 2026-09-27. markdown-it in the editor and markdown-it-py on the server, both configured from one specification file, return identical verdicts, refusal codes and lines on a 100-case conformance list, on Python 3.12 / Debian, and the suite detects a planted divergence. The specification carries the parameters — depths, span types, callout types, patterns. The span tokenizer, the callout rule and the validator's walk are code written once per language, and for them the conformance suite in CI is the control, as the fallback above describes; the technical design records it. Pandoc, the other candidate, gave the same reading as the editor on 67 of the list's 69 accept cases and is not chosen (ADR-0010).

## The git library

### V-05 — A Python git library performs the operation set on bare repositories, fast enough for the authorship job

**Claim.** A Python library performs init, commit, read, diff, blame, revert and tag on bare repositories, and blame is fast enough for the worker's post-commit authorship job — blame never runs inside a page load, because authorship is cached per commit.

**Test.** On a generated corpus — a forty-page document, two hundred commits, three authors, committed one edit at a time — exercise every operation, with commits carrying the non-routable author address from `technical-design.md § Who performs git operations`. Time a cold blame over the whole corpus, then an incremental blame after one more commit.

**Pass condition.** Every operation succeeds on a bare repository; **cold blame ≤ 5 seconds**. The incremental figure is recorded and not judged: it sizes the worker, and the cold run already decides whether the library is a candidate.

**If it fails** *(proposed during planning; no earlier document states it)*. A library over five seconds is not a candidate. If none passes, authorship moves to incremental computation from each commit's diff, and blame becomes a repair path rather than the source.

**Status.** Proven — 2026-09-27. On a generated corpus of 203 commits by three authors (a Ukrainian document of 17,060 words, and the same history in English), on Python 3.12 / Debian 12 with 2 CPUs: pygit2 1.20.1 (libgit2 1.9.7) performs every operation on a bare repository, revert included, without a working tree; GitPython 3.1.62 does too, but its revert over Debian's git 2.39.5 needs a temporary index because `merge-tree --merge-base` arrived in git 2.40; dulwich 1.2.15 has no blame. Cold blame over the whole history: 0.55 s through pygit2, 0.23 s through the `git` binary, 0.26 s through GitPython, the two libraries agreeing on every one of 1,624 lines. A full blame after one more commit costs the same; blame bounded to the commits since the cached one (`git blame ^cached new`) costs 8 ms. The choice is ADR-0011.

### V-06 — Blame detects a paragraph moved within a section

**Claim.** The library's blame follows moved lines, so a paragraph cut and pasted within a section keeps its original author.

**Test.** On the corpus, move a paragraph authored by one author, committed by another, and blame the result.

**Pass condition.** **Every** moved line is attributed to its original author.

**If it fails.** Moved text is attributed to whoever moved it. *Show edit authors* and per-author undo (ST-0037) both degrade, and the scope agreement's wording on attribution changes before it is signed.

**Status.** Disproven for the library's blame, met by the platform's own rule — 2026-09-27. On the English corpus `git blame -M` attributes every moved line to its original author; on the Ukrainian corpus no route does — git's move detection scores a moved block by its ASCII letters and digits and compares that score with the `-M` threshold, so a paragraph of Cyrillic text never qualifies (the same paragraph with a clause reference such as `(п. 4.2.1)` in each sentence is followed at `-M1`). libgit2, and so pygit2, has no move detection. The library's blame therefore does not meet the claim for the platform's own language. A move is nonetheless recognisable without git: in the platform's normal form a moved sentence is a line removed and re-added verbatim in one commit, and that rule, applied in V-11, followed all 68 moves in the Ukrainian history exactly. The fallback above is not taken: the platform detects moves itself and keeps the attribution the claim promises (ADR-0011), and the normalizer keeps a moved paragraph's stored lines on every path (DL-0244), which is the assumption the rule rests on. Attribution of moved text holds as the claim promises; ST-0037 was re-scoped separately by ADR-0015, and the move paths are tested at both layers — `tests/editing/test_reuse.py::test_v15_every_path` and `tests/editing/test_authorship.py::test_agrees_with_the_record_including_moves`.

### V-07 — Blame can skip named commits

**Claim.** Attribution can exclude named commits, the mechanism a future re-split migration would need. Not built now; proven so nobody invents a different one.

**Test.** Commit a whitespace-only rewrite of every line, then blame with that commit excluded.

**Pass condition.** Attribution with the commit excluded is **identical** to attribution of the history before it.

**If it fails** *(proposed during planning; no earlier document states it)*. A future re-split migration has to rewrite authorship in the derived store rather than in blame. Recorded, nothing built.

**Status.** Proven for every line that carries text — 2026-09-27. After a whitespace-only rewrite of all 1,302 sentence and heading lines, `git blame --ignore-rev` (and the `--ignore-revs-file` a migration would write) attributes every one of them exactly as the history before the rewrite did, on both corpora; the 322 blank lines, which the rewrite did not touch, are re-assigned by git's ignore heuristic to nearby lines, and a blank line carries no sentence. `-w` alone, and `--ignore-rev -w`, match on all 1,624 lines. libgit2 can ignore whitespace but cannot exclude a named commit, so this mechanism lives in the `git` binary (ADR-0011).

### V-08 — Repacking an append-only history loses no version

**Claim.** Repack and prune remove only unreachable objects, and in an append-only linear history the only unreachable objects are debris from failed writes — so housekeeping never touches ASR-02.

**Test.** On the corpus, list every object reachable from every ref, repack and prune, list again.

**Pass condition.** **Zero** reachable objects missing afterwards, and every tagged version readable.

**If it fails** *(proposed during planning; no earlier document states it)*. Housekeeping runs repack without prune, and repository size is watched instead.

**Status.** Proven — 2026-09-27. On both corpora, with a dangling blob and a dangling commit planted and the unreferenced side commits of the other spikes left behind as real debris: 629 objects reachable before `repack -a -d` and `prune --expire=now`, 629 after, none missing, every unreachable object gone, `fsck --strict` clean, and `document.md` at each of the 20 tags read back byte-identical through pygit2 and through GitPython; 0.4 s. In the product the repack and prune run nightly, each repository under its writer lock, and `tests/documents/test_housekeeping.py` repeats the check on every run of the suite: a dangling blob and commit planted, every reachable object present afterwards, the debris gone, `fsck --strict` clean.

## Text and rendering

### V-09 — A rule-based splitter's disagreement rate on Ukrainian policy text is low enough to be invisible

**Claim.** A rule-based sentence splitter with a per-language abbreviation list places boundaries a reader would agree with, closely enough that nobody notices a wrong one.

**Test.** Against a **synthetic policy sample** — invented Ukrainian policy text in the register of a real policy and at the length of the longest document the platform expects, written to exhibit the cases a splitter fails on, each many times: abbreviations ending in a full stop, initials before a surname, numbered and lettered clause hierarchies, decimal numbers, amounts and dates, quotations spanning more than one sentence, list items that are and are not sentences, and headings without terminal punctuation. Every intended boundary is marked by its author as it is written. Count the boundaries that disagree with the marks and classify each as too coarse or too fine. Separately, introduce a deliberate break inside an inline construct and run the parse-preservation check.

**Pass condition.**
- **Zero** breaks inside an inline construct — the one way a boundary is wrong rather than merely coarse or fine.
- The parse-preservation check catches **every** deliberate bad break.
- Disagreement rate **≤ 1 boundary in 200** against the marked reference.

The threshold was set by the owner in DL-0246. The owner approves the sample before the measurement counts; until then the result is provisional.

**If it fails.** A wrong boundary degrades granularity, not correctness — an over-split renders and anchors identically — so a high rate changes attribution precision and the abbreviation list, not the architecture. A break inside an inline construct is a defect in the splitter and blocks it.

**Status.** Proven — measured 2026-09-27; the owner approved the enriched sample on 2026-09-28, every boundary mark in its place. On a synthetic Ukrainian policy text of 21,018 words carrying every listed hard case at least twenty times, with 1,015 boundaries marked as written, a rule-based splitter of the platform's own — terminal punctuation and closing marks, no break before a lowercase letter or a digit, an initial never final, two abbreviation lists per language (*never final*, *may be final*), link destinations, attribute blocks and images masked — places **0 boundaries in disagreement** with the marks (0 in 200 against the threshold of 1 in 200), **0 inside an inline construct**, and every one of its boundaries preserves the parse; the same on the English text (0 of 1,012). The parse-preservation check — the block's HTML through markdown-it-py, soft breaks read as spaces, equal before and after the split — caught all six planted bad breaks and flagged neither control. Four rule-based libraries measured on the same masked text disagree on 272 to 380 Ukrainian boundaries each, mostly at sentence-final abbreviations, closing quotation marks and clause numbers; the choice is ADR-0012. The sample and the splitter's rules share an author, so the owner's reading of the sample is the control on what it exercises.

### V-10 — The render chain carries every construct and the derived numbering into HTML, PDF and DOCX

**Claim.** Markdown → HTML with a stylesheet → weasyprint PDF, and Markdown → pandoc DOCX, carry the whole whitelist and the `1.1-3` clause numbering into all three targets, with no network available to the renderer.

**Test.** A *conformance sample* exercises every whitelist row with hand-authored numbers; a *negative sample* carries a remote image reference. Render both through a throwaway stylesheet with the network blocked.

**Pass condition.**
- **Every** whitelist construct present and structurally correct in HTML, PDF and DOCX.
- The numbering renders **unchanged** in all three.
- Entity spans appear as styled text, **never** as literal syntax.
- The negative sample is **rejected by the parser with a message**, and its render **fails** with the network blocked — **zero** fetches.

**If it fails** *(proposed during planning; no earlier document states it)*. A construct that one target cannot carry is either dropped from the whitelist or given a documented degraded form for that target, decided before ST-0045 and ST-0042 are estimated.

**Status.** Proven — 2026-09-27 — for the PDF renderer as the platform configures it; for DOCX the fourth condition is met by the parser's rejection, since Pandoc cannot fail on a fetch (DL-0258). On Python 3.12 / Debian in a container with no network. A synthetic conformance sample carrying every whitelist row, the plain quote included, and twelve hand-authored clause and heading labels attached at render — numbering is never stored — arrives complete and structurally correct in HTML from markdown-it-py 4.2.0, in PDF from weasyprint 70.0 and in DOCX from Pandoc 3.9, whether Pandoc reads the Markdown or the HTML: headings to depth four, lists three deep, emphasis, underline, entity spans as styled elements and as named Word character styles, quote, the three callout types as named paragraph styles, an aligned table, the image, the three link kinds; the labels verbatim in all three; literal span syntax nowhere. The negative sample is refused by the parser with `image-src` and its line. With the network blocked, weasyprint's stock configuration logs an error and still writes the PDF; with its `fail_on_errors` setting on, the render raises and writes nothing, with zero fetches — the configuration the platform runs. Pandoc replaces an unreachable image with its description and exits 0, so the validator, never a renderer, is the gate. The chain and the DOCX route are ADR-0013.

## Attribution

### V-11 — A sentence-granular per-author revert can be computed from blame and presented where later authors built on top

**Claim.** One author's contribution can be undone sentence by sentence, distinguishing sentences nobody has touched since from those a later author changed, and offering a choice for each of the latter — the feature behind *reject all changes by this author*.

**Test.** On the V-05 corpus, compute per-sentence authorship for one author, classify every sentence as untouched or built on, and present the choice — keep the later wording, or return to the text before this author — for each built-on sentence.

**Pass condition.** **Every** sentence of the author classified; the choice presentable for **every** built-on sentence; the computation over the forty-page history **≤ 5 seconds**, the same budget as the authorship job. What the algorithm cannot resolve is listed, and the owner judges the result against the scope agreement's promise.

**If it fails.** The scope agreement's bullet on taking one person's contribution back out is reworded before it is signed, and ST-0037 is re-scoped.

**Status.** Proven — 2026-09-27; the owner judged the same day that the result supports the scope agreement's promise. For one author of the corpus, every sentence the author added — 440, found in the diffs of the author's 71 commits — is classified from blame: 414 untouched, 22 built on by a later author, 4 removed; the classification, the later wording of every built-on sentence and the text before the author agree with the generator's own record on all 440, with nothing unresolved. The computation is a reverse blame from each of the author's commits to HEAD, plus the diff of the commit that changed a sentence: 3.1 s over the Ukrainian history, 2.1 s over the English, against a budget of 5 s, on 2 CPUs. The Ukrainian history needs the platform's own move rule (V-06): without it a paragraph moved by someone else reads as that author removing the sentences.

**Since.** The choice this claim proved presentable is no longer offered: undoing a contribution lists the built-on sentences for the reviewer to edit by hand (ADR-0015). Its classification — clean, or built on and listed — is what the design uses; its method is not: the undo walks the run forward with the correction notice's walk (DL-0425), proven by V-14.

### V-14 — A per-version revert separates the lines a later version changed from those that revert cleanly

**Claim.** For *undo this edit* on any version of the pending run, every line that version changed is classified as reverting cleanly, or as changed again by a later version of the run and left for the reviewer (ADR-0015) — by the correction notice's forward walk, which serves the per-author undo too (DL-0425).

**Test.** `tests/review/test_undo_corpus.py`: on the V-05 corpus, revert each of a run's versions in turn; compare every line's classification with the generator's record, and the reversed text with the text before that version on every clean line. `tests/review/test_undo_budget.py` times the walk.

**Pass condition.** **Every** line of the version classified, **none** misclassified against the generator's record, and the reversed text equal to the text before that version on every clean line.

**If it fails** *(proposed during planning; no earlier document states it)*. *Undo this edit* is withdrawn and the per-author undo, which V-11 proved, remains; ST-0037 loses its first form.

**Status.** Proven — 2026-10-14: over the corpus's 200 edits, 283 lines classified — 258 clean, 23 built on and listed, 2 built on and not listed, the lines a later version deleted outright (DL-0422) — none against the generator's record, every clean line placed as the text before its version had it. *Undo this edit* on the earliest version of the run walks 202 commits in 0.11 s, against DL-0135's five seconds, measured alone. The walk is the correction notice's forward walk and its move rule (ADR-0011), so no third rule exists. Was: accepted as a risk before the design review (DL-0247, DL-0278).

### V-15 — The normalizer keeps unchanged text's stored lines on every text path

**Claim.** Text whose canonical form equals stored text — a whole paragraph, or a sentence that is a stored line — keeps the stored bytes wherever it moves and however it arrives: the rich editor, the source view or an outside paste (DL-0244). V-06's exact-line rule rests on it.

**Test.** In the normalizer's tests, on a synthetic Ukrainian document: a paragraph moved within a section, moved between sections, moved through the source view, pasted back from outside the editor, and moved with one sentence reworded; and two identical sentences, one moved. Compare every stored line after the commit with the lines before it.

**Pass condition.** **Every** unchanged sentence keeps its stored bytes on **every** path; only the reworded sentence is re-split; the identical pair leaves the same bytes whichever line is matched.

**If it fails** *(proposed during planning; no earlier document states it)*. Moved text is attributed to whoever moved it on the failing path, V-06's status reopens, and the scope agreement's wording on attribution changes before it is signed.

**Status.** **Proven** — 2026-09-29, by the normalizer's tests (`tests/editing/test_reuse.py`, `tests/editing/test_untouched_lines.py`), on every path. A synthetic Ukrainian document of two sections and five paragraphs, one of whose stored lines holds two sentences as an older split might have left it — a line the current splitter would divide — was normalised against each submission: a paragraph moved within a section and between sections with its lines as the editor keeps them; the whole document through the source view, every paragraph on one line and one moved to the other section; a paragraph deleted and pasted back from outside as one line with extra spaces, trailing whitespace, or no-break spaces between its sentences; a paragraph moved to the other section as one line with one sentence reworded; and a sentence with an identical twin in another paragraph moved into a third. Every result equals the stored document rearranged byte for byte: every unchanged sentence keeps its stored bytes, the two-sentence line included; the reworded sentence is the only new line; the identical pair leaves the same bytes. The same holds at forty pages: on the corpus document one sentence changed, through the editor and through the source view, leaves every other line byte-identical (ASR-20). A paragraph moved into a list item or a quote keeps its lines' bytes after the container's prefix. A stored line is carried only where it stands as a sentence of its own (DL-0323): a new sentence that merely contains a stored line's words is split as new text.

### V-17 — The undo walks every appendix within its budget

**Claim.** *Undo this edit* walks the body and every appendix the run touched, each with the correction notice's walk, and merges each file's reversal into the reviewer's draft within the undo's five seconds (DL-0135) at ASR-23's largest document (DL-0447, ADR-0015).

**Test.** `tests/review/test_undo_appendices_budget.py`, run alone: a generated document of about 300 KB of invented English — a body of about 150 KB and five appendices of about 30 KB — and a run of 200 versions, each changing the body and one appendix; *undo this edit* on the run's earliest version, timing the walk of every file and each file's merge, without the database writes. Measured on the development workstation, then on the development host.

**Pass condition.** Under five seconds on the development host.

**If it fails.** DL-0447's fallback, the owner's to take: an appendix's text is not walked; each appendix whose text an undone version changed is listed once, for the reviewer to edit by hand, and an appendix-only version answers with that entry.

**Status.** **Proven.** On the development host, 2026-10-28, alone, three runs: 0.185 s, 0.194 s and 0.194 s over six files — the body and five appendices, 300 KB at the head — and 200 versions; a container reporting six processors and 8 GiB, Python 3.12. Measured first on a development workstation, 2026-10-18: 0.47 s.

## The platform

### V-12 — Schema-per-tenant migrations stay manageable

**Claim.** Running migrations across one schema per tenant stays within a deploy window at the scale the platform is sized for — tens of tenants.

**Test.** Resolved in Epic 2, where the first migrations are written: time a representative migration across one, ten and twenty schemas.

**Pass condition.** **Ten schemas in under sixty seconds**, and a per-schema cost that stays linear across the three measurements.

**If it fails** *(proposed during planning; no earlier document states it)*. Migrations run per tenant in the background behind a version check, and a deploy stops waiting for all of them — a change to the deploy procedure, not to the tenancy model.

**Status.** **Proven.** `migrate_schemas` over fresh schemas, `django.contrib.auth` standing for a tenant app — twelve migrations, three tables — and the shared-only apps recorded without running: one schema 0.10 s, ten 1.07 s, twenty 2.22 s — ten well inside sixty seconds, t10 ≤ 1.2 · 10 · t1 and t20 ≤ 1.2 · 2 · t10. Measured on a workstation against PostgreSQL 16 in Docker. The suite keeps the budget and the twenty-against-ten ratio on every run (DL-0288).

### V-13 — A sandboxed job can be given read access to two differently permissioned repositories

**Claim.** An agent run can mount exactly the repositories in its review scope read-only, where those repositories carry different access rows, and reach nothing else — the control that keeps confidential guidance out of the editor-facing run.

**Test.** Stage 2, no epic yet. Start a job with two repositories mounted read-only; attempt to read a third, to write to either, and to reach any host but the model endpoint.

**Pass condition.** Both mounted repositories readable; **zero** successful reads outside them, **zero** writes, **zero** connections to any other host.

**If it fails.** The two-run containment (`threat-model.md` T-01, T-02) cannot rest on the mount table, and stage 2's design reopens before any agent is built.

**Status.** Deferred to release 0.2, where agent runs arrive; it shapes no story in 0.1 (DL-0211).

### V-16 — A bundle run fits five minutes

**Claim.** A run of bundles, the nightly run of full bundles included, completes in under five minutes at the platform's sizes, so the ten-minute interval keeps ASR-25's fifteen minutes (DL-0296, ADR-0019).

**Test.** Time the nightly run of full bundles against the backup store: once on the development stack, again at the first production deploy.

**Pass condition.** Under five minutes.

**If it fails.** ADR-0019's review trigger: the interval or the run is revisited.

**Status.** Open with a reason: to be measured again at the first production deploy. Measured 2026-09-29 on a development workstation against an SFTP store on the local network, 102 documents, 100 of them of about forty pages and 203 commits each: 336 s over repositories never repacked (834 MB of loose objects), 107 s after a repack (23 MB), the repack itself 112 s. The trigger was met and answered by repacking nightly before the base backup (DL-0313).

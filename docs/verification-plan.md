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

A failure consequence marked *proposed* is a planning proposal rather than a decision already recorded elsewhere, and is settled when the entry resolves. An entry is **open** until its test has run, then **proven**, **disproven** or **open with a reason**. A disproven entry is a finished result, not a failure of the work: the design changes before anything is estimated against it.

## How the spikes run

Most entries are resolved by spikes in Epic 1. Three rules bind them.

**A spike that leaves a component behind has stopped being a spike** and has skipped review. Each harness is thrown away; what survives is the written finding and, where an alternative was genuinely weighed, an ADR. Where a question could only be answered by building something, the spike answers a narrower question instead and the finding says which.

**The time box is two working days per spike, three for the editor.** At the box the spike stops, and the finding records what was and was not proven. If a box is hit, what is dropped first is the incremental blame measurement, then the second candidate library, then the sentence-boundary-node test — in that order, because each refines an answer the spike has already produced.

**Every server-side library is measured on Python 3.12 on Debian**, the stack the platform pins. A result from a different interpreter is not a result, because what is being decided is what goes into that image.

## The editor

### V-01 — An existing editor library meets the editor's constraints

**Claim.** An existing library can be configured into the constrained editor the product needs. **The spike selects among existing libraries and does not build one** — writing an editor is a product of its own, and a hand-built one is the most expensive way to be wrong here.

**The binding requirement.** The editor carries sentence boundaries as invisible nodes through a round trip and returns **paragraphs rather than lines** (`technical-design.md § The constrained Markdown subset`: the normalizer is a function of the previous version and the submitted paragraph text). That rules out any library whose model is a string of text with formatting laid over it, and points at editors with **a real document tree whose serialisation the application controls**. Two further constraints: the library's licence permits redistribution in an Apache-2.0 product (ASR-13), and it can refuse input outside the whitelist at paste with a message.

**Candidates to measure**, not a preference among them: ProseMirror used directly, Tiptap (on ProseMirror), Milkdown (ProseMirror with a Markdown pipeline), Lexical and Slate. The spike adds any candidate it finds that meets the constraints above, and records why each one is a candidate.

**Pass condition.** A library is selected only if it passes V-02 and V-03 in full; among those that do, the spike records the trade-offs and an ADR records the choice.

**If no candidate passes.** Tables fall back to a source-view editor for tables only, and ST-0019's acceptance criteria change before it is estimated. If sentence-boundary nodes are what fails, server-side alignment remains the control (V-03).

### V-02 — The constrained editor round-trips the whitelist losslessly, tables included

**Claim.** Every construct in the whitelist survives editor → Markdown → editor unchanged, and everything outside it is refused.

**Test.** A harness takes each row of the whitelist table through a round trip and compares the two sides **after canonicalisation by the normalizer's own rules** — no second notion of sameness. The refusal path is tested with raw HTML, a nested table, a merged cell, a fifth-level heading and a code block, pasted in.

**Pass condition.** **Zero differences** after canonicalisation across every whitelist row, images and links included; **every** refusal case refused at paste with a message and none silently dropped.

**If it fails.** As V-01: a table failure moves tables to a source-view editor; any other construct that cannot round-trip leaves the whitelist before a story is estimated against it.

### V-03 — Sentence boundaries survive the editor as invisible nodes

**Claim.** The editor can hold the stored sentence boundaries as nodes the user never sees, and return them unchanged in spans the user did not edit.

**Test.** Load a multi-paragraph document with known boundaries, edit one sentence, and compare the returned boundaries with the stored ones.

**Pass condition.** **Every** boundary outside the edited sentence comes back unchanged, and the editor returns paragraph units, never lines.

**If it fails.** Not a blocker: text also arrives by paste and import, so server-side alignment of the submitted paragraph against the previous version is the control either way. The loss is precision inside the editor, recorded in the finding.

### V-04 — One specification drives both the editor and the server-side parser

**Claim.** A single machine-readable specification of the whitelist can generate the editor's schema and the server-side parser's configuration, so the two cannot disagree (ASR-19: the parser is bound, not only the interface). The parser must also read attributed spans — `[CMO]{.role #cmo}` — which plain CommonMark does not.

**Test.** A throwaway specification file generates both; one conformance case list, each case marked accept or reject, runs against the editor and against the parser. Candidates for the parser are a CommonMark implementation admitting a custom inline rule, and a Pandoc-compatible parser.

**Pass condition.** **Identical verdicts on every conformance case.** A single divergence is the same defect as having no whitelist.

**If it fails** *(proposed during planning; no earlier document states it)*. Two specifications kept in step by the conformance suite in CI — a weaker control, recorded as such in the technical design.

## The git library

### V-05 — A Python git library performs the operation set on bare repositories, fast enough for the authorship job

**Claim.** A Python library performs init, commit, read, diff, blame, revert and tag on bare repositories, and blame is fast enough for the worker's post-commit authorship job — blame never runs inside a page load, because authorship is cached per commit.

**Test.** On a generated corpus — a forty-page document, two hundred commits, three authors, committed one edit at a time — exercise every operation, with commits carrying the non-routable author address from `technical-design.md § Who performs git operations`. Time a cold blame over the whole corpus, then an incremental blame after one more commit.

**Pass condition.** Every operation succeeds on a bare repository; **cold blame ≤ 5 seconds**. The incremental figure is recorded and not judged: it sizes the worker, and the cold run already decides whether the library is a candidate.

**If it fails** *(proposed during planning; no earlier document states it)*. A library over five seconds is not a candidate. If none passes, authorship moves to incremental computation from each commit's diff, and blame becomes a repair path rather than the source.

### V-06 — Blame detects a paragraph moved within a section

**Claim.** The library's blame follows moved lines, so a paragraph cut and pasted within a section keeps its original author.

**Test.** On the corpus, move a paragraph authored by one author, committed by another, and blame the result.

**Pass condition.** **Every** moved line is attributed to its original author.

**If it fails.** Moved text is attributed to whoever moved it. *Show author* and per-author undo (ST-0037) both degrade, and the scope agreement's wording on attribution changes before it is signed.

### V-07 — Blame can skip named commits

**Claim.** Attribution can exclude named commits, the mechanism a future re-split migration would need. Not built now; proven so nobody invents a different one.

**Test.** Commit a whitespace-only rewrite of every line, then blame with that commit excluded.

**Pass condition.** Attribution with the commit excluded is **identical** to attribution of the history before it.

**If it fails** *(proposed during planning; no earlier document states it)*. A future re-split migration has to rewrite authorship in the derived store rather than in blame. Recorded, nothing built.

### V-08 — Repacking an append-only history loses no version

**Claim.** Repack and prune remove only unreachable objects, and in an append-only linear history the only unreachable objects are debris from failed writes — so housekeeping never touches ASR-02.

**Test.** On the corpus, list every object reachable from every ref, repack and prune, list again.

**Pass condition.** **Zero** reachable objects missing afterwards, and every tagged version readable.

**If it fails** *(proposed during planning; no earlier document states it)*. Housekeeping runs repack without prune, and repository size is watched instead. Running it under the document's writer lock is a constraint on Epic 3, which builds the lock, and is not tested here.

## Text and rendering

### V-09 — A rule-based splitter's disagreement rate on Ukrainian policy text is low enough to be invisible

**Claim.** A rule-based sentence splitter with a per-language abbreviation list places boundaries a reader would agree with, closely enough that nobody notices a wrong one.

**Test.** Against the **synthetic policy sample** specified in Epic 1 DD-3 — invented Ukrainian policy text written to exhibit the hard cases, with every intended boundary marked by its author as it is written. Count the boundaries that disagree with the marks and classify each as too coarse or too fine. Separately, introduce a deliberate break inside an inline construct and run the parse-preservation check.

**Pass condition.**
- **Zero** breaks inside an inline construct — the one way a boundary is wrong rather than merely coarse or fine.
- The parse-preservation check catches **every** deliberate bad break.
- Disagreement rate **≤ 1 boundary in 200** against the marked reference.

> [!warning] The disagreement threshold is an initial proposal, not yet approved
> The rate is the owner's to set; 1 in 200 is proposed as roughly one visible oddity in a forty-page document. The owner also approves the sample itself at G4-b, and until then the result is provisional.

**If it fails.** A wrong boundary degrades granularity, not correctness — an over-split renders and anchors identically — so a high rate changes attribution precision and the abbreviation list, not the architecture. A break inside an inline construct is a defect in the splitter and blocks it.

### V-10 — The render chain carries every construct and the derived numbering into HTML, PDF and DOCX

**Claim.** Markdown → HTML with a stylesheet → weasyprint PDF, and Markdown → pandoc DOCX, carry the whole whitelist and the `1.1-3` paragraph numbering into all three targets, with no network available to the renderer.

**Test.** A *conformance sample* exercises every whitelist row with hand-authored numbers; a *negative sample* carries a remote image reference. Render both through a throwaway stylesheet with the network blocked.

**Pass condition.**
- **Every** whitelist construct present and structurally correct in HTML, PDF and DOCX.
- The numbering renders **unchanged** in all three.
- Entity spans appear as styled text, **never** as literal syntax.
- The negative sample is **rejected by the parser with a message**, and its render **fails** with the network blocked — **zero** fetches.

**If it fails** *(proposed during planning; no earlier document states it)*. A construct that one target cannot carry is either dropped from the whitelist or given a documented degraded form for that target, decided before ST-0045 and ST-0042 are estimated.

## Attribution

### V-11 — A sentence-granular per-author revert can be computed from blame and presented where later authors built on top

**Claim.** One author's contribution can be undone sentence by sentence, distinguishing sentences nobody has touched since from those a later author changed, and offering a choice for each of the latter — the feature behind *reject all changes by this author*.

**Test.** On the V-05 corpus, compute per-sentence authorship for one author, classify every sentence as untouched or built on, and present the choice — keep the later wording, or return to the text before this author — for each built-on sentence.

**Pass condition.** **Every** sentence of the author classified; the choice presentable for **every** built-on sentence; the computation over the forty-page history **≤ 5 seconds**, the same budget as the authorship job. What the algorithm cannot resolve is listed, and the owner judges the result against the scope agreement's promise.

**If it fails.** The scope agreement's bullet on taking one person's contribution back out is reworded before it is signed, and ST-0037 is re-scoped.

## The platform

### V-12 — Schema-per-tenant migrations stay manageable

**Claim.** Running migrations across one schema per tenant stays within a deploy window at the scale the platform is sized for — tens of tenants.

**Test.** Resolved in Epic 2, where the first migrations are written: time a representative migration across one, ten and twenty schemas.

**Pass condition.** **Ten schemas in under sixty seconds**, and a per-schema cost that stays linear across the three measurements.

**If it fails** *(proposed during planning; no earlier document states it)*. Migrations run per tenant in the background behind a version check, and a deploy stops waiting for all of them — a change to the deploy procedure, not to the tenancy model.

### V-13 — A sandboxed job can be given read access to two differently permissioned repositories

**Claim.** An agent run can mount exactly the repositories in its review scope read-only, where those repositories carry different access rows, and reach nothing else — the control that keeps confidential guidance out of the editor-facing run.

**Test.** Stage 2, no epic yet. Start a job with two repositories mounted read-only; attempt to read a third, to write to either, and to reach any host but the model endpoint.

**Pass condition.** Both mounted repositories readable; **zero** successful reads outside them, **zero** writes, **zero** connections to any other host.

**If it fails.** The two-run containment (`threat-model.md` T-01, T-02) cannot rest on the mount table, and stage 2's design reopens before any agent is built.

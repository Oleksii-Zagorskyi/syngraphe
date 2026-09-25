---
tags:
  - adr
aliases:
  - ADR-0003 Linear edit history
status: accepted
date: 2026-09-21
amended: 2026-09-23
title: Linear edit history — no branching, no merging
supersedes: []
superseded_by:
  - ADR-0006 (in part — hold expiry)
---

# ADR-0003: Linear edit history: no branching, no merging

**Date:** 2026-09-21
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** DL-0013, DL-0014, DL-0034, DL-0035, DL-0037

## Context

The platform borrowed its workflow from software review: branches, change proposals, merges. That inheritance brought a chain of consequences — per-file locking to make conflicts impossible, retained refs to preserve pre-squash history, an amend-versus-commit question about how saves accumulate, and a merge algorithm to build.

Each of those was a solution to a problem branching created. The owner's experience running a wiki engine on the same job supplied the alternative: a wiki has no branches, only a single sequence of changes, and for controlled versioning of a document that was enough. What the wiki could not do was mark milestone editions — and that is a tagging problem, not a branching one.

The two requirements that had forced branching were a reviewable unit accumulating several saves over days, and several such units open at once. Both dissolve if the editing session itself is the unit: one person holds the document, edits continuously, and returns it as a single commit.

## Decision

**One editing sequence per document. No branches, no forks from a past point, no merges.**

1. An editor **takes the document** for editing. Nobody else edits it meanwhile.
2. Edits are **captured continuously** — no Save control. The draft persists server-side but is not a commit and is invisible to others.
3. **Undo** operates within the editing session.
4. The editor **returns the document**, producing one commit with an agent-written summary. The editor may consult the companion before committing.
5. Commits land **in sequence**. The reviewer accepts them in runs (DL-0041).
6. Going back is **only ever forward**: an unwanted change is undone by a new commit that reverts it, never by rewriting history.

## Rationale

**The complexity being removed was self-inflicted.** Merge algorithms, conflict detection, conflict-resolution interfaces, branch lifecycle, retained refs and the amend question were all downstream of branching. None of them served a requirement; they served a mechanism.

**"All pending edits right now" becomes a plain read.** With no competing branches, the pending state is the commits since the last accepted revision — attributed, ordered, and readable without any overlay computation. The grievance that motivated the platform is answered by the storage model rather than by a feature.

**The stance model sharpens.** *Pending* is now committed-but-unaccepted; *Accepted* is the last revision a reviewer accepted; *Canonical* is the last approved edition. Three states, each with a commit or a ref behind it.

**Rewriting history was never available anyway.** In a governed document, dropping a commit erases the record that a passage existed and was accepted. Revert-only is not a limitation of the linear model — it is a requirement the branching model would also have had to honour.

## Consequences

- **No merge code, no conflict interface, no branch lifecycle.** The largest block of work in the previous design is deleted.
- **`refs/proposals/{id}/head` is unnecessary.** Nothing is squashed, so nothing needs retaining; ADR-0002's retention consequence lapses.
- **Editing is exclusive per document.** One editor at a time, which serialises contributors. There is no finer-grained exclusivity: section-scoped roles went at DL-0091 and section files at DL-0126. Per-section editing is a raised, undesigned candidate (DL-0159).
- **Stale holds need handling** — visible holder, expiry, forced release by the document editor or tenant administrator, with the released draft preserved rather than discarded. This is the failure mode wikis avoid locking to escape, and it must be designed rather than discovered.
- **Draft durability is now load-bearing.** With no intermediate commits, an editing session is unrecoverable if the draft is lost. It persists server-side for that reason.
- **Undoing one author's contribution is a revert**, computed per sentence from blame, with the platform resolving the case where a later author built on top (`linear-workflow.md`).
- **Disputes are unaffected.** The Statement of Disagreements was always a record holding competing wordings as text, never a branch.
- **Git usage reduces to init, commit, read, diff, blame, revert and tag**, which is what allowed Forgejo to be dropped entirely (DL-0042).

## Where divergence re-enters, and it does

*Added 2026-09-21 after the architecture review's F-06.* The claim above — no merges, therefore no conflicts, therefore no conflict interface — is true of the **history** and not quite true of the product. Two stage 1 features are divergence resolution under another name, and saying so here is cheaper than a future reader discovering it:

- **Per-author undo (ST-0037).** Showing which sentences somebody else has since built on, and asking which wording should survive, is a conflict interface at sentence granularity. It is also the hardest algorithm in stage 1 and is listed as unverified. It is **spiked before the scope agreement keeps promising it** (DL-0108).
- **A draft preserved past a forced release.** It is based on a version that stops being the head as soon as the next editor commits. The rule, decided rather than left open: **a stale draft opens read-only beside the current text** for its editor to copy from. It is never replayed onto moved text, because replaying is the merge this ADR exists to avoid.

Neither invalidates the linear model. Both bound the claim made for it: divergence is confined to these two places and appears nowhere in the history.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| Branching with per-file locking (DL-0037) | | Made conflicts structurally impossible but kept branches, proposals, merges and retained refs to achieve it. Rejected as a large mechanism preserving a model nothing required. |
| Branching with sentence-level concurrency | | Two editors in one section, conflicts resolved by the reviewer. Rejected: it buys simultaneous editing of one section, which nobody asked for, at the price of the entire merge and conflict-resolution surface. |
| A wiki engine | | The linear model comes from wiki practice, but the engines cannot carry a folder of section files with entity metadata, named immutable editions, long-lived drafts another person may edit, per-file approval, or a confidentiality layer. The user experience is borrowed; the engine is not. |

## References

- Originating decision-log entry: the project decision log DL-0039.
- Supersedes DL-0013, DL-0014, DL-0034, DL-0035, DL-0037.
- Restates DL-0028.
- Analysis that produced it: `linear-workflow.md`.
- Amended 2026-09-23 by owner override: the git operation set listed in full (DL-0142), and the section-level escape valve removed, since section-scoped roles no longer exist (DL-0161).

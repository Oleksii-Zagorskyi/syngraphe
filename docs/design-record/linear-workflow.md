---
tags:
  - brief
  - engineering
aliases:
  - Linear workflow proposal
status: adopted
date: 2026-09-20
outcome-note: >
  The analysis behind ADR-0003: a single linear editing sequence per document,
  with no branches and no merges, was adopted. The body is the analysis as
  written on 2026-09-20 and is not edited.
---

# Linear workflow — the owner's proposal, and what adopting it would cost

Working analysis, not a decision. Registered as Q30. Nothing in the Discovery set has been changed against it.

## The proposal

1. An editor **checks out the document** — all files. Nobody else can edit it meanwhile.
2. Edits are **captured continuously**; there is no Save button and nothing is written to a file.
3. **Undo** works within the checkout session, in the browser.
4. The editor **returns the document**, which commits. Optionally in two steps: capture, then consult the assistant, then commit with an AI-generated summary.
5. Another editor then checks out and repeats.
6. Commits land **sequentially**; the reviewer approves each, or edits before approving.
7. **No branching.** No forking from a past point.
8. The reviewer sees each diff with its author.

## What it changes

| Decision | Under the linear model |
|---|---|
| DL-0013 — *send for review* / *approve review* = squash and merge | **Rewritten.** There is no proposal object and no merge. Commit *is* submission; approval marks a revision approved |
| DL-0014 — a proposal covers one document folder | **Retired.** The unit becomes a checkout session |
| DL-0034 — save = commit, `<` `>` steps through saves | **Rewritten.** One commit per checkout session; `<` `>` steps through sessions |
| DL-0035 — send, generated description, amend, cancel | **Simplified.** The generated description survives as the commit summary; amend and cancel disappear with the proposal |
| DL-0037 — per-file locking | **Coarsened** to whole-document checkout |
| DL-0028 — nothing enters the document without approval | **Restated.** Nothing enters the *approved* state without approval; the working state accepts commits immediately |
| ADR-0002 — retained `refs/proposals/{id}/head` | **Unnecessary.** Nothing is squashed, so nothing needs retaining |
| Q29(ii) — amend or commit-per-save | **Dissolved.** One commit per session by construction |
| Q24 — the git boundary | **Moves again.** Git usage reduces to commit, diff, blame, revert and tag. Rent-versus-operate becomes almost purely an operations question |

## What survives unchanged

The per-file approval ledger and section reviewers as code owners (DL-0025) — a commit touching five sections needs those five reviewers. The reviewer's right to edit before approving and the generated rejection record (ADR-0001, DL-0026). The Statement of Disagreements (DL-0009). Comments and their anchors (DL-0027). Heuristics, agent scopes, finding provenance and audience (DL-0021, DL-0031, DL-0032). Editions and canonical approval (DL-0010). The five stances (DL-0033) — they become sharper, not weaker: **Pending is now committed-but-unapproved**, which is exactly the MS Word grievance the platform exists to fix.

## Removing one author's work after later edits — the answer

**Never drop a commit. Always add one that undoes it.** `git revert` creates a new commit inverting an earlier one, leaving the original in history. Rewriting history — rebase, drop, cherry-pick onto a new base — is not available here: it would erase the record that the text existed and was approved, which is the audit promise the product is built on.

The owner's instinct — *"a fresh healing commit"* — is exactly right and is the standard mechanism.

The interesting part is semantic, not mechanical. Because the source is one sentence per line, `git blame` attributes **each sentence** to an author and a revision. So the platform can offer precisely what Word offers, per author, and compute three cases per sentence:

- **Untouched since that author wrote it** — revert is clean and exact.
- **Refined by a later author on top** — a blind revert would also discard the later author's work. The platform must ask: keep the later wording, or return to the text before this author touched it?
- **Already replaced or deleted** — nothing to revert.

That is the whole of "reject all changes by this author", done better than Word, because the reversal is itself an authored, attributed, reviewable act rather than a silent deletion.

## Disputes without branching — the answer

**The Statement of Disagreements was never a branch.** It is a record holding each disputed passage in its competing variants as text (DL-0009), and variants come from history, not from refs. Nothing about it needs branching.

In the linear model a dispute arises two ways:

- **Reviewer against editor** — the reviewer edits before approving; the platform generates a rejection record from the two revisions; the editor escalates it (ADR-0001, DL-0026).
- **Editor against editor** — the second editor changes a passage the first wrote. The first disagrees and opens a dispute on that passage. Both wordings are recoverable by blame, and the entry holds them.

While an entry is open, the document holds the **latest committed wording** and the register holds the competing one. The decider rules; if the earlier wording wins, a new commit restores it. No edition can become canonical with an entry still open (DL-0010).

## Open sub-questions if the model is adopted

- **Checkout granularity.** Whole-document is deterministic: an editor never discovers mid-session that a section they now need is held. Lazy per-file locking never blocks someone who needs an untouched section, but can fail mid-session. *Recommendation: whole-document checkout by default, with an explicit section-only checkout for holders of section-scoped roles; the two are mutually exclusive on the same file.*
- **Draft durability.** "Lives only in the browser" means a closed laptop loses a day's work. *Recommendation: the draft persists server-side as draft state — still not a commit, still invisible to others, but survivable.*
- **Agent run frequency.** The reviewer agent runs per commit rather than per proposal. With one commit per session this is proportionate, but it should be stated rather than assumed.
- **Stale checkouts.** Same problem as stale locks: visible holder, expiry, forced release by the document editor or tenant administrator, and the released draft preserved rather than discarded.

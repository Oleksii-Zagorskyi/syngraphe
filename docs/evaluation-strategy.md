---
tags:
  - evaluation
aliases:
  - Syngraphē evaluation strategy
status: draft
fidelity: fog
date: 2026-09-23
---

# Evaluation strategy

> [!note] Fog — intent, not design
> Written 2026-09-23, while release 0.1 carries no AI. It states what the evaluation of the AI half will have to be, so nothing built in 0.1 closes it off. It sharpens when 0.2 is designed, and none of it is a commitment to a method, a tool or a number yet.

The AI half — the companion and the reviewer agent — is judged the way code is: against cases, with a target, and again after every change.

## Five commitments

1. **A labelled case set, not impression.** Each heuristic in [`review-findings.md`](review-findings.md) is judged on documents whose correct findings are known in advance — including the cases the prompt currently gets wrong, because a set that only passes measures nothing. The documents are invented, like every other test material in this repository.

2. **A named axis.** Precision and recall pull against each other, and a prompt tuned without naming which one it serves is tuned by feel. Each heuristic states its axis. The expected default is precision, because a reviewer reads every finding and trusts the channel less with each wrong one.

3. **A false-positive budget.** An ungrounded finding costs a reviewer more attention than a correct one saves, so a heuristic that surfaces noise is worse than one that stays quiet. Each heuristic will carry a ceiling on wrong findings per document, and the review-findings rule that an ungrounded finding is a suggestion rather than a finding is the first half of that control.

4. **A regression suite over heuristic changes.** Prompt text is versioned (`technical-design.md § Prompts are source`), and every change to it re-runs that heuristic's cases, with dated results kept beside them, so a regression shows as a change rather than being remembered as an impression. Runs record the heuristic version they used, which is what lets a past result be reproduced.

5. **Prompts and cases live side by side at the repository root** — `prompts/` for the text, `evals/` for the cases and results, one directory per heuristic. Neither exists yet. A prompt enters `prompts/` when it has cases to be measured against; before that it is a draft and stays out of this repository.

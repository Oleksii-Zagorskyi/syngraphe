---
tags:
  - evaluation
aliases:
  - Syngraphē evaluation strategy
status: active
fidelity: stable
date: 2026-09-23
last-updated: 2026-11-13
---

# Evaluation strategy

The agents of release 0.2, the AI reader (DL-0558) — the companion and the reviewer agent — are judged the way code is: against cases, with a target, and again after every change. This file states, for each of the eleven heuristics of the first cut (`review-findings.md`, DL-0568, DL-0571), the axis it is measured on, its target, its false-positive budget and its cost, and how the measurement runs. The numbers were set before any prompt was measured (DL-0566); the first cut's claims, when they join the verification plan, are settled against them.

## Five commitments

1. **A labelled case set, not impression.** Each heuristic is judged on invented documents whose correct findings are known in advance — including the cases the prompt currently gets wrong, because a set that only passes measures nothing.
2. **A named axis.** Every heuristic is measured first on **precision**, because a reviewer reads every finding and trusts the channel less with each wrong one (DL-0566).
3. **A false-positive budget.** An ungrounded finding costs a reviewer more attention than a correct one saves. Each heuristic carries a ceiling on wrong findings; a finding whose quote is not in the text is withheld and counted as wrong (DL-0559).
4. **A regression suite over heuristic changes.** Every change to a prompt version — its text, the shared base, its model or its effort — re-runs that heuristic's cases, with dated results kept beside them under the version's hash (DL-0560, DL-0562).
5. **Prompts and cases live side by side at the repository root** — `prompts/` for the text, `evals/` for the cases and results (§ The layout). A prompt version enters `prompts/` only with a passing result — at its target, and with a passing adversarial result under the same hash — and the command that loads the prompts refuses one without either (ADR-0024, DL-0571 (12)).

## The numbers

Set by DL-0566, for every heuristic of the first cut.

| | Value |
|---|---|
| Axis | precision first |
| Target | precision ≥ 0.90 and recall ≥ 0.70 on the heuristic's case set, **in each of three runs** |
| False-positive budget | at most one wrong finding per five case documents, in any run; a reported trap counts as wrong |
| Case set | at least 20 invented documents, at least 5 of them carrying traps, about half Ukrainian and half English |
| Adversarial set | separate, shared by every heuristic, every supported language; **zero** instructions followed (ADR-0022); the load command and CI refuse a prompt version without a passing adversarial result under its hash (DL-0571 (12)) |
| Judge | trusted after agreeing with the owner on ≥ 90% of ≥ 50 findings; then one verdict in five reviewed by the owner; below 90%, every verdict returns to the owner (DL-0563) |
| In production | at most 10% of the analyses of one kind in a month marked *not right* — each companion action, the reviewer agent's analysis and each standing list is a kind of its own; above it, that kind's prompts return to the workbench (DL-0566, DL-0571 (10)) |

## The layout

Set by DL-0570. Prompts are the code, evals the tests and the invented documents their fixtures.

| Path | Holds |
|---|---|
| `prompts/_base/` | the shared base prompt |
| `prompts/_judge/` | the judge's prompt |
| `prompts/<heuristic>/` | one heuristic's prompt and its settings — model and effort |
| `evals/_documents/<case>/` | an invented document and its key, naming each heuristic's planted defects and traps |
| `evals/_adversarial/` | the injection set |
| `evals/<heuristic>/` | a list naming the documents of the heuristic's set, and its dated results under the prompt version's hash |

A document serves several heuristics (DL-0566), so the documents are shared and written once; a heuristic's directory names the documents of its set and keeps no copy of them.

## The case set

- **A case is an invented document and its key**, in `evals/_documents/<case>/` (DL-0570). The key names each planted defect, the heuristic it belongs to and the passages it rests on, and each **trap** — a passage that looks like a defect of that heuristic and is not (DL-0563).
- **A document may serve several heuristics.** Each heuristic is scored on every document of its set, so a document without its defects tests its restraint (DL-0566).
- **The language is what these tests are about**: the documents the agents read are mostly Ukrainian, so every set has Ukrainian and English cases.
- **Every document is invented.** Nothing from a real document enters the repository, as a case or as a key (`CLAUDE.md § The data boundary`).
- **Labelling is paired with the owner**: a key is a judgment about what the product must find, and the owner approves each set before it measures anything.

## How a run is scored

1. Each case runs **three times** on the production code path — prompt assembly, the provider call, the quote check, the sorting (DL-0563). The model answers differently from one run to the next, so a heuristic is at its target only if every run is: the consistency measure agent benchmarks call pass^k, here pass^3.
2. A finding **matches** a planted defect when its verified quotes overlap the key's passages. Matches give recall; findings that match a trap or nothing count against precision until judged.
3. A finding that matches nothing is judged by the **judge** — a prompt of its own, on a stronger model than the one it judges — and by the owner. The owner's verdict stands; a real defect nobody planted joins the key with the owner's approval.
4. The result is written into `evals/<heuristic>/`, dated, under the prompt version's hash (DL-0570), with each run's recall and precision, how far the runs agree, the cost of the run and the judge's agreement with the owner.
5. The prompt version also runs the adversarial set, and its result is dated under the same hash. A version that follows any injected instruction has no passing adversarial result, and neither the load command nor CI accepts it (ADR-0022, DL-0571 (12)).

## Where it runs

The workbench is management commands in the product, on the code path production uses, run on the developer's machine through the development stack (DL-0563). CI never calls a model: on every push it checks that every prompt version in `prompts/` has a committed, passing result under its hash, at its target and on the adversarial set (DL-0571 (12)). Before the platform goes live with a new model version, the evals run again against the model version production will call.

## Cost

Estimates before the spike measures them, on Claude Sonnet 5.5 at the provider's listed prices (ADR-0023): a ten-page document taken as about 10,000 tokens and each call's output, thinking included, as about 3,000 — both to be replaced by measurement. The shared base and the document form a cached prefix, so the second and later heuristics on the same text pay the cached rate for it (ADR-0022).

| Operation, a ten-page document | Calls | Estimate |
|---|---|---|
| One heuristic within the document | 1 | about $0.03 to $0.06, the first call of an operation the most |
| A companion action of four heuristics | 4 | about $0.16 |
| The standing set at an accepted state, all three types assigned | 6 | about $0.22; half through the provider's batch interface (DL-0564) |
| The reviewer agent at *send for review*, all three types assigned | 7 | about $0.25 — the six heuristics within the document and D1 |
| Cross-document heuristics, per neighbour in scope | 4 | about $0.19 |
| A review with three neighbours | 19 | about $0.82 — the reviewer agent's seven calls and four for each of three neighbours; about $1.40 at forty pages with neighbours of the same length |
| One heuristic's eval: 20 cases, three runs | 60 | about $2.40, the judge on top |

Release 0.2 makes no guidance call (DL-0568), so none is costed. Spend is bounded by a monthly cap per organisation, in US dollars, and a limit on companion runs per person per hour (DL-0564, DL-0569). A stored call is reused: there is at most one model call per heuristic per key — its prompt version and the content states of the documents it read (DL-0567).

## The heuristics

Eleven in the first cut, each described in `review-findings.md`; C1 and C3 keep their entries below, marked, and are not among them (DL-0568, DL-0571 (3)). Every one is a model heuristic in release 0.2 (DL-0551, ADR-0022); the numbers above apply to each. The standing lists group six of them, one side-document type per list: *contradictions* — A1, A4, A5; *ambiguities* — A2; *blind spots* — A3, A6 (DL-0567, DL-0571 (3)). The other five belong to no assignable unit: the reviewer agent runs D1, and B1, B2, B3 and B5 for each neighbour in scope, for every document assigned any analysis (DL-0571 (2)).

### A1 — Contradiction between statements
Context: the document alone. Calls per standing set, per review: one each. Its output reaches every reader of the document through the standing lists, so its false-positive budget matters most.

### A2 — Ambiguity
Context: the document alone. A sentence that admits two operative readings; a vague word with no operative second reading is a trap.

### A3 — Gap inside the declared scope
Context: the document alone. Reaches readers as the blind-spot list. Recall is the harder axis; precision still leads.

### A4 — One term, two meanings
Context: the document alone.

### A5 — Circular or self-referential authority
Context: the document alone, read from the prose; marking is not relied on (DL-0559).

### A6 — Unowned obligation, or a right without an accountable role
Context: the document alone, read from the prose. A passive obligation the document assigns elsewhere is a trap.

### B1 — Contradiction with another document
Context: the document and one neighbour of the reviewer's scope per call (DL-0559). Cost grows with each neighbour.

### B2 — Override of a matter another document governs
Context: the document and one neighbour per call. Agreement between the two documents is a trap: B2 is about authority, not contradiction.

### B3 — Broken outbound reference
Context: the document and one neighbour per call.

### B5 — Term collision across the base
Context: the document and one neighbour per call.

### C1 — Guidance conflict
*Not in release 0.2* (DL-0568, backlog B-079): no prompt, no case set and no guidance call until the confidential guidance returns. Its design stands for then. Context: the document and the guidance, in a call of its own; reviewer-eyes-only (DL-0095). Its adversarial cases include attempts to copy the guidance into a finding.

### C3 — Citation of a superseded edition
*Not in release 0.2* (DL-0571 (3), backlog B-081): no prompt and no case set. A call over the document alone cannot tell that a cited edition is superseded; the heuristic waits for a call that is given each mentioned document's current edition number.

### D1 — What the run changes in a role's obligations
Context: the run and its accepted version. Read from the prose wherever the role appears, marked or not (DL-0559).

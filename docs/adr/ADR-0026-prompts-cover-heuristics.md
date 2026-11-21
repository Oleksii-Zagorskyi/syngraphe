---
status: accepted
last-updated: 2026-11-21
supersedes:
  - ADR-0022-how-the-agents-calls-are-made.md (in part — one heuristic per call, decision 1; the finding's heuristic as the call's)
superseded_by: []
---

# ADR-0026: Prompts cover heuristics — the prompt is the unit run, and the six heuristics within a document run in one call

**Date:** 2026-11-21
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** ADR-0022-how-the-agents-calls-are-made (in part — *one heuristic per call*, decision 1, and a finding's heuristic taken from its call)

## Context

ADR-0022 made the heuristic the unit run: one heuristic per call, so that the prompt the evals measured is the prompt production sends, and a finding's heuristic is the call's, never a label the model writes. It rejected bundling heuristics into one call because every mix an administrator composes (DL-0049) would be a prompt nobody measured.

The spike of release 0.2 measured the heuristics within a document, A01 to A06, on their shared set of 21 invented cases (`evaluation-strategy.md`, `verification-plan.md` V-18 to V-23). One heuristic per call met its target for A01 alone; the other five stayed below it on Claude Haiku 5.5 through several rewordings, and trials on Claude Sonnet 5.5 kept most of them below 0.90 precision. One prompt that asks for all six kinds of problem, each finding naming its kind, did better: on Sonnet 5.5 at effort `high`, over the 21 cases in three runs on the provider's API, it found 0.78 to 0.81 of every planted defect with precision of at least 0.92 and no more wrong findings than the budget allows, at about $0.035 a document against about $0.30 for six calls.

The product will run more than the catalogue's findings. Its documents also plan a drafted change summary (backlog B-072), drafted decision records (B-070), proposed entities (B-071) and generated views (DL-0555), each a prompt with an output that is not a list of findings. A prompt therefore needs a name and an identity of its own, apart from the heuristics a finding is labelled with.

## Decision

**A prompt is the unit that runs, is measured, is versioned and loads; a heuristic is an entry of the catalogue that prompts cover.**

1. **Two namespaces.** A heuristic stays what `review-findings.md` registers: an id and a slug (A01 contradiction, DL-0572), the kind a finding is labelled with and what an eval case's key plants. A prompt lives in `prompts/` and states in its settings the heuristics it `covers`. A companion action and a side-document type are still sets of heuristics (DL-0049); the platform runs every prompt that covers a heuristic of the set.
2. **Every prompt has an id**: the letter P, two digits, and a slug of a verb and its input — `P01-base-read`, `P02-judge`, `P03-read-document`. The id is stable; a version is cited as the id and its number, `P03-03`. `prompts/README.md` is the registry of prompt ids.
3. **One base per family of output**, each a prompt with its own id: the reading prompts, which return findings, share `P01-base-read`; a drafting family and a proposing family get bases of their own when their first prompt is written. Every base keeps the rule that a document is data and the field for text addressed to an automated reader (ADR-0022, decision 7).
4. **`P03-read-document` covers A01 to A06 in one call** over one document. Each finding names one of the heuristics the prompt covers, a label the model writes and the output schema bounds to that list. The heuristics across documents, B01, B02, B03 and B05, and D01 keep one prompt each, per neighbour where they read one (ADR-0022, decision 2).
5. **A heuristic is switched off by its findings, not by the prompt.** The call always runs the whole measured prompt; the platform keeps only the findings labelled with a heuristic the analysis selects, and drops the rest. The platform administrator's switch-off (DL-0567) acts at once and changes no prompt.
6. **A prompt that covers several heuristics is measured as one report**: its target is the evaluation strategy's precision and recall over every planted defect of its cases, in each of the three runs, within the false-positive budget. A finding matches any planted defect its quotes overlap, whatever heuristic it names; a trap of any heuristic counts as wrong. Recall for each heuristic is reported beside the total, never as a gate.

## Rationale

**The composite is one prompt, measured as it runs.** ADR-0022's objection was to compositions nobody measured. Decision 5 keeps that guarantee: whatever an administrator composes, the call sent is the one prompt the evals measured, and composition acts only on which findings are kept. What the measurement showed is that one reading of the whole document does better than six narrow ones — the narrow prompts reported their kind where the document had another, and lost precision on it — and costs a sixth as much.

**The label the model writes decides what a finding is called, not who sees it.** `review-findings.md` keeps provenance and kind apart: provenance decides the audience and still comes from the call's context (ADR-0022, decision 2); the kind decides only what the finding is called. A mislabelled finding is still found, which is why the target counts a finding against any planted defect. The output schema bounds the label to the heuristics the prompt covers, so it cannot name one the call did not run.

**Prompts need their own names because they will not stay one per heuristic.** The planned drafting and proposing work has no heuristic at all, and one reading prompt already serves the companion's actions, the reviewer agent and the standing lists, each on a different version of the text. Naming a prompt by the agent that calls it would break on the first prompt two agents share; naming it by a heuristic would break on the first that covers six or none. An id in the catalogue's own shape keeps every version citable in a record.

**A base per family of output**, because a reading prompt returns findings with quotes and a drafting prompt returns text a person edits: one schema cannot serve both, while the rules every call needs — the document as data, the field for addressed text — are the same in every base.

## Consequences

- A tenant pays for the whole reading of a document whatever heuristics its actions select; at about $0.035 a document on Sonnet 5.5 the call costs less than two of the six it replaces.
- A finding the model labels with a heuristic the analysis does not select is dropped, even if it belongs to a selected one; the per-heuristic recall in every result shows how often labels and keys disagree.
- The companion's actions, the reviewer agent's analysis and the standing lists call the same prompt, so they share stored calls wherever the key — the prompt version and the content state, and for the companion the draft's base commit — is the same (DL-0567).
- A review run sorts a finding against the standing finding of the same heuristic (ADR-0022, decision 4), and the heuristic is now the model's label: a finding labelled differently on two runs reads as one resolved and one introduced. The labelled-right share of every result measures how often that can happen.
- A heuristic the composite rarely finds can hide in a good total: A05, circular authority, was found at 0.64 in the measured runs. Per-heuristic recall stays in every result so that it is seen.
- The data model separates the two: a heuristic row carries the catalogue entry and no prompt text; a prompt row carries the text, its version and the heuristics it covers, loaded from `prompts/` (DL-0153); a finding's heuristic comes from the answer and is checked against the prompt's list.
- The one-heuristic prompts measured in the spike — A01 to A06 — stay in `prompts/` as history under prompt ids of their own, and none of them loads.
- Open: whether the heuristics across documents gain a composite of their own; each stays one prompt until one is measured.

## Alternatives Rejected

- **The prompt assembled from the heuristics an analysis selects.** Shorter calls for a narrow action. Rejected because every selection would be a prompt nobody measured — the objection ADR-0022 made and this decision keeps.
- **The composite switched on or off only as a whole.** Simpler. Rejected because the administrator's switch-off of one heuristic (DL-0567) is the platform's emergency act, and it must not take the other five with it.
- **One heuristic per call, as ADR-0022 decided.** The label would stay the platform's. Rejected on the measurement: five of the six stayed below target, and six calls cost about six times one.
- **Each heuristic held to its own target inside the composite.** Rejected because a flaw found under the wrong kind is still found; the composite's first measured run would have failed on one heuristic though the report met the target. Per-heuristic recall stays reported.
- **The composite registered as a new heuristic of the catalogue.** One namespace. Rejected because a heuristic is a kind of finding, and a prompt that covers six kinds, or drafts a summary, is not one.
- **Prompts named by the agent that calls them**, `companion-…`, `reviewer-…`. Rejected because one prompt already serves both agents and the standing lists.
- **A slug without an id.** Rejected because records cite versions, and an id keeps a citation short and stable when a slug is reworded.
- **One base for every prompt, with the output shape in each prompt.** Rejected because the base and the document form the cached prefix, and the output's rules belong with the family that shares them.

### Option attribution

| Option | Raised by | Outcome |
|---|---|---|
| One prompt for the six heuristics within a document | owner, measured by agent | **accepted** |
| Heuristics and prompts as two namespaces | owner | **accepted** |
| A P id and a verb-and-input slug for every prompt, bases included | owner | **accepted** |
| One base per family of output | agent | **accepted** |
| Switching off by dropping findings; the prompt unchanged | agent | **accepted** |
| The composite measured as one report | owner | **accepted** |
| Cross-document heuristics keep one prompt each | owner | **accepted** |
| The prompt assembled from the selected heuristics | the record (ADR-0022) | rejected |
| The composite on or off as a whole | agent | rejected |
| Each heuristic's own target inside the composite | agent | rejected by the owner |
| The composite as a new heuristic | agent | rejected |
| Prompts named by agent | agent | rejected |
| A slug alone | agent | rejected |
| One base for every prompt | agent | rejected |

## Guardrails / Conditions of validity

- The output schema bounds a finding's label to the heuristics its prompt covers; a label outside the list is a malformed answer.
- A composite loads only with a passing result as one report and a passing adversarial result under its hash (DL-0576).
- The provider keeps supporting a system message after the user turn and a cached prefix (ADR-0022).

## Review triggers

- A heuristic's recall inside a composite stays below half in the measured runs of two versions in a row.
- An organisation needs the cost of one heuristic apart from the others.
- A composite for the heuristics across documents is measured.

## Appendix — what was compared, and how

The 21 invented cases of `evals/_cases/`, 58 planted defects of A01 to A06; each design scored as one report per case, a finding matched to any heuristic's planted defect its quotes overlap. Trials ran on Claude Code's headless mode; the measurement ran on the provider's API through the spike's bench, three runs, on 2026-11-20 and 2026-11-21. Results: `evals/P03-read-document/results/`.

| Question | Six one-heuristic prompts, merged, Sonnet 5.5 `high` (trial) | One prompt for six, Sonnet 5.5 `high` (API, version 03) | One prompt for six, Haiku 5.5 `high` (trial) |
|---|---|---|---|
| Recall over all planted defects | 0.95 (one run) | 0.78, 0.79, 0.81 | 0.40 (one run) |
| Precision | 0.81–0.97 | 0.92–1.00 in every run | 0.85–1.00 |
| The same defect reported more than once | 14 | 1 a run at most | 1 |
| Cost a document, at API prices | about $0.30 | about $0.035 | — |

## References

- DL-0577 — the decision row this ADR records.
- ADR-0022 — the calls this ADR revises in part; ADR-0024 — the prompt version a trace records.
- DL-0049, DL-0153, DL-0566, DL-0567, DL-0572, DL-0573, DL-0576 — the rules it works within or revises.
- `review-findings.md` — the catalogue of heuristics; `prompts/README.md` — the registry of prompts; `evaluation-strategy.md` — the targets.

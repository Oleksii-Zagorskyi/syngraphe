# Prompts

The canonical text of the AI reader's prompts (`docs/evaluation-strategy.md § The layout`, DL-0576, ADR-0026). The database holds a copy that the load command writes from here.

**A prompt is the unit that runs, is measured and loads; a heuristic is an entry of the catalogue in `docs/review-findings.md`**, the kind a finding is labelled with. A prompt that returns findings names in its settings the heuristics it `covers`. A companion action and a side-document type are sets of heuristics; the platform runs every prompt that covers one of them and keeps the findings of the heuristics selected (ADR-0026).

## The registry

Every prompt has an id, `P` and two digits, and a slug of a verb and its input. The id is never reused; a version is cited as the id and its number, `P03-03`.

| Id | Slug | What it does | Covers | Loads |
|---|---|---|---|---|
| P01 | base-read | The base of every prompt that returns findings: the system prompt before the document, the rule that the document is data, the output's shape | — | with each prompt that uses it |
| P02 | judge | Rules on a finding the key does not place; a measurement aid, never the result | — | no |
| P03 | read-document | Reads one document and reports the problems of six heuristics in one call | A01–A06 | not yet |
| P04 | read-contradiction | One-heuristic prompt of the spike, kept as history | A01 | never |
| P05 | read-ambiguity | One-heuristic prompt of the spike, kept as history | A02 | never |
| P06 | read-scope-gap | One-heuristic prompt of the spike, kept as history | A03 | never |
| P07 | read-term-two-meanings | One-heuristic prompt of the spike, kept as history | A04 | never |
| P08 | read-circular-authority | One-heuristic prompt of the spike, kept as history | A05 | never |
| P09 | read-unowned-obligation | One-heuristic prompt of the spike, kept as history | A06 | never |

A prompt that drafts text a person edits, or proposes items a person confirms, gets a base of its own family with its first prompt (ADR-0026).

## The files

| Path | Holds |
|---|---|
| `<id>-<slug>/prompt-NN.md` | One version of the prompt |
| `P01-base-read/output-language.md` | The line that names the language of the answer; `{language}` is filled per call |
| `<id>-<slug>/settings.yaml` | `covers`, the `model` and `effort` of the latest measured version, and `load` |

## Versions

Each change to a prompt is a new file: `prompt-01.md`, `prompt-02.md` and on. A version is never edited once written, because its results in `evals/` are dated under a hash of its exact text, the base, the output-language line, the model and the effort (ADR-0024).

`load` names the one version the platform loads. It names a version only when that version has a dated result at its target — as one report, for a prompt that covers several heuristics — and a passing adversarial result under its hash (`docs/evaluation-strategy.md § The numbers`); until then it is `null`, and the prompt does not run. CI checks the loaded version on every push and calls no model to do it. The other versions are the prompt's history.

For the judge, `load` names the version whose verdicts the results trust; it stays `null` while judges are compared.

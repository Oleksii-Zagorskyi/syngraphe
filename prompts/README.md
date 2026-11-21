# Prompts

The canonical text of the AI reader's prompts (`docs/evaluation-strategy.md § The layout`, DL-0570, DL-0576). The database holds a copy that the load command writes from here.

| Path | Holds |
|---|---|
| `_base/prompt-NN.md` | The shared base: the system prompt before the document. It names the delimiter that wraps the document (ADR-0022) |
| `_base/output-language.md` | The line that names the language of the answer; `{language}` is filled per call |
| `_judge/prompt-NN.md` | The judge: it rules on a finding the key does not place. Its verdicts are a measurement aid, never the result |
| `<id>-<slug>/prompt-NN.md` | One heuristic, read after the document. `A01-contradiction` is heuristic A01 of `docs/evaluation-strategy.md § The heuristics` |
| `<folder>/settings.yaml` | `model` and `effort` of the latest measured version, and `load` |

## Versions

Each change to a prompt is a new file: `prompt-01.md`, `prompt-02.md` and on. A version is never edited once written, because its results in `evals/` are dated under a hash of its exact text, the base, the output-language line, the model and the effort (ADR-0024).

`load` names the one version the platform loads. It names a version only when that version has a dated result at its target and a passing adversarial result under its hash (`docs/evaluation-strategy.md § The numbers`); until then it is `null`, and the heuristic does not run. CI checks the loaded version on every push and calls no model to do it. The other versions are the prompt's history.

For the judge, `load` names the version whose verdicts the results trust; it stays `null` while judges are compared.

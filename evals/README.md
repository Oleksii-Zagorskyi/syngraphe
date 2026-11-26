# Evals

The cases and the dated results of the AI reader's prompts (`docs/evaluation-strategy.md § The layout`, DL-0570, DL-0576, ADR-0026). Each prompt's folder here has the name of its folder in `prompts/`. Every case is invented: no real document enters this folder (`CLAUDE.md § The data boundary`).

| Path | Holds |
|---|---|
| `_cases/<case>/document.md` | An invented document, written clean and then planted with defects. Its frontmatter marks it as invented and names its language |
| `_cases/<case>/key.yaml` | What the heuristics must find in that document |
| `_held-out/<case>/` | The held-out set, in the same form, numbered from `case-101`: written without sight of the prompt, never read to tune it; its result decides the target and the load (DL-0579) |
| `progress.md` | Every API result of every prompt in date order — generated from the result folders; not edited by hand |
| `<id>-<slug>/cases.yaml` | The cases of one prompt's set |
| `<id>-<slug>/results/<date>-<model>-<effort>-<hash12>/` | One measurement of one prompt version: the set run three times. `<hash12>` begins the prompt version's hash (`prompts/README.md`) |

## The key

For each heuristic, the key lists:

- **`defects`** — each planted defect, with the `passages` it rests on. A finding whose quotes overlap a defect's passages matches it. `also` names other heuristics whose finding on the same passages is right as well, where one flaw is honestly two kinds.
- **`traps`** — passages that look like that heuristic's defect but are not one, each with `why`. A finding on a trap counts as wrong.

**`residue`** lists flaws that came with the writing and were not planted, each with the heuristic most likely to report it and a `confidence`, from 0 to 1, that it is a real defect of that kind. A finding on residue stays unmatched and waits on a ruling; the residue shows the reviewer what is already known on those lines. A `note` explains a judgment a reader might not share.

**`accepted`** lists flaws found after the key was written and ruled real by the maintainer, each with the heuristic its finding named, the `passages` it quotes, a `note` with the ruling's reason and its `source`, the result and item it was ruled in. A finding on an accepted item counts as correct for precision, never enters recall, and is not sent for a ruling again. It becomes a planted defect only on the maintainer's word, when a careful human reviewer of that kind of document would be expected to catch it and it changes what a reader does. A held-out key's planted defects never change once the set is approved (DL-0581).

## A result

| File | Holds |
|---|---|
| `meta.json` | The prompt version and its parts, the model, the effort, the runs and the cases |
| `result.md`, `result.json` | Recall and precision of each run, with the wrong findings against the budget, the findings that wait on a ruling, the findings withheld because their quote is not in the text, and the cost |
| `calls.json` | Every call's answer, tokens and cost |
| `unmatched.json` | The findings that match no planted defect |
| `triangulation.json` | Where an unmatched finding lands on another heuristic's planted item, the key's verdict: it is wrong for this heuristic |
| `review.md` | The findings the key does not place, each with its quotes, what the key holds on those lines, and the maintainer's verdict |
| `judge*.json` | The verdicts of a judge model on the same findings, for comparison: `judge.json` from `prompts/P02-judge/prompt-01.md` on Opus, `judge-sonnet.json` from the same prompt on Sonnet, `judge-j02.json` from `prompt-02.md` on Sonnet |

The target is precision ≥ 0.90 and recall ≥ 0.70 in each of the three runs; the budget allows at most one wrong finding per five case documents in any run (`docs/evaluation-strategy.md § The numbers`). A prompt that covers several heuristics, `P03-read-document`, is measured as one report per case: a finding matches any planted defect its quotes overlap, whatever heuristic it names, and recall for each heuristic is reported beside the total, not as a gate (ADR-0026). Its result folders hold `meta.json` and `calls.json`; the scores are computed from them. A result that fails is kept: it is the record of why the next version exists.

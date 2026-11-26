# prompts/P03-read-document/prompt-05.md — 2026-11-21

Prompt version `2c8efa5cdf0e8e9625a987c212e5bada52b9db43ff693a12aaad0b6af142334c` · claude-sonnet-5-5 at effort `high` · 21 cases × 3 runs · the development set, scored as one report per case, against the key at commit 0bdd771 2026-11-26

| Run | Recall | Precision | Wrong / budget | Accepted | Trap | Withheld | Unruled | Labelled right | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.814 (48/59) | 0.96–0.96 | 2–2 / 4.2 | 0 | 0 | 0 | 0 | 0.958 | $0.7927 |
| 2 | 0.847 (50/59) | 0.945–0.945 | 3–3 / 4.2 | 2 | 1 | 0 | 0 | 0.96 | $0.6486 |
| 3 | 0.814 (48/59) | 1.0–1.0 | 0–0 / 4.2 | 0 | 0 | 0 | 0 | 0.958 | $0.6681 |

Recall by heuristic, reported beside the total and not a gate:

- run 1: A01 0.91, A02 0.56, A03 0.91, A04 0.88, A05 0.73, A06 0.89
- run 2: A01 1.0, A02 0.67, A03 0.91, A04 0.88, A05 0.73, A06 0.89
- run 3: A01 1.0, A02 0.44, A03 0.82, A04 1.0, A05 0.73, A06 0.89

Precision is a range while findings the key does not place wait on a ruling (`review*.md`); a finding matches any planted defect its quotes overlap, whatever heuristic it names; a trap or a withheld quote counts as wrong.

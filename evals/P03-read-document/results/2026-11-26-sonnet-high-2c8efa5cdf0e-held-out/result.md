# prompts/P03-read-document/prompt-05.md — 2026-11-26

Prompt version `2c8efa5cdf0e8e9625a987c212e5bada52b9db43ff693a12aaad0b6af142334c` · claude-sonnet-5-5 at effort `high` · 22 cases × 3 runs · the held-out set, scored as one report per case, against the key at commit 67f899a 2026-11-21

| Run | Recall | Precision | Wrong / budget | Trap | Withheld | Unruled | Labelled right | Cost |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.783 (47/60) | 0.925–0.925 | 4–4 / 4.4 | 1 | 0 | 0 | 0.936 | $0.9122 |
| 2 | 0.85 (51/60) | 0.981–0.981 | 1–1 / 4.4 | 0 | 0 | 0 | 0.941 | $0.8055 |
| 3 | 0.883 (53/60) | 0.982–0.982 | 1–1 / 4.4 | 0 | 0 | 0 | 0.981 | $0.7574 |

Recall by heuristic, reported beside the total and not a gate:

- run 1: A01 1.0, A02 0.4, A03 1.0, A04 0.6, A05 0.9, A06 0.8
- run 2: A01 1.0, A02 0.8, A03 0.9, A04 0.7, A05 0.8, A06 0.9
- run 3: A01 1.0, A02 0.6, A03 1.0, A04 0.9, A05 0.8, A06 1.0

Precision is a range while findings the key does not place wait on a ruling (`review*.md`); a finding matches any planted defect its quotes overlap, whatever heuristic it names; a trap or a withheld quote counts as wrong.

# prompts/P03-read-document/prompt-05.md — 2026-11-21

Prompt version `2c8efa5cdf0e8e9625a987c212e5bada52b9db43ff693a12aaad0b6af142334c` · claude-sonnet-5-5 at effort `high` · 3 cases × 3 runs · the development set, scored as one report per case, against the key at commit a3291e0 2026-11-21 with uncommitted changes

| Run | Recall | Precision | Wrong / budget | Trap | Withheld | Unruled | Labelled right | Cost |
|---|---|---|---|---|---|---|---|---|
| 1 | 1.0 (9/9) | 0.818–1.0 | 0–2 / 0.6 | 0 | 0 | 2 | 1.0 | $0.0928 |
| 2 | 0.889 (8/9) | 1.0–1.0 | 0–0 / 0.6 | 0 | 0 | 0 | 1.0 | $0.0709 |
| 3 | 1.0 (9/9) | 1.0–1.0 | 0–0 / 0.6 | 0 | 0 | 0 | 1.0 | $0.0903 |

Recall by heuristic, reported beside the total and not a gate:

- run 1: A01 1.0, A02 None, A03 1.0, A04 1.0, A05 1.0, A06 1.0
- run 2: A01 1.0, A02 None, A03 1.0, A04 1.0, A05 0.5, A06 1.0
- run 3: A01 1.0, A02 None, A03 1.0, A04 1.0, A05 1.0, A06 1.0

Precision is a range while findings the key does not place wait on a ruling (`review*.md`); a finding matches any planted defect its quotes overlap, whatever heuristic it names; a trap or a withheld quote counts as wrong.

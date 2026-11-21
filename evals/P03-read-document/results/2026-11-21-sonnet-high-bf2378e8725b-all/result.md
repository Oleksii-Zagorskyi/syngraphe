# prompts/P03-read-document/prompt-03.md — 2026-11-21

Prompt version `bf2378e8725ba9ec3c4d300c9dde98e3738c554544e0b2a012ef4c1becbe35f8` · claude-sonnet-5-5 at effort `high` · 21 cases × 3 runs · the development set, scored as one report per case, against the key at commit a3291e0 2026-11-21 with uncommitted changes

| Run | Recall | Precision | Wrong / budget | Trap | Withheld | Unruled | Labelled right | Cost |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.78 (46/59) | 0.92–0.92 | 4–4 / 4.2 | 0 | 1 | 0 | 0.891 | $0.8063 |
| 2 | 0.78 (46/59) | 0.979–0.979 | 1–1 / 4.2 | 1 | 0 | 0 | 0.891 | $0.6747 |
| 3 | 0.797 (47/59) | 0.979–0.979 | 1–1 / 4.2 | 0 | 0 | 0 | 0.936 | $0.7011 |

Recall by heuristic, reported beside the total and not a gate:

- run 1: A01 0.91, A02 0.67, A03 0.73, A04 0.88, A05 0.64, A06 0.89
- run 2: A01 0.91, A02 0.78, A03 0.73, A04 0.88, A05 0.64, A06 0.78
- run 3: A01 1.0, A02 0.56, A03 0.73, A04 1.0, A05 0.64, A06 0.89

Precision is a range while findings the key does not place wait on a ruling (`review*.md`); a finding matches any planted defect its quotes overlap, whatever heuristic it names; a trap or a withheld quote counts as wrong.

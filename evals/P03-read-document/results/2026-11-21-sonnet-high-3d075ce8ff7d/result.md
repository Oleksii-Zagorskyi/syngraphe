# prompts/P03-read-document/prompt-02.md — 2026-11-21

Prompt version `3d075ce8ff7d15d166201e6c71f378b5345c47ce37b2b36f76024ad5124e6c0e` · claude-sonnet-5-5 at effort `high` · 3 cases × 3 runs · the development set, scored as one report per case, against the key at commit a3291e0 2026-11-21 with uncommitted changes

| Run | Recall | Precision | Wrong / budget | Trap | Withheld | Unruled | Labelled right | Cost |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.778 (7/9) | 1.0–1.0 | 0–0 / 0.6 | 0 | 0 | 0 | 0.857 | $0.1016 |
| 2 | 0.889 (8/9) | 0.667–1.0 | 0–4 / 0.6 | 0 | 0 | 4 | 0.875 | $0.0936 |
| 3 | 0.778 (7/9) | 0.875–1.0 | 0–1 / 0.6 | 0 | 0 | 1 | 0.857 | $0.0763 |

Recall by heuristic, reported beside the total and not a gate:

- run 1: A01 1.0, A02 None, A03 1.0, A04 1.0, A05 0.5, A06 0.5
- run 2: A01 1.0, A02 None, A03 1.0, A04 1.0, A05 1.0, A06 0.5
- run 3: A01 1.0, A02 None, A03 1.0, A04 0.5, A05 1.0, A06 0.5

Precision is a range while findings the key does not place wait on a ruling (`review*.md`); a finding matches any planted defect its quotes overlap, whatever heuristic it names; a trap or a withheld quote counts as wrong.

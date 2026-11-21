# prompts/P03-read-document/prompt-03.md — 2026-11-21

Prompt version `bf2378e8725ba9ec3c4d300c9dde98e3738c554544e0b2a012ef4c1becbe35f8` · claude-sonnet-5-5 at effort `high` · 3 cases × 3 runs · the development set, scored as one report per case, against the key at commit a3291e0 2026-11-21 with uncommitted changes

| Run | Recall | Precision | Wrong / budget | Trap | Withheld | Unruled | Labelled right | Cost |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.889 (8/9) | 1.0–1.0 | 0–0 / 0.6 | 0 | 0 | 0 | 0.875 | $0.1068 |
| 2 | 0.889 (8/9) | 0.889–1.0 | 0–1 / 0.6 | 0 | 0 | 1 | 0.875 | $0.0873 |
| 3 | 0.889 (8/9) | 0.889–1.0 | 0–1 / 0.6 | 0 | 0 | 1 | 0.875 | $0.0963 |

Recall by heuristic, reported beside the total and not a gate:

- run 1: A01 1.0, A02 None, A03 1.0, A04 1.0, A05 0.5, A06 1.0
- run 2: A01 1.0, A02 None, A03 1.0, A04 1.0, A05 0.5, A06 1.0
- run 3: A01 1.0, A02 None, A03 1.0, A04 1.0, A05 0.5, A06 1.0

Precision is a range while findings the key does not place wait on a ruling (`review*.md`); a finding matches any planted defect its quotes overlap, whatever heuristic it names; a trap or a withheld quote counts as wrong.

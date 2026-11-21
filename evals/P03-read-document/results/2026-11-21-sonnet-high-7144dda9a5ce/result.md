# prompts/P03-read-document/prompt-04.md — 2026-11-21

Prompt version `7144dda9a5ce61ea3a8bdd1d69e84ba6fe7793bd80caed86f339689d8bde76c0` · claude-sonnet-5-5 at effort `high` · 3 cases × 3 runs · the development set, scored as one report per case, against the key at commit a3291e0 2026-11-21 with uncommitted changes

| Run | Recall | Precision | Wrong / budget | Trap | Withheld | Unruled | Labelled right | Cost |
|---|---|---|---|---|---|---|---|---|
| 1 | 0.778 (7/9) | 0.875–0.875 | 1–1 / 0.6 | 0 | 1 | 0 | 1.0 | $0.1241 |
| 2 | 0.889 (8/9) | 1.0–1.0 | 0–0 / 0.6 | 0 | 0 | 0 | 1.0 | $0.0951 |
| 3 | 0.778 (7/9) | 0.875–0.875 | 1–1 / 0.6 | 0 | 1 | 0 | 1.0 | $0.0806 |

Recall by heuristic, reported beside the total and not a gate:

- run 1: A01 1.0, A02 None, A03 1.0, A04 1.0, A05 0.5, A06 0.5
- run 2: A01 1.0, A02 None, A03 1.0, A04 1.0, A05 1.0, A06 0.5
- run 3: A01 0.5, A02 None, A03 1.0, A04 1.0, A05 1.0, A06 0.5

Precision is a range while findings the key does not place wait on a ruling (`review*.md`); a finding matches any planted defect its quotes overlap, whatever heuristic it names; a trap or a withheld quote counts as wrong.

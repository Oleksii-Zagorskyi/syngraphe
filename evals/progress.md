# The prompts' progression

Every measurement of every prompt on the provider's API, in date order, rebuilt from the result folders under each prompt's directory here. Target: precision ≥ 0.90 and recall ≥ 0.70 in each of three runs, at most one wrong finding per five case documents (`docs/evaluation-strategy.md § The numbers`). A range is open while findings the key does not place wait on a ruling. `P03` is scored as one report per case against the key as it stands now (ADR-0026); a one-heuristic prompt keeps the scores its result was written with. This file is generated: do not edit it by hand.

## `P03-read-document`

| Date | Version | Model, effort | Cases | Recall, each run | Precision, each run | Wrong / budget | Traps | Withheld | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-21 | `P03-02` | sonnet-5-5 `high` | 3 | 0.78 · 0.89 · 0.78 | 1.00 · 0.67–1.00 · 0.88–1.00 | 0 · 0–4 · 0–1 / 0.6 | 0 · 0 · 0 | 0 · 0 · 0 | $0.27 |
| 2026-11-21 | `P03-03` | sonnet-5-5 `high` | 3 | 0.89 · 0.89 · 0.89 | 1.00 · 0.89–1.00 · 0.89–1.00 | 0 · 0–1 · 0–1 / 0.6 | 0 · 0 · 0 | 0 · 0 · 0 | $0.29 |
| 2026-11-21 | `P03-03` | sonnet-5-5 `high` | 21 | 0.78 · 0.78 · 0.80 | 0.92 · 0.98 · 0.98 | 4 · 1 · 1 / 4.2 | 0 · 1 · 0 | 1 · 0 · 0 | $2.18 |
| 2026-11-21 | `P03-04` | sonnet-5-5 `high` | 3 | 0.78 · 0.89 · 0.78 | 0.88 · 1.00 · 0.88 | 1 · 0 · 1 / 0.6 | 0 · 0 · 0 | 1 · 0 · 1 | $0.30 |
| 2026-11-21 | `P03-05` | sonnet-5-5 `high` | 3 | 1.00 · 0.89 · 1.00 | 0.91 · 1.00 · 1.00 | 1 · 0 · 0 / 0.6 | 0 · 0 · 0 | 0 · 0 · 0 | $0.25 |
| 2026-11-21 | `P03-05` | sonnet-5-5 `high` | 21 | 0.81 · 0.85 · 0.81 | 0.96 · 0.94 · 1.00 | 2 · 3 · 0 / 4.2 | 0 · 1 · 0 | 0 · 0 · 0 | $2.11 |
| 2026-11-26 | `P03-05` · **held-out** | sonnet-5-5 `high` | 22 | 0.78 · 0.84 · 0.86 | 0.93 · 0.98 · 0.98 | 4 · 1 · 1 / 4.4 | 1 · 0 · 0 | 0 · 0 · 0 | $2.48 |

## `P04-read-contradiction`

| Date | Version | Model, effort | Cases | Recall, each run | Precision, each run | Wrong / budget | Traps | Withheld | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-18 | `P04-02` | sonnet-5-5 `medium` | 1 | 1.00 · 1.00 · 1.00 | 0.33 · 1.00 · 0.33 | 2 · 0 · 2 / 0.2 | 0 · 0 · 0 | 0 · 0 · 0 | $0.10 |
| 2026-11-18 | `P04-02` | haiku-5-5 `medium` | 1 | 1.00 · 1.00 · 1.00 | 1.00 · 1.00 · 1.00 | 0 · 0 · 0 / 0.2 | 0 · 0 · 0 | 0 · 0 · 0 | $0.00 |
| 2026-11-18 | `P04-02` | haiku-5-5 `medium` | 21 | 0.90 · 0.90 · 1.00 | 0.64–0.71 · 0.83 · 0.73 | 4–5 · 2 · 4 / 4.2 | 0 · 0 · 0 | 0 · 0 · 0 | $0.38 |
| 2026-11-18 | `P04-03` | haiku-5-5 `medium` | 21 | 0.82 · 0.82 · 0.91 | 0.75 · 0.75 · 0.77 | 3 · 3 · 3 / 4.2 | 0 · 0 · 0 | 0 · 0 · 0 | $0.33 |
| 2026-11-18 | `P04-03` | haiku-5-5 `high` | 21 | 1.00 · 1.00 · 0.91 | 0.92 · 0.92 · 0.91 | 1 · 1 · 1 / 4.2 | 0 · 0 · 0 | 0 · 0 · 0 | $0.24 |

## `P05-read-ambiguity`

| Date | Version | Model, effort | Cases | Recall, each run | Precision, each run | Wrong / budget | Traps | Withheld | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-18 | `P05-02` | haiku-5-5 `high` | 21 | 1.00 · 0.86 · 1.00 | 0.34 · 0.23 · 0.31 | 23 · 24 · 22 / 4.2 | 0 · 2 · 0 | 0 · 0 · 0 | $1.96 |
| 2026-11-20 | `P05-03` | haiku-5-5 `high` | 21 | 0.56 · 0.67 · 0.89 | 0.22–0.61 · 0.27–0.64 · 0.38–0.62 | 9–18 · 8–16 · 8–13 / 4.2 | 1 · 1 · 1 | 0 · 0 · 0 | $0.65 |

## `P06-read-scope-gap`

| Date | Version | Model, effort | Cases | Recall, each run | Precision, each run | Wrong / budget | Traps | Withheld | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-18 | `P06-02` | haiku-5-5 `high` | 21 | 0.90 · 0.80 · 1.00 | 0.51 · 0.49 · 0.50 | 17 · 18 · 16 / 4.2 | 0 · 1 · 2 | 0 · 0 · 0 | $1.75 |
| 2026-11-20 | `P06-03` | haiku-5-5 `high` | 21 | 1.00 · 1.00 · 1.00 | 0.37–0.63 · 0.29–0.54 · 0.30–0.58 | 10–17 · 16–25 · 14–23 / 4.2 | 1 · 2 · 2 | 0 · 0 · 0 | $0.54 |

## `P07-read-term-two-meanings`

| Date | Version | Model, effort | Cases | Recall, each run | Precision, each run | Wrong / budget | Traps | Withheld | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-18 | `P07-01` | haiku-5-5 `high` | 21 | 0.88 · 1.00 · 0.88 | 0.64 · 0.73 · 0.78 | 4 · 3 · 2 / 4.2 | 0 · 0 · 0 | 0 · 0 · 0 | $0.31 |
| 2026-11-20 | `P07-02` | haiku-5-5 `high` | 21 | 1.00 · 1.00 · 1.00 | 0.80–0.90 · 0.89 · 0.80 | 1–2 · 1 · 2 / 4.2 | 0 · 0 · 0 | 0 · 1 · 1 | $0.12 |

## `P08-read-circular-authority`

| Date | Version | Model, effort | Cases | Recall, each run | Precision, each run | Wrong / budget | Traps | Withheld | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-18 | `P08-01` | haiku-5-5 `high` | 21 | 0.62 · 0.75 · 0.38 | 0.50 · 0.64 · 0.78 | 5 · 5 · 2 / 4.2 | 2 · 0 · 0 | 1 · 0 · 0 | $0.46 |
| 2026-11-20 | `P08-02` | haiku-5-5 `high` | 21 | 0.91 · 0.64 · 1.00 | 0.67 · 0.50–0.64 · 0.69–0.81 | 5 · 5–7 · 3–5 / 4.2 | 0 · 0 · 0 | 0 · 0 · 0 | $0.15 |

## `P09-read-unowned-obligation`

| Date | Version | Model, effort | Cases | Recall, each run | Precision, each run | Wrong / budget | Traps | Withheld | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-18 | `P09-01` | haiku-5-5 `high` | 21 | 1.00 · 1.00 · 1.00 | 0.82 · 0.75 · 0.69 | 2 · 3 · 4 / 4.2 | 0 · 0 · 0 | 0 · 0 · 0 | $0.32 |
| 2026-11-20 | `P09-02` | haiku-5-5 `high` | 21 | 1.00 · 1.00 · 1.00 | 0.75 · 1.00 · 0.69–0.77 | 3 · 0 · 3–4 / 4.2 | 1 · 0 · 0 | 0 · 0 · 0 | $0.11 |

---
tags:
  - index
aliases:
  - Design record
---

# Design record

How this design was arrived at. The specifications are in [`docs/`](../); these are the arguments that produced them, including the ones that lost.

| File | What it is |
|---|---|
| [`decision-log.md`](decision-log.md) | Every decision, with its rationale and what it touched. Newest first. Superseded rows stay, marked as such |
| [`architecture-review-report-01.md`](architecture-review-report-01.md) | A review of the design set by a session with no authoring context, ranked by consequence |
| [`architecture-review-report-02.md`](architecture-review-report-02.md) | The same reviewer reading the repairs, by diff |
| [`architecture-review-report-03.md`](architecture-review-report-03.md) | A second full review before the design review, after the reservation, the editor, the Git library and the pages were settled; findings continue the series |
| [`architecture-review-report-04.md`](architecture-review-report-04.md) | The same reviewer reading the repairs to report 03, by diff |
| [`linear-workflow.md`](linear-workflow.md) | The analysis that settled a single linear edit sequence over branching |
| [`markdown-vs-latex.md`](markdown-vs-latex.md) | The analysis that settled the storage format |
| [`concept.md`](concept.md) | The original pitch, unedited. Most of what it describes was abandoned; the decision log says when and why |

## How the record is kept

In the ADRs' alternatives tables, *Raised by* names who proposed each option: the maintainer, or the coding agent that worked on the design with the maintainer.

`scripts/check_record.py` checks the record's consistency, and CI runs it on every push. Its `log` check reads every decision log here and the ADRs' frontmatter: a decision that supersedes another decision, or an ADR, passes only when the superseded one's status names it.

## References that point outside this repository

A decision's *Impact* column may name a file that is not here; gates appear as `G1`–`G4`. Planning and working notes are not published, so these are deliberate rather than broken. Decision ids that carry a second number, `DL-10-001`, were decided on a branch built beside another; the log's own header explains them.

The first two review reports were renamed when the third was added: `architecture-review.md` is now `architecture-review-report-01.md`, and `architecture-review-second-pass.md` is `architecture-review-report-02.md`. Older rows cite them by their first names.

Decision ids are not contiguous for the same reason. The rows that remain are unedited and keep their original numbers, so every citation from `docs/` resolves.

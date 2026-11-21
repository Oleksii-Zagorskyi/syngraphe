# Unmatched findings of A06 — unowned-obligation — the verdicts

**What was tested.** Each finding below came from heuristic A06, prompt `prompts/P09-read-unowned-obligation/prompt-01.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — a contradiction, an ambiguity, a gap, a term with two meanings, circular authority.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.
Notes marked *Second reviewer* hold the verdict of an independent model review, accepted by the maintainer; the word in brackets is that review's confidence.

**Status.** 2 of 2 items ruled.

<details><summary>The instruction A06 obeyed (<code>prompts/P09-read-unowned-obligation/prompt-01.md</code>)</summary>

Find each obligation that has no role, and each right that no role answers for.
Report each one as a separate finding.

An obligation is an action that the document requires.
A right is a permission that the document gives to a role.

Read the document as the reader who obeys it.
This reader knows only the text of the document.
For each obligation, find the role that does it.
Look in the sentence, then in the whole document.
Look also in each list of duties, each section about responsibility and each rule that gives tasks to a role.

Find these causes:

- The document requires an action, and no passage gives the action to a role. The sentence often has the passive voice or no person, for example "Records are kept".
- A step receives a thing, for example a document, a notice or a decision, and no passage tells which role sends it.
- A right lets a role not do, delay or change a required action. No passage makes the role tell, explain, record or end its use.

Do not report these:

- A passive sentence, if a different passage gives its action to a role.
- An action whose role is clear from the sentence or from the step before it.
- A role that the document names with a general word, for example "the employee" or "the requester", if the reader knows who it is.
- A right to ask, to propose or to get information.
- A case that the document does not cover. That is a gap, a different kind of problem.
- A role that approves its own act. That is a different kind of problem.

Quote the passage of the obligation or the right.
In the explanation, write where you looked for the role, and what does not occur if no role acts.

</details>

## U-02 — case-017-en-annual-leave, runs 1, 2, 3 (also U-05, U-09)

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**Title.** Leave deduction obligation has no responsible role

**Explanation.** The sentence requires that leave days be deducted for each day of absence, but it is written in the passive and names no role. I checked the Approval, Requesting, Entitlement and Carry-over sections and the list of Head of People and Payroll Officer duties, and none gives the deduction to a role. If no role acts, the leave register would not reflect absences, so the balance used to approve later requests would be wrong.

**Quotes, in their lines:**

- line 27, § Entitlement and counting: «One leave day is deducted for each leave day of absence, and half a leave day for an absence of half of the contracted hours of that day.»

**What the key holds on these lines:**

- `R-7`, residue the case set accepted: The term is defined as a kind of calendar day and is then used as a unit of entitlement (which can be a half and can be below zero). The last line uses both senses in one sentence. No reader acts differently because of it, so I would not key it; a model may report it.

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: The deduction sentence defines how leave is counted. The remaining-entitlement definition incorporates taken and approved days without requiring a separate register transaction. (medium)

## U-03 — case-005-en-spending-authority, run 2

Document: *Spending Approval Matrix* — `evals/_cases/case-005-en-spending-authority/document.md`

**Title.** The earlier approved request is replaced, but no role is told to withdraw or cancel it.

**Explanation.** The document says the new request replaces the earlier one, both after an amount rise and when a split purchase is found. It never says which role withdraws or cancels the earlier approval, or records the replacement. I checked the duties of the requester, the approver, the finance director and the absence rules, and none covers this step. Without such a role, the earlier approval could still allow the Organisation to commit money after it has been replaced.

**Quotes, in their lines:**

- line 52, § 6. Duties of the requester and the approver: «Where the amount rises after approval, the requester raises a new spending request for the full new amount, and it replaces the earlier one.»
- line 60, § 7. No splitting of a purchase: «That spending request replaces every earlier spending request for the same purchase.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: The new request supersedes the old one under the rule itself. No separate cancellation step is required, and the requester owns submission. (high)

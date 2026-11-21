# Unmatched findings of A06 — unowned-obligation — the verdicts

**What was tested.** Each finding below came from heuristic A06, prompt `prompts/P09-read-unowned-obligation/prompt-02.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — a contradiction, an ambiguity, a gap, a term with two meanings, circular authority.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.

**Status.** 0 of 1 items ruled.

<details><summary>The instruction A06 obeyed (<code>prompts/P09-read-unowned-obligation/prompt-02.md</code>)</summary>

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
- A rule that tells how a value is counted or calculated, for example a balance of leave days. It is not an action.
- A result that the rule itself makes, for example a new request that replaces an earlier request.
- Two readings of who does an action. That is an ambiguity, a different kind of problem.
- A case that the document does not cover. That is a gap, a different kind of problem.
- A role that approves its own act. That is a different kind of problem.

Quote the passage of the obligation or the right.
In the explanation, write where you looked for the role, and what does not occur if no role acts.

</details>

## U-06 — case-019-en-vehicles, run 3

Document: *Policy on the Use of Company Vehicles* — `evals/_cases/case-019-en-vehicles/document.md`

**Title.** No role is given the duty to provide the fuel cards.

**Explanation.** Section 6 states that each vehicle carries a fuel card and that the driver pays with it, but no passage says who supplies or maintains these cards. Section 2 lists the Fleet Manager's arrangements (registration, insurance, inspection, servicing, repair) and fuel cards are not among them. Without a named role, a vehicle may have no card for the driver to use.

**Quotes, in their lines:**

- line 42, § 6. Fuel and costs: «Each vehicle carries a fuel card, and the driver pays for fuel with that card.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

# Unmatched findings of A01 — contradiction — the verdicts

**What was tested.** Each finding below came from heuristic A01, prompt `prompts/A01-contradiction/prompt-03.md` on claude-haiku-5-5 at effort `medium`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — an ambiguity, a gap, a term with two meanings, circular authority, an unowned obligation.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.

**Status.** 1 of 1 items ruled.

<details><summary>The instruction A01 obeyed (<code>prompts/A01-contradiction/prompt-03.md</code>)</summary>

Find each contradiction in the document.
Report each contradiction as a separate finding.

A contradiction is two passages that cannot both be true under any reading.
A reader who obeys one passage breaks the other passage.

Read the document as the reader who obeys it.
This reader knows only the text of the document.
Compare the passages that apply to the same case.
The same case has the same person, action, time or amount.

Find these causes:

- Two passages give two different values for the same thing: an amount, a limit, a time limit, a number or a date.
- One passage permits or requires an action, and a different passage forbids the same action in the same case.
- Two passages each give a task or a decision to a different role, and each passage says that only that role does it.
- The document sets a rule or a definition, and a different passage of the same document does not obey it.

Before you report, look for a reading that makes the two passages true together.
Read the whole document for this reading.
If you find such a reading, do not report the two passages.

Do not report these:

- A general rule and an exception, if the document marks the exception, for example with "except", "instead" or "unless".
- A general rule and a narrower rule for a special case, also with no mark. The narrower rule applies to its case, and the general rule applies to the other cases.
- Two limits of the same kind, if the reader obeys both limits when they obey the stricter limit.
- Two passages about different cases, different times, different persons or different places.
- Two steps in a sequence, if a later step changes the result of an earlier step and the document gives the sequence.
- Two rules for the same case that a reading can make true together. That is an ambiguity, a different kind of problem.
- One term that the document uses with two meanings. That is a different kind of problem.
- A case that the scope of the document includes and that no rule of the document handles. That is a gap, a different kind of problem.

Quote the two passages.
In the explanation, write the case in which the two passages apply, and why the reader cannot obey both.

</details>

## U-05 — case-007-en-office-closing, run 2

Document: *Office Closing Checklist* — `evals/_cases/case-007-en-office-closing/document.md`

**Title.** Closing log must be written after the key safe is locked, but the log is kept inside that safe

**Explanation.** The keys step tells the closing person to put the key in the key safe and scramble the code dial, which locks the safe. The last step then requires writing in the closing log, which the document says is kept in that same key safe. The steps are given in order, so the reader must write in a log they have just locked away, and the document does not say how to reach it.

**Quotes, in their lines:**

- line 37, § Closing steps: «Keys: the closing person puts the office key in the key safe beside the main door and scrambles the code dial.»
- line 38, § Closing steps: «Closing log: the closing person writes the date, the time of closing and their own role in the closing log, which is kept in the key safe, and signs the entry.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: The order written scrambles the dial before the closing log step, the log is kept in the key safe, and no step secures the safe again.
- `R-6`, residue the case set accepted: The document uses "the office" and "the building" and does not say if they are one place, so one reader sends the message before the alarm step (or inside the 60 seconds after a remote set) and another sends it at the key safe after locking the main door; the readings differ in sequence.

Verdict: not a defect

Note: The checklist establishes three relevant requirements:
1. Closing steps must be performed in the order written.
2. The closing person must put the office key into the key safe and scramble its code dial.
3. Only afterward must the closing person write and sign an entry in the closing log, which is kept inside that same safe.
These requirements are not logically contradictory.

The closing person could theoretically reopen the safe, retrieve the log, complete the entry, and return the log to the safe.

Nothing explicitly prohibits reopening the safe.

However, this interpretation reveals a genuine procedural omission: the checklist never instructs the closing person to reopen the safe, nor does it explicitly require securing the safe again after completing the log entry.

Statement "The requirements cannot both be fulfilled" is incorrect if interpreted as a strict contradiction. Both actions can be performed sequentially by reopening the safe. But anyway, the document gap is obvious and it is correctly caught. Not sure, if this gap is about A1 heuristic or not.

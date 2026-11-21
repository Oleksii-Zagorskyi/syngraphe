# Unmatched findings of A01 — contradiction — the verdicts

**What was tested.** Each finding below came from heuristic A01, prompt `prompts/A01-contradiction/prompt-02.md` on claude-haiku-5-5 at effort `medium`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — an ambiguity, a gap, a term with two meanings, circular authority, an unowned obligation.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.

**Status.** No finding needs a ruling: the key places every unmatched finding of this result.

<details><summary>The instruction A01 obeyed (<code>prompts/A01-contradiction/prompt-02.md</code>)</summary>

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

Quote the two passages.
In the explanation, write the case in which the two passages apply, and why the reader cannot obey both.

</details>

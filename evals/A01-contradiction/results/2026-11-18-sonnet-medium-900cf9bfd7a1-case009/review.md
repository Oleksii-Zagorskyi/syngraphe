# Unmatched findings of A01 — contradiction — the verdicts

**What was tested.** Each finding below came from heuristic A01, prompt `prompts/A01-contradiction/prompt-02.md` on claude-sonnet-5-5 at effort `medium`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — an ambiguity, a gap, a term with two meanings, circular authority, an unowned obligation.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.

**Status.** 4 of 4 items ruled.

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

## U-01 — case-009-en-gifts, run 1

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Declaration duty contradicts the rule on who decides exceptions and records

**Explanation.** Section 7.5 says the Compliance Officer approves or refuses requests, but then says "the role that decides the request" records the decision. This is not a clear contradiction on its own, but 7.1 says the Chief Executive decides in place of the Compliance Officer for the Officer's own gifts. Not a contradiction; see the other findings.

**Quotes, in their lines:**

- line 41, § 7.5 Exceptions: «The role that decides the request records the decision in the Gifts and Hospitality Register on the same day.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: trap

Note: There is no contradiction. These provisions are logically consistent because Section 7.1 explicitly authorizes the Chief Executive to perform the Compliance Officer's functions in the specified circumstances.

## U-02 — case-009-en-gifts, run 1

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Register is kept by the Compliance Officer but employees declare in it, and time limits for a wrongly received gift differ

**Explanation.** Section 7.6 requires an employee who learns that a received gift was above the limit to hand it over and declare it within two working days. Section 7.4 gives five working days to declare every accepted gift. For the same received gift above the limit, the deadline to declare is two days in one passage and five in the other. Obeying the five-day rule breaks the two-day rule.

**Quotes, in their lines:**

- line 33, § 7.4 Declaration: «The employee makes the declaration within five working days of the acceptance or the giving.»
- line 46, § 7.6 A gift or hospitality above the limit: «the employee hands it, unused, to the Compliance Officer and declares it, both within two working days of learning that it is such a gift.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: trap

Note: The key distinction is that they establish deadlines relative to different events:
1. General rule: Declaration within five working days of accepting or giving the gift.
2. Special rule: Declaration within two working days of learning that the gift exceeds the limit or is a money gift.

## U-03 — case-009-en-gifts, run 3

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Declaration of all gifts versus no declaration of refused offers, and declaration timing for over-limit items

**Explanation.** Section 7.4 says an employee declares every gift and all hospitality accepted or given within five working days. Section 7.6 requires an employee to declare a gift above the limit within two working days, and an after-the-fact discovery within ten working days. For the same gift, the declaration deadline is five, two or ten days, so the reader cannot obey all of them.

**Quotes, in their lines:**

- line 33, § 7.4 Declaration: «The employee makes the declaration within five working days of the acceptance or the giving.»
- line 46, § 7.6 A gift or hospitality above the limit: «the employee hands it, unused, to the Compliance Officer and declares it, both within two working days of learning that it is such a gift.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: trap

Note: Overlapping deadlines, not a contradiction.
The claim that "the reader cannot obey all of them" is incorrect. An employee can comply with multiple deadlines simultaneously, and later discoveries can require additional actions.
The document does not explicitly say that the ten-day requirement concerns updating an existing declaration. Nevertheless, the phrase "records it in the declaration" is compatible with that interpretation.
Similarly, the two-day deadline can simply impose a stricter requirement for a particular category of gifts.
There is no logical principle requiring every obligation concerning the same gift to have the same deadline.

## U-04 — case-009-en-gifts, run 3

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Who records the exception decision differs

**Explanation.** Section 7.5 says the Compliance Officer decides the request. The next passage says 'the role that decides' records it. This is consistent with the Compliance Officer, but Section 7.1 gives the decision to the Chief Executive when the Compliance Officer is the one offered the gift. This is an apparent conflict only, so it is not reported as a contradiction.

**Quotes, in their lines:**

- line 41, § 7.5 Exceptions: «The role that decides the request records the decision in the Gifts and Hospitality Register on the same day.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: trap

Note: There is no contradiction. These provisions are logically consistent because Section 7.1 explicitly authorizes the Chief Executive to perform the Compliance Officer's functions in the specified circumstances.

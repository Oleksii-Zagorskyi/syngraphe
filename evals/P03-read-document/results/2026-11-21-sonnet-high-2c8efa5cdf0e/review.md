# Findings the key does not place — the verdicts

**What was tested.** One prompt that reports the problems of six heuristics, A01 to A06, in one call. Each finding below names its heuristic; the key places it on no planted defect and no trap.

**What a verdict means.**

- `real defect` — the document has the problem the finding states, of one of the six kinds; the maintainer decides whether it joins the key.
- `trap` — the passages look like such a problem, but the document resolves it.
- `not a defect` — the document does not have the problem the finding states, of any of the six kinds.

Line numbers count from the first line after the case document's frontmatter.

**Status.** 0 of 2 items ruled.

## U-01 — run 1, case-009-en-gifts, lines 41-41

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**A06 — No role named to record the decision**

The register is recorded by 'the role that decides the request', which is not named; it is the Compliance Officer, but the wording is indirect and, when the Chief Executive stands in, it is unclear who records. Also the register keeper and the recorder are not tied together.

Quotes, in their lines:

- line 41, § 7.5 Exceptions: «The role that decides the request records the decision in the Gifts and Hospitality Register on the same day.»

What the key holds on these lines:

- nothing

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Line 39 names the Compliance Officer as decider, line 8 names the Chief Executive as stand-in, and line 41 assigns recording to whoever decides.

## U-02 — run 1, case-009-en-gifts, lines 46-46

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**A03 — No rule for hospitality given above the limit when discovered later, or for received hospitality above the limit at the time**

Section 7.6 handles gifts received above the limit by handing them over. It has no handling for hospitality received above the limit when the employee knows it at the time, and it does not say what happens with gifts given above the limit that the employee knows of. Only the case 'learns after the occasion' is covered for hospitality and given gifts.

Quotes, in their lines:

- line 46, § 7.6 A gift or hospitality above the limit: «When an employee has received, without an approved exception, a gift above the gift limit or a money gift, the employee hands it, unused, to the Compliance Officer and declares it, both within two working days of learning that it is such a gift.»

What the key holds on these lines:

- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Section 7.6 covers hospitality discovered over-limit afterwards and omits corrective action for unauthorized hospitality received or gifts given when the employee already knows their value.

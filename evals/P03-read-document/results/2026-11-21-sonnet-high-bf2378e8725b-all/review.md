# Findings the key does not place — the verdicts

**What was tested.** One prompt that reports the problems of six heuristics, A01 to A06, in one call. Each finding below names its heuristic; the key places it on no planted defect and no trap.

**What a verdict means.**

- `real defect` — the document has the problem the finding states, of one of the six kinds; the maintainer decides whether it joins the key.
- `trap` — the passages look like such a problem, but the document resolves it.
- `not a defect` — the document does not have the problem the finding states, of any of the six kinds.

Line numbers count from the first line after the case document's frontmatter.

**Status.** 5 of 5 items ruled.

## U-01 — run 1, case-001-en-travel-expenses, lines 31-31

Document: *Travel expenses* — `evals/_cases/case-001-en-travel-expenses/document.md`

**A03 — No rule for a claim when a receipt is missing or for the person who decides the claim**

The claim must include a receipt for each cost except meals, but no rule handles a lost receipt. Also, the document does not say who checks the claim against approval, only that the finance department pays it.

Quotes, in their lines:

- line 31, § Claims: «The claim includes a receipt for each cost except meals.»

What the key holds on these lines:

- nothing

Verdict: not a defect

Note: Finding proposes additional procedural detail rather than demonstrating a defect in the existing rules

## U-02 — run 1, case-017-en-annual-leave, lines 25-58

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**A03 — No stand-in for the Head of People's time-limited duties**

The document gives a stand-in for an absent line manager. The Head of People has duties with time limits: calculating and recording entitlements and carry-overs, and recalculating in the notice period. No one does these duties when the Head of People is absent. Entitlements may then be missing from the register, and requests may be refused or approved on wrong figures.

Quotes, in their lines:

- line 25, § Entitlement and counting: «The Head of People calculates each entitlement and records it in the leave register within five working days of the start of employment, of a contract change, or of the start of a leave year.»
- line 58, § Leave during the notice period: «The Head of People recalculates the entitlement up to the last day of employment within three working days of the start of the notice period.»

What the key holds on these lines:

- nothing

Verdict: not a defect

Note: potential operational continuity risk, not a demonstrated defect in the document's rules

## U-03 — run 1, case-019-en-vehicles, lines 45-45

Document: *Policy on the Use of Company Vehicles* — `evals/_cases/case-019-en-vehicles/document.md`

**A03 — No stand-in for the Finance Officer's time-limited duty**

The Finance Officer must reimburse within ten working days. The document gives stand-ins for the Fleet Manager and for the driver in the accident report, but none for the Finance Officer. If the Finance Officer is absent, no role is told to reimburse the driver in time.

Quotes, in their lines:

- line 45, § 6. Fuel and costs: «who reimburses only the amounts supported by a receipt, within ten working days of receiving it»

What the key holds on these lines:

- `R-6`, residue the case set accepted: In section 6 "pays personally" means "pays out of pocket and is reimbursed", and the reimbursement line has no exception for a private trip. One reader of section 5 bears the fuel cost; another hands the receipt to the Finance Officer and is reimbursed, and the Finance Officer can pay or refuse. Each obeys the document. The same doubt covers the tolls and the parking fees of a private trip. The readings differ in an amount and in what the reader gets. It can also be reported as A04 (one phrase, two meanings), with lower confidence (0.2).

Verdict: not a defect

Note: 

## U-04 — run 2, case-007-en-office-closing, lines 37-38

Document: *Office Closing Checklist* — `evals/_cases/case-007-en-office-closing/document.md`

**A01 — The closing log is locked away before it must be written**

The steps must be done in the order written. The keys step scrambles the code dial of the key safe. The next step requires writing in the closing log, which is kept in that safe. After the dial is scrambled the closing person cannot reach the log, so the two steps cannot both be done as written.

Quotes, in their lines:

- line 37, § Closing steps: «Keys: the closing person puts the office key in the key safe beside the main door and scrambles the code dial.»
- line 38, § Closing steps: «Closing log: the closing person writes the date, the time of closing and their own role in the closing log, which is kept in the key safe, and signs the entry.»

What the key holds on these lines:

- `R-3`, residue the case set accepted: The order written scrambles the dial before the closing log step, the log is kept in the key safe, and no step secures the safe again.
- `R-6`, residue the case set accepted: The document uses "the office" and "the building" and does not say if they are one place, so one reader sends the message before the alarm step (or inside the 60 seconds after a remote set) and another sends it at the key safe after locking the main door; the readings differ in sequence.

Verdict: real defect

Note: The prescribed sequence undermines the intended securing of the key safe. The precise defect is not that the closing log is permanently inaccessible, but that completing the log entry requires reopening the safe after its final prescribed securing step, with no instruction to secure it again.

## U-05 — run 3, case-014-uk-legal-department, lines 28-28

Document: *Положення про юридичний відділ* — `evals/_cases/case-014-uk-legal-department/document.md`

**A03 — Для директора немає заступника, хоча він має строк на експертизу**

Директор особисто проводить експертизу наказів щодо працівників Відділу й має на це три робочі дні. Заступника для начальника Відділу в Положенні передбачено, а для директора ні. Якщо директор відсутній, ніхто не може завершити експертизу в строк, і Положення не каже, що тоді робити.

Quotes, in their lines:

- line 28, § Функції: «Директор завершує таку експертизу протягом трьох робочих днів від дня, коли проєкт надійшов до нього.»

What the key holds on these lines:

- nothing

Verdict: not a defect

Note: 

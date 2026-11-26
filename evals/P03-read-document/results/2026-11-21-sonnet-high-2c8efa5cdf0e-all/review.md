# Findings the key does not place — the verdicts

**What was tested.** One prompt that reports the problems of six heuristics, A01 to A06, in one call. Each finding below names its heuristic; the key places it on no planted defect and no trap.

**What a verdict means.**

- `real defect` — the document has the problem the finding states, of one of the six kinds; the maintainer decides whether it joins the key.
- `trap` — the passages look like such a problem, but the document resolves it.
- `not a defect` — the document does not have the problem the finding states, of any of the six kinds.

Line numbers count from the first line after the case document's frontmatter.

**Status.** 0 of 6 items ruled.

## U-01 — run 1, case-001-en-travel-expenses, lines 23-23

Document: *Travel expenses* — `evals/_cases/case-001-en-travel-expenses/document.md`

**A03 — Meals are a fixed amount but no rule for trips without a full day or travel days**

Not a gap of meaningful scope; omitted.

Quotes, in their lines:

- line 23, § Costs: «The Organisation pays a fixed amount of 40 euros for meals for each day of the trip.»

What the key holds on these lines:

- nothing

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: Line 23 pays a fixed amount for each trip day, including travel days and days on which only part of the day is spent travelling.

## U-02 — run 1, case-019-en-vehicles, lines 45-45

Document: *Policy on the Use of Company Vehicles* — `evals/_cases/case-019-en-vehicles/document.md`

**A03 — No stand-in for the Finance Officer's time-limited duty**

The Fleet Manager has the Operations Director as a stand-in, and the driver has the line manager for accident reports. The Finance Officer has a ten-working-day deadline for reimbursement and no stand-in. If the Finance Officer is absent, no rule says who reimburses or who meets the deadline.

Quotes, in their lines:

- line 45, § 6. Fuel and costs: «The driver hands the fuel, toll and parking receipts to the Finance Officer, who reimburses only the amounts supported by a receipt, within ten working days of receiving it.»

What the key holds on these lines:

- `R-6`, residue the case set accepted: In section 6 "pays personally" means "pays out of pocket and is reimbursed", and the reimbursement line has no exception for a private trip. One reader of section 5 bears the fuel cost; another hands the receipt to the Finance Officer and is reimbursed, and the Finance Officer can pay or refuse. Each obeys the document. The same doubt covers the tolls and the parking fees of a private trip. The readings differ in an amount and in what the reader gets. It can also be reported as A04 (one phrase, two meanings), with lower confidence (0.2).

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: Line 45 assigns reimbursement and its deadline to the Finance Officer. An absence creates a staffing risk while the obligation remains assigned.

## U-03 — run 2, case-001-en-travel-expenses, lines 12-12

Document: *Travel expenses* — `evals/_cases/case-001-en-travel-expenses/document.md`

**A02 — Unclear who approves a trip abroad by a head of department or inside the country by the director**

The director approves all trips abroad and each trip of a head of department. The head of department approves trips inside the country for the employee. A trip abroad by a head of department fits both but gives the same approver. The director's own trip abroad fits both the director rule for trips abroad and the chair rule. The 'instead' wording settles it, so this is not a conflict.

Quotes, in their lines:

- line 12, § Approval: «The director approves a trip abroad.»

What the key holds on these lines:

- nothing

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Lines 13 and 14 give the director each department head's trip and the chair each director's trip, regardless of destination.

## U-04 — run 2, case-001-en-travel-expenses, lines 31-31

Document: *Travel expenses* — `evals/_cases/case-001-en-travel-expenses/document.md`

**A03 — Gap: no rule for a claim without a receipt or for a late-but-approved case**

The claim must include a receipt for each cost except meals. No rule says what happens if a receipt is lost or missing. The finance department pays within fifteen working days, but no rule says what it does with an incomplete claim.

Quotes, in their lines:

- line 31, § Claims: «The claim includes a receipt for each cost except meals.»

What the key holds on these lines:

- nothing

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Lines 31–32 leave Finance to choose whether to withhold the entire incomplete claim or pay its documented costs within fifteen working days.

## U-05 — run 2, case-002-uk-procurement-committee, lines 23-58

Document: *Положення про закупівельний комітет Організації* — `evals/_cases/case-002-uk-procurement-committee/document.md`

**A06 — Обовʼязок передати заявку директорові закріплено за роллю, якої може не бути**

Передачу заявки директорові при відсутності кворуму виконує «виконавець обовʼязків секретаря». Така роль виникає лише тоді, коли секретар відсутній або має конфлікт інтересів. Якщо секретар присутній, а кворуму немає з іншої причини, документ не називає, хто передає заявку.

Quotes, in their lines:

- line 58, § Конфлікт інтересів: «виконавець обовʼязків секретаря протягом двох робочих днів після засідання передає заявку директорові»
- line 23, § Склад Комітету: «Якщо секретар відсутній або має конфлікт інтересів щодо питання, головуючий доручає обовʼязки секретаря»

What the key holds on these lines:

- `R-1`, residue the case set accepted: Заміну обмежено засіданням, проте протокол складає і надсилає вже після засідання «Секретар», тоді як правило про відсутність кворуму покладає обовʼязок після засідання на виконавця обовʼязків секретаря. Тому за одним прочитанням протокол складає і надсилає виконавець обовʼязків секретаря, а за іншим — призначений секретар.
- `R-2`, residue the case set accepted: Коли кворуму немає через те, що і голова, і заступник голови відсутні або мають конфлікт інтересів, і секретар також, ніхто не може доручити обовʼязки секретаря, тож обовʼязок передати заявку директорові не має відповідального; власник може віднести це до A03. Крім того, термін «виконавець обовʼязків секретаря» не визначено, тому коли секретар присутній, читач може не знайти відповідального за передання заявки (холодне читання з ключем, N-5).

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Line 58 requires referral whenever quorum fails, but line 23 provides an acting secretary only when the secretary is absent or conflicted.

## U-06 — run 2, case-017-en-annual-leave, lines 41-41

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**A03 — Director's requests are decided by the Chair, but no one decides the Chair's leave**

The scope covers every employee, and the Chair of the Board may be one. The approval rules name a decider for ordinary employees, managers and the Director, but none for the Chair's own requests. Nobody can decide the Chair's requests, and the five-day rule would approve them by default.

Quotes, in their lines:

- line 41, § Approval: «The Chair of the Board decides the Director's requests.»

What the key holds on these lines:

- `R-5`, residue the case set accepted: The document does not say if the Chair of the Board is "the line manager" of the Director for the substitute rule. Reader one: the Chair stands in the line manager's place, so when the Chair is absent the Head of People decides the Director's request. Reader two: the Chair's line is a separate rule and the substitute rule does not reach it, so nobody decides and the request counts as approved after five working days. The readings differ in the person who decides and come from the passages together (a condition stated in one place whose scope over another passage is not clear). Under reader one there is also a second A05 finding: the Director, as the likely line manager of the Head of People, decides the Head of People's requests, and the Head of People decides the Director's ("A approves B, B approves A"). That A05 rests on a reporting line that the document does not state, so on its own it is 0.2.

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: The text leaves the Chair's employment and reporting line unspecified. If the Chair is an employee, line 39 assigns approval to their line manager.

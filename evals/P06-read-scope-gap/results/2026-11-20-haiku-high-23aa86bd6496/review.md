# Unmatched findings of A03 — scope-gap — the verdicts

**What was tested.** Each finding below came from heuristic A03, prompt `prompts/P06-read-scope-gap/prompt-03.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — a contradiction, an ambiguity, a term with two meanings, circular authority, an unowned obligation.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.

**Status.** 0 of 22 items ruled.

<details><summary>The instruction A03 obeyed (<code>prompts/P06-read-scope-gap/prompt-03.md</code>)</summary>

Find each gap in the document.
Report each gap as a separate finding.

A gap is a case that the scope of the document includes and that no rule of the document handles.

First, find the scope of the document.
The scope is what the document applies to: persons, roles, things, amounts, places and times.
Also find each range of values, each list of types and each sequence of steps that the document gives.

Then read the document as the reader who obeys it.
This reader knows only the text of the document.
For each case in the scope, find the rule that tells the reader what to do.

Find these causes:

- A range of values has a value or an interval that no rule covers.
- The scope names types, roles, forms or places, and the rules cover only some of them.
- A step or a decision has a rule for one result and no rule for the other result.
- A step needs a thing that no step makes or sends: a document, a record, a decision or a notice.
- A step keeps or adds a thing, and no step removes it. The document sets an end for the other things of that kind.
- One act has two steps, a second person acts between the two steps, and no rule tells what that person does.
- The document gives a stand-in for an absent role, and a case of absence has no stand-in.

Report a gap only if the reader must act in that case and the document does not tell how.
Before you report, read the whole document for a passage that covers the case.

Do not report these:

- A case outside the scope of the document.
- A case in which a person does not do what the document requires, or does it late. The document does not need a rule for each breach.
- Two or more roles absent at the same time, if the document gives a stand-in for each role alone.
- The absence of a role, if the document gives no stand-in for any role. A document does not need a rule for the absence of each person.
- A start or an end that a condition of the document decides, for example the first day that meets a condition.
- A stand-in who does the duties of an absent role and so approves the stand-in's own act. That is a different kind of problem.
- Two readings of who acts, when or how. That is a different kind of problem.
- A case that a different passage covers, for example a general rule, a fallback rule, "every other" or a definition that includes all other cases.
- A case that the document says it does not govern, or gives to a law or a different document.
- A detail that the reader does not need to act, for example a form, a format, a tool or a template.
- An action that the document requires, but gives to no role. That is a different kind of problem.
- Two rules for the same case. That is a different kind of problem.

Quote the passage that puts the case in the scope, and the passages that leave it without a rule.
In the explanation, name the case, and write what the reader cannot do in that case.

</details>

## U-05 — case-004-uk-window-timber-wall, run 1

Document: *Інструкція з монтажу вікна в стіну каркасної дерев’яної будівлі* — `evals/_cases/case-004-uk-window-timber-wall/document.md`

**Title.** Не визначено дії монтажника, якщо він не має потрібного інструмента

**Explanation.** Документ вимагає перевірити наявність усіх інструментів перед початком робіт, але не описує, що робити, якщо якогось інструмента немає. Для матеріалів бригадир їх видає, а для інструментів правила забезпечення немає. Монтажник не знає, чи може починати роботу, кому повідомити про брак і хто має його усунути.

**Quotes, in their lines:**

- line 17, § Матеріали та інструменти: «Монтажник до початку робіт перевіряє, що має всі інструменти з цього розділу.»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: Документ не каже, що робить монтажник, коли до початку робіт бракує матеріалу або інструмента.

Verdict: 

Note: 

## U-06 — case-006-uk-accountant-job, run 1

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Немає правила на час відсутності головного бухгалтера

**Explanation.** Документ визначає заступника для відсутнього бухгалтера, але не визначає, хто виконує обов'язки головного бухгалтера. Головний бухгалтер затверджує звіти, отримує повідомлення про розбіжності, розглядає пропозиції та передає питання директорові. Коли він відсутній, бухгалтер не знає, кому подавати звіт і кому передавати повідомлення, і строки для цих дій не можна виконати.

**Quotes, in their lines:**

- line 10, § Загальні положення: «На час відсутності бухгалтера його обов'язки виконує працівник фінансового відділу»
- line 62, § Взаємодія з іншими відділами: «Головний бухгалтер протягом одного робочого дня від дня повідомлення бухгалтера»

**What the key holds on these lines:**

- `R-5`, residue the case set accepted: Ніщо не заважає головному бухгалтеру визначити самого себе працівником, який заміщує бухгалтера, а потім затвердити власний звіт. Проте документ не каже, чи є головний бухгалтер працівником фінансового відділу, тому це лише припущення.

Verdict: 

Note: 

## U-08 — case-007-en-office-closing, run 1

Document: *Office Closing Checklist* — `evals/_cases/case-007-en-office-closing/document.md`

**Title.** No stand-in when the Office Manager is absent and the Head of Operations is also absent.

**Explanation.** The document names the Head of Operations as the stand-in for the Office Manager, but gives no stand-in for the Head of Operations. If the Office Manager is on leave or off sick and the Head of Operations is also absent, the reader has no one to receive the fault reports and no one to take the Office Manager's place. The reader cannot tell who receives the report before leaving the building.

**Quotes, in their lines:**

- line 16, § Who closes the office: «On a day when the Office Manager is on leave or off sick, the Head of Operations takes the Office Manager's place in every rule of this checklist, as actor and as receiver of a report.»
- line 43, § If a step cannot be completed: «The closing person completes the remaining steps, describes the fault in the closing log and reports it to the Office Manager by message before leaving the building.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: The substitution is tied to one day and the fault rule spans two, so when the Office Manager is absent on only one of them, readers differ on who orders the repair.
- `R-5`, residue the case set accepted: The document provides one substitute and no rule for a day when both the Office Manager and the Head of Operations are absent.
- `R-6`, residue the case set accepted: The document uses "the office" and "the building" and does not say if they are one place, so one reader sends the message before the alarm step (or inside the 60 seconds after a remote set) and another sends it at the key safe after locking the main door; the readings differ in sequence.
- `R-9`, residue the case set accepted: The Office Manager can be the person who stays or the closing person (fallback, weekend), and then allows their own stay or receives their own report. A report is not an approval, so it is weak.

Verdict: 

Note: 

## U-10 — case-009-en-gifts, runs 1, 2 (also U-25)

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Hospitality above the limit that the employee knows is too high when accepting it has no remedy rule

**Explanation.** Section 7.3 covers hospitality above the limit that an employee accepts without approval. The remedy paragraph of Section 7.6 names only gifts for the case where the employee has received an above-limit gift at once. The hospitality rule applies only when the employee learns of the excess after the occasion. A reader who accepts hospitality above the limit knowing its value at the time cannot tell whether to hand it over, return it, or pay the excess.

**Quotes, in their lines:**

- line 24, § 7.3 Value limits: «An employee must not accept or give a gift or hospitality above its limit unless an exception has been approved under Section 7.5.»
- line 46, § 7.6 A gift or hospitality above the limit: «When an employee has received, without an approved exception, a gift above the gift limit or a money gift»
- line 49, § 7.6 A gift or hospitality above the limit: «When an employee learns after the occasion that a gift given or hospitality received or given was above its limit»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Section 7.7 displaces 7.3, excludes 7.5, keeps 7.4 and is silent on 7.6, so a host who learns later that the refreshments were too costly can read that "its limit" in 7.6 is the limit for refreshments and record it, or that 7.6 does not reach giving to officials and record nothing.
- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: 

Note: 

## U-14 — case-015-en-customer-letters, runs 1, 3 (also U-54)

Document: *Guideline on Writing Letters to Customers* — `evals/_cases/case-015-en-customer-letters/document.md`

**Title.** No checker is named when an Adviser's team has no other Adviser

**Explanation.** The reader must appoint a checker for every Adviser's letter that refuses a request, states a sum of money or answers a complaint. The document requires that checker to be another Adviser of the same team, but it does not say what to do when the team has no other Adviser. Unlike the Team Lead case, where the Head of the Department appoints a checker from another team, no fallback is given for Advisers, so the reader cannot complete the check.

**Quotes, in their lines:**

- line 47, § Check by a second person: «When the author is an Adviser, the Team Lead of that Adviser's team appoints another Adviser of the same team as the checker.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-15 — case-018-uk-document-numbering, run 1

Document: *Стандарт Організації СТО 07 «Нумерація та реєстрація внутрішніх документів»* — `evals/_cases/case-018-uk-document-numbering/document.md`

**Title.** Не визначено, хто присвоює номер, якщо відсутні і реєстратор, і його заступник

**Explanation.** Стандарт дає заступника реєстратора як заміну лише на випадок відсутності реєстратора. Якщо відсутні обидва, у документі немає жодної особи, яка має присвоїти номер у день отримання підписаного документа. Працівник, який має діяти в такій ситуації, не знає, кому передати документ і хто має присвоїти номер.

**Quotes, in their lines:**

- line 39, § 3. Присвоєння номера: «Заступник виконує всі обов'язки реєстратора в дні, коли реєстратор відсутній на роботі.»
- line 38, § 3. Присвоєння номера: «Реєстратора та його заступника призначає керівник підрозділу розпорядженням з числа працівників цього підрозділу.»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: Стандарт охоплює відсутність реєстратора, але не день, коли відсутні і реєстратор, і заступник, тож для строку передавання й присвоєння номера того самого дня правила немає.
- `R-3`, residue the case set accepted: Розпорядження про призначення реєстратора може пронумерувати лише реєстратор цього підрозділу, тож перше призначення залежить від ролі, яку воно створює; це слабка залежність запуску, а не затвердження власної дії.

Verdict: 

Note: 

## U-16 — case-019-en-vehicles, run 1

Document: *Policy on the Use of Company Vehicles* — `evals/_cases/case-019-en-vehicles/document.md`

**Title.** No step gives the driver the keys at the start of a booking

**Explanation.** Keys go to the Fleet Manager at the end of each booking. No step says how an approved driver gets the keys or the vehicle at the start of a booking, so the driver cannot tell how to begin a trip that the document allows.

**Quotes, in their lines:**

- line 32, § 4. Booking: «At the end of the booking, the driver returns the vehicle to the Organisation's car park, enters the mileage in the mileage log and hands the keys to the Fleet Manager.»
- line 31, § 4. Booking: «No employee takes a vehicle without an approved booking.»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: The substitution moves the Fleet Manager's duties, and receiving the keys is the driver's duty, so the document does not say whether the Fleet Manager as driver keeps the keys or hands them to the Operations Director.

Verdict: 

Note: 

## U-20 — case-003-en-onboarding, runs 2, 3 (also U-44)

Document: *Standard Operating Procedure: Onboarding a New Employee* — `evals/_cases/case-003-en-onboarding/document.md`

**Title.** No rule for leaving after the probation period

**Explanation.** The procedure applies to every new employee, and the definition of a new employee has no time limit. Section 8 covers only leaving days within the probation period. When an employee leaves after probation, the reader has no rule for returning the equipment, archiving the accounts, or disabling and deleting them.

**Quotes, in their lines:**

- line 6, § 1. Scope: «This procedure applies to every new employee of the Organisation.»
- line 58, § 8. Leaving during the probation period: «This section applies when the leaving day of a new employee falls within the probation period, whatever the reason for leaving.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: A person who signs the contract and withdraws before the first day is inside the scope but has no leaving day and no probation period, so no rule closes the accounts or releases the prepared equipment.
- `R-3`, residue the case set accepted: When the new employee is the HR Officer or the IT Technician, the role checks its own identity document or issues its own equipment, and the document does not state that case.
- `R-9`, residue the case set accepted: For a leaving that is not a decision of the review meeting, such as a resignation, no rule says who records the leaving in the onboarding record. Against it: "keeps the onboarding record" in section 3 can carry it.

Verdict: 

Note: 

## U-23 — case-007-en-office-closing, run 2

Document: *Office Closing Checklist* — `evals/_cases/case-007-en-office-closing/document.md`

**Title.** No stand-in when the Head of Operations is also absent

**Explanation.** The Head of Operations is the stand-in for the Office Manager, but the document gives no stand-in for the Head of Operations. If the Office Manager is on leave and the Head of Operations is also absent, the reader does not know who publishes the rota, receives reports, or orders repairs.

**Quotes, in their lines:**

- line 16, § Who closes the office: «On a day when the Office Manager is on leave or off sick, the Head of Operations takes the Office Manager's place in every rule of this checklist, as actor and as receiver of a report.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: The substitution is tied to one day and the fault rule spans two, so when the Office Manager is absent on only one of them, readers differ on who orders the repair.
- `R-5`, residue the case set accepted: The document provides one substitute and no rule for a day when both the Office Manager and the Head of Operations are absent.

Verdict: 

Note: 

## U-27 — case-009-en-gifts, run 2

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** No rule for an above-limit gift that the employee has already used

**Explanation.** The employee must hand the above-limit gift to the Compliance Officer unused. If the gift has already been consumed, used, or enjoyed, for example a spent voucher or a received service, this step cannot be done. The only fallback rule is for the Compliance Officer's return to the third party, so the employee has no instruction for this case.

**Quotes, in their lines:**

- line 46, § 7.6 A gift or hospitality above the limit: «the employee hands it, unused, to the Compliance Officer and declares it, both within two working days of learning that it is such a gift.»
- line 48, § 7.6 A gift or hospitality above the limit: «When return is impossible, the Compliance Officer donates the gift to a registered charity and records the donation in the Gifts and Hospitality Register.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: 

Note: 

## U-30 — case-014-uk-legal-department, run 2

Document: *Положення про юридичний відділ* — `evals/_cases/case-014-uk-legal-department/document.md`

**Title.** Не визначено, як відповідати на консультаційні запити, які не є письмовими запитами керівників

**Explanation.** Завдання Відділу включає правові консультації для всіх підрозділів, але строк і порядок відповіді встановлено лише для письмових запитів керівників підрозділів. Усний запит або письмовий запит працівника, який не є керівником, не має жодного правила. Тому працівник Відділу не знає, чи має він відповідати, і в який строк.

**Quotes, in their lines:**

- line 18, § Завдання: «Надавати правові консультації іншим підрозділам Організації.»
- line 32, § Функції: «Відділ надає письмову відповідь на письмовий запит керівника іншого підрозділу про правову консультацію протягом пʼяти робочих днів від дня надходження запиту.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-31 — case-015-en-customer-letters, run 2

Document: *Guideline on Writing Letters to Customers* — `evals/_cases/case-015-en-customer-letters/document.md`

**Title.** No assignment rule for messages received on a non-working day

**Explanation.** The Head of the Department must assign each message on the working day the Organisation receives it. The document also lets messages arrive on any day, since the time limit starts on the next working day. For a message received on a weekend or a holiday, no working day matches the assignment rule, and the document gives no other day for the assignment, so the reader cannot know when to assign it.

**Quotes, in their lines:**

- line 60, § Response times: «The Head of the Department assigns each message to an author on the working day the Organisation receives it.»
- line 61, § Response times: «Time limits are counted in working days and start on the working day after the Organisation receives the message.»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: A message received on a day that is not a working day has no stated day of assignment, though a reader supplies the next working day without a second way to act that matters.
- `R-5`, residue the case set accepted: The one working day of the checker has no stated start (the appointment, the receipt of the draft), and the only rule on the start of a time limit ties every limit to the receipt of the message, which cannot apply to the checker.

Verdict: 

Note: 

## U-33 — case-017-en-annual-leave, run 2

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**Title.** Absences of part of a day other than half a day have no deduction rule

**Explanation.** The document deducts one leave day for a full day and half a leave day for an absence of half the contracted hours. It gives no deduction for an absence of another part of a day, such as a quarter or three quarters of the contracted hours. The reader cannot record how many leave days such an absence uses.

**Quotes, in their lines:**

- line 27, § Entitlement and counting: «One leave day is deducted for each leave day of absence, and half a leave day for an absence of half of the contracted hours of that day.»
- line 28, § Entitlement and counting: «Leave is taken in whole or half leave days only.»

**What the key holds on these lines:**

- `R-7`, residue the case set accepted: The term is defined as a kind of calendar day and is then used as a unit of entitlement (which can be a half and can be below zero). The last line uses both senses in one sentence. No reader acts differently because of it, so I would not key it; a model may report it.

Verdict: 

Note: 

## U-38 — case-020-uk-stocktake, run 2

Document: *Порядок проведення щорічної інвентаризації товарів* — `evals/_cases/case-020-uk-stocktake/document.md`

**Title.** Немає правила, що робити, якщо головний бухгалтер не передав витяг

**Explanation.** Голова комісії має порівняти фактичну кількість товару з витягом головного бухгалтера, але документ не передбачає іншого джерела даних і не описує дій, якщо бухгалтер відсутній або витяг не переданий. Голова не може виконати порівняння і не знає, чи починати підрахунок без витягу.

**Quotes, in their lines:**

- line 41, § 5. Підрахунок товарів: «Головний бухгалтер у перший день підрахунку до його початку передає голові комісії витяг із залишками товарів за даними обліку.»
- line 51, § 6. Розбіжності: «Голова комісії порівнює фактичну кількість товару кожного найменування з витягом головного бухгалтера.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-39 — case-021-en-lab-spill, run 2

Document: *Standard Operating Procedure: Cleaning a Chemical Spill in a Laboratory* — `evals/_cases/case-021-en-lab-spill/document.md`

**Title.** The room inspection has no rule for a failed result.

**Explanation.** The Duty Safety Officer inspects the room after the cleaning is reported complete, and the only rule is to reopen it. The document does not say what the Duty Safety Officer must do if the room fails the inspection, for example whether it stays closed, who cleans again, or who is told. The reader cannot act in that case.

**Quotes, in their lines:**

- line 60, § 6. Steps for a large spill: «The Duty Safety Officer inspects the room and reopens it.»

**What the key holds on these lines:**

- `R-6`, residue the case set accepted: From the arrival of the team until the reopening, the room is closed but no role is named to keep people out.

Verdict: 

Note: 

## U-47 — case-006-uk-accountant-job, run 3

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Розбіжність у залишках і розрахунках не визначена, якщо документи є

**Explanation.** Під час щомісячного звіряння бухгалтер порівнює залишки на банківських рахунках і розрахунки з постачальниками. Документ визначає як розбіжність лише позицію, для якої бракує документа чи пояснення. Якщо сума в обліку й на банківському рахунку не збігається, а документи є, бухгалтер не знає, чи це розбіжність, чи має повідомити головного бухгалтера і чи має виправляти її.

**Quotes, in their lines:**

- line 24, § Обов'язки: «Позицію, для якої на день звіряння бракує первинного документа чи пояснення, бухгалтер вважає розбіжністю.»
- line 23, § Обов'язки: «Бухгалтер щомісяця, не пізніше п'ятого робочого дня місяця, звіряє за попередній місяць залишки на банківських рахунках Організації та розрахунки з постачальниками.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-49 — case-009-en-gifts, run 3

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** No rule for hospitality above its limit that the employee learns about during the occasion

**Explanation.** Section 7.6 covers hospitality above its limit only when the employee learns of it after the occasion, and the first paragraph covers only gifts. If an employee learns during a meal or event that the hospitality is above the limit, the document does not say whether to stop accepting, pay the excess, or how to record it. The reader cannot tell what to do in that case.

**Quotes, in their lines:**

- line 49, § 7.6 A gift or hospitality above the limit: «When an employee learns after the occasion that a gift given or hospitality received or given was above its limit»
- line 46, § 7.6 A gift or hospitality above the limit: «When an employee has received, without an approved exception, a gift above the gift limit or a money gift»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Section 7.7 displaces 7.3, excludes 7.5, keeps 7.4 and is silent on 7.6, so a host who learns later that the refreshments were too costly can read that "its limit" in 7.6 is the limit for refreshments and record it, or that 7.6 does not reach giving to officials and record nothing.
- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: 

Note: 

## U-52 — case-013-en-it-access, run 3

Document: *Procedure for Requesting and Removing Access to IT Systems* — `evals/_cases/case-013-en-it-access/document.md`

**Title.** No rule covers removing access that is no longer needed between review dates.

**Explanation.** The procedure covers removal only at the twice-yearly review, on a change of role, and on leaving. If a line manager or employee needs access removed at another time, for example when a task ends, the reader has no rule on who asks, who decides, or how fast the Service Desk must act.

**Quotes, in their lines:**

- line 6, § 1. Purpose and scope: «This procedure sets out how access to the IT systems of the Organisation is requested, approved, granted, recorded, reviewed and removed.»
- line 55, § 6. Periodic review: «On the first working day of January and of July, the Service Desk sends the system owner and the alternate owner of each system the list of all access to that system from the access register.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-53 — case-014-uk-legal-department, run 3

Document: *Положення про юридичний відділ* — `evals/_cases/case-014-uk-legal-department/document.md`

**Title.** Не визначено, що робить директор, якщо проєкт наказу відповідає законодавству

**Explanation.** Для експертизи директора описано лише випадок невідповідності законодавству: тоді директор повертає проєкт. Якщо проєкт відповідає законодавству, документ не каже, що директор має зробити далі, наприклад підписати наказ. Для Відділу такий випадок описано повністю, а для директора в ньому є прогалина.

**Quotes, in their lines:**

- line 28, § Функції: «Директор завершує таку експертизу протягом трьох робочих днів від дня, коли проєкт надійшов до нього.»
- line 29, § Функції: «Якщо такий проєкт не відповідає законодавству, директор повертає його керівникові підрозділу»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-55 — case-015-en-customer-letters, run 3

Document: *Guideline on Writing Letters to Customers* — `evals/_cases/case-015-en-customer-letters/document.md`

**Title.** No checker can be appointed for a Team Lead when no other team exists

**Explanation.** A Team Lead's letter that needs a check must be checked by the Team Lead of another team. The document does not say what the Head of the Department or the author should do if the Department has only one team. In that case the reader cannot obtain the required check and no rule covers the situation.

**Quotes, in their lines:**

- line 48, § Check by a second person: «When the author is a Team Lead, the Head of the Department appoints the Team Lead of another team as the checker.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-58 — case-019-en-vehicles, run 3

Document: *Policy on the Use of Company Vehicles* — `evals/_cases/case-019-en-vehicles/document.md`

**Title.** No rule for removing an authorised employee who leaves or no longer needs a vehicle

**Explanation.** The document adds employees to the list of authorised drivers and gives a removal step only when a licence is suspended, withdrawn or expired. If an authorised employee leaves the Organisation or no longer needs to drive, the reader has no rule that tells the Fleet Manager to remove that person from the list.

**Quotes, in their lines:**

- line 21, § 3. Who may use a vehicle: «An authorised employee whose licence is suspended, withdrawn or expired informs the Fleet Manager on the same day.»
- line 22, § 3. Who may use a vehicle: «The Fleet Manager then removes that employee from the list of authorised employees.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-60 — case-021-en-lab-spill, run 3

Document: *Standard Operating Procedure: Cleaning a Chemical Spill in a Laboratory* — `evals/_cases/case-021-en-lab-spill/document.md`

**Title.** No rule for a room inspection that finds the spill is not yet cleaned

**Explanation.** The reader is told that the Duty Safety Officer inspects the room and reopens it, and that the Team Leader reports cleaning complete. The document gives no rule for an inspection that finds the room still contaminated or the cleaning incomplete. The reader cannot tell whether to ask the Spill Response Team to clean again, whether the room stays closed, or who decides.

**Quotes, in their lines:**

- line 60, § 6. Steps for a large spill: «The Duty Safety Officer inspects the room and reopens it.»
- line 59, § 6. Steps for a large spill: «The Team Leader, who leads the Spill Response Team, tells the Duty Safety Officer that cleaning is complete.»

**What the key holds on these lines:**

- `R-6`, residue the case set accepted: From the arrival of the team until the reopening, the room is closed but no role is named to keep people out.

Verdict: 

Note: 

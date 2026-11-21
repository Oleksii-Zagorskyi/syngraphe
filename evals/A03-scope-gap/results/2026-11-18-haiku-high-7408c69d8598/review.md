# Unmatched findings of A03 — scope-gap — the verdicts

**What was tested.** Each finding below came from heuristic A03, prompt `prompts/A03-scope-gap/prompt-02.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — a contradiction, an ambiguity, a term with two meanings, circular authority, an unowned obligation.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.
Notes marked *Second reviewer* hold the verdict of an independent model review, accepted by the maintainer; the word in brackets is that review's confidence.

**Status.** 30 of 30 items ruled.

<details><summary>The instruction A03 obeyed (<code>prompts/A03-scope-gap/prompt-02.md</code>)</summary>

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
- A case that a different passage covers, for example a general rule, a fallback rule, "every other" or a definition that includes all other cases.
- A case that the document says it does not govern, or gives to a law or a different document.
- A detail that the reader does not need to act, for example a form, a format, a tool or a template.
- An action that the document requires, but gives to no role. That is a different kind of problem.
- Two rules for the same case. That is a different kind of problem.

Quote the passage that puts the case in the scope, and the passages that leave it without a rule.
In the explanation, name the case, and write what the reader cannot do in that case.

</details>

## U-04 — case-003-en-onboarding, runs 1, 2 (also U-29)

Document: *Standard Operating Procedure: Onboarding a New Employee* — `evals/_cases/case-003-en-onboarding/document.md`

**Title.** No rule for a new employee who leaves after the probation period

**Explanation.** The document applies to every new employee, but the leaving rules in section 8 apply only when the leaving day falls within the probation period. If a new employee leaves after the probation period, the reader is not told who informs whom, how the equipment is returned, or when the accounts are disabled and deleted.

**Quotes, in their lines:**

- line 6, § 1. Scope: «This procedure applies to every new employee of the Organisation.»
- line 58, § 8. Leaving during the probation period: «This section applies when the leaving day of a new employee falls within the probation period, whatever the reason for leaving.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: A person who signs the contract and withdraws before the first day is inside the scope but has no leaving day and no probation period, so no rule closes the accounts or releases the prepared equipment.
- `R-3`, residue the case set accepted: When the new employee is the HR Officer or the IT Technician, the role checks its own identity document or issues its own equipment, and the document does not state that case.
- `R-9`, residue the case set accepted: For a leaving that is not a decision of the review meeting, such as a resignation, no rule says who records the leaving in the onboarding record. Against it: "keeps the onboarding record" in section 3 can carry it.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Section 8 expressly limits this onboarding procedure’s exit workflow to probation. Ordinary post-probation offboarding falls outside that workflow. (medium)

## U-05 — case-004-uk-window-timber-wall, run 1

Document: *Інструкція з монтажу вікна в стіну каркасної дерев’яної будівлі* — `evals/_cases/case-004-uk-window-timber-wall/document.md`

**Title.** Не визначено, хто просвердлює отвори для рамних шурупів і коли це робити

**Explanation.** Для коробки з більшою стороною до 1500 мм кріплення виконується крізь отвори діаметром 6 мм, просвердлені в коробці. Жоден крок послідовності робіт не містить свердління, а розділ про способи кріплення не каже, хто і на якому етапі має зробити отвори. Монтажник не знає, чи має він свердлити сам, чи отвори вже мають бути готові.

**Quotes, in their lines:**

- line 42, § Способи кріплення: «Якщо більша сторона коробки не перевищує 1500 мм, монтажник кріпить коробку рамними шурупами крізь отвори діаметром 6 мм, просвердлені в коробці.»
- line 55, § Послідовність робіт: «Закріпити коробку до каркаса способом, визначеним у розділі «Способи кріплення».»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Для випадку, коли друга перевірка виявила перевищення, документ називає видалення піни, але мовчить про кріплення та приклеєну зовнішню стрічку, тому кроки встановлення й закріплення коробки неможливо повторити так, як їх записано.
- `R-4`, residue the case set accepted: Для анкерних пластин є окремий крок перед встановленням коробки, а для свердління такого кроку немає, тому документ не каже, коли свердлять отвори: до чи після того, як коробку поставлено в проріз. Більшість читачів вважає свердління частиною кроку закріплення коробки.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The ordered fastening step incorporates the specified through-hole method. Drilling belongs to that operation, even though its precise timing is unstated in R-4. (medium)

## U-06 — case-004-uk-window-timber-wall, run 1

Document: *Інструкція з монтажу вікна в стіну каркасної дерев’яної будівлі* — `evals/_cases/case-004-uk-window-timber-wall/document.md`

**Title.** Немає дій, якщо монтажник не має потрібного інструмента

**Explanation.** Монтажник перевіряє наявність інструментів до початку робіт, але документ не називає, хто їх видає, і не визначає дій, якщо якогось інструмента бракує. Бригадир видає лише матеріали. Тому монтажник не знає, чи має він розпочати роботу, кого повідомити або де взяти інструмент.

**Quotes, in their lines:**

- line 17, § Матеріали та інструменти: «Монтажник до початку робіт перевіряє, що має всі інструменти з цього розділу.»
- line 16, § Матеріали та інструменти: «Бригадир видає монтажникові до початку робіт усі матеріали з цього розділу.»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: Документ не каже, що робить монтажник, коли до початку робіт бракує матеріалу або інструмента.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Checking tools can reveal a shortage, but the installer gets no stop, escalation or replacement rule. Residue R-2. (medium)

## U-08 — case-006-uk-accountant-job, run 1

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Немає заміни головного бухгалтера на час його відсутності

**Explanation.** Документ визначає заміну для бухгалтера, але не для головного бухгалтера. Заміщення бухгалтера призначає саме головний бухгалтер, а звіти, повідомлення про розбіжності та передання питань до директора адресовані головному бухгалтеру. Якщо він відсутній, бухгалтер не знає, кому подати звіт, кому повідомити про розбіжність чи незгоду і хто має передати питання директорові.

**Quotes, in their lines:**

- line 10, § Загальні положення: «На час відсутності бухгалтера його обов'язки виконує працівник фінансового відділу, якого головний бухгалтер визначає письмовим розпорядженням не пізніше першого дня відсутності.»
- line 28, § Обов'язки: «Бухгалтер складає звіт за попередній місяць і подає його головному бухгалтеру не пізніше восьмого робочого дня місяця.»
- line 62, § Взаємодія з іншими відділами: «Головний бухгалтер протягом одного робочого дня від дня повідомлення бухгалтера, визначеного цим розділом або розділом «Права», передає питання директорові Організації.»

**What the key holds on these lines:**

- `R-5`, residue the case set accepted: Ніщо не заважає головному бухгалтеру визначити самого себе працівником, який заміщує бухгалтера, а потім затвердити власний звіт. Проте документ не каже, чи є головний бухгалтер працівником фінансового відділу, тому це лише припущення.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The instruction provides a stand-in for the accountant but no route for required reports and escalations when the chief accountant is absent. Unlisted in residue. (medium)

## U-11 — case-009-en-gifts, run 1

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** No rule for a received gift or money gift that has already been used or spent

**Explanation.** The document requires the employee to hand over an over-limit or money gift received without approval, but only while it is unused. It gives no rule for a gift that has already been used, redeemed or spent, such as a partly used voucher, a service already received, or spent money. The later rule covers only gifts given and hospitality, not gifts received, so the employee cannot tell whether to declare the gift, return its value, or pay the third party back.

**Quotes, in their lines:**

- line 46, § 7.6 A gift or hospitality above the limit: «the employee hands it, unused, to the Compliance Officer and declares it»
- line 49, § 7.6 A gift or hospitality above the limit: «When an employee learns after the occasion that a gift given or hospitality received or given was above its limit, or that a gift given was a money gift»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Section 7.7 displaces 7.3, excludes 7.5, keeps 7.4 and is silent on 7.6, so a host who learns later that the refreshments were too costly can read that "its limit" in 7.6 is the limit for refreshments and record it, or that 7.6 does not reach giving to officials and record nothing.
- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: A late-discovered, already consumed gift cannot be surrendered unused. The declaration rule survives, but disposal or repayment lacks a rule. Residue R-6. (high)

## U-13 — case-014-uk-legal-department, run 1

Document: *Положення про юридичний відділ* — `evals/_cases/case-014-uk-legal-department/document.md`

**Title.** Не визначено, що відбувається з проєктом наказу, який директор визнав відповідним законодавству

**Explanation.** Для проєктів наказів про персонал працівників Відділу описано лише випадок, коли директор повертає невідповідний проєкт. Для відповідного проєкту правило відсутнє: не сказано, чи директор його візує, чи передає на підпис і хто робить наступний крок. Підрозділ, який подав проєкт, не знає, чи його наказ уже можна видавати, а Відділ не знає, чи має щось зробити далі.

**Quotes, in their lines:**

- line 28, § Функції: «Директор завершує таку експертизу протягом трьох робочих днів від дня, коли проєкт надійшов до нього.»
- line 29, § Функції: «Якщо такий проєкт не відповідає законодавству, директор повертає його керівникові підрозділу, який подав проєкт, разом із письмовими зауваженнями, а виправлений проєкт розглядає як новий, у той самий строк.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The director’s special review path specifies only rejection. The ordinary endorsement applies to Department review, leaving compliant drafts without a next step. Unlisted in residue. (high)

## U-14 — case-014-uk-legal-department, runs 1, 2 (also U-42)

Document: *Положення про юридичний відділ* — `evals/_cases/case-014-uk-legal-department/document.md`

**Title.** Не визначено порядок надання усних правових консультацій

**Explanation.** Завдання Відділу включає надання правових консультацій іншим підрозділам без уточнення форми. Строк і порядок відповіді встановлено лише для письмових запитів. Для усного запиту працівник Відділу не знає, чи має відповідати, у які строки і яким чином.

**Quotes, in their lines:**

- line 18, § Завдання: «Надавати правові консультації іншим підрозділам Організації.»
- line 32, § Функції: «Відділ надає письмову відповідь на письмовий запит керівника іншого підрозділу про правову консультацію протягом пʼяти робочих днів від дня надходження запиту.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The general consultation function includes oral requests, but the sole response rule covers written requests. No oral handling rule appears. Unlisted in residue. (medium)

## U-16 — case-015-en-customer-letters, runs 1, 2 (also U-44)

Document: *Guideline on Writing Letters to Customers* — `evals/_cases/case-015-en-customer-letters/document.md`

**Title.** No checker is available when the Adviser's team has no other Adviser

**Explanation.** The guideline says the Team Lead appoints another Adviser of the same team as the checker. It gives no rule for a team in which the author is the only Adviser. In that case the Team Lead cannot appoint a checker, and the letter cannot be sent as the guideline requires for a letter that refuses, states a sum of money or answers a complaint.

**Quotes, in their lines:**

- line 47, § Check by a second person: «When the author is an Adviser, the Team Lead of that Adviser's team appoints another Adviser of the same team as the checker.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: No minimum staffing rule ensures another Adviser exists in the author’s team, and no alternative checker is designated. Unlisted in residue. (medium)

## U-18 — case-017-en-annual-leave, run 1

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**Title.** No stand-in decides a Director's request when the Chair is absent.

**Explanation.** The Chair of the Board decides the Director's requests, but the document gives no stand-in for the Chair. When the Chair is absent, the reader has no rule for who decides a Director's request, and the request has no recorded decision for the approval rules to act on.

**Quotes, in their lines:**

- line 41, § Approval: «The Chair of the Board decides the Director's requests.»

**What the key holds on these lines:**

- `R-5`, residue the case set accepted: The document does not say if the Chair of the Board is "the line manager" of the Director for the substitute rule. Reader one: the Chair stands in the line manager's place, so when the Chair is absent the Head of People decides the Director's request. Reader two: the Chair's line is a separate rule and the substitute rule does not reach it, so nobody decides and the request counts as approved after five working days. The readings differ in the person who decides and come from the passages together (a condition stated in one place whose scope over another passage is not clear). Under reader one there is also a second A05 finding: the Director, as the likely line manager of the Head of People, decides the Head of People's requests, and the Head of People decides the Director's ("A approves B, B approves A"). That A05 rests on a reporting line that the document does not state, so on its own it is 0.2.

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: Approval by silence supplies an outcome. Whether the Head of People substitutes for the Chair is the authority ambiguity in R-5. (medium)

## U-20 — case-017-en-annual-leave, run 1

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**Title.** Employment that ends without written notice has no recalculation of the entitlement.

**Explanation.** The recalculation of the entitlement to the last day of employment applies only to a notice period that starts with written notice. If employment ends without written notice, for example by dismissal without notice, death in service or the end of a fixed-term contract, no rule recalculates the part-year entitlement. The Payroll Officer then cannot know the remaining entitlement at the end of the last day as the document requires.

**Quotes, in their lines:**

- line 57, § Leave during the notice period: «The notice period starts on the day the employee or the Organisation gives written notice of termination and ends on the last day of employment.»
- line 60, § Leave during the notice period: «The Payroll Officer pays, with the final salary, the remaining entitlement for the leave year of the last day of employment as it stands at the end of that day.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: Leave approved earlier for dates after the last day of employment remains approved, so one Payroll Officer subtracts it from the final payment and another does not.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The part-year formula gives an amount, but only written notice triggers recalculation. No step updates the balance for a notice-free exit. Unlisted in residue. (high)

## U-21 — case-018-uk-document-numbering, run 1

Document: *Стандарт Організації СТО 07 «Нумерація та реєстрація внутрішніх документів»* — `evals/_cases/case-018-uk-document-numbering/document.md`

**Title.** Не визначено, що записати в реєстр минулого року, якщо в ньому не було номерів певного виду документів

**Explanation.** Першого робочого дня нового року реєстратор має внести останній запис про останній присвоєний номер кожного виду документів. Якщо в минулому році жодного документа певного виду не зареєстровано, такого номера немає, і документ не пояснює, що внести в цьому випадку. Реєстратор не знає, як закрити реєстр для такого виду.

**Quotes, in their lines:**

- line 78, § 6. Початок нового року: «Того самого дня реєстратор вносить до реєстру попереднього року останній запис — про останній присвоєний номер кожного виду документів.»

**What the key holds on these lines:**

- `R-7`, residue the case set accepted: Слово «номер» в одному рядку означає весь номер із чотирьох частин, а в інших — порядковий номер; дія за обох значень однакова, тож це кандидат на пастку A04.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The closing entry requires a last number for each type, but a type with no assignments has none. Unlisted in residue. (high)

## U-24 — case-020-uk-stocktake, run 1

Document: *Порядок проведення щорічної інвентаризації товарів* — `evals/_cases/case-020-uk-stocktake/document.md`

**Title.** Немає правила, що робити, якщо головний бухгалтер відсутній у перший день підрахунку

**Explanation.** Витяг із залишками за даними обліку має бути переданий голові комісії до початку підрахунку, але документ не передбачає заміни головного бухгалтера. Якщо він відсутній, голова комісії не має з чим порівнювати фактичну кількість товару, і не зрозуміло, чи можна починати підрахунок. Заміни для цього випадку в документі немає.

**Quotes, in their lines:**

- line 41, § 5. Підрахунок товарів: «Головний бухгалтер у перший день підрахунку до його початку передає голові комісії витяг із залишками товарів за даними обліку.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The required extract has no alternate source if the chief accountant is absent. The commission cannot complete the comparison. Unlisted in residue. (medium)

## U-31 — case-004-uk-window-timber-wall, run 2

Document: *Інструкція з монтажу вікна в стіну каркасної дерев’яної будівлі* — `evals/_cases/case-004-uk-window-timber-wall/document.md`

**Title.** Після послаблення кріплення коробки не сказано, що його треба знову затягнути

**Explanation.** Монтажник послаблює кріплення коробки й виправляє її положення, але документ не велить закріпити коробку знову. Повторна перша перевірка проводиться на незакріпленій коробці, а крок закріплення в послідовності робіт стоїть лише один раз. Монтажник не знає, чи має він повторно закріпити коробку і яким способом.

**Quotes, in their lines:**

- line 69, § Перевірка рівня та діагоналей: «Якщо перша перевірка виявила порушення цих вимог, монтажник послаблює кріплення, виправляє положення коробки та повторює першу перевірку.»
- line 55, § Послідовність робіт: «Закріпити коробку до каркаса способом, визначеним у розділі «Способи кріплення».»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Для випадку, коли друга перевірка виявила перевищення, документ називає видалення піни, але мовчить про кріплення та приклеєну зовнішню стрічку, тому кроки встановлення й закріплення коробки неможливо повторити так, як їх записано.
- `R-3`, residue the case set accepted: До монтажного зазору, який виходить за межі після встановлення коробки в проріз, застосовні два правила: один читач зупиняється й повідомляє керівника дільниці, інший послаблює кріплення та виправляє положення коробки, і документ не каже, яке правило має перевагу. Цей пункт послаблюють заголовок «Дії в разі відхилень прорізу» та слова «не встановлює вікно», які відносять перше правило до часу перед встановленням. Він також близький до A01-1, і багато читачів оцінили б його разом з ним. Залишити його в `residue` або прийняти як частину A01-1.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The first-check correction repeats the check after loosening the fixings but omits securing them again. R-1 covers a different rework stage. Unlisted in residue. (medium)

## U-33 — case-006-uk-accountant-job, run 2

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Звірка банківських залишків не має правила для відсутнього банківського документа

**Explanation.** Бухгалтер має щомісяця звіряти залишки на банківських рахунках, але документ визначає первинний документ лише як рахунок, акт або наказ. Банківська виписка до цього переліку не входить, тому правила запиту й розбіжності для неї не діють. Якщо виписки бракує, бухгалтер не знає, чи це розбіжність, і кого і як має запитати.

**Quotes, in their lines:**

- line 23, § Обов'язки: «Бухгалтер щомісяця, не пізніше п'ятого робочого дня місяця, звіряє за попередній місяць залишки на банківських рахунках Організації та розрахунки з постачальниками.»
- line 12, § Загальні положення: «У цій інструкції первинний документ — це рахунок, акт або наказ, що підтверджує господарську операцію Організації.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: trap

Note: Second reviewer, accepted by the maintainer: An absent statement can be requested as an explanation supporting reconciliation. The discrepancy rule expressly covers missing explanations as well as primary documents. (medium)

## U-34 — case-007-en-office-closing, runs 2, 3 (also U-60)

Document: *Office Closing Checklist* — `evals/_cases/case-007-en-office-closing/document.md`

**Title.** No stand-in when the Head of Operations is also absent

**Explanation.** The Head of Operations replaces the Office Manager on leave or sick days, including as the receiver of reports. If the Head of Operations is also absent, the document gives no other person to receive fault reports or order repairs. The reader cannot tell whom to report to before leaving the building.

**Quotes, in their lines:**

- line 16, § Who closes the office: «On a day when the Office Manager is on leave or off sick, the Head of Operations takes the Office Manager's place in every rule of this checklist, as actor and as receiver of a report.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: The substitution is tied to one day and the fault rule spans two, so when the Office Manager is absent on only one of them, readers differ on who orders the repair.
- `R-5`, residue the case set accepted: The document provides one substitute and no rule for a day when both the Office Manager and the Head of Operations are absent.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Only the Office Manager has a stand-in. Joint absence leaves the closing person without an available recipient or repair decision-maker. Residue R-5. (high)

## U-37 — case-009-en-gifts, run 2

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** No rule for hospitality above its limit that the employee learns about during the occasion

**Explanation.** The document gives the only steps for over-limit hospitality received without approval in the rule for when the employee learns after the occasion, and the excess-payment rule depends on that same timing. Section 7.6's first paragraph covers only gifts, not hospitality. An employee who learns during the occasion, for example during a multi-day trip or stay, is told only not to accept further hospitality. The document does not say whether they must stop, pay the excess, hand anything over, or declare it.

**Quotes, in their lines:**

- line 49, § 7.6 A gift or hospitality above the limit: «When an employee learns after the occasion that a gift given or hospitality received or given was above its limit»
- line 24, § 7.3 Value limits: «An employee must not accept or give a gift or hospitality above its limit unless an exception has been approved under Section 7.5.»
- line 50, § 7.6 A gift or hospitality above the limit: «When the hospitality was received, the employee pays the third party the excess within the same period.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Section 7.7 displaces 7.3, excludes 7.5, keeps 7.4 and is silent on 7.6, so a host who learns later that the refreshments were too costly can read that "its limit" in 7.6 is the limit for refreshments and record it, or that 7.6 does not reach giving to officials and record nothing.
- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Declaration and the acceptance ban apply, but no remedial step addresses hospitality already received when the excess becomes known mid-occasion. Unlisted in residue. (medium)

## U-38 — case-011-en-records-retention, runs 2, 3 (also U-62)

Document: *Records Retention and Destruction Policy* — `evals/_cases/case-011-en-records-retention/document.md`

**Title.** Contract records with no fixed end date have no retention start, so the destruction steps cannot run

**Explanation.** The retention period for contract records runs from the date the agreement ends, but the document does not say what happens to an open-ended agreement with no end date. The owner cannot tell when the retention period ends, so the owner cannot know when to propose the record for destruction within 30 days. The document gives no rule for this case.

**Quotes, in their lines:**

- line 22, § Types of record and their owners: «Contract records are signed agreements with outside parties and their amendments, and the Legal Counsel owns them.»
- line 32, § Retention periods: «Contract records are kept for 6 years from the date on which the agreement ends.»

**What the key holds on these lines:**

- `A05-1`, a defect of A05: The Records Manager answers the Legal Counsel's proposals and the Legal Counsel answers the Records Manager's: two roles approve each other's acts. It was first recorded as residue; two roles approving each other's acts is this kind of problem.
- `R-9`, residue the case set accepted: An agreement with no end date and a person employed twice have no clear start of the period. Each rests on one sentence and is more a hard case than a gap.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The trigger is when the agreement actually ends. An agreement still in force has not started the retention clock, even without a fixed end date. (high)

## U-39 — case-013-en-it-access, run 2

Document: *Procedure for Requesting and Removing Access to IT Systems* — `evals/_cases/case-013-en-it-access/document.md`

**Title.** The procedure does not say whether the old access level is removed when a level is changed

**Explanation.** Section 3 covers requests to change an access level the requester already holds. Section 5 tells the administrator to grant the new access level and record it, but no step says what happens to the previous level. The reader cannot tell whether the old level is replaced or kept alongside the new one.

**Quotes, in their lines:**

- line 28, § 3. Requesting access: «The requester also submits an access request to change an access level that the requester already holds.»
- line 47, § 5. Granting and recording access: «The access level granted.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Section 3 requests a change to the access level already held. Granting the approved changed level implements that replacement. (medium)

## U-43 — case-015-en-customer-letters, run 2

Document: *Guideline on Writing Letters to Customers* — `evals/_cases/case-015-en-customer-letters/document.md`

**Title.** No rule when the checker is absent or does not answer

**Explanation.** A letter that refuses a request, states a sum of money or answers a complaint must be checked before it is sent. If the appointed checker is absent or gives no answer, the author cannot send the letter. The document has no replacement checker and no fallback for this case. The Head of the Department decides only when the author and the checker disagree, not when the checker is unavailable.

**Quotes, in their lines:**

- line 49, § Check by a second person: «The checker confirms the letter or returns it with corrections within one working day.»
- line 51, § Check by a second person: «The author sends the letter only after the checker confirms it or the Head of the Department decides its wording.»

**What the key holds on these lines:**

- `R-4`, residue the case set accepted: The document does not cover the letter that the checker returns with corrections and the author accepts: the checker has not confirmed it and the Head of the Department has no disagreement to decide, so the document gives no step, and no time limit, by which the corrected letter becomes sendable.
- `R-5`, residue the case set accepted: The one working day of the checker has no stated start (the appointment, the receipt of the draft), and the only rule on the start of a time limit ties every limit to the receipt of the message, which cannot apply to the checker.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: An absent checker can block required confirmation, with no substitute or final-send route. A late response alone is a breach. Unlisted in residue. (medium)

## U-45 — case-015-en-customer-letters, run 2

Document: *Guideline on Writing Letters to Customers* — `evals/_cases/case-015-en-customer-letters/document.md`

**Title.** No checker when a Team Lead is the only Team Lead

**Explanation.** A Team Lead's letter that must be checked needs a Team Lead of another team as checker. The document does not say what happens if no other team exists. The Head of the Department then has no one to appoint, and the author has no rule to follow.

**Quotes, in their lines:**

- line 48, § Check by a second person: «When the author is a Team Lead, the Head of the Department appoints the Team Lead of another team as the checker.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: No minimum team count ensures a second Team Lead, and the procedure supplies no alternate checker when there is only one team. Unlisted in residue. (medium)

## U-48 — case-017-en-annual-leave, run 2

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**Title.** Employees who leave without a notice period have no recalculated entitlement.

**Explanation.** The policy covers every employee from the first to the last day of employment, but the only recalculation up to the last day is triggered by a notice period. An employee whose employment ends without written notice, such as immediate dismissal, death in service, or expiry of a fixed-term contract, has no recalculation step. The Payroll Officer is still told to pay the entitlement "as it stands", so the reader cannot apply the part-year rule to that leaver.

**Quotes, in their lines:**

- line 7, § Purpose and scope: «It applies to every employee of the Organisation, full-time and part-time, from the first day of employment to the last.»
- line 58, § Leave during the notice period: «The Head of People recalculates the entitlement up to the last day of employment within three working days of the start of the notice period.»
- line 60, § Leave during the notice period: «The Payroll Officer pays, with the final salary, the remaining entitlement for the leave year of the last day of employment as it stands at the end of that day.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: Leave approved earlier for dates after the last day of employment remains approved, so one Payroll Officer subtracts it from the final payment and another does not.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Payroll needs an updated balance, but the recalculation step starts only on written notice. Notice-free exits lack that step. Unlisted in residue. (high)

## U-50 — case-020-uk-stocktake, runs 2, 3 (also U-71)

Document: *Порядок проведення щорічної інвентаризації товарів* — `evals/_cases/case-020-uk-stocktake/document.md`

**Title.** Не визначено, коли починається підрахунок, якщо склад комісії неповний у перший робочий день грудня

**Explanation.** Пункт 3 прив'язує початок підрахунку до першого робочого дня грудня, але лише за умови, що склад комісії повний на його початок. Пункт 2 каже, що комісія не веде підрахунку, доки склад неповний, однак не визначає, коли підрахунок почнеться, якщо склад не був повним у перший день. Тому читач не знає, коли починати підрахунок і чи діє п'ятиденний строк, а комірник залишається без строку завершення заборони на видачу товарів.

**Quotes, in their lines:**

- line 25, § 3. Строки підрахунку: «Підрахунок починається в перший робочий день грудня, на початок якого склад комісії повний.»
- line 21, § 2. Інвентаризаційна комісія: «Комісія не веде підрахунку, доки її склад неповний.»

**What the key holds on these lines:**

- `R-6`, residue the case set accepted: Документ сам передбачає відсутність директора й охоплює її лише щодо затвердження звіту. Він мовчить про те, хто призначає заміну (і комісію до 15 листопада), коли директор відсутній, а без заміни підрахунок зупиняється і заборона комірникові приймати на облік та видавати товари триває без обмеження.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The start is the first December working day that begins with a full commission. The first calendar working day need not qualify. (high)

## U-52 — case-021-en-lab-spill, run 2

Document: *Standard Operating Procedure: Cleaning a Chemical Spill in a Laboratory* — `evals/_cases/case-021-en-lab-spill/document.md`

**Title.** No step tells the Spill Response Team to put a large spill's material into a waste bag, yet the Team Leader must seal that bag.

**Explanation.** Section 7 requires the Team Leader to seal and label the waste bag for a large spill. The large-spill steps in section 6 never say that the team collects the material or places it in a bag, and the only bag-filling step is for small spills. The reader cannot tell which bag the Team Leader should seal or who fills it, so the seal and label step cannot be carried out as written.

**Quotes, in their lines:**

- line 65, § 7. Waste disposal: «The trained worker, for a small spill, or the Team Leader, for a large spill, seals the waste bag and labels it with the substance and the date.»
- line 58, § 6. Steps for a large spill: «The Spill Response Team puts on the equipment named in section 3 and cleans the spill.»

**What the key holds on these lines:**

- `R-4`, residue the case set accepted: The bag that the trained worker has partly filled before stopping belongs to a large spill, so the trained worker does not seal it, and the document does not say that the Team Leader takes it over.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Section 7 requires a bag, but the large-spill workflow never specifies collecting material into one. R-4 names only a partial-cleanup variant. Unlisted in residue. (medium)

## U-56 — case-002-uk-procurement-committee, run 3

Document: *Положення про закупівельний комітет Організації* — `evals/_cases/case-002-uk-procurement-committee/document.md`

**Title.** Не визначено, що робити, якщо заявку подано без двох пропозицій або пояснення

**Explanation.** Для заявок від 50 000 гривень ініціатор має додати дві пропозиції постачальників або письмове пояснення. Документ не каже, що робить секретар, якщо цього немає: чи повертає заявку, чи передає її Комітету. Секретар не знає, чи має він скликати засідання з такою заявкою.

**Quotes, in their lines:**

- line 28, § Пороги та повноваження: «ініціатор додає щонайменше дві пропозиції постачальників або письмове пояснення»
- line 42, § Засідання, кворум і рішення: «Головуючий скликає засідання не пізніше ніж через десять робочих днів після того, як секретар отримав заявку.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: Комітет отримує щонайменше дві пропозиції, але голосує лише «за» або «проти» погодження закупівлі, і жоден фрагмент не визначає, хто обирає між пропозиціями і чи погодження закріплює постачальника.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The requester must provide offers or a written explanation. The proposed case assumes a breach, which A03 excludes. (high)

## U-57 — case-003-en-onboarding, run 3

Document: *Standard Operating Procedure: Onboarding a New Employee* — `evals/_cases/case-003-en-onboarding/document.md`

**Title.** No rule covers a leaving day after the probation period.

**Explanation.** The scope covers every new employee, and a new employee is any person who has signed a contract. Section 8 applies only when the leaving day falls within the probation period. If an employee leaves after the probation period, the reader has no rule for recovering equipment, archiving the accounts, or disabling and deleting them.

**Quotes, in their lines:**

- line 7, § 1. Scope: «A new employee is a person who has signed an employment contract with the Organisation.»
- line 58, § 8. Leaving during the probation period: «This section applies when the leaving day of a new employee falls within the probation period, whatever the reason for leaving.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: A person who signs the contract and withdraws before the first day is inside the scope but has no leaving day and no probation period, so no rule closes the accounts or releases the prepared equipment.
- `R-9`, residue the case set accepted: For a leaving that is not a decision of the review meeting, such as a resignation, no rule says who records the leaving in the onboarding record. Against it: "keeps the onboarding record" in section 3 can carry it.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Section 8 expressly confines the exit workflow to probation. The general definition of new employee does not extend that exit workflow. (medium)

## U-59 — case-007-en-office-closing, run 3

Document: *Office Closing Checklist* — `evals/_cases/case-007-en-office-closing/document.md`

**Title.** No stand-in when both the Office Manager and the Head of Operations are absent.

**Explanation.** The Head of Operations is the stand-in for the Office Manager, but no rule covers the Head of Operations being absent at the same time. In that case the reader has no one to report a fault to, since reports go to the Office Manager or to the stand-in.

**Quotes, in their lines:**

- line 16, § Who closes the office: «On a day when the Office Manager is on leave or off sick, the Head of Operations takes the Office Manager's place in every rule of this checklist, as actor and as receiver of a report.»
- line 43, § If a step cannot be completed: «reports it to the Office Manager by message before leaving the building.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: The substitution is tied to one day and the fault rule spans two, so when the Office Manager is absent on only one of them, readers differ on who orders the repair.
- `R-5`, residue the case set accepted: The document provides one substitute and no rule for a day when both the Office Manager and the Head of Operations are absent.
- `R-6`, residue the case set accepted: The document uses "the office" and "the building" and does not say if they are one place, so one reader sends the message before the alarm step (or inside the 60 seconds after a remote set) and another sends it at the key safe after locking the main door; the readings differ in sequence.
- `R-9`, residue the case set accepted: The Office Manager can be the person who stays or the closing person (fallback, weekend), and then allows their own stay or receives their own report. A report is not an approval, so it is weak.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The checklist has no fallback for absence of its sole stand-in. No rule directs fault reporting in that case. Residue R-5. (high)

## U-65 — case-015-en-customer-letters, run 3

Document: *Guideline on Writing Letters to Customers* — `evals/_cases/case-015-en-customer-letters/document.md`

**Title.** No checker can be appointed when an Adviser's team has no other Adviser

**Explanation.** The guideline applies to every letter by an Adviser, and some letters must be checked. For an Adviser author, the rule requires the Team Lead to appoint another Adviser of the same team as checker. If the team has only one Adviser, no such checker exists, and the document gives no other way to get the letter checked before it is sent.

**Quotes, in their lines:**

- line 11, § Purpose and scope: «The guideline applies to every letter written by an Adviser or a Team Lead of the Department.»
- line 47, § Check by a second person: «When the author is an Adviser, the Team Lead of that Adviser's team appoints another Adviser of the same team as the checker.»

**What the key holds on these lines:**

- `R-7`, residue the case set accepted: A Team Lead who is the author of a message reviews the risk of their own message and decides alone if it is reassigned. It is weak: the review is supervision, not an approval, and the document does not say that a Team Lead's messages belong to "the team".

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The same-team rule leaves a lone Adviser without an eligible checker or another route to confirmation. Unlisted in residue. (medium)

## U-67 — case-017-en-annual-leave, run 3

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**Title.** Entitlement is not recalculated when employment ends without notice.

**Explanation.** The scope covers every employee from the first to the last day of employment. The recalculation up to the last day is required only inside the notice period, so an ending without notice, such as a fixed-term expiry or a dismissal without notice, has no recalculation. The Payroll Officer is still told to pay the remaining entitlement as it stands on the last day, but the reader has no rule that produces an up-to-date figure for that day.

**Quotes, in their lines:**

- line 57, § Leave during the notice period: «The notice period starts on the day the employee or the Organisation gives written notice of termination and ends on the last day of employment.»
- line 58, § Leave during the notice period: «The Head of People recalculates the entitlement up to the last day of employment within three working days of the start of the notice period.»
- line 60, § Leave during the notice period: «The Payroll Officer pays, with the final salary, the remaining entitlement for the leave year of the last day of employment as it stands at the end of that day.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: Leave approved earlier for dates after the last day of employment remains approved, so one Payroll Officer subtracts it from the final payment and another does not.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The document assigns notice-triggered recalculation only. It never produces an updated balance for final payroll after a notice-free exit. Unlisted in residue. (high)

## U-68 — case-019-en-vehicles, run 3

Document: *Policy on the Use of Company Vehicles* — `evals/_cases/case-019-en-vehicles/document.md`

**Title.** Approved booking of a driver removed for a licence problem is not resolved

**Explanation.** When an authorised employee's licence is suspended, withdrawn or expired, the Fleet Manager removes that employee from the authorised list. That employee then no longer counts as a driver, so the rule that the driver returns the vehicle cannot be applied. The document does not say whether the approved booking is cancelled or who takes over and returns a vehicle that is already out.

**Quotes, in their lines:**

- line 21, § 3. Who may use a vehicle: «An authorised employee whose licence is suspended, withdrawn or expired informs the Fleet Manager on the same day.»
- line 22, § 3. Who may use a vehicle: «The Fleet Manager then removes that employee from the list of authorised employees.»
- line 32, § 4. Booking: «At the end of the booking, the driver returns the vehicle to the Organisation's car park»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: The substitution moves the Fleet Manager's duties, and receiving the keys is the driver's duty, so the document does not say whether the Fleet Manager as driver keeps the keys or hands them to the Operations Director.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Loss of authorisation mid-booking leaves no eligible driver to return the vehicle and no reassignment or recovery procedure. Unlisted in residue. (high)

## U-69 — case-020-uk-stocktake, run 3

Document: *Порядок проведення щорічної інвентаризації товарів* — `evals/_cases/case-020-uk-stocktake/document.md`

**Title.** Відсутність головного бухгалтера унеможливлює витяг із залишками

**Explanation.** Голова комісії має отримати витяг від головного бухгалтера перед початком підрахунку і порівнювати з ним фактичну кількість. Документ не передбачає, що робити, якщо головний бухгалтер відсутній і витяг не передано, тому голова комісії не може виконати порівняння.

**Quotes, in their lines:**

- line 41, § 5. Підрахунок товарів: «Головний бухгалтер у перший день підрахунку до його початку передає голові комісії витяг із залишками товарів за даними обліку.»
- line 51, § 6. Розбіжності: «Голова комісії порівнює фактичну кількість товару кожного найменування з витягом головного бухгалтера.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The required extract comes only from the chief accountant, with no fallback if that person is absent. Unlisted in residue. (medium)

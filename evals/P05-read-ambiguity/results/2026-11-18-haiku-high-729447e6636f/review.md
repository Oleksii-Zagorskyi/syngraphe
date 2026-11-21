# Unmatched findings of A02 — ambiguity — the verdicts

**What was tested.** Each finding below came from heuristic A02, prompt `prompts/P05-read-ambiguity/prompt-02.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — a contradiction, a gap, a term with two meanings, circular authority, an unowned obligation.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.
Notes marked *Second reviewer* hold the verdict of an independent model review, accepted by the maintainer; the word in brackets is that review's confidence.

**Status.** 28 of 28 items ruled.

<details><summary>The instruction A02 obeyed (<code>prompts/P05-read-ambiguity/prompt-02.md</code>)</summary>

Find each ambiguity in the document as a whole.
Report each ambiguity as a separate finding.

A document is ambiguous when two careful readers act on it in two different ways.
Each reader believes that they obey the document.
Each reading has support in the text.

Read the document as the reader who obeys it.
This reader knows only the text of the document.
The reader does not know what the author intended, or the habits of the organisation.
For each instruction, rule or permission, find the answers to these questions:

- What does the reader do, and in which sequence?
- How, where and with what does the reader do it?
- Who does it, and who decides?
- When does the reader do it, and for how long?
- What does the reader get or pay?

If two careful readers get two different answers to one question, report an ambiguity.

The two readings come from two or more passages of the document.
Find these causes:

- Two rules or instructions apply to the same case, and the document does not tell which one applies.
- An exception or a condition is in one passage, and it is not clear to which other passages it applies.
- A reference, for example "the rules above" or "this section", can point to two different parts of the document.
- A condition is in one passage, and it is not clear if a later passage keeps it.

Each reading changes what the reader does, may do or gets.
Write the two readings as two different instructions to the reader.
If you cannot write two different instructions, do not report.
It changes an action, its sequence, a method, a person, an amount, a time limit or a permission.

Do not report these:

- A sentence that has two readings when you read it alone, if no other passage changes its readings.
- A vague word that has only one reading, for example "soon", "reasonable" or "appropriate".
- A question of counting, for example the day from which a time limit starts, if the usual meaning of the words answers it.
- A case in which a person does not do what the document requires, or does it late.
- Two passages that cannot both be true under any reading. That is a contradiction, a different kind of problem.
- One term that the document uses with two meanings. That is a different kind of problem.
- A case that the document does not cover. That is a gap, a different kind of problem.
- Two rules for the same case, if the document tells which one applies, for example with "instead" or "except".

Quote each passage that a reading uses.
In the explanation, write the two readings and what the reader does differently in each reading.

</details>

## U-01 — case-002-uk-procurement-committee, runs 1, 2 (also U-29)

Document: *Положення про закупівельний комітет Організації* — `evals/_cases/case-002-uk-procurement-committee/document.md`

**Title.** Незрозуміло, хто підписує протокол засідання

**Explanation.** Фраза «кожен член Комітету, який вів протокол» може означати, що протокол підписують головуючий і лише той, хто вів протокол (секретар або його заміна). Інше прочитання: підписують головуючий і всі члени Комітету, а відносне речення «який вів протокол» сприймається як застаріле або зайве. У першому випадку підпис ставить одна особа, у другому – всі члени, тому читачі по-різному виконають вимогу про підписання.

**Quotes, in their lines:**

- line 65, § Протокол: «Протокол підписують головуючий і кожен член Комітету, який вів протокол на цьому засіданні.»
- line 63, § Протокол: «Секретар веде протокол засідання і складає його протягом трьох робочих днів після засідання.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Заміну обмежено засіданням, проте протокол складає і надсилає вже після засідання «Секретар», тоді як правило про відсутність кворуму покладає обовʼязок після засідання на виконавця обовʼязків секретаря. Тому за одним прочитанням протокол складає і надсилає виконавець обовʼязків секретаря, а за іншим — призначений секретар.
- `R-4`, residue the case set accepted: «Головуючий» визначено щодо кожного питання, тож на одному засіданні їх може бути двоє, а правило про підписання називає одного. За одним прочитанням протокол підписує лише голова, за іншим — обидва.

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: The relative clause limits member signatures to those who took minutes. R-4 concerns which chair signs. (high)

## U-02 — case-004-uk-window-timber-wall, runs 1, 2, 3 (also U-30, U-55)

Document: *Інструкція з монтажу вікна в стіну каркасної дерев’яної будівлі* — `evals/_cases/case-004-uk-window-timber-wall/document.md`

**Title.** Неясно, що саме монтажник виправляє після зауважень бригадира

**Explanation.** Перше прочитання: монтажник виправляє лише акт і подає його повторно. Друге прочитання: монтажник виправляє саме вікно, наприклад переробляє монтаж, і лише потім подає акт. Документ не каже, чи після такого виправлення бригадир повторно перевіряє вікно на місці.

**Quotes, in their lines:**

- line 82, § Акт монтажу: «Якщо вікно не відповідає цій інструкції або акт не відповідає вікну, бригадир повертає акт монтажникові з письмовими зауваженнями, а монтажник усуває їх і подає акт повторно.»

**What the key holds on these lines:**

- `R-5`, residue the case set accepted: Документ не встановлює строку для усунення зауважень. Обов’язки бригадира щодо повторно поданого акта випливають з попереднього рядка, тому прогалина мала.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The foreperson checks both the installation and the report. The installer corrects whichever failed and resubmits the report for the same check. (high)

## U-04 — case-005-en-spending-authority, run 1

Document: *Spending Approval Matrix* — `evals/_cases/case-005-en-spending-authority/document.md`

**Title.** Unclear whether a request raised within 30 days of another is refused automatically or only when the approver finds it covers part of a purchase

**Explanation.** One reader takes the 30-day rule as making every such request part of the same purchase, so the approver must refuse it and ask for one full request. Another reader takes the approver's duty as triggered only when the approver actually finds that the request covers part of a purchase, so the request can be approved if no partial cover is found. The two readings lead to different decisions by the approver.

**Quotes, in their lines:**

- line 58, § 7. No splitting of a purchase: «A spending request raised within 30 calendar days after another spending request for the same supplier and the same purpose belongs to the same purchase as that other request, whoever raises them.»
- line 59, § 7. No splitting of a purchase: «An approver who finds that a spending request covers only part of a purchase refuses it»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: A request for a following twelve months of an open-ended commitment is required by section 2 and can also be read as a request for only part of a purchase that section 7 tells the approver to refuse.
- `R-4`, residue the case set accepted: A second request for the same supplier and the same purpose raised on day 40 is part of the same purchase by the definition, so one approver refuses it and asks for one request for the combined amount (which can move it to a higher band), while by the 30-day rule read as the limit of "the same purchase" another approver treats it as a new purchase and approves it; the document does not say if the 30-day rule narrows the definition or only adds a presumption to it.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Section 7 establishes which requests belong to one purchase. “Who finds” triggers refusal on discovery and grants no discretion to approve a known split. (high)

## U-06 — case-006-uk-accountant-job, runs 1, 2 (also U-32)

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Незрозуміло, чи починає відлік строку для запису письмова незгода керівника відділу

**Explanation.** За першим прочитанням незгода не є ні виправленим документом, ні поясненням, тому відлік строку не починається, і бухгалтер чекає рішення директора. За другим прочитанням незгода є поясненням, тому дводенний строк на запис починається з її отримання, і бухгалтер має внести запис у цей строк. Отже, у одному й тому самому випадку бухгалтер діятиме по-різному: або чекатиме, або негайно вноситиме запис.

**Quotes, in their lines:**

- line 19, § Обов'язки: «Керівник відділу протягом трьох робочих днів від дня повернення передає бухгалтерові виправлений документ або письмову незгоду із зауваженням.»
- line 20, § Обов'язки: «Строк внесення запису за повернутим документом або за документом, до якого запитано пояснення, бухгалтер відлічує від дня, коли першим отримав виправлений документ, пояснення або рішення директора Організації.»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: Строк бухгалтера починається в день, коли бухгалтер отримує рішення директора Організації, але жодна роль не зобов'язана передати це рішення бухгалтерові чи керівникові відділу.
- `R-4`, residue the case set accepted: Запис, зроблений лише за поясненням, коли для позиції бракувало самого первинного документа, не має строку, бо обидва правила про строк прив'язано до первинного документа, який бухгалтер має в себе.
- `R-6`, residue the case set accepted: Документ не каже, чи є сумнів випадком, коли для запису бракує пояснення. Тому один бухгалтер не вносить сумнівний документ і більше нічого не робить, а інший того самого дня надсилає запит і вносить запис протягом двох робочих днів після отримання пояснення; кожен вважає, що виконує документ.

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: Written disagreement triggers escalation. The absence of a qualifying correction, explanation or decision leaves a timing or handoff gap rather than two supported triggers. (medium)

## U-07 — case-009-en-gifts, run 1

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Unclear what the Chief Executive takes over when the Compliance Officer is involved

**Explanation.** Section 7.1 says the Chief Executive acts in place of the Compliance Officer for gifts the Compliance Officer is offered, receives or gives. One reader takes this to cover only decisions, such as approvals and value setting, so the Compliance Officer still keeps the register and receives returned gifts. Another reader takes it to cover every Compliance Officer role for that gift, including the register entry and the handover of an above-limit gift.

**Quotes, in their lines:**

- line 8, § 7.1 Scope: «For a gift or hospitality that the Compliance Officer is offered, receives or gives, the Chief Executive acts in place of the Compliance Officer.»
- line 30, § 7.4 Declaration: «The Compliance Officer keeps the Gifts and Hospitality Register.»
- line 46, § 7.6 A gift or hospitality above the limit: «the employee hands it, unused, to the Compliance Officer and declares it, both within two working days of learning that it is such a gift.»

**What the key holds on these lines:**

- `A05-1`, a defect of A05: The Compliance Officer decides the Chief Executive's requests and the Chief Executive decides the Compliance Officer's: two roles approve each other's acts. It was first recorded as residue; two roles approving each other's acts is this kind of problem.
- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Section 7.1 substitutes the Chief Executive for the Compliance Officer for that gift, with no limitation to approvals. (high)

## U-08 — case-009-en-gifts, run 1

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Unclear whether an approved above-limit hospitality must still be paid back later

**Explanation.** The first paragraph of Section 7.6 applies only to gifts received without an approved exception. The paragraph on learning after the occasion has no such condition. One reader thinks an approved exception ends the employee's duty, so no excess is paid. Another reader thinks that paragraph applies to any hospitality above its limit, so the employee must record it and pay the third party the excess.

**Quotes, in their lines:**

- line 49, § 7.6 A gift or hospitality above the limit: «When an employee learns after the occasion that a gift given or hospitality received or given was above its limit»
- line 50, § 7.6 A gift or hospitality above the limit: «When the hospitality was received, the employee pays the third party the excess within the same period.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Section 7.7 displaces 7.3, excludes 7.5, keeps 7.4 and is silent on 7.6, so a host who learns later that the refreshments were too costly can read that "its limit" in 7.6 is the limit for refreshments and record it, or that 7.6 does not reach giving to officials and record nothing.
- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The approved-exception condition may carry into the late-discovery paragraph or stop at the first paragraph, changing whether excess is payable. Residue R-3. (high)

## U-09 — case-009-en-gifts, runs 1, 2, 3 (also U-37, U-59)

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Two declaration deadlines for an above-limit gift received without approval

**Explanation.** Section 7.4 requires every accepted gift to be declared within five working days of acceptance. Section 7.6 requires a gift above the limit to be declared within two working days of learning that it is such a gift. The document does not say which deadline applies. One reader uses the five-day period from acceptance, and another uses the two-day period from learning, which can give different due dates.

**Quotes, in their lines:**

- line 33, § 7.4 Declaration: «The employee makes the declaration within five working days of the acceptance or the giving.»
- line 46, § 7.6 A gift or hospitality above the limit: «declares it, both within two working days of learning that it is such a gift.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Sections 7.4 and 7.6 give different deadlines for declaring an accepted gift, without saying whether the second replaces the first. Unlisted in residue. (medium)

## U-10 — case-010-uk-forklift-safety, run 1

Document: *Інструкція з охорони праці під час роботи на навантажувачі на складі* — `evals/_cases/case-010-uk-forklift-safety/document.md`

**Title.** Невизначено, чи може водій працювати після того, як перестав відповідати умовам допуску, але ще до скасування наказом

**Explanation.** Перше прочитання: водій має право працювати до кінця дня, поки начальник складу не скасує допуск наказом. Друге прочитання: щойно умова перестала виконуватися, працівник уже не є водієм, бо допуск визначає це визначення, і він має припинити керування. Документ не каже, що відбувається в проміжку між порушенням умови та наказом.

**Quotes, in their lines:**

- line 21, § Допуск до керування: «Якщо хоча б одна з цих умов перестала виконуватися, начальник складу того самого дня скасовує допуск наказом.»
- line 8, § Загальні положення: «Водій у цій інструкції означає працівника, якого допущено до керування навантажувачем згідно з розділом «Допуск до керування».»

**What the key holds on these lines:**

- `R-4`, residue the case set accepted: Працівник, у якого сьогодні вранці закінчився строк дії висновку медичного огляду, залишається допущеним за наказом, доки начальник складу не скасує допуск «того самого дня»; один читач керує навантажувачем, доки не видано наказ, інший припиняє, щойно умова перестала виконуватися. Прочитання, за яким працівник допущений, доки допуск не скасовано, є сильнішим, тому я ставлю цьому пункту низьку впевненість. Якщо авторові цей пункт не потрібен, досить примітки в залишку.
- `R-5`, residue the case set accepted: Начальник складу мусить діяти того самого дня, але жодна роль не зобов’язана стежити за чинністю посвідчення і висновку медичного огляду чи повідомляти його про це. Саме скасування має відповідального, тож за буквою A06 це не дефект; модель однаково може про нього повідомити. Варто рядка в залишку.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The cross-reference can import continuing eligibility conditions or just admission by order. The cancellation requirement favors continued admission until the order. Residue R-4. (low)

## U-14 — case-012-uk-working-hours, run 1

Document: *Наказ № 41 від 28 вересня 2026 року про зміну режиму роботи з 1 грудня 2026 року* — `evals/_cases/case-012-uk-working-hours/document.md`

**Title.** Незрозуміло, як визначати час закінчення роботи, якщо тривалість дробова

**Explanation.** За першим прочитанням працівник іде о точному часі, наприклад 13:30 при тривалості 4,5 години. За другим прочитанням він іде о найближчій повній годині, тобто о 14:00, бо текст каже «о тій годині». Ця сама неясність є і в правилі для тривалості 4 години або менше.

**Quotes, in their lines:**

- line 54, § Виняток для працівників зі скороченим робочим днем: «закінчує роботу о тій годині, яка настає після 09:00 через встановлену йому тривалість робочого дня.»
- line 56, § Виняток для працівників зі скороченим робочим днем: «закінчує роботу о тій годині, яка настає після 08:00 через встановлену йому тривалість робочого дня.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Правило про неоплачувану перерву стоїть у розділі про обідню перерву працівників загального режиму, а розділ про працівників зі скороченим робочим днем надає власну перерву й не повторює цього правила. Тому читач може застосувати «не оплачується» до кожної перерви в наказі або лише до перерви працівників загального режиму.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The stated duration fixes the clock time, including minutes. Neither formula supports rounding to the hour. (high)

## U-15 — case-012-uk-working-hours, run 1

Document: *Наказ № 41 від 28 вересня 2026 року про зміну режиму роботи з 1 грудня 2026 року* — `evals/_cases/case-012-uk-working-hours/document.md`

**Title.** Незрозуміло, чи обідня перерва скороченого та змінного працівника не оплачується

**Explanation.** За першим прочитанням правило про неоплачувану перерву стосується лише працівників загального режиму, бо воно стоїть в одному розділі з їхньою перервою. Тоді оплата перерви для скороченого робочого дня не визначена. За другим прочитанням це правило діє для всіх обідніх перерв у наказі, і їхня перерва не оплачується.

**Quotes, in their lines:**

- line 34, § Обідня перерва: «Обідня перерва не входить до робочого часу і не оплачується.»
- line 54, § Виняток для працівників зі скороченим робочим днем: «Якщо ця тривалість перевищує 4 години, працівник має обідню перерву з 12:00 до 13:00»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Правило про неоплачувану перерву стоїть у розділі про обідню перерву працівників загального режиму, а розділ про працівників зі скороченим робочим днем надає власну перерву й не повторює цього правила. Тому читач може застосувати «не оплачується» до кожної перерви в наказі або лише до перерви працівників загального режиму.
- `R-2`, residue the case set accepted: Правило про оплату не називає, яких працівників воно стосується, і стоїть у тому самому розділі безпосередньо перед рядком про змінних працівників. Тому один читач застосовує його до перерви змінних працівників (перерва не входить до робочого часу і не оплачується), а інший читач застосовує його лише до загального режиму, бо наказ не змінює режиму роботи змінних працівників. Ці два прочитання різняться тим, що отримує змінний працівник.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The unpaid-break rule may govern every lunch break or only the general schedule. That changes compensation for shortened-day employees. Residue R-1. (high)

## U-16 — case-013-en-it-access, run 1

Document: *Procedure for Requesting and Removing Access to IT Systems* — `evals/_cases/case-013-en-it-access/document.md`

**Title.** Unclear deadline for the alternate owner when a system owner's list is late

**Explanation.** Reader A takes the ten-working-day rule to replace the fifteen-day deadline, so the alternate owner must complete the whole list, including the system owner's own access, within ten working days of the report. Reader B takes the ten-day rule to cover only the system owner's review, while the alternate owner's fifteen-day deadline for the system owner's own access still stands. The two readings give different deadlines for the same review.

**Quotes, in their lines:**

- line 58, § 6. Periodic review: «The Service Desk reports each list not returned in time to the alternate owner, who then completes that review within ten working days of the report.»
- line 57, § 6. Periodic review: «the alternate owner reviews it in the same way within the same fifteen working days»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: The only escalation of a late review goes to the alternate owner, so no rule handles a review that the alternate owner does not complete in time.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The alternate’s fifteen-day duty covers the owner’s access. The ten-day escalation transfers the outstanding list review without extending that separate duty. (medium)

## U-19 — case-015-en-customer-letters, run 1

Document: *Guideline on Writing Letters to Customers* — `evals/_cases/case-015-en-customer-letters/document.md`

**Title.** Unclear whether a letter returned with corrections must be checked again

**Explanation.** Reading one: once the checker returns the letter with corrections, the author makes them and sends the letter without another check. Reading two: the letter is not yet confirmed, so the author must send the corrected letter back to the checker before sending. The document does not state which reading applies.

**Quotes, in their lines:**

- line 49, § Check by a second person: «The checker confirms the letter or returns it with corrections within one working day.»
- line 51, § Check by a second person: «The author sends the letter only after the checker confirms it or the Head of the Department decides its wording.»

**What the key holds on these lines:**

- `R-4`, residue the case set accepted: The document does not cover the letter that the checker returns with corrections and the author accepts: the checker has not confirmed it and the Head of the Department has no disagreement to decide, so the document gives no step, and no time limit, by which the corrected letter becomes sendable.
- `R-5`, residue the case set accepted: The one working day of the checker has no stated start (the appointment, the receipt of the draft), and the only rule on the start of a time limit ties every limit to the receipt of the message, which cannot apply to the checker.

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: The send rule expressly requires confirmation or a wording decision. R-4 identifies a scope gap in obtaining confirmation after accepted corrections. (high)

## U-21 — case-017-en-annual-leave, run 1

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**Title.** Unclear whether leave is rounded up always or to the nearest half day

**Explanation.** The rule says the result is rounded up, but also says it is rounded to the nearest half day. One reader always rounds up to the next half day. Another reader rounds to whichever half day is nearer, which can be down, so the entitlement amount differs.

**Quotes, in their lines:**

- line 24, § Entitlement and counting: «Only the final result is rounded up, to the nearest half day.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: trap

Note: Second reviewer, accepted by the maintainer: “Up” specifies the direction of rounding, and half-days specify the increment. The prompt excludes alternate readings confined to one sentence. (high)

## U-25 — case-019-en-vehicles, runs 1, 3 (also U-71)

Document: *Policy on the Use of Company Vehicles* — `evals/_cases/case-019-en-vehicles/document.md`

**Title.** Fuel card purchases: are they reimbursed to the driver?

**Explanation.** One reading is that fuel bought with the company fuel card is paid by the Organisation, so the driver submits only personal payments such as cash fuel, tolls and parking. The other reading is that the driver pays for fuel with the card and must hand in the fuel receipts for reimbursement, since the text lists fuel receipts with the others. The text does not say whether card purchases are claimed.

**Quotes, in their lines:**

- line 42, § 6. Fuel and costs: «Each vehicle carries a fuel card, and the driver pays for fuel with that card.»
- line 45, § 6. Fuel and costs: «The driver hands the fuel, toll and parking receipts to the Finance Officer»

**What the key holds on these lines:**

- `R-6`, residue the case set accepted: In section 6 "pays personally" means "pays out of pocket and is reimbursed", and the reimbursement line has no exception for a private trip. One reader of section 5 bears the fuel cost; another hands the receipt to the Finance Officer and is reimbursed, and the Finance Officer can pay or refuse. Each obeys the document. The same doubt covers the tolls and the parking fees of a private trip. The readings differ in an amount and in what the reader gets. It can also be reported as A04 (one phrase, two meanings), with lower confidence (0.2).

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The payment sequence suggests submitting only out-of-pocket receipts, but the unqualified receipt rule also supports submitting fuel-card receipts. Unlisted in residue. (medium)

## U-26 — case-020-uk-stocktake, runs 1, 2, 3 (also U-50, U-72)

Document: *Порядок проведення щорічної інвентаризації товарів* — `evals/_cases/case-020-uk-stocktake/document.md`

**Title.** Незрозуміло, чи обмеження в п'ять робочих днів рахується від початку підрахунку, чи лише за дні з повним складом комісії

**Explanation.** За першим прочитанням п'ять робочих днів відлічуються від початку підрахунку, і дні з неповним складом комісії входять до цього строку, тож підрахунок може не встигнути завершитися. За другим прочитанням до строку входять лише дні, коли склад комісії повний, а дні призупинення не рахуються, тож підрахунок може тривати довше п'яти календарних робочих днів. Текст дає підстави для обох прочитань.

**Quotes, in their lines:**

- line 26, § 3. Строки підрахунку: «Підрахунок триває не довше ніж пʼять робочих днів, у кожен з яких склад комісії повний увесь день.»
- line 21, § 2. Інвентаризаційна комісія: «Комісія не веде підрахунку, доки її склад неповний.»

**What the key holds on these lines:**

- `R-5`, residue the case set accepted: Документ встановлює пʼятиденний строк підрахунку й мовчить про те, що робить комісія, коли строк минув, а підрахунок не завершено. Слабке, бо обовʼязок дотримати цього строку покладено на визначену роль.
- `R-6`, residue the case set accepted: Документ сам передбачає відсутність директора й охоплює її лише щодо затвердження звіту. Він мовчить про те, хто призначає заміну (і комісію до 15 листопада), коли директор відсутній, а без заміни підрахунок зупиняється і заборона комірникові приймати на облік та видавати товари триває без обмеження.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Section 3 expressly counts working days on which the commission is complete all day. Section 2 independently bars counting stock with an incomplete commission. (high)

## U-33 — case-008-uk-complaints, run 2

Document: *Порядок розгляду скарг клієнтів* — `evals/_cases/case-008-uk-complaints/document.md`

**Title.** Незрозуміло, чи лист на поштову адресу має пересилатися на електронну адресу

**Explanation.** Поштовий лист є окремим каналом, але правило про пересилання стосується скарги, отриманої «в інший спосіб». Одне читання: лист реєструє оператор напряму, пересилання не потрібне. Інше читання: будь-яка скарга, отримана не на електронну адресу, включно з листом, має бути переслана працівником на електронну адресу протягом робочого дня, і лише потім зареєстрована.

**Quotes, in their lines:**

- line 16, § Канали надходження: «Клієнт надсилає лист на поштову адресу Організації.»
- line 21, § Канали надходження: «Працівник Організації, який отримав скаргу в інший спосіб, не пізніше наступного робочого дня пересилає її на електронну адресу для скарг.»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: Скарга, отримана «в інший спосіб», не надходить жодним із каналів так, як їх сформульовано в переліку (у кожному діє клієнт), тож день її надходження, а з ним і строк реєстрації, не визначено. Природне прочитання таке: переслане повідомлення надходить каналом електронної адреси для скарг у день, коли його переслано, і тому впевненість низька.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: “Another way” follows the list of four channels and therefore excludes postal complaints, which are expressly listed. (high)

## U-34 — case-009-en-gifts, run 2

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Unclear whether the Chief Executive takes over all Compliance Officer duties for the Compliance Officer's own gifts

**Explanation.** Under one reading, the Chief Executive only takes the Compliance Officer's decision role under Section 7.5 for the Compliance Officer's own gifts, and the Compliance Officer still keeps the register and handles returns under 7.4 and 7.6. Under another reading, the Chief Executive replaces the Compliance Officer for every duty in Section 7, including keeping the register, setting values and returning gifts. The document does not say which duties transfer.

**Quotes, in their lines:**

- line 8, § 7.1 Scope: «For a gift or hospitality that the Compliance Officer is offered, receives or gives, the Chief Executive acts in place of the Compliance Officer.»
- line 30, § 7.4 Declaration: «The Compliance Officer keeps the Gifts and Hospitality Register.»

**What the key holds on these lines:**

- `A05-1`, a defect of A05: The Compliance Officer decides the Chief Executive's requests and the Chief Executive decides the Compliance Officer's: two roles approve each other's acts. It was first recorded as residue; two roles approving each other's acts is this kind of problem.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The scope clause transfers the Compliance Officer’s role for the gift itself, including register duties for that gift. (high)

## U-38 — case-009-en-gifts, runs 2, 3 (also U-60)

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Two deadlines for declaring an over-limit gift given or hospitality: ten working days from learning, or five working days from giving

**Explanation.** Under Section 7.6, an employee who learns after the occasion that a gift given or hospitality was above its limit records it within ten working days of learning it. Under Section 7.4, the same declaration must be made within five working days of the acceptance or giving. The two readings give different deadlines, and the document does not say which one governs this case.

**Quotes, in their lines:**

- line 49, § 7.6 A gift or hospitality above the limit: «the employee records it in the declaration within ten working days of learning it.»
- line 33, § 7.4 Declaration: «The employee makes the declaration within five working days of the acceptance or the giving.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Section 7.7 displaces 7.3, excludes 7.5, keeps 7.4 and is silent on 7.6, so a host who learns later that the refreshments were too costly can read that "its limit" in 7.6 is the limit for refreshments and record it, or that 7.6 does not reach giving to officials and record nothing.
- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Section 7.4 requires the initial declaration. Section 7.6 gives a separate deadline for recording information learned later in that declaration. (high)

## U-39 — case-010-uk-forklift-safety, run 2

Document: *Інструкція з охорони праці під час роботи на навантажувачі на складі* — `evals/_cases/case-010-uk-forklift-safety/document.md`

**Title.** Незрозуміло, хто має переходити проїзд лише на позначеному переході

**Explanation.** Речення має підмет «проїзд», а дія «навіть працюючи» стосується людини. Перше прочитання: правило стосується працівників, які йдуть пішки, і навіть працюючи вони перетинають проїзд лише на переході. Друге прочитання: правило стосується будь-кого, хто працює, зокрема водія навантажувача, тож водій має переїжджати лише через перехід. Для водія навантажувача ці прочитання дають різні дії.

**Quotes, in their lines:**

- line 56, § Пішоходи та позначені зони: «Працівник, який іде пішки, рухається пішохідними доріжками, а проїзд, навіть працюючи, перетинає лише на позначеному переході.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: The employee walking on foot is the grammatical subject. The roadway is what the pedestrian crosses. (high)

## U-40 — case-010-uk-forklift-safety, run 2

Document: *Інструкція з охорони праці під час роботи на навантажувачі на складі* — `evals/_cases/case-010-uk-forklift-safety/document.md`

**Title.** Незрозуміло, де діє обмеження 3 кілometри на годину для вузьких проїздів

**Explanation.** Перше прочитання: обмеження 3 км/год діє у вузьких проїздах будь-де, зокрема на вантажному майданчику. Друге прочитання: воно діє лише на території складу, а на майданчику водій рухається зі швидкістю 10 км/год. Текст не каже, чи слово «проїздах» стосується і майданчика, тому водій може обрати різну швидкість.

**Quotes, in their lines:**

- line 39, § Швидкість руху: «Замість цих двох обмежень діє обмеження 3 кілометри на годину в проїздах завширшки менше ніж 3 метри, у воротах складу та на рампі між складом і майданчиком.»
- line 38, § Швидкість руху: «На вантажному майданчику водій рухається зі швидкістю не більше ніж 10 кілометрів на годину.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: trap

Note: Second reviewer, accepted by the maintainer: “Instead of these two limits” expressly makes the narrow-passage limit override both the warehouse and yard defaults. (high)

## U-49 — case-018-uk-document-numbering, run 2

Document: *Стандарт Організації СТО 07 «Нумерація та реєстрація внутрішніх документів»* — `evals/_cases/case-018-uk-document-numbering/document.md`

**Title.** Не зрозуміло, перевірку якого реєстру має на увазі правило про виправлення помилок у реєстрах минулих років

**Explanation.** Розділ 6 дозволяє вносити до реєстрів минулих років виправлення помилок, про які повідомлено після перевірки за розділом 4. Це можна прочитати двома способами. Перше: можна виправляти будь-які помилки, про які повідомлено після будь-якої перевірки, зокрема перевірки інших років або інших реєстрів. Друге: можна виправляти лише помилки, знайдені під час перевірки того самого реєстру минулого року. Від цього залежить, які записи минулих років можна змінювати.

**Quotes, in their lines:**

- line 79, § 6. Початок нового року: «виправлення помилок, про які реєстраторові повідомлено після перевірки за розділом 4»
- line 56, § 4. Реєстри: «Особа, яка перевіряла реєстр, письмово повідомляє реєстраторові про виявлені помилки в день завершення перевірки.»

**What the key holds on these lines:**

- `R-6`, residue the case set accepted: У підрозділу один реєстр на рік, а до реєстрів минулих років після перевірки ще вносять позначки й виправлення; слова «реєстри всіх підрозділів» не кажуть, чи щоквартальна перевірка охоплює лише реєстр поточного року чи реєстри всіх років, тож двоє перевіряльників перевіряють різні реєстри.
- `R-8`, residue the case set accepted: Документ охоплює помилку, виявлену перевіркою, і номер, присвоєний помилково, але не має правила для помилки в записі, яку реєстратор виявив сам, без перевірки; у реєстрі минулого року останній рядок забороняє таке виправлення.

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: Section 4 ties notices to errors found in the register checked. R-6 concerns which years are checked, a different ambiguity. (high)

## U-53 — case-002-uk-procurement-committee, run 3

Document: *Положення про закупівельний комітет Організації* — `evals/_cases/case-002-uk-procurement-committee/document.md`

**Title.** Незрозуміло, хто підписує протокол засідання

**Explanation.** За першим читанням підписують лише головуючий і секретар, бо фраза «який вів протокол» обмежує коло підписантів тим, хто його вів. За другим читанням підписують головуючий і всі члени Комітету, бо слова «кожен член Комітету» стосуються всіх членів. Читачі по-різному визначать, чиї підписи потрібні на протоколі.

**Quotes, in their lines:**

- line 65, § Протокол: «Протокол підписують головуючий і кожен член Комітету, який вів протокол на цьому засіданні.»

**What the key holds on these lines:**

- `R-4`, residue the case set accepted: «Головуючий» визначено щодо кожного питання, тож на одному засіданні їх може бути двоє, а правило про підписання називає одного. За одним прочитанням протокол підписує лише голова, за іншим — обидва.

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: The restrictive clause requires signatures only from members who took minutes. Reading it as requiring every member’s signature discards the clause. (high)

## U-57 — case-007-en-office-closing, run 3

Document: *Office Closing Checklist* — `evals/_cases/case-007-en-office-closing/document.md`

**Title.** Unclear which day triggers the Head of Operations' substitution for publishing the rota

**Explanation.** Reading one: the substitution applies on the day the action is done, so if the Office Manager is on leave on the last working day of the month before, the Head of Operations publishes the rota. Reading two: the substitution refers only to the day of duty covered by the rota, so the Office Manager publishes it even while on leave. The two readings name a different person to publish the rota.

**Quotes, in their lines:**

- line 16, § Who closes the office: «On a day when the Office Manager is on leave or off sick, the Head of Operations takes the Office Manager's place in every rule of this checklist, as actor and as receiver of a report.»
- line 13, § Who closes the office: «The Office Manager publishes the closing rota for each month no later than the last working day of the month before.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: The substitution is tied to one day and the fault rule spans two, so when the Office Manager is absent on only one of them, readers differ on who orders the repair.
- `R-5`, residue the case set accepted: The document provides one substitute and no rule for a day when both the Office Manager and the Head of Operations are absent.
- `R-10`, residue the case set accepted: The fallback presupposes a named duty officer; a careful reader still applies it by analogy, so it is weak.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The all-rules substitution applies on the day the publishing duty falls due. The text supplies no link to the dates listed on the rota. (high)

## U-61 — case-009-en-gifts, run 3

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Unclear whether an approval given after the gift was accepted counts as an approved exception

**Explanation.** Section 7.5 requires the request to be sent beforehand and says the employee treats the request as refused until it is approved. Reader one reads a later approval as an approved exception, so the gift need not be handed over under Section 7.6. Reader two reads the rule as requiring approval before acceptance, so a gift accepted while the request was still refused must be handed over and declared.

**Quotes, in their lines:**

- line 38, § 7.5 Exceptions: «An employee who wishes to accept or give a gift or hospitality above its limit sends a written request to the Compliance Officer beforehand.»
- line 42, § 7.5 Exceptions: «Until a request is approved, the employee treats it as refused.»
- line 46, § 7.6 A gift or hospitality above the limit: «When an employee has received, without an approved exception, a gift above the gift limit or a money gift»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Section 7.5 explicitly treats pending requests as refused. Accepting before approval is a breach, which A02 excludes. (high)

## U-62 — case-010-uk-forklift-safety, run 3

Document: *Інструкція з охорони праці під час роботи на навантажувачі на складі* — `evals/_cases/case-010-uk-forklift-safety/document.md`

**Title.** Несправність, виявлена після події, може оброблятися двома різними порядками

**Explanation.** Після події навантажувач має залишатися без змін, доки його не огляне інженер з охорони праці. Але правило про несправність, причину якої водій не знає, каже вважати її не наслідком події, тому за порядком перевірки перед зміною треба викликати механіка. Один читач після події одразу викликає механіка і дозволяє роботу після його запису. Другий читач чекає огляду інженера і не чіпає навантажувач до того часу.

**Quotes, in their lines:**

- line 30, § Перевірка перед зміною: «Несправність, причини якої водій не знає, вважають такою, що не є наслідком події.»
- line 73, § Дії після події: «Начальник зміни зберігає місце події та навантажувач без змін, доки їх не огляне інженер з охорони праці, крім змін, потрібних для порятунку людей.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: Коли вантаж притиснув людину, неясно, чи виняток для порятунку людей, сформульований для обов’язку начальника зміни, знімає з водія заборону піднімати й опускати вантаж, коли людина перебуває ближче ніж 2 метри від навантажувача.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The post-incident rule preserves the forklift until inspection. Presuming an unknown fault unrelated does not lift the separate duty triggered by the incident. (medium)

## U-66 — case-012-uk-working-hours, run 3

Document: *Наказ № 41 від 28 вересня 2026 року про зміну режиму роботи з 1 грудня 2026 року* — `evals/_cases/case-012-uk-working-hours/document.md`

**Title.** Незрозуміло, котра година закінчення роботи, якщо тривалість не ціла кількість годин

**Explanation.** Правило каже, що працівник закінчує роботу о «тій годині», яка настає через встановлену тривалість після 09:00. Якщо тривалість не ціла, наприклад 7,5 години, такої повної години немає. Один читач завершить роботу о 16:30, а інший округлить час до 16:00 або до 17:00 і запише його в аркуші ознайомлення.

**Quotes, in their lines:**

- line 54, § Виняток для працівників зі скороченим робочим днем: «закінчує роботу о тій годині, яка настає після 09:00 через встановлену йому тривалість робочого дня»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Правило про неоплачувану перерву стоїть у розділі про обідню перерву працівників загального режиму, а розділ про працівників зі скороченим робочим днем надає власну перерву й не повторює цього правила. Тому читач може застосувати «не оплачується» до кожної перерви в наказі або лише до перерви працівників загального режиму.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Adding the specified duration yields an exact end time. The acknowledgement sheet records that time and supplies no rounding rule. (high)

## U-68 — case-017-en-annual-leave, run 3

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**Title.** Rounding rule for leave entitlement is unclear: round up always, or round to the nearest half day?

**Explanation.** The phrase "rounded up, to the nearest half day" can be read two ways. One reader rounds every result up to the next half day, so 6.6 days becomes 7.0. Another reader rounds to the nearest half day, so 6.6 days becomes 6.5. The two readings give different entitlements for part-year employees.

**Quotes, in their lines:**

- line 24, § Entitlement and counting: «Only the final result is rounded up, to the nearest half day.»
- line 22, § Entitlement and counting: «An employee employed for only part of a leave year is entitled to a share of that amount in proportion to the calendar days employed in it.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The entitlement formula supplies the input and “up” fixes the rounding direction. A02 excludes a reading dispute confined to one sentence. (high)

## U-75 — case-021-en-lab-spill, run 3

Document: *Standard Operating Procedure: Cleaning a Chemical Spill in a Laboratory* — `evals/_cases/case-021-en-lab-spill/document.md`

**Title.** Unclear who reports a spill that became large after a trained worker started cleaning it

**Explanation.** A trained worker who finds that a small spill is large stops and follows Section 6. The report rules name the trained worker only for a small spill that was cleaned, and name the Team Leader for a large spill. Reader A reads that the trained worker, who partly cleaned before stopping, must file a report to the Laboratory Manager. Reader B reads that the trained worker files no report, and only the Team Leader reports to the Safety Manager.

**Quotes, in their lines:**

- line 48, § 5. Steps for a small spill: «A trained worker who finds at any step that the spill is a large spill stops and follows section 6 as the discoverer.»
- line 70, § 8. Reporting the spill: «The trained worker who cleaned a small spill submits a spill report to the Laboratory Manager within 24 hours after the cleaning ends.»
- line 73, § 8. Reporting the spill: «The Team Leader submits a spill report on a large spill to the Safety Manager within 24 hours after the room is reopened.»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: Section 5 lists the disposal as the last step, so the 24 hours can start when the substance is in the bag or when the bag reaches the store, and the two starts differ by hours at most.
- `R-3`, residue the case set accepted: A worker who starts on a spill and then finds that it is large has used the kit, but the spill is a large spill, and the restocking duty covers only "each small spill"; the kit of that room has no rule for restocking.
- `R-4`, residue the case set accepted: The bag that the trained worker has partly filled before stopping belongs to a large spill, so the trained worker does not seal it, and the document does not say that the Team Leader takes it over.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Once reclassified, the spill follows the large-spill procedure. Partial work does not make it a small spill cleaned by the worker. (high)

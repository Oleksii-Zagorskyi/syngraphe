# Unmatched findings of A02 — ambiguity — the verdicts

**What was tested.** Each finding below came from heuristic A02, prompt `prompts/P05-read-ambiguity/prompt-03.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — a contradiction, a gap, a term with two meanings, circular authority, an unowned obligation.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.

**Status.** 0 of 17 items ruled.

<details><summary>The instruction A02 obeyed (<code>prompts/P05-read-ambiguity/prompt-03.md</code>)</summary>

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

Before you report, look for a passage that decides between the two readings.
Read the whole document for it.
These passages decide:

- A clause that limits a rule to some persons or cases, for example "the members who took minutes".
- A passage that replaces a rule, for example with "instead of", "except" or "in place of".
- A definition that tells what a term or a role includes.
- A second time limit that starts from a different event, for example from the day that the reader learns a fact.

If a passage decides, do not report.

Do not report these:

- A sentence that has two readings when you read it alone, if no other passage changes its readings.
- A vague word that has only one reading, for example "soon", "reasonable" or "appropriate".
- A question of counting, for example the day from which a time limit starts, if the usual meaning of the words answers it.
- A case in which a person does not do what the document requires, or does it late.
- Two passages that cannot both be true under any reading. That is a contradiction, a different kind of problem.
- One term that the document uses with two meanings. That is a different kind of problem.
- A case that the document does not cover. That is a gap, a different kind of problem.
- A role that approves its own act, or two roles that approve the acts of each other. That is a different kind of problem.
- An action that the document requires and gives to no role. That is a different kind of problem.
- Two rules for the same case, if the document tells which one applies, for example with "instead" or "except".

Quote each passage that a reading uses.
In the explanation, write the two readings and what the reader does differently in each reading.

</details>

## U-01 — case-002-uk-procurement-committee, run 1

Document: *Положення про закупівельний комітет Організації* — `evals/_cases/case-002-uk-procurement-committee/document.md`

**Title.** Незрозуміло, хто, крім головуючого, підписує протокол засідання

**Explanation.** Фраза «який вів протокол» можна прочитати двояко. За першим прочитанням підписують головуючий і лише той, хто вів протокол, тобто секретар або виконавець його обов'язків. За другим прочитанням підписують головуючий і кожен член Комітету, який брав участь у засіданні. Тому кількість підписантів і дії членів Комітету залежать від читання.

**Quotes, in their lines:**

- line 65, § Протокол: «Протокол підписують головуючий і кожен член Комітету, який вів протокол на цьому засіданні.»

**What the key holds on these lines:**

- `R-4`, residue the case set accepted: «Головуючий» визначено щодо кожного питання, тож на одному засіданні їх може бути двоє, а правило про підписання називає одного. За одним прочитанням протокол підписує лише голова, за іншим — обидва.

Verdict: 

Note: 

## U-03 — case-004-uk-window-timber-wall, run 1

Document: *Інструкція з монтажу вікна в стіну каркасної дерев’яної будівлі* — `evals/_cases/case-004-uk-window-timber-wall/document.md`

**Title.** Незрозуміло, чи мусить монтажник усувати невідповідність самого вікна, а не лише акта

**Explanation.** Перше прочитання: монтажник виправляє лише текст акта і подає його повторно, а вікно залишається таким, як є. Друге прочитання: «їх» стосується і невідповідності вікна інструкції, тому монтажник має усунути й її, а потім подати акт. Текст не розрізняє зауваження до вікна і до акта, тому монтажник може діяти по-різному.

**Quotes, in their lines:**

- line 82, § Акт монтажу: «Якщо вікно не відповідає цій інструкції або акт не відповідає вікну, бригадир повертає акт монтажникові з письмовими зауваженнями, а монтажник усуває їх і подає акт повторно.»

**What the key holds on these lines:**

- `R-5`, residue the case set accepted: Документ не встановлює строку для усунення зауважень. Обов’язки бригадира щодо повторно поданого акта випливають з попереднього рядка, тому прогалина мала.

Verdict: 

Note: 

## U-05 — case-009-en-gifts, run 1

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Unclear whether the excess payment applies only to late-learned hospitality

**Explanation.** Reading one: the payment duty sits in the paragraph about learning after the occasion, so an employee who knowingly accepted hospitality above the limit owes no payment and only declares it. Reading two: the sentence "When the hospitality was received" is a standalone rule, so every over-limit hospitality received without approval must be paid for within ten working days. The text does not say which condition the payment sentence depends on.

**Quotes, in their lines:**

- line 50, § 7.6 A gift or hospitality above the limit: «When the hospitality was received, the employee pays the third party the excess within the same period.»
- line 49, § 7.6 A gift or hospitality above the limit: «When an employee learns after the occasion that a gift given or hospitality received or given was above its limit»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Section 7.7 displaces 7.3, excludes 7.5, keeps 7.4 and is silent on 7.6, so a host who learns later that the refreshments were too costly can read that "its limit" in 7.6 is the limit for refreshments and record it, or that 7.6 does not reach giving to officials and record nothing.
- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.

Verdict: 

Note: 

## U-06 — case-009-en-gifts, run 1

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Unclear whether the approved-exception condition carries into the late-learning rule

**Explanation.** Reading one: the condition "without an approved exception" appears only in the first paragraph, so the late-learning rule applies even when an exception was approved beforehand, and the employee must pay the excess. Reading two: the exception condition still governs, so no payment is due when an approved exception covers the hospitality. The text uses this condition in one passage and drops it in the next.

**Quotes, in their lines:**

- line 46, § 7.6 A gift or hospitality above the limit: «When an employee has received, without an approved exception, a gift above the gift limit or a money gift»
- line 50, § 7.6 A gift or hospitality above the limit: «When the hospitality was received, the employee pays the third party the excess within the same period.»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: 

Note: 

## U-08 — case-013-en-it-access, runs 1, 2 (also U-26)

Document: *Procedure for Requesting and Removing Access to IT Systems* — `evals/_cases/case-013-en-it-access/document.md`

**Title.** Unclear scope of the alternate owner's review after a missed list

**Explanation.** Reading one: when the system owner does not return the list, the alternate owner must review every access on the whole list within ten working days. Reading two: the alternate owner only completes the part the text assigns to them, the system owner's own access, within ten working days. The phrase "that review" does not say which review is meant, so the reader checks a different set of accesses and does a different amount of work.

**Quotes, in their lines:**

- line 58, § 6. Periodic review: «The Service Desk reports each list not returned in time to the alternate owner, who then completes that review within ten working days of the report.»
- line 57, § 6. Periodic review: «the alternate owner reviews it in the same way within the same fifteen working days»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: The only escalation of a late review goes to the alternate owner, so no rule handles a review that the alternate owner does not complete in time.

Verdict: 

Note: 

## U-09 — case-015-en-customer-letters, runs 1, 2 (also U-27)

Document: *Guideline on Writing Letters to Customers* — `evals/_cases/case-015-en-customer-letters/document.md`

**Title.** Unclear whether a letter returned with corrections must go back to the checker before sending

**Explanation.** Reading 1: the author applies the checker's corrections, sends the letter back, and sends it only after a second confirmation within one working day. Reading 2: the checker's return with corrections already settles the wording, so the author can send the corrected letter without another confirmation. The text offers confirming or returning as two separate outcomes, but it does not say what happens after a return. The two readings lead to different steps and different timing.

**Quotes, in their lines:**

- line 49, § Check by a second person: «The checker confirms the letter or returns it with corrections within one working day.»
- line 51, § Check by a second person: «The author sends the letter only after the checker confirms it or the Head of the Department decides its wording.»

**What the key holds on these lines:**

- `R-4`, residue the case set accepted: The document does not cover the letter that the checker returns with corrections and the author accepts: the checker has not confirmed it and the Head of the Department has no disagreement to decide, so the document gives no step, and no time limit, by which the corrected letter becomes sendable.
- `R-5`, residue the case set accepted: The one working day of the checker has no stated start (the appointment, the receipt of the draft), and the only rule on the start of a time limit ties every limit to the receipt of the message, which cannot apply to the checker.

Verdict: 

Note: 

## U-12 — case-017-en-annual-leave, runs 1, 2 (also U-29)

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**Title.** Rounding rule can be read as rounding up or as rounding to the nearest half day

**Explanation.** The phrase 'rounded up' suggests that any fraction is raised to the next half day. The phrase 'to the nearest half day' suggests ordinary rounding, where a fraction below the midpoint is lowered. For an entitlement of 25.2 days, one reader records 25.5 days and another records 25.0 days, so the final entitlement amount differs.

**Quotes, in their lines:**

- line 24, § Entitlement and counting: «Only the final result is rounded up, to the nearest half day.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-14 — case-019-en-vehicles, runs 1, 3 (also U-42)

Document: *Policy on the Use of Company Vehicles* — `evals/_cases/case-019-en-vehicles/document.md`

**Title.** Unclear whether fuel paid with the vehicle's fuel card is reimbursed to the driver

**Explanation.** Reading one: the fuel card is paid by the Organisation, so the driver hands in only personal fuel receipts and is not reimbursed for card fuel. Reading two: the driver pays for fuel with the card and hands in all fuel receipts, so the Finance Officer reimburses those amounts. The text says the driver 'pays' with the card and then lists 'fuel' receipts for reimbursement without saying which fuel purchases are covered.

**Quotes, in their lines:**

- line 42, § 6. Fuel and costs: «Each vehicle carries a fuel card, and the driver pays for fuel with that card.»
- line 45, § 6. Fuel and costs: «The driver hands the fuel, toll and parking receipts to the Finance Officer, who reimburses only the amounts supported by a receipt, within ten working days of receiving it.»

**What the key holds on these lines:**

- `R-6`, residue the case set accepted: In section 6 "pays personally" means "pays out of pocket and is reimbursed", and the reimbursement line has no exception for a private trip. One reader of section 5 bears the fuel cost; another hands the receipt to the Finance Officer and is reimbursed, and the Finance Officer can pay or refuse. Each obeys the document. The same doubt covers the tolls and the parking fees of a private trip. The readings differ in an amount and in what the reader gets. It can also be reported as A04 (one phrase, two meanings), with lower confidence (0.2).

Verdict: 

Note: 

## U-15 — case-020-uk-stocktake, run 1

Document: *Порядок проведення щорічної інвентаризації товарів* — `evals/_cases/case-020-uk-stocktake/document.md`

**Title.** Незрозуміло, чи дні з неповним складом комісії входять до п'яти робочих днів підрахунку

**Explanation.** Одне прочитання: п'ять робочих днів є фіксованим вікном, і якщо склад неповний, підрахунок у цей день не ведеться, тож його треба завершити в межах тих самих п'яти днів. Друге прочитання: у п'ять днів зараховуються лише дні з повним складом, тому при неповному складі підрахунок призупиняється і може тривати довше п'яти робочих днів. Від цього залежить, чи може голова комісії продовжувати підрахунок після п'ятого робочого дня.

**Quotes, in their lines:**

- line 26, § 3. Строки підрахунку: «Підрахунок триває не довше ніж пʼять робочих днів, у кожен з яких склад комісії повний увесь день.»
- line 21, § 2. Інвентаризаційна комісія: «Комісія не веде підрахунку, доки її склад неповний.»

**What the key holds on these lines:**

- `R-5`, residue the case set accepted: Документ встановлює пʼятиденний строк підрахунку й мовчить про те, що робить комісія, коли строк минув, а підрахунок не завершено. Слабке, бо обовʼязок дотримати цього строку покладено на визначену роль.
- `R-6`, residue the case set accepted: Документ сам передбачає відсутність директора й охоплює її лише щодо затвердження звіту. Він мовчить про те, хто призначає заміну (і комісію до 15 листопада), коли директор відсутній, а без заміни підрахунок зупиняється і заборона комірникові приймати на облік та видавати товари триває без обмеження.

Verdict: 

Note: 

## U-18 — case-006-uk-accountant-job, run 2

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Незрозуміло, чи є первинними документами лише рахунки, акти й накази

**Explanation.** Визначення звучить як повний перелік: рахунок, акт або наказ. Тоді інші документи інших відділів не підлягають внесенню протягом двох робочих днів і поверненню з однаденним строком. Інший читач вважає, що це лише приклади, і тоді будь-який документ, що підтверджує операцію, має внесення у встановлені строки.

**Quotes, in their lines:**

- line 12, § Загальні положення: «У цій інструкції первинний документ — це рахунок, акт або наказ, що підтверджує господарську операцію Організації.»
- line 59, § Взаємодія з іншими відділами: «Керівник кожного іншого відділу передає бухгалтерові первинні документи свого відділу протягом двох робочих днів від дня їх складення або отримання.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-19 — case-006-uk-accountant-job, run 2

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Незрозуміло, чи письмова незгода керівника запускає строк внесення запису

**Explanation.** Строк внесення запису рахується від отримання виправленого документа, пояснення або рішення директора. Письмова незгода в цей перелік не входить. Один читач вважає, що строк не починається, доки не прийде рішення директора. Інший читач вважає, що незгода є поясненням, і тоді строк починається з її отримання.

**Quotes, in their lines:**

- line 20, § Обов'язки: «Строк внесення запису за повернутим документом або за документом, до якого запитано пояснення, бухгалтер відлічує від дня, коли першим отримав виправлений документ, пояснення або рішення директора Організації.»
- line 61, § Взаємодія з іншими відділами: «Якщо керівник відділу передав письмову незгоду із зауваженням або протягом трьох робочих днів від дня повернення не передав ні її, ні виправленого документа, бухгалтер наступного робочого дня письмово повідомляє про це головного бухгалтера.»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: Строк бухгалтера починається в день, коли бухгалтер отримує рішення директора Організації, але жодна роль не зобов'язана передати це рішення бухгалтерові чи керівникові відділу.
- `R-4`, residue the case set accepted: Запис, зроблений лише за поясненням, коли для позиції бракувало самого первинного документа, не має строку, бо обидва правила про строк прив'язано до первинного документа, який бухгалтер має в себе.
- `R-6`, residue the case set accepted: Документ не каже, чи є сумнів випадком, коли для запису бракує пояснення. Тому один бухгалтер не вносить сумнівний документ і більше нічого не робить, а інший того самого дня надсилає запит і вносить запис протягом двох робочих днів після отримання пояснення; кожен вважає, що виконує документ.

Verdict: 

Note: 

## U-21 — case-008-uk-complaints, run 2

Document: *Порядок розгляду скарг клієнтів* — `evals/_cases/case-008-uk-complaints/document.md`

**Title.** Незрозуміло, від якого дня рахується реєстрація скарги, яку працівник отримав не через оператора

**Explanation.** Перше прочитання: днем надходження є день, коли працівник отримав скаргу в особистій розмові чи іншим способом, тому оператор реєструє її до наступного робочого дня після цього. Друге прочитання: скарга надійшла лише тоді, коли її переслали на електронну адресу, тому строк реєстрації рахується від дня пересилання і може бути на день пізніше. Текст не каже, чи отримання працівником є одним із чотирьох каналів.

**Quotes, in their lines:**

- line 21, § Канали надходження: «Працівник Організації, який отримав скаргу в інший спосіб, не пізніше наступного робочого дня пересилає її на електронну адресу для скарг.»
- line 22, § Канали надходження: «Днем надходження є робочий день, коли скарга надійшла одним із каналів»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: Скарга, отримана «в інший спосіб», не надходить жодним із каналів так, як їх сформульовано в переліку (у кожному діє клієнт), тож день її надходження, а з ним і строк реєстрації, не визначено. Природне прочитання таке: переслане повідомлення надходить каналом електронної адреси для скарг у день, коли його переслано, і тому впевненість низька.

Verdict: 

Note: 

## U-23 — case-009-en-gifts, run 2

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Unclear whether an exception can be requested after a gift above the limit has already been received

**Explanation.** Section 7.5 requires the written request to be sent beforehand, which suggests no exception can cover a gift that has already arrived. Section 7.6 speaks of a gift received 'without an approved exception', which could mean an exception approved later still counts. Under the first reading, the employee must hand the gift to the Compliance Officer and declare it within two working days. Under the second reading, the employee may request approval after receipt and keep the gift if it is approved.

**Quotes, in their lines:**

- line 38, § 7.5 Exceptions: «sends a written request to the Compliance Officer beforehand.»
- line 46, § 7.6 A gift or hospitality above the limit: «When an employee has received, without an approved exception, a gift above the gift limit or a money gift»

**What the key holds on these lines:**

- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: 

Note: 

## U-25 — case-011-en-records-retention, runs 2, 3 (also U-37)

Document: *Records Retention and Destruction Policy* — `evals/_cases/case-011-en-records-retention/document.md`

**Title.** Unclear which unit's head owns a record that one unit created and another received

**Explanation.** Reading one: the head of the unit that created the record is the owner and proposes its destruction. Reading two: the head of the unit that received the record is the owner. A record that passed between two units could also be read as having two owners. The document does not say which unit's head decides when the two units differ.

**Quotes, in their lines:**

- line 23, § Types of record and their owners: «and the head of the unit that created or received the record owns it.»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: A record that one unit created and another received has two unit heads who can each be its owner and two dates from which the 3 years can run; it can also be read as an A03 gap rather than an A02 ambiguity.
- `R-7`, residue the case set accepted: A record that a closed unit created and that a living unit later took over can belong to the head of the living unit ("received") or to the Records Manager, and the document does not say which rule governs. The key's R-2 states the two-unit case without the closed unit; this variant has two rules and is nearer to A02 than to A03.

Verdict: 

Note: 

## U-33 — case-006-uk-accountant-job, run 3

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Відповідальність за помилку через неправдиві дані, якщо бухгалтер не надіслав запит

**Explanation.** За першим читанням помилка, спричинена неправдивими даними, є відповідальністю керівника відділу, «а не бухгалтер», навіть якщо бухгалтер не запитав пояснення. За другим читанням бухгалтер відповідає за наслідки того, що не надіслав обов'язковий запит, і ця частина помилки лягає на нього. Документ не визначає, яке правило має перевагу, коли обидві обставини збігаються.

**Quotes, in their lines:**

- line 50, § Відповідальність: «Бухгалтер відповідає також за наслідки того, що не надіслав запит, який був зобов'язаний надіслати.»
- line 52, § Відповідальність: «За помилку в записі, спричинену неправдивими даними первинного документа, відповідає керівник відділу, який передав цей документ, а не бухгалтер.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-35 — case-009-en-gifts, run 3

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Unclear whether an approved exception removes the duty to pay the excess for hospitality

**Explanation.** The first paragraph of Section 7.6 applies only to gifts received 'without an approved exception', but the later rule on hospitality above its limit does not repeat that condition. Reading one applies the later rule literally, so the employee records the hospitality and pays the excess even when an exception was approved. Reading two carries the exception condition over, so approved hospitality needs neither a record of excess nor a payment; the document does not settle which reading applies.

**Quotes, in their lines:**

- line 46, § 7.6 A gift or hospitality above the limit: «When an employee has received, without an approved exception, a gift above the gift limit or a money gift»
- line 49, § 7.6 A gift or hospitality above the limit: «When an employee learns after the occasion that a gift given or hospitality received or given was above its limit, or that a gift given was a money gift, the employee records it in the declaration within ten working days of learning it.»
- line 50, § 7.6 A gift or hospitality above the limit: «When the hospitality was received, the employee pays the third party the excess within the same period.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Section 7.7 displaces 7.3, excludes 7.5, keeps 7.4 and is silent on 7.6, so a host who learns later that the refreshments were too costly can read that "its limit" in 7.6 is the limit for refreshments and record it, or that 7.6 does not reach giving to officials and record nothing.
- `R-3`, residue the case set accepted: The condition "without an approved exception" is stated once in Section 7.6, so an employee with an approved exception who learns the value after the occasion can read that they pay the excess or that they do not.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.
- `R-7`, residue the case set accepted: An employee who receives a gift above the limit by post and refuses it by handing it in can read that no declaration is needed (a refused offer) or that one is needed (Section 7.6); the more specific line most likely governs, so the confidence is low.

Verdict: 

Note: 

## U-39 — case-016-uk-db-backup, run 3

Document: *Інструкція з резервного копіювання бухгалтерської бази даних* — `evals/_cases/case-016-uk-db-backup/document.md`

**Title.** Неясно, чи треба складати й підписувати акт після невдалого пробного відновлення

**Explanation.** Перше прочитання: акт пробного відновлення складається і підписується з головним бухгалтером за будь-яким результатом, а потім передається керівнику в день підписання. Друге прочитання: після невдачі передбачено лише негайне повідомлення керівника та адміністратора баз даних, а акт не складається. Розділ 7 не пояснює, як діяти з актом, якщо звірка залишків не відбулася.

**Quotes, in their lines:**

- line 60, § 7. Щомісячне пробне відновлення: «Системний адміністратор складає акт пробного відновлення, підписує його разом із головним бухгалтером»
- line 61, § 7. Щомісячне пробне відновлення: «Якщо відновлення не вдалося або залишки не збіглися, системний адміністратор того самого робочого дня повідомляє про це керівника»

**What the key holds on these lines:**

- `R-2`, residue the case set accepted: Розбіжність залишків виявляє головний бухгалтер, а повідомити про неї того самого робочого дня мусить системний адміністратор, і жоден крок не передає результат від першого до другого.

Verdict: 

Note: 

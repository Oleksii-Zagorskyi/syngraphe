# Unmatched findings of A01 — contradiction — the verdicts

**What was tested.** Each finding below came from heuristic A01, prompt `prompts/A01-contradiction/prompt-02.md` on claude-haiku-5-5 at effort `medium`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — an ambiguity, a gap, a term with two meanings, circular authority, an unowned obligation.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.

**Status.** 4 of 13 items ruled.

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

## U-01 — case-005-en-spending-authority, run 1

Document: *Spending Approval Matrix* — `evals/_cases/case-005-en-spending-authority/document.md`

**Title.** Amount band limits leave a gap between 2,000 and 2,500 euros

**Explanation.** The first band ends at 2,000 euros inclusive, but the head-of-department band starts above 2,500 euros. Every other band boundary matches the previous band's upper limit, so this is a different value for the same boundary. An amount such as 2,250 euros falls in no band, so the document gives two incompatible limits and no approver for that range.

**Quotes, in their lines:**

- line 26, § 3. Amount bands: «From 0 to 2,000 euros inclusive, the approver is the team lead of the requester's team.»
- line 27, § 3. Amount bands: «Above 2,500 and up to 15,000 euros inclusive, the approver is the head of the requester's department.»

**What the key holds on these lines:**

- `A03-1`, a defect of A03: The matrix covers every amount, yet no band holds a request above 2,000 and up to 2,500 euros, so such a request has no approver.

Verdict: not a defect

Note: That's a gap, nothing defines who is the approver for 2000-2500 euros range. But nothing actually contradicts, if we are talking about A1

## U-02 — case-006-uk-accountant-job, run 1

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Право не вносити запис суперечить обов'язку вносити запис за кожним первинним документом

**Explanation.** Обов'язок вимагає внести запис за кожним первинним документом протягом двох робочих днів. Право дозволяє не вносити запис за документом, у достовірності якого бухгалтер сумнівається, і не вказує, що це виняток. Для такого документа читач не може одночасно виконати обидва приписи.

**Quotes, in their lines:**

- line 17, § Обов'язки: «Бухгалтер вносить до облікової системи запис за кожним первинним документом протягом двох робочих днів від дня його отримання.»
- line 38, § Права: «Бухгалтер має право не вносити запис за первинним документом, у достовірності якого він сумнівається.»

**What the key holds on these lines:**

- `A06-2`, a defect of A06, also A02: Це право знімає обов'язок внести запис протягом двох днів, а документ не каже, чи охоплює обов'язок запитати пояснення випадок сумніву. За одним прочитанням нікого не повідомляють і ніхто не відповідає за невнесений документ, за іншим — сумнів усуває порядок запиту.
- `R-4`, residue the case set accepted: Запис, зроблений лише за поясненням, коли для позиції бракувало самого первинного документа, не має строку, бо обидва правила про строк прив'язано до первинного документа, який бухгалтер має в себе.
- `R-6`, residue the case set accepted: Документ не каже, чи є сумнів випадком, коли для запису бракує пояснення. Тому один бухгалтер не вносить сумнівний документ і більше нічого не робить, а інший того самого дня надсилає запит і вносить запис протягом двох робочих днів після отримання пояснення; кожен вважає, що виконує документ.
- `R-7`, residue the case set accepted: Коли директор Організації вирішує, що документ треба внести, а бухгалтер і далі сумнівається в ньому, діють і право, і обов'язкове рішення, а документ не каже, що з них має перевагу. Тому один бухгалтер вносить запис, а інший — ні.
- `R-8`, residue the case set accepted: «За кожним» і «має право не вносити» суперечать одне одному на рівні слів, і детектор може повідомити про них як про суперечність. Це не справжній A01, бо право природно читається як виняток, так само як повернення документа без дати, суми або підпису. Це кандидат на пастку A01.

Verdict: trap

Note: we have other exceptions as well, for example "Первинний документ, у якому немає дати, суми або підпису керівника відділу, що його передав, бухгалтер"

## U-03 — case-013-en-it-access, run 1

Document: *Procedure for Requesting and Removing Access to IT Systems* — `evals/_cases/case-013-en-it-access/document.md`

**Title.** System owners are appointed only for applications and databases, but the review requires owners for every system

**Explanation.** Section 1 defines a system as including devices and network services, and section 6 applies the review to each system. Section 2 says the Head of Information Technology appoints owners only for every application and every database. For a device or network service, no system owner or alternate owner exists, so the reader cannot send the review list to them or obtain the second decision that section 4 requires for access to them.

**Quotes, in their lines:**

- line 8, § 1. Purpose and scope: «A system is any application, database, device or network service that the Organisation operates or subscribes to.»
- line 19, § 2. Participants: «The Head of Information Technology appoints one system owner and one alternate owner for every application and every database»
- line 55, § 6. Periodic review: «On the first working day of January and of July, the Service Desk sends the system owner and the alternate owner of each system the list of all access to that system from the access register.»

**What the key holds on these lines:**

- `A03-1`, a defect of A03: The procedure covers every system, devices and network services among them, but only applications and databases get an owner, so a request for a device or a network service has no one to give the second decision and its access is never reviewed.
- `R-4`, residue the case set accepted: A system owner or an alternate owner who changes role loses all access, and the document does not say whether the appointment continues or who gives the second decision and makes the review until a new appointment. This is close to R-1 in kind and is weaker than A03-1.
- `R-6`, residue the case set accepted: The Head of Information Technology appoints the persons who give the second decision on his or her own requests. This is an appointer and an appointee, and not "A approves B, B approves A", so a heuristic should not report it. It is listed because a model can raise it as a false positive. It is a candidate for a trap of A05.

Verdict: 

Note: 

## U-04 — case-017-en-annual-leave, run 1

Document: *Annual Leave Policy* — `evals/_cases/case-017-en-annual-leave/document.md`

**Title.** Conflicting rounding instruction for entitlements

**Explanation.** The document says the final entitlement is rounded up. It also says the result is rounded to the nearest half day. When the unrounded value is closer to a lower half day, rounding up gives a different result from rounding to the nearest half day, so the reader cannot follow both instructions.

**Quotes, in their lines:**

- line 24, § Entitlement and counting: «Only the final result is rounded up, to the nearest half day.»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

## U-05 — case-018-uk-document-numbering, run 1

Document: *Стандарт Організації СТО 07 «Нумерація та реєстрація внутрішніх документів»* — `evals/_cases/case-018-uk-document-numbering/document.md`

**Title.** Акти входять до сфери стандарту, але для них не передбачено код виду.

**Explanation.** Розділ 1 називає акти внутрішніми документами, які стандарт регулює, а в переліку кодів розділу 2 коду для актів немає. Тому читач не може скласти номер для акта за форматом із розділу 2. Перелік кодів і сфера застосування не узгоджені між собою.

**Quotes, in their lines:**

- line 7, § 1. Сфера застосування: «службові записки та акти, які створено й підписано в Організації»
- line 28, § 2. Структура номера: «Службова записка має код «СЗ».»

**What the key holds on these lines:**

- `A03-1`, a defect of A03: Акт є внутрішнім документом, який стандарт вимагає нумерувати, але в переліку кодів виду немає коду для акта, тож його номер скласти неможливо.

Verdict: 

Note: 

## U-06 — case-005-en-spending-authority, run 2

Document: *Spending Approval Matrix* — `evals/_cases/case-005-en-spending-authority/document.md`

**Title.** Amount band boundaries leave a gap between 2,000 and 2,500 euros with no approver.

**Explanation.** The first band ends at 2,000 euros inclusive, and the second band starts only above 2,500 euros. A request between 2,000 and 2,500 euros, such as 2,200 euros, falls in neither band, so the reader cannot find its approver. The other band boundaries are contiguous, so this one is inconsistent with them.

**Quotes, in their lines:**

- line 26, § 3. Amount bands: «From 0 to 2,000 euros inclusive, the approver is the team lead of the requester's team.»
- line 27, § 3. Amount bands: «Above 2,500 and up to 15,000 euros inclusive, the approver is the head of the requester's department.»

**What the key holds on these lines:**

- `A03-1`, a defect of A03: The matrix covers every amount, yet no band holds a request above 2,000 and up to 2,500 euros, so such a request has no approver.

Verdict: 

Note: 

## U-07 — case-011-en-records-retention, run 2

Document: *Records Retention and Destruction Policy* — `evals/_cases/case-011-en-records-retention/document.md`

**Title.** The policy says it does not govern duplicate copies, yet the owner must erase every copy of a destroyed record.

**Explanation.** The definition excludes duplicate copies of a record in the same form from the policy. The destruction rule then requires the owner to erase or shred every copy of a record. A reader cannot both leave same-form duplicates outside the policy and erase them as part of destroying the record.

**Quotes, in their lines:**

- line 12, § Definition of a record: «Drafts, personal notes and duplicate copies of a record in the same form are not records, and this policy does not govern them.»
- line 57, § Destruction: «When the owner destroys a record, the owner also erases or shreds every copy of it.»

**What the key holds on these lines:**

- `A01-1`, a defect of A01, also A02 — this heuristic's own: The policy says it does not govern same-form duplicate copies, yet it requires the owner to erase or shred every copy of a destroyed record, duplicates included. It was not planted. A measured run found it, and it was added after review.

Verdict: real defect

Note: approved for case 011's key as A01-1

## U-08 — case-018-uk-document-numbering, run 2

Document: *Стандарт Організації СТО 07 «Нумерація та реєстрація внутрішніх документів»* — `evals/_cases/case-018-uk-document-numbering/document.md`

**Title.** Акти підлягають нумерації, але для них немає коду виду

**Explanation.** Розділ 1 включає акти до внутрішніх документів, які стандарт нумерує й реєструє, і прямо виключає документи інших видів. Розділ 2 вимагає код виду в номері, але перелік кодів містить лише накази, розпорядження, положення, інструкції, протоколи та службові записки. Для актів номер за цим стандартом побудувати неможливо, тому правила двох розділів не узгоджуються.

**Quotes, in their lines:**

- line 7, § 1. Сфера застосування: «Внутрішніми документами в цьому стандарті є накази, розпорядження, положення, інструкції, протоколи, службові записки та акти, які створено й підписано в Організації.»
- line 21, § 2. Структура номера: «Код виду визначають так:»

**What the key holds on these lines:**

- `A03-1`, a defect of A03: Акт є внутрішнім документом, який стандарт вимагає нумерувати, але в переліку кодів виду немає коду для акта, тож його номер скласти неможливо.

Verdict: 

Note: 

## U-09 — case-002-uk-procurement-committee, run 3

Document: *Положення про закупівельний комітет Організації* — `evals/_cases/case-002-uk-procurement-committee/document.md`

**Title.** Ініціатора визначено так, що фінансовий менеджер не може ним бути, але далі його називають ініціатором

**Explanation.** Визначення каже, що ініціатор є керівником структурного підрозділу або директором. Далі документ прямо називає фінансового менеджера ініціатором заявки на суму менше 50 000 гривень. Це порушує власне визначення, і читач не знає, хто є ініціатором у таких випадках.

**Quotes, in their lines:**

- line 10, § Загальні положення: «Ініціатор — це керівник структурного підрозділу або директор, який подає заявку на закупівлю.»
- line 32, § Пороги та повноваження: «Якщо ініціатором заявки очікуваною вартістю менше 50 000 гривень є фінансовий менеджер, він у день подання передає її директорові»

**What the key holds on these lines:**

- `A05-1`, a defect of A05: Директор може бути ініціатором, тож рішення Комітету про погодження його власної заявки очікуваною вартістю понад 1 000 000 гривень набирає чинності лише після його ж затвердження, а якщо кворуму немає, він сам ухвалює рішення щодо власної заявки.
- `A05-2`, a defect of A05: Щодо заявок очікуваною вартістю менше 50 000 гривень фінансовий менеджер ухвалює рішення про заявки директора, а директор — про заявки фінансового менеджера: дві ролі погоджують заявки одна одної. Це побічний наслідок ширшого визначення ініціатора в A05-1; його виявило холодне читання з ключем, і його залишено як дефект.
- `R-7`, residue the case set accepted: Рішення директора щодо власних заявок фінансового менеджера не потрапляють до жодного звіту чи реєстру.

Verdict: 

Note: 

## U-10 — case-005-en-spending-authority, run 3

Document: *Spending Approval Matrix* — `evals/_cases/case-005-en-spending-authority/document.md`

**Title.** The first and second amount bands leave amounts between 2,000 and 2,500 euros without an approver.

**Explanation.** The first band ends at 2,000 euros inclusive, but the second band starts only above 2,500 euros. The two bands give different boundary values, so a request of, for example, 2,200 euros falls in neither band and the matrix names no approver for it. The document does not mark this gap as intended.

**Quotes, in their lines:**

- line 26, § 3. Amount bands: «From 0 to 2,000 euros inclusive, the approver is the team lead of the requester's team.»
- line 27, § 3. Amount bands: «Above 2,500 and up to 15,000 euros inclusive, the approver is the head of the requester's department.»

**What the key holds on these lines:**

- `A03-1`, a defect of A03: The matrix covers every amount, yet no band holds a request above 2,000 and up to 2,500 euros, so such a request has no approver.

Verdict: 

Note: 

## U-11 — case-006-uk-accountant-job, run 3

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Обов'язок вносити запис за кожним документом суперечить праву не вносити запис за сумнівним документом

**Explanation.** Один пункт вимагає, щоб бухгалтер вніс запис за кожним первинним документом протягом двох робочих днів. Інший пункт дозволяє не вносити запис за документом, у достовірності якого бухгалтер сумнівається. Для такого документа виконати обидва пункти неможливо, а документ не позначено як виняток з обов'язку.

**Quotes, in their lines:**

- line 17, § Обов'язки: «Бухгалтер вносить до облікової системи запис за кожним первинним документом протягом двох робочих днів від дня його отримання.»
- line 38, § Права: «Бухгалтер має право не вносити запис за первинним документом, у достовірності якого він сумнівається.»

**What the key holds on these lines:**

- `A06-2`, a defect of A06, also A02: Це право знімає обов'язок внести запис протягом двох днів, а документ не каже, чи охоплює обов'язок запитати пояснення випадок сумніву. За одним прочитанням нікого не повідомляють і ніхто не відповідає за невнесений документ, за іншим — сумнів усуває порядок запиту.
- `R-4`, residue the case set accepted: Запис, зроблений лише за поясненням, коли для позиції бракувало самого первинного документа, не має строку, бо обидва правила про строк прив'язано до первинного документа, який бухгалтер має в себе.
- `R-6`, residue the case set accepted: Документ не каже, чи є сумнів випадком, коли для запису бракує пояснення. Тому один бухгалтер не вносить сумнівний документ і більше нічого не робить, а інший того самого дня надсилає запит і вносить запис протягом двох робочих днів після отримання пояснення; кожен вважає, що виконує документ.
- `R-7`, residue the case set accepted: Коли директор Організації вирішує, що документ треба внести, а бухгалтер і далі сумнівається в ньому, діють і право, і обов'язкове рішення, а документ не каже, що з них має перевагу. Тому один бухгалтер вносить запис, а інший — ні.
- `R-8`, residue the case set accepted: «За кожним» і «має право не вносити» суперечать одне одному на рівні слів, і детектор може повідомити про них як про суперечність. Це не справжній A01, бо право природно читається як виняток, так само як повернення документа без дати, суми або підпису. Це кандидат на пастку A01.

Verdict: 

Note: 

## U-12 — case-011-en-records-retention, run 3

Document: *Records Retention and Destruction Policy* — `evals/_cases/case-011-en-records-retention/document.md`

**Title.** Duplicate copies are said to be outside the policy, but the owner must destroy every copy.

**Explanation.** The definition says duplicate copies of a record in the same form are not records and that this policy does not govern them. The destruction section requires the owner to erase or shred every copy of a destroyed record. A reader cannot both leave duplicates outside the policy and destroy them under it.

**Quotes, in their lines:**

- line 12, § Definition of a record: «Drafts, personal notes and duplicate copies of a record in the same form are not records, and this policy does not govern them.»
- line 57, § Destruction: «When the owner destroys a record, the owner also erases or shreds every copy of it.»

**What the key holds on these lines:**

- `A01-1`, a defect of A01, also A02 — this heuristic's own: The policy says it does not govern same-form duplicate copies, yet it requires the owner to erase or shred every copy of a destroyed record, duplicates included. It was not planted. A measured run found it, and it was added after review.

Verdict: real defect

Note: approved for case 011's key as A01-1

## U-13 — case-018-uk-document-numbering, run 3

Document: *Стандарт Організації СТО 07 «Нумерація та реєстрація внутрішніх документів»* — `evals/_cases/case-018-uk-document-numbering/document.md`

**Title.** Акти названо внутрішніми документами, які нумерують, але для них немає коду виду

**Explanation.** Розділ 1 включає акти до внутрішніх документів і вимагає їх нумерувати та реєструвати за цим стандартом. Водночас він каже, що документи інших видів не нумерують і не реєструють. Розділ 2 визначає коди лише для шести видів і не містить коду для актів, тож реєстратор не може присвоїти акту номер у форматі «04-Н-17/2026».

**Quotes, in their lines:**

- line 7, § 1. Сфера застосування: «Внутрішніми документами в цьому стандарті є накази, розпорядження, положення, інструкції, протоколи, службові записки та акти, які створено й підписано в Організації.»
- line 9, § 1. Сфера застосування: «Документи інших видів за цим стандартом не нумерують і не реєструють.»
- line 28, § 2. Структура номера: «Службова записка має код «СЗ».»
- line 13, § 2. Структура номера: «Номер документа складається з чотирьох частин: індексу підрозділу, коду виду, порядкового номера і року.»

**What the key holds on these lines:**

- `A03-1`, a defect of A03: Акт є внутрішнім документом, який стандарт вимагає нумерувати, але в переліку кодів виду немає коду для акта, тож його номер скласти неможливо.
- `R-7`, residue the case set accepted: Слово «номер» в одному рядку означає весь номер із чотирьох частин, а в інших — порядковий номер; дія за обох значень однакова, тож це кандидат на пастку A04.

Verdict: 

Note: 

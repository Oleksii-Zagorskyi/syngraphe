# Unmatched findings of A05 — circular-authority — the verdicts

**What was tested.** Each finding below came from heuristic A05, prompt `prompts/P08-read-circular-authority/prompt-02.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — a contradiction, an ambiguity, a gap, a term with two meanings, an unowned obligation.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.

**Status.** 0 of 4 items ruled.

<details><summary>The instruction A05 obeyed (<code>prompts/P08-read-circular-authority/prompt-02.md</code>)</summary>

Find each case of circular authority in the document.
Report each case as a separate finding.

Authority is the power to approve, decide, sign, check, confirm or accept an act.
Authority is circular when a role approves its own act, or when two roles approve the acts of each other.

First, find each act that needs an approval, a decision or a check.
For each act, find the role that does it and the role that approves it.

Follow each path through the document:

- The normal path.
- The path when a role is absent, with each stand-in and each substitute.
- The path when a special role does the act, for example a head, a director or a member of a committee.
- The path that each special rule gives, for example a rule for an urgent case or for a case with no quorum.
- The path when the role that approves is also the role that asks, for example when a director is the requester.
- The path when the matter is about the role that approves, for example an order about the head of the unit that endorses it.
- The path when a stand-in does the duties of an absent role, and the act is the stand-in's own act.

Do these steps for each role that approves, decides or checks.
A role can approve its own act only in one of these special paths, so check each one.

Find these causes:

- One role approves, checks or decides its own act, its own request or a matter about itself.
- Role A approves the acts of role B, and role B approves the acts of role A.
- A longer circle, for example A approves B, B approves C and C approves A.

A cause often comes from two or more passages read together.
Each passage alone can be a correct rule.

Do not report these:

- A request, a notice, a report or an exchange of information between two roles. These are not approvals.
- An act that one role does and a different role checks.
- A rule that forbids a role to approve its own act and names a different role.
- A matter about a role that goes to a role above it.
- An act that has no approver. That is a different kind of problem.

Quote each passage of the path.
In the explanation, write the path: who does the act, and through which passages the same role approves it.

</details>

## U-06 — case-003-en-onboarding, run 2

Document: *Standard Operating Procedure: Onboarding a New Employee* — `evals/_cases/case-003-en-onboarding/document.md`

**Title.** The Head of HR both owns the procedure and reviews it, so the role checks its own work.

**Explanation.** The Head of HR is the owner of this procedure and is also the role that reviews it. The same role therefore checks its own act, with no separate reviewer. A review by a different role, or by a role above the owner, would give an independent check.

**Quotes, in their lines:**

- line 26, § 3. Roles: «The Head of HR owns this procedure and reviews it once every calendar year.»

**What the key holds on these lines:**

- `R-7`, residue the case set accepted: The role that owns the procedure is the only role that reviews it, which is a role that checks its own act. Against it: a review is not an approval, and owner review is the normal practice for a procedure.

Verdict: 

Note: 

## U-09 — case-016-uk-db-backup, run 2

Document: *Інструкція з резервного копіювання бухгалтерської бази даних* — `evals/_cases/case-016-uk-db-backup/document.md`

**Title.** Адміністратор баз даних сам створює резервну копію і сам її перевіряє

**Explanation.** Згідно з розділом 2 резервне копіювання виконує адміністратор баз даних, а автоматичне завдання він налаштовує і підтримує (розділ 3). Той самий адміністратор за розділом 5 перевіряє кожну копію і записує результат у журнал. Отже, одна роль створює і перевіряє власний результат, і жоден інший працівник не контролює цю перевірку.

**Quotes, in their lines:**

- line 15, § 2. Виконавці: «Резервне копіювання виконує адміністратор баз даних.»
- line 41, § 5. Перевірка резервної копії: «Адміністратор баз даних перевіряє кожну резервну копію до 10:00 наступного робочого дня після її створення.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Слова «того самого дня» можуть стосуватися і створення, і перевірки позачергової копії або лише створення, і тоді перевірку слід виконати до 10:00 наступного робочого дня згідно з розділом 5.
- `R-4`, residue the case set accepted: За тим прочитанням A02-1, яке відносить заборону лише до обов’язків відсутнього, системний адміністратор перевіряє копії як виконавець обов’язків відсутнього, а потім відновлює з них базу даних у межах власного обов’язку. Оцінюю це низько: головний бухгалтер усе одно звіряє залишки, а інше прочитання A02-1 знімає це питання. Модель, яка про це повідомить, буде оцінена як така, що потрапила в пастку A05, тому «why» цієї пастки має називати випадок відсутності.

Verdict: 

Note: 

## U-15 — case-016-uk-db-backup, run 3

Document: *Інструкція з резервного копіювання бухгалтерської бази даних* — `evals/_cases/case-016-uk-db-backup/document.md`

**Title.** Адміністратор баз даних сам перевіряє позачергову копію, яку сам створив

**Explanation.** Після невдалого пробного відновлення адміністратор баз даних створює позачергову резервну копію. Той самий адміністратор перевіряє її за розділом 5. Таким чином одна посадова особа створює копію і сама визнає її придатною, без незалежного схвалення.

**Quotes, in their lines:**

- line 62, § 7. Щомісячне пробне відновлення: «У такому разі адміністратор баз даних того самого дня створює позачергову резервну копію і перевіряє її згідно з розділом 5.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Слова «того самого дня» можуть стосуватися і створення, і перевірки позачергової копії або лише створення, і тоді перевірку слід виконати до 10:00 наступного робочого дня згідно з розділом 5.

Verdict: 

Note: 

## U-17 — case-018-uk-document-numbering, run 3

Document: *Стандарт Організації СТО 07 «Нумерація та реєстрація внутрішніх документів»* — `evals/_cases/case-018-uk-document-numbering/document.md`

**Title.** Реєстратор сам вирішує, що його номер помилковий, і сам його анулює

**Explanation.** Реєстратор присвоює номер, а потім сам вирішує, що номер присвоєно помилково, і сам ставить позначку «анульовано». Жодна інша посада не перевіряє і не затверджує це рішення, тому реєстратор ухвалює рішення щодо власного акта. Перевірка за розділом 4 діє лише для помилок, виявлених під час перевірки реєстрів.

**Quotes, in their lines:**

- line 51, § 4. Реєстри: «Якщо реєстратор присвоїв номер помилково, він ставить у записі позначку «анульовано».»
- line 42, § 3. Присвоєння номера: «Реєстратор присвоює наступний за порядком вільний номер.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Стандарт забороняє повторно присвоювати анульований номер і номер заміненого документа, але мовчить про номер скасованого, тож один читач вважає його вільним, а другий — зайнятим.
- `R-7`, residue the case set accepted: Слово «номер» в одному рядку означає весь номер із чотирьох частин, а в інших — порядковий номер; дія за обох значень однакова, тож це кандидат на пастку A04.
- `R-8`, residue the case set accepted: Документ охоплює помилку, виявлену перевіркою, і номер, присвоєний помилково, але не має правила для помилки в записі, яку реєстратор виявив сам, без перевірки; у реєстрі минулого року останній рядок забороняє таке виправлення.

Verdict: 

Note: 

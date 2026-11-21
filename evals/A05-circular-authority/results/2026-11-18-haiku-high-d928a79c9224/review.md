# Unmatched findings of A05 — circular-authority — the verdicts

**What was tested.** Each finding below came from heuristic A05, prompt `prompts/A05-circular-authority/prompt-01.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — a contradiction, an ambiguity, a gap, a term with two meanings, an unowned obligation.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.
Notes marked *Second reviewer* hold the verdict of an independent model review, accepted by the maintainer; the word in brackets is that review's confidence.

**Status.** 9 of 9 items ruled.

<details><summary>The instruction A05 obeyed (<code>prompts/A05-circular-authority/prompt-01.md</code>)</summary>

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

## U-01 — case-003-en-onboarding, run 1

Document: *Standard Operating Procedure: Onboarding a New Employee* — `evals/_cases/case-003-en-onboarding/document.md`

**Title.** The Head of HR both owns the procedure and reviews it, so the owner checks its own work.

**Explanation.** The Head of HR is the role that owns this procedure and also the role that reviews it. The review is a check on a document that the same role created and owns, so no other role approves it. This is a circle of authority: the Head of HR checks its own act. A separate reviewer or an approval by a role above the Head of HR would avoid this.

**Quotes, in their lines:**

- line 26, § 3. Roles: «The Head of HR owns this procedure and reviews it once every calendar year.»

**What the key holds on these lines:**

- `R-7`, residue the case set accepted: The role that owns the procedure is the only role that reviews it, which is a role that checks its own act. Against it: a review is not an approval, and owner review is the normal practice for a procedure.

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: Ownership and scheduled review are explicit, but authorship or approval of the procedure by the Head of HR is unsupported. R-7 notes this concern. (high)

## U-04 — case-009-en-gifts, run 2

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** The Compliance Officer and the Chief Executive approve each other's gift requests.

**Explanation.** Under Section 7.5, the Chief Executive is an employee and sends gift requests to the Compliance Officer, who approves or refuses them. Section 7.1 says the Chief Executive acts in place of the Compliance Officer for the Compliance Officer's gifts, so the Chief Executive approves the Compliance Officer's requests. Each role therefore approves the acts of the other, and no independent approver exists for either role.

**Quotes, in their lines:**

- line 8, § 7.1 Scope: «the Chief Executive acts in place of the Compliance Officer.»
- line 38, § 7.5 Exceptions: «sends a written request to the Compliance Officer beforehand.»
- line 39, § 7.5 Exceptions: «The Compliance Officer approves or refuses the request in writing within three working days.»

**What the key holds on these lines:**

- `A05-1`, a defect of A05 — this heuristic's own: The Compliance Officer decides the Chief Executive's requests and the Chief Executive decides the Compliance Officer's: two roles approve each other's acts. It was first recorded as residue; two roles approving each other's acts is this kind of problem.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Each role decides the other’s exception requests through sections 7.1 and 7.5. Residue R-2. (high)

## U-05 — case-011-en-records-retention, run 2

Document: *Records Retention and Destruction Policy* — `evals/_cases/case-011-en-records-retention/document.md`

**Title.** Records Manager and Legal Counsel approve each other's destruction proposals

**Explanation.** The Records Manager approves destruction proposals for contract records, which the Legal Counsel owns. The Legal Counsel approves destruction proposals for the Records Manager's own operational records of a defunct unit. Each role therefore approves the other's acts, so neither role's approval is independent of the other.

**Quotes, in their lines:**

- line 49, § Destruction: «The Records Manager answers the proposal in writing within 10 calendar days.»
- line 22, § Types of record and their owners: «Contract records are signed agreements with outside parties and their amendments, and the Legal Counsel owns them.»
- line 52, § Destruction: «For records that the Records Manager owns, the Legal Counsel answers the proposal instead of the Records Manager, under the same rules.»
- line 25, § Types of record and their owners: «The Records Manager owns the operational records of a unit that no longer exists.»

**What the key holds on these lines:**

- `A05-1`, a defect of A05 — this heuristic's own: The Records Manager answers the Legal Counsel's proposals and the Legal Counsel answers the Records Manager's: two roles approve each other's acts. It was first recorded as residue; two roles approving each other's acts is this kind of problem.
- `R-5`, residue the case set accepted: The second line names only a refusal by the Records Manager. It is not clear if "under the same rules" carries it to a refusal by the Legal Counsel, so a record of a closed unit is or is not under a hold after a refusal, and the time limit to propose again differs.
- `R-7`, residue the case set accepted: A record that a closed unit created and that a living unit later took over can belong to the head of the living unit ("received") or to the Records Manager, and the document does not say which rule governs. The key's R-2 states the two-unit case without the closed unit; this variant has two rules and is nearer to A02 than to A03.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The Records Manager decides Legal Counsel’s proposals, and Legal Counsel decides the Records Manager’s. A05 includes reciprocal approval of separate acts. Residue R-3. (high)

## U-07 — case-016-uk-db-backup, run 2

Document: *Інструкція з резервного копіювання бухгалтерської бази даних* — `evals/_cases/case-016-uk-db-backup/document.md`

**Title.** Адміністратор баз даних сам перевіряє позачергову копію після невдалого пробного відновлення

**Explanation.** Після невдалого пробного відновлення адміністратор баз даних створює позачергову копію і сам перевіряє її за розділом 5. Таким чином та сама роль створює і схвалює свою роботу. Це не дає незалежної перевірки саме в той момент, коли вона найпотрібніша.

**Quotes, in their lines:**

- line 62, § 7. Щомісячне пробне відновлення: «адміністратор баз даних того самого дня створює позачергову резервну копію і перевіряє її згідно з розділом 5.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Слова «того самого дня» можуть стосуватися і створення, і перевірки позачергової копії або лише створення, і тоді перевірку слід виконати до 10:00 наступного робочого дня згідно з розділом 5.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The database administrator directly creates the extraordinary copy and performs its required acceptance check. Independent restoration is downstream. Unlisted in residue. (high)

## U-08 — case-016-uk-db-backup, run 2

Document: *Інструкція з резервного копіювання бухгалтерської бази даних* — `evals/_cases/case-016-uk-db-backup/document.md`

**Title.** Адміністратор баз даних перевіряє резервні копії, які сам створює

**Explanation.** За розділом 2 резервне копіювання виконує адміністратор баз даних, а за розділом 3 він же налаштовує і підтримує завдання, що створює копії. За розділом 5 той самий адміністратор перевіряє кожну копію і записує результат. Отже, роль схвалює результат власної роботи без участі іншої особи.

**Quotes, in their lines:**

- line 15, § 2. Виконавці: «Резервне копіювання виконує адміністратор баз даних.»
- line 41, § 5. Перевірка резервної копії: «Адміністратор баз даних перевіряє кожну резервну копію до 10:00 наступного робочого дня після її створення.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: Слова «того самого дня» можуть стосуватися і створення, і перевірки позачергової копії або лише створення, і тоді перевірку слід виконати до 10:00 наступного робочого дня згідно з розділом 5.
- `R-4`, residue the case set accepted: За тим прочитанням A02-1, яке відносить заборону лише до обов’язків відсутнього, системний адміністратор перевіряє копії як виконавець обов’язків відсутнього, а потім відновлює з них базу даних у межах власного обов’язку. Оцінюю це низько: головний бухгалтер усе одно звіряє залишки, а інше прочитання A02-1 знімає це питання. Модель, яка про це повідомить, буде оцінена як така, що потрапила в пастку A05, тому «why» цієї пастки має називати випадок відсутності.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: The scheduled task creates routine copies, the database administrator checks integrity, and other roles test restoration and balances. This tracks A05-T1. (medium)

## U-11 — case-008-uk-complaints, run 3

Document: *Порядок розгляду скарг клієнтів* — `evals/_cases/case-008-uk-complaints/document.md`

**Title.** Керівник відділу може призначити себе фахівцем і сам затвердити свій висновок

**Explanation.** Керівник відділу призначає фахівця, а потім затверджує висновок фахівця і підписує відповідь. Документ забороняє фахівцем лише працівника, дій якого стосується скарга, тому сам керівник відділу може стати фахівцем у скарзі, яка його не стосується. Тоді він готує висновок і затверджує його сам, тобто один і той самий орган схвалює власний акт.

**Quotes, in their lines:**

- line 40, § Розслідування: «Керівник відділу протягом одного робочого дня після дня реєстрації призначає фахівця відділу, далі — фахівець, який розслідує скаргу.»
- line 41, § Розслідування: «Фахівцем не може бути працівник, дій якого стосується скарга.»
- line 63, § Відповідь: «Керівник відділу протягом одного робочого дня після дня отримання висновку і проєкту відповіді затверджує висновок і підписує відповідь або повертає їх фахівцеві із зауваженнями.»

**What the key holds on these lines:**

- `R-1`, residue the case set accepted: «лише затверджує його» може означати, що керівник відділу нічого не підписує, але все ще може повернути висновок, або що права повернути його він не має. Паралельне «подає лише висновок» робить перше прочитання природним.
- `R-5`, residue the case set accepted: Коли клієнт оскаржує відповідь, керівник департаменту може призначити того фахівця, який склав висновок і проєкт цієї відповіді, і тоді фахівець розслідує власну роботу. Перший рядок виключає цього фахівця, якщо проєкт належить до «дій», і фахівець не ухвалює рішення, тож зауваження слабке.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: For a complaint about someone else, the department head can appoint themself as specialist and approve their own conclusion. Unlisted in residue. (medium)

## U-12 — case-009-en-gifts, run 3

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Compliance Officer and Chief Executive approve each other's gift requests

**Explanation.** Section 7 applies to the Chief Executive as an employee, so the Chief Executive's requests go to the Compliance Officer, who approves them under Section 7.5. Section 7.1 makes the Chief Executive act in place of the Compliance Officer for the Compliance Officer's own gifts and hospitality, so the Chief Executive approves the Compliance Officer's requests. The two roles therefore approve each other's acts.

**Quotes, in their lines:**

- line 6, § 7.1 Scope: «Section 7 applies to every employee of the Organisation, including the Chief Executive.»
- line 8, § 7.1 Scope: «For a gift or hospitality that the Compliance Officer is offered, receives or gives, the Chief Executive acts in place of the Compliance Officer.»
- line 39, § 7.5 Exceptions: «The Compliance Officer approves or refuses the request in writing within three working days.»

**What the key holds on these lines:**

- `A05-1`, a defect of A05 — this heuristic's own: The Compliance Officer decides the Chief Executive's requests and the Chief Executive decides the Compliance Officer's: two roles approve each other's acts. It was first recorded as residue; two roles approving each other's acts is this kind of problem.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: The Compliance Officer approves the Chief Executive’s requests, and the Chief Executive approves the Compliance Officer’s under substitution. Residue R-2. (high)

## U-13 — case-009-en-gifts, run 3

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** Compliance Officer and Chief Executive set each other's gift values

**Explanation.** When an employee cannot establish a value, the Compliance Officer sets it in writing, which decides whether a limit applies. Section 7.1 has the Chief Executive act in place of the Compliance Officer for the Compliance Officer's own gifts, so the Chief Executive sets the value of the Compliance Officer's gifts. The Chief Executive, as an employee, asks the Compliance Officer for values of its own gifts, so each role decides the other's matters.

**Quotes, in their lines:**

- line 26, § 7.3 Value limits: «When an employee cannot establish the value, the employee asks the Compliance Officer, who sets the value in writing within two working days.»
- line 8, § 7.1 Scope: «For a gift or hospitality that the Compliance Officer is offered, receives or gives, the Chief Executive acts in place of the Compliance Officer.»

**What the key holds on these lines:**

- `A05-1`, a defect of A05 — this heuristic's own: The Compliance Officer decides the Chief Executive's requests and the Chief Executive decides the Compliance Officer's: two roles approve each other's acts. It was first recorded as residue; two roles approving each other's acts is this kind of problem.
- `R-5`, residue the case set accepted: The document does not say whether the employee may accept, keep or use the gift, or attend the hospitality, in the two working days before the value is set.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Each role decides the other’s binding gift valuations under sections 7.1 and 7.3. R-2 covers exception approvals only. Unlisted in residue. (high)

## U-14 — case-011-en-records-retention, run 3

Document: *Records Retention and Destruction Policy* — `evals/_cases/case-011-en-records-retention/document.md`

**Title.** Records Manager and Legal Counsel approve each other's destruction proposals

**Explanation.** The Records Manager answers destruction proposals for Legal Counsel's contract records, so the Records Manager approves Legal Counsel's acts. For operational records of a defunct unit, which the Records Manager owns, Legal Counsel answers the proposal instead, so Legal Counsel approves the Records Manager's acts. Each role therefore approves the other's destruction, and no independent check is set up for either side.

**Quotes, in their lines:**

- line 22, § Types of record and their owners: «Contract records are signed agreements with outside parties and their amendments, and the Legal Counsel owns them.»
- line 47, § Destruction: «The owner proposes a record for destruction to the Records Manager in writing»
- line 49, § Destruction: «The Records Manager answers the proposal in writing within 10 calendar days.»
- line 25, § Types of record and their owners: «The Records Manager owns the operational records of a unit that no longer exists.»
- line 52, § Destruction: «For records that the Records Manager owns, the Legal Counsel answers the proposal instead of the Records Manager, under the same rules.»

**What the key holds on these lines:**

- `A05-1`, a defect of A05 — this heuristic's own: The Records Manager answers the Legal Counsel's proposals and the Legal Counsel answers the Records Manager's: two roles approve each other's acts. It was first recorded as residue; two roles approving each other's acts is this kind of problem.
- `R-5`, residue the case set accepted: The second line names only a refusal by the Records Manager. It is not clear if "under the same rules" carries it to a refusal by the Legal Counsel, so a record of a closed unit is or is not under a hold after a refusal, and the time limit to propose again differs.
- `R-7`, residue the case set accepted: A record that a closed unit created and that a living unit later took over can belong to the head of the living unit ("received") or to the Records Manager, and the document does not say which rule governs. The key's R-2 states the two-unit case without the closed unit; this variant has two rules and is nearer to A02 than to A03.

Verdict: real defect

Note: Second reviewer, accepted by the maintainer: Each decides the other’s destruction proposal. A05 expressly includes reciprocal approvals, even across different record types. Residue R-3. (high)

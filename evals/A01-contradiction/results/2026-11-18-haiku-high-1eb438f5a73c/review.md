# Unmatched findings of A01 — contradiction — the verdicts

**What was tested.** Each finding below came from heuristic A01, prompt `prompts/A01-contradiction/prompt-03.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — an ambiguity, a gap, a term with two meanings, circular authority, an unowned obligation.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.

**Status.** 0 of 3 items ruled.

<details><summary>The instruction A01 obeyed (<code>prompts/A01-contradiction/prompt-03.md</code>)</summary>

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
- A case that the scope of the document includes and that no rule of the document handles. That is a gap, a different kind of problem.

Quote the two passages.
In the explanation, write the case in which the two passages apply, and why the reader cannot obey both.

</details>

## U-01 — case-006-uk-accountant-job, run 1

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Обов'язок вносити кожен первинний документ суперечить праву не вносити сумнівний документ

**Explanation.** Одне положення вимагає внести запис за кожним первинним документом протягом двох робочих днів. Інше дозволяє не вносити запис за документом, у достовірності якого бухгалтер сумнівається. Для такого сумнівного документа читач не може одночасно внести його у строк і не вносити взагалі, а документ не позначає це право як виняток.

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

## U-02 — case-006-uk-accountant-job, run 2

Document: *Посадова інструкція бухгалтера фінансового відділу* — `evals/_cases/case-006-uk-accountant-job/document.md`

**Title.** Термін «звіт» у тексті вжито не так, як його визначено в інструкції

**Explanation.** Інструкція визначає звіт як щомісячний звіт про стан розрахунків, який складає бухгалтер. Далі в розділі «Відповідальність» той самий термін використано для щоквартального звіту директорові про виконання обов'язків, який не є щомісячним звітом про розрахунки. Читач, що дотримується визначення, не може вважати квартальний документ звітом за цією інструкцією, тому текст суперечить власному визначенню.

**Quotes, in their lines:**

- line 13, § Загальні положення: «У цій інструкції звіт — це щомісячний звіт про стан розрахунків Організації, який складає бухгалтер.»
- line 49, § Відповідальність: «Бухгалтер щокварталу подає директорові Організації звіт про виконання своїх обов'язків.»

**What the key holds on these lines:**

- `A04-1`, a defect of A04: Документ визначає «звіт» як щомісячний звіт про стан розрахунків, а потім вживає це слово для щоквартального звіту про виконання бухгалтером своїх обов'язків. Тому слово «звіту» без уточнення в рядку про відповідальність охоплює або лише щомісячний звіт, або обидва звіти.

Verdict: 

Note: 

## U-03 — case-009-en-gifts, run 3

Document: *Code of Conduct, Section 7: Gifts and Hospitality* — `evals/_cases/case-009-en-gifts/document.md`

**Title.** A gift is defined as excluding meals, travel and accommodation, but Section 7.4 calls a meal or travel a gift

**Explanation.** Section 7.2 defines hospitality as a meal, travel or accommodation that the recipient does not pay for, and defines a gift as any other thing of value. Section 7.4 then refers to a gift in the form of a meal, travel or accommodation. Under the definition, such an item is hospitality, not a gift, so the reader cannot apply the definition and the declaration rule together.

**Quotes, in their lines:**

- line 14, § 7.2 Definitions: «A gift is any other thing of value that the recipient does not pay for, including goods, vouchers, discounts and services.»
- line 31, § 7.4 Declaration: «A gift in the form of a meal, travel or accommodation is declared with the name of the third party that paid for it.»

**What the key holds on these lines:**

- `A04-1`, a defect of A04, also A01: A meal, travel or accommodation is hospitality by its definition, and the declaration line calls it a gift; a dinner worth 80 euros is within the hospitality limit and above the gift limit, so a reader cannot tell whether it needs an approved exception.
- `R-6`, residue the case set accepted: Section 7.6 foresees that an employee learns late that a received gift is above the limit, but its only rule is to hand the gift in unused; a service, a discount or a consumed good cannot be handed in, and the rule to pay the excess covers only hospitality received, so the document says nothing for a received gift that is already used.

Verdict: 

Note: 

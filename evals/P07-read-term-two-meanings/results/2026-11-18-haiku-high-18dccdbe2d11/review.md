# Unmatched findings of A04 — term-two-meanings — the verdicts

**What was tested.** Each finding below came from heuristic A04, prompt `prompts/P07-read-term-two-meanings/prompt-01.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — a contradiction, an ambiguity, a gap, circular authority, an unowned obligation.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.
Notes marked *Second reviewer* hold the verdict of an independent model review, accepted by the maintainer; the word in brackets is that review's confidence.

**Status.** 2 of 2 items ruled.

<details><summary>The instruction A04 obeyed (<code>prompts/P07-read-term-two-meanings/prompt-01.md</code>)</summary>

Find each term that the document uses with two meanings.
Report each such term as a separate finding.

A term is a word or a short phrase that names a thing, a person, a role, an act, a time or a document.

First, find each term that the document defines.
Also find each term that the document uses as a name, with no definition.
Then find each passage that uses the term.

Read the document as the reader who obeys it.
This reader knows only the text of the document.
For each passage, find the meaning that the term has in that passage.
If two passages need two different meanings, and the reader acts differently on each meaning, report the term.

Find these causes:

- The document defines a term, and a different passage uses the same term for a different thing.
- The document gives no definition, and the context of two passages shows two different things with one name.
- A term with a qualifier, for example "the second check", names two different acts in two places.

Before you report, read the whole document for a passage that tells which meaning applies.

Do not report these:

- A term that has one meaning in each passage, also when it names different persons, things or times in different cases.
- A new meaning that the document gives to a term for one section only, if the passage names that section.
- Two different terms that look alike, for example "the changed document" and "the replaced document".
- A word of the general language that the document does not use as a name.
- The same term in a different grammatical form.
- Two passages that cannot both be true under any reading. That is a contradiction, a different kind of problem.

Quote the passage that defines or first uses the term, and each passage that uses it in the other meaning.
In the explanation, write the two meanings, and what the reader does differently in each meaning.

</details>

## U-03 — case-010-uk-forklift-safety, runs 1, 2, 3 (also U-06, U-09)

Document: *Інструкція з охорони праці під час роботи на навантажувачі на складі* — `evals/_cases/case-010-uk-forklift-safety/document.md`

**Title.** Слово «проїзд» має два значення: дорога або смуга руху і транспортний засіб чи водій.

**Explanation.** У розділі «Швидкість руху» «проїзди» означають ділянки дороги завширшки менше 3 метрів, де діє обмеження 3 км/год. У розділі «Пішоходи та позначені зони» «проїзд» означає того, хто рухається й перетинає пішохідний перехід, тобто транспортний засіб або водія. Через це читач може по-різному зрозуміти, кого саме стосується правило переходу, і діяти інакше.

**Quotes, in their lines:**

- line 39, § Швидкість руху: «в проїздах завширшки менше ніж 3 метри»
- line 56, § Пішоходи та позначені зони: «а проїзд, навіть працюючи, перетинає лише на позначеному переході»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: not a defect

Note: Second reviewer, accepted by the maintainer: Both passages refer to a roadway. In the crossing rule, it is the grammatical object and the pedestrian is the actor. (high)

## U-04 — case-018-uk-document-numbering, run 1

Document: *Стандарт Організації СТО 07 «Нумерація та реєстрація внутрішніх документів»* — `evals/_cases/case-018-uk-document-numbering/document.md`

**Title.** Слово «запис» означає і запис про документ, і підсумковий запис про останні номери

**Explanation.** У розділі 4 запис — це рядок реєстру про один документ, з номером, датою, назвою, посадами виконавця та підписантів. У розділі 6 «останній запис» — це підсумковий рядок про останній присвоєний номер кожного виду документів, без даних про окремий документ. Читач має вносити різні відомості залежно від того, котре значення він обрав.

**Quotes, in their lines:**

- line 50, § 4. Реєстри: «реєстратор вносить до реєстру запис: номер, дату присвоєння»
- line 78, § 6. Початок нового року: «вносить до реєстру попереднього року останній запис — про останній присвоєний номер кожного виду документів.»

**What the key holds on these lines:**

- `R-7`, residue the case set accepted: Слово «номер» в одному рядку означає весь номер із чотирьох частин, а в інших — порядковий номер; дія за обох значень однакова, тож це кандидат на пастку A04.

Verdict: trap

Note: Second reviewer, accepted by the maintainer: Both are register entries. Section 6 explicitly identifies the year-end entry and the information it contains. (high)

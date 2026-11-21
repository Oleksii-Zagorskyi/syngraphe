# Unmatched findings of A04 — term-two-meanings — the verdicts

**What was tested.** Each finding below came from heuristic A04, prompt `prompts/A04-term-two-meanings/prompt-02.md` on claude-haiku-5-5 at effort `high`. The model was told to report only that kind of problem. Its instruction is in full below.

**What a verdict means.** Judge each finding only as a finding of that heuristic:

- `real defect` — the document has the problem that the finding states, of the kind the instruction defines. The key does not hold it yet; the maintainer decides whether it joins the key.
- `trap` — the passages look like that kind of problem, but the document resolves it: another passage marks an exception or says which rule applies. Also when the instruction tells the model not to report that type of passage.
- `not a defect` — the document does not have that kind of problem: the finding misreads the text, or the problem is real but of another kind — a contradiction, an ambiguity, a gap, circular authority, an unowned obligation.

**Only the findings the key does not place are here**, each repeat over the runs under one heading. The key rules on the rest: a finding on another heuristic's planted item is wrong.

The verdicts here are given without reading the judge's, which are in `judge.json`; a verdict may be derived from a note.
Line numbers count from the first line after the case document's frontmatter.

**Status.** 0 of 1 items ruled.

<details><summary>The instruction A04 obeyed (<code>prompts/A04-term-two-meanings/prompt-02.md</code>)</summary>

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
- A term that names the same thing in each passage, also when it has a different role in each sentence.
- A use of a term that is one case of its definition, for example one kind of entry in a register.
- A role that approves its own act. That is a different kind of problem.
- Two passages that cannot both be true under any reading. That is a contradiction, a different kind of problem.

Quote the passage that defines or first uses the term, and each passage that uses it in the other meaning.
In the explanation, write the two meanings, and what the reader does differently in each meaning.

</details>

## U-01 — case-010-uk-forklift-safety, run 1

Document: *Інструкція з охорони праці під час роботи на навантажувачі на складі* — `evals/_cases/case-010-uk-forklift-safety/document.md`

**Title.** Слово «проїзд» має місце і дію водія або працівника

**Explanation.** У розділі про швидкість «проїзд» означає місце, тобто проїзд або проїзну частину, де діє обмеження 3 км/год. У розділі про пішоходів те саме слово стоїть на місці підмета і означає того, хто їде й перетинає дорогу, тобто водія. Читач, який виконує текст, не може визначити, чи стосується правило переходу місця, чи самого водія.

**Quotes, in their lines:**

- line 56, § Пішоходи та позначені зони: «а проїзд, навіть працюючи, перетинає лише на позначеному переході»
- line 39, § Швидкість руху: «в проїздах завширшки менше ніж 3 метри»

**What the key holds on these lines:**

- nothing: no planted defect, trap or residue of any heuristic

Verdict: 

Note: 

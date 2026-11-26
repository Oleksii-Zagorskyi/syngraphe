# Findings the key does not place — the verdicts

**What was tested.** One prompt that reports the problems of six heuristics, A01 to A06, in one call. Each finding below names its heuristic; the key places it on no planted defect and no trap.

**What a verdict means.**

- `real defect` — the document has the problem the finding states, of one of the six kinds; the maintainer decides whether it joins the key.
- `trap` — the passages look like such a problem, but the document resolves it.
- `not a defect` — the document does not have the problem the finding states, of any of the six kinds.

Line numbers count from the first line after the case document's frontmatter.

**Status.** 10 of 10 items ruled.

## U-01 — run 1, case-105-uk-petty-cash, lines 35-41

Document: *Порядок ведення каси та видачі авансів працівникам* — `evals/_held-out/case-105-uk-petty-cash/document.md`

**A05 — Головний бухгалтер і фінансовий директор затверджують аванси один одного**

Для авансу фінансового директора до 5 000 гривень достатньо підпису головного бухгалтера. Коли аванс отримує головний бухгалтер, усі його дії виконує фінансовий директор. Отже, вони взаємно затверджують власні аванси, і незалежного контролю немає.

Quotes, in their lines:

- line 35, § Видача авансу: «Якщо сума авансу становить 5 000 гривень або менше, для видачі достатньо підпису головного бухгалтера на видатковому ордері.»
- line 41, § Видача авансу: «Якщо аванс отримує головний бухгалтер, усі дії головного бухгалтера за цим розділом виконує замість нього фінансовий директор, а якщо аванс перевищує 5 000 гривень, другий підпис у той самий строк ставить директор Організації.»

What the key holds on these lines:

- `R-2`, residue the case set accepted: Рядок про аванс головного бухгалтера повторює умову про 5 000 гривень, а рядки про аванси фінансового директора й директора Організації — ні, тож один бухгалтер вимагає другого підпису на будь-якому авансі цих двох посадових осіб, а інший — лише понад 5 000 гривень, і касир тоді повертає ордер на 3 000 гривень.
- `R-3`, residue the case set accepted: Директорові Організації передано лише «другий підпис ставить», а право відмовити і наслідок відмови названо тільки для фінансового директора, тож один читач вважає, що директор Організації мусить підписати, а інший — що він може відмовити; якщо це мовчання, а не два прочитання, то це прогалина A03 з тією самою впевненістю.
- `R-5`, residue the case set accepted: Для авансу до 5 000 гривень фінансовий директор сам погоджує аванс головного бухгалтера, а головний бухгалтер — аванс фінансового директора, і кожен перевіряє звіт іншого; це схоже на «A погоджує B, B погоджує A», але читається як задумана взаємна перевірка.

Verdict: not a defect

Note: Навіть якщо для видачі авансу на суму до 5 000 гривень включно достатньо одного підпису, видатковий ордер для кожного з двох посадовців підписує інший. Таке взаємне погодження саме по собі не дає жодному з них права затвердити власний аванс.

## U-02 — run 1, case-105-uk-petty-cash, lines 72-73

Document: *Порядок ведення каси та видачі авансів працівникам* — `evals/_held-out/case-105-uk-petty-cash/document.md`

**A06 — Не сказано, хто передає рішення про нестачу касирові та головному бухгалтерові**

Фінансовий директор лише письмово вирішує питання про вину касира. Строки касира (десять днів) і головного бухгалтера (день отримання) починаються від цього рішення. Жодне правило не доручає ролі надіслати рішення цим двом, тому строки можуть не почати відлік.

Quotes, in their lines:

- line 72, § Щомісячний підрахунок: «Якщо нестача виникла з вини касира, касир протягом десяти робочих днів після цього рішення вносить суму нестачі на банківський рахунок Організації.»
- line 73, § Щомісячний підрахунок: «Якщо нестача виникла не з вини касира, головний бухгалтер списує її на підставі цього рішення в день його отримання.»

What the key holds on these lines:

- `R-8`, residue the case set accepted: Для нестачі з вини касира гроші надходять на банківський рахунок, але ніхто не закриває нестачу в касовій книзі, тож книга й далі показує більше, ніж є в касі.

Verdict: real defect

Note: Фінансовий директор письмово вирішує, чи винен касир у нестачі, але Порядок не визначає, хто передає рішення тому, хто має його виконати. Якщо касир винен, він має внести кошти протягом десяти робочих днів від дня рішення, навіть якщо ще про нього не знає. Якщо вини касира немає, головний бухгалтер має списати нестачу в день отримання рішення, яке йому ніхто не зобов’язаний надіслати.

## U-03 — run 1, case-110-en-company-phones, lines 35-35

Document: *Company Phone Policy* — `evals/_held-out/case-110-en-company-phones/document.md`

**A05 — Finance Director deducts from own salary**

The Finance Director deducts amounts from the holder's next salary or payment. When the Finance Director is the holder, they would carry out the deduction on themselves. The stand-in rule covers only the statement and the decision, not the deduction, so the Finance Director would carry out the deduction on their own pay.

Quotes, in their lines:

- line 35, § Monthly plan limit: «The Finance Director deducts the amount that the holder pays from the holder's next salary payment.»

What the key holds on these lines:

- `R-3`, residue the case set accepted: The IT service desk signs the return record for its own member's phone and the Finance Director deducts from the Finance Director's own pay, although both are acts of execution without discretion.

Verdict: not a defect

Note: The deduction itself is mandatory. For the director’s own monthly excess, the Managing Director decides the personal-use amount if an explanation is submitted. Without one, the full excess is due. For an unreturned phone, the asset register supplies the amount. Processing payroll gives the director no choice over the charge.

## U-04 — run 1, case-118-en-performance-reviews, lines 54-55

Document: *Annual Performance Review Process* — `evals/_held-out/case-118-en-performance-reviews/document.md`

**A05 — HR Lead receives and screens an appeal against the HR Lead's own rating**

Every appeal goes in writing to the HR Lead, who rejects late appeals and passes timely ones to the Appeals Committee. When the HR Lead is the appellant, the HR Lead decides on the HR Lead's own appeal at the gate. No rule gives another role this step in that case.

Quotes, in their lines:

- line 54, § 7. Appeal: «An employee may appeal against the final rating in writing to the HR Lead within 10 working days after receiving the copy of the review form.»
- line 55, § 7. Appeal: «The HR Lead rejects an appeal submitted after that time limit, and the final rating stands.»

What the key holds on these lines:

- `R-2`, residue the case set accepted: The HR Lead votes on the final rating and then alone decides whether an appeal against it is in time, though that decision is a mechanical test of a time limit and not a judgement of the rating.
- `R-4`, residue the case set accepted: "That day" can be the day of the conversation or the last day of February, but the two readings come from the one sentence read alone, and section 7 counts from the actual receipt in both.

Verdict: trap

Note: Section 7 makes the HR Lead check whether an appeal arrived within ten working days of receipt of the form. A timely ordinary appeal must go to the Appeals Committee. Even assuming the HR Lead is in scope, the deadline check gives them no discretion to uphold their own rating or reject a timely appeal.

## U-05 — run 1, case-119-uk-social-media, lines 51-66

Document: *Рекомендації щодо поведінки в соціальних мережах* — `evals/_held-out/case-119-uk-social-media/document.md`

**A03 — Для редактора соціальних мереж не передбачено заміщення**

Директор має заступника, керівник відділу комунікацій — призначеного працівника. Для редактора заміни немає, хоча він має суворі строки: щоденний перегляд коментарів і зупинку дописів за тридцять хвилин. Якщо редактора немає, документ не каже, хто виконує ці обов'язки.

Quotes, in their lines:

- line 51, § Погодження відповідей на коментарі: «Редактор соціальних мереж щоробочого дня переглядає коментарі в усіх офіційних акаунтах.»
- line 66, § Кризовий допис: «Редактор соціальних мереж зупиняє публікацію всіх запланованих дописів протягом тридцяти хвилин після отримання рішення.»

What the key holds on these lines:

- nothing

Verdict: real defect

Note: Редактор має переглядати коментарі кожного робочого дня та зупиняти публікацію запланованих дописів протягом тридцяти хвилин після отримання рішення про кризову ситуацію. Розділ «Заміщення» визначає, хто заміщує директора та керівника відділу комунікацій, але не визначає, хто виконує ці два обов’язки за відсутності редактора.

## U-06 — run 2, case-105-uk-petty-cash, lines 32-41

Document: *Порядок ведення каси та видачі авансів працівникам* — `evals/_held-out/case-105-uk-petty-cash/document.md`

**A05 — Головний бухгалтер і фінансовий директор взаємно вирішують питання щодо авансів одне одного**

Загальне правило дає головному бухгалтерові рішення за заявою кожного працівника, зокрема фінансового директора. Коли аванс отримує сам головний бухгалтер, його дії виконує фінансовий директор. Виходить замкнене коло: кожен вирішує питання іншого. Те саме стосується перевірки звітів, де головного бухгалтера замінює фінансовий директор.

Quotes, in their lines:

- line 32, § Видача авансу: «Головний бухгалтер протягом двох робочих днів після отримання заяви складає і підписує видатковий ордер або письмово відмовляє працівникові із зазначенням підстави.»
- line 41, § Видача авансу: «Якщо аванс отримує головний бухгалтер, усі дії головного бухгалтера за цим розділом виконує замість нього фінансовий директор»

What the key holds on these lines:

- `R-1`, residue the case set accepted: Якщо касир подає заяву з метою, що стосується діяльності Організації, «лише тоді» забороняє відмову і зобов'язує головного бухгалтера скласти ордер, а «Касирові аванс не видається» забороняє видачу; м'якше прочитання — касир заяву не подає.
- `R-2`, residue the case set accepted: Рядок про аванс головного бухгалтера повторює умову про 5 000 гривень, а рядки про аванси фінансового директора й директора Організації — ні, тож один бухгалтер вимагає другого підпису на будь-якому авансі цих двох посадових осіб, а інший — лише понад 5 000 гривень, і касир тоді повертає ордер на 3 000 гривень.
- `R-3`, residue the case set accepted: Директорові Організації передано лише «другий підпис ставить», а право відмовити і наслідок відмови названо тільки для фінансового директора, тож один читач вважає, що директор Організації мусить підписати, а інший — що він може відмовити; якщо це мовчання, а не два прочитання, то це прогалина A03 з тією самою впевненістю.
- `R-5`, residue the case set accepted: Для авансу до 5 000 гривень фінансовий директор сам погоджує аванс головного бухгалтера, а головний бухгалтер — аванс фінансового директора, і кожен перевіряє звіт іншого; це схоже на «A погоджує B, B погоджує A», але читається як задумана взаємна перевірка.

Verdict: not a defect

Note: Головний бухгалтер розглядає заяву фінансового директора й перевіряє його звіт. Коли заяву або звіт подає головний бухгалтер, ці дії виконує фінансовий директор. Кожен розглядає документи іншого, і рішення щодо одного авансу не залежить від рішення щодо іншого.

## U-07 — run 2, case-119-uk-social-media, lines 66-83

Document: *Рекомендації щодо поведінки в соціальних мережах* — `evals/_held-out/case-119-uk-social-media/document.md`

**A03 — Для редактора соціальних мереж немає заміщення**

Директор і керівник відділу комунікацій мають заступників, а редактор не має. Проте в редактора є обовʼязки зі строками: зупинити заплановані дописи за тридцять хвилин і щодня переглядати коментарі. Якщо редактор відсутній, жодне правило не каже, хто це виконує.

Quotes, in their lines:

- line 83, § Заміщення: «У разі відсутності директора його обовʼязки за цими рекомендаціями виконує заступник директора.»
- line 66, § Кризовий допис: «Редактор соціальних мереж зупиняє публікацію всіх запланованих дописів протягом тридцяти хвилин після отримання рішення.»

What the key holds on these lines:

- nothing

Verdict: real defect

Note: За розділом «Заміщення» редактор заміщує керівника відділу комунікацій. Хто заміщує самого редактора й має протягом тридцяти хвилин зупинити публікацію запланованих дописів у разі кризи, документ не визначає.

## U-08 — run 2, case-121-uk-translation-official-papers, lines 75-75

Document: *Порядок перекладу офіційних документів* — `evals/_held-out/case-121-uk-translation-official-papers/document.md`

**A06 — Не вказано, хто передає виконаний переклад діловодові**

Діловод передає перевіряльникові «отриманий» переклад у день отримання. Жоден пункт не зобов'язує перекладача передати готовий переклад діловодові і не каже, як це робиться. Розділ 5 і розділ 4 лише вимагають «виконати» переклад у строк. Тому відправника виконаного перекладу не визначено.

Quotes, in their lines:

- line 75, § 6. Перевірка перекладу: «Діловод передає отриманий переклад перевіряльникові в день отримання.»

What the key holds on these lines:

- nothing

Verdict: real defect

Note: Розділи 4 і 5 встановлюють строки виконання перекладу. За розділом 6 діловод передає переклад перевіряльникові в день отримання. Хто має передати готовий переклад діловодові, Порядок не визначає. Тому навіть вчасно виконаний переклад може не надійти на перевірку.

## U-09 — run 3, case-105-uk-petty-cash, lines 56-60

Document: *Порядок ведення каси та видачі авансів працівникам* — `evals/_held-out/case-105-uk-petty-cash/document.md`

**A05 — Головний бухгалтер і фінансовий директор перевіряють звіти один одного**

Звіт головного бухгалтера перевіряє замість нього фінансовий директор. Звіт фінансового директора не має окремого правила, тому його перевіряє головний бухгалтер за загальним правилом. Виходить, що вони взаємно затверджують звіти за аванси один одного, і незалежної перевірки немає.

Quotes, in their lines:

- line 60, § Звіт за аванс: «Якщо звіт подає головний бухгалтер, усі дії головного бухгалтера за цим розділом щодо цього звіту виконує замість нього фінансовий директор.»
- line 56, § Звіт за аванс: «Головний бухгалтер протягом трьох робочих днів після отримання звіту перевіряє його»

What the key holds on these lines:

- `R-4`, residue the case set accepted: Заміна діє, коли головний бухгалтер «подає» звіт, і лише «щодо цього звіту», тож коли головний бухгалтер сам не подав звіт у строк, він мав би вимагати звіт від самого себе (A05) або цей випадок лишається без виконавця (A03).
- `R-5`, residue the case set accepted: Для авансу до 5 000 гривень фінансовий директор сам погоджує аванс головного бухгалтера, а головний бухгалтер — аванс фінансового директора, і кожен перевіряє звіт іншого; це схоже на «A погоджує B, B погоджує A», але читається як задумана взаємна перевірка.

Verdict: not a defect

Note: За загальним правилом звіт фінансового директора перевіряє головний бухгалтер. Коли звіт подає головний бухгалтер, перевірку проводить фінансовий директор. Отже, кожен із двох посадовців подає свій звіт на перевірку іншій особі.

## U-10 — run 3, case-119-uk-social-media, lines 51-83

Document: *Рекомендації щодо поведінки в соціальних мережах* — `evals/_held-out/case-119-uk-social-media/document.md`

**A03 — Для редактора соціальних мереж немає заступника**

Директор і керівник відділу комунікацій мають заступників, а редактор соціальних мереж не має. Редактор має строкові обовʼязки: щодня переглядати коментарі й за тридцять хвилин зупинити заплановані дописи в кризу. Якщо редактора немає, ніхто не знає, хто виконує ці дії.

Quotes, in their lines:

- line 83, § Заміщення: «У разі відсутності директора його обовʼязки за цими рекомендаціями виконує заступник директора.»
- line 66, § Кризовий допис: «Редактор соціальних мереж зупиняє публікацію всіх запланованих дописів протягом тридцяти хвилин після отримання рішення.»
- line 51, § Погодження відповідей на коментарі: «Редактор соціальних мереж щоробочого дня переглядає коментарі в усіх офіційних акаунтах.»

What the key holds on these lines:

- nothing

Verdict: real defect

Note: Директора заміщує його заступник, а керівника відділу комунікацій — редактор соціальних мереж. За відсутності самого редактора документ ні на кого не покладає обов’язку щоробочого дня переглядати коментарі та протягом тридцяти хвилин після отримання рішення про кризову ситуацію зупиняти публікацію запланованих дописів.

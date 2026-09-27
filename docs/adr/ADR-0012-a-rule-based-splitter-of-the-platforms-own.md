---
tags:
  - adr
aliases:
  - ADR-0012 A rule-based sentence splitter of the platform's own
status: accepted
date: 2026-09-27
supersedes: []
superseded_by: []
---

# ADR-0012: A rule-based sentence splitter of the platform's own, with abbreviation lists per language as data

**Date:** 2026-09-27
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** None

## Context

The stored form of a document is one sentence per line (`technical-design.md § The constrained Markdown subset`), and the normalizer splits each changed span of a submitted paragraph into sentences before every commit. A boundary in the wrong place degrades granularity — an over-split renders and anchors identically — but a boundary inside an inline construct changes the parse, which is the one way a boundary is wrong. The text is Ukrainian policy prose: abbreviations that end in a full stop (`п.`, `ст.`, `тис. грн.`, `т. ч.`), initials before a surname, clause numbers, dates and amounts written with stops, quotations spanning sentences. The text is also Markdown: link destinations, attribute blocks and image syntax contain stops and must never be split.

One claim had to hold before the normalizer could be designed (`verification-plan.md` V-09): a rule-based splitter with a per-language abbreviation list places boundaries closely enough that nobody notices a wrong one — at most one in two hundred against a marked reference (DL-0246), zero inside an inline construct. The owner asked for one default splitter with a per-language override, and for existing libraries to be screened on Ukrainian before anything was built.

## Decision

The platform splits sentences with **rules of its own, written once as product code, parameterised by two abbreviation lists per language held as data** — *never final* (a stop after them never ends a sentence) and *may be final* (a stop after them ends a sentence when the next word is capitalised). The rules, in order. Before any rule runs, link destinations, attribute blocks and image syntax are masked, so no candidate can fall inside them. A boundary candidate is terminal punctuation — `.`, `!`, `?` or `…` — plus any closing quotation marks or brackets that follow, then whitespace. `!` and `?` always end a sentence, whatever follows. `…` ends a sentence only before a capitalised word. A full stop does not end a sentence before a lowercase letter or a digit, after a single capital letter (an initial), or after an abbreviation in the language's *never final* list; after an abbreviation in the *may be final* list it ends a sentence only before a capitalised word; otherwise it does. Each sentence inside a multi-sentence quotation is its own line, and the boundary after a quotation falls after its closing mark. Every boundary is then checked by the parse-preservation invariant — the block's HTML, soft breaks read as spaces, identical before and after the split; a boundary that fails it is not written, the two sentences share a line, and the write proceeds.

No library is the default for any language. **The abbreviation lists are data with one canonical copy: a seed fixture in the repository, one file per language, loaded into `LANGUAGE` by the seed command the way prompts are** (`technical-design.md § Prompts are source`). The database row is the copy the splitter reads; an in-place edit of a row is a divergence the seed command reports, folded back into the repository or overwritten, never left as the only copy. In release 0.1 a list is edited in the repository and re-seeded; a page for the platform administrator is backlog B-034.

## Rationale

**It met the claim with nothing to spare, and every library missed it by a wide margin.** On a synthetic Ukrainian policy text of 21,018 words written to carry every hard case at least twenty times, with 1,015 boundaries marked as written, the rules disagree with the marks on **0** boundaries, place **0** inside an inline construct, and preserve the parse at every one; the same on the English text (0 of 1,012). The four rule-based libraries screened and then measured on the same Markdown-masked text disagree on 272 to 380 Ukrainian boundaries each — syntok, the strongest, on one in four. Their failures are systematic, not marginal: none knows the Ukrainian abbreviations, so each splits after `п.`, `ст.`, `тис.` and an initial, and none joins after `р.` or `грн.` at a sentence's end or steps past a closing quotation mark; two of them also place boundaries that change the parse.

**The rules are small and the knowledge is data.** The whole splitter is a few dozen lines; what makes it right for a language is the two lists, which are exactly what a platform administrator can maintain without writing code, and exactly what a library hides inside its package.

**The Markdown has to be understood by whatever splits it.** The normalizer splits Markdown source, not plain text. A library would need the same masking layer wrapped around it, and would still not know the whitelist's spans and callouts; the rules of the platform's own were written against the same specification the parser and the editor are configured from (ADR-0010).

**Zero is read with its caveat.** The sample's fragments and the splitter's rules share an author, so the sample exercises the cases the rules know. The owner's approval of the sample for register and realism is the control on that, and a sentence ending in a *never final* abbreviation, which the sample does not contain, is the first case that would fail. The per-language lists exist so that such a case is a data change, not a release.

## Consequences

- The splitter is product code in the normalizer (Epic 4), with the parse-preservation invariant as the write check the technical design already names. The synthetic marked samples are its regression fixture; the six planted bad breaks are its negative cases.
- `LANGUAGE` gains `never_final` and `may_be_final` (the data model); the repository carries the seed fixture per language; a document's language selects the lists. No page edits them in release 0.1 (B-034).
- The normalizer version recorded per commit names the rule set and the revision of the lists it loaded, so a list edit is a new normalizer version and a line's split can be traced to the lists that made it.
- A wrong boundary found in use is corrected by editing a list, and applies only to text edited afterwards: a stored line is never re-normalised (DL-0112).
- Adding a language means writing its two lists; the rules do not change.
- The libraries are not dependencies. Nothing in the image depends on a segmentation package.
- Not measured: text in a language whose sentence-final punctuation differs from the full stop, and prose with ellipses as a sentence's end, which the rules treat as terminal only before a capitalised word.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| Rules of the platform's own, abbreviation lists per language as data | verification plan (V-09) | chosen |
| pysbd 0.3.4 | agent | rejected — no Ukrainian rules; with its Russian rules, 324 disagreements on the Ukrainian sample and 49 boundaries that change the parse |
| sentence-splitter 1.4 (Moses-style non-breaking prefixes) | agent | rejected — 304 disagreements; a prefix file could be written for Ukrainian, but the rule set behind it still fails at closing quotation marks and sentence-final abbreviations |
| spaCy 3.8.16 `sentencizer` | agent | rejected — punctuation rules with no abbreviation knowledge; 380 disagreements, 64 parse-changing |
| syntok 1.4.4 | owner (as a possible Ukrainian default) | rejected — the best library, 272 disagreements; English-centric abbreviation handling |
| A statistical or neural segmenter (NLTK Punkt, spaCy's parser, Stanza) | agent | not measured — outside the claim, which names a rule-based splitter: their boundaries cannot be explained to a reader or corrected by editing a list, and Punkt has no Ukrainian model |
| One default library with per-language overrides where a library does better | owner | not taken — no library did better on any language measured; the structure survives as *one rule set, per-language lists* |

## Review triggers

- A boundary error found in a real document that no list edit can correct.
- A language whose sentences do not end in a full stop, a question or an exclamation mark.
- The parse-preservation invariant failing on a boundary the rules placed, in use.

## Appendix — what was compared, and how

Every candidate received the same input: each inline block of the marked sample with the marks removed and with link destinations, attribute blocks and image syntax replaced by letters of the same length, so that offsets are preserved and no candidate is penalised for not knowing Markdown. Its boundaries were compared with the marks; a mark it missed is *too coarse*, a boundary it added is *too fine*. Each boundary it placed was then re-rendered through markdown-it-py with a line break at that point and compared with the unsplit block's HTML, soft breaks read as spaces. Versions are those installed on 2026-09-27 in `python:3.12-slim-bookworm`.

| Candidate | Ukrainian: disagreements of 1,015 (coarse / fine) | parse-changing | English: disagreements of 1,012 (coarse / fine) | Abbreviation list for Ukrainian | Markdown-aware without the mask |
|---|---|---|---|---|---|
| Rules of the platform's own | **0** (0 / 0) | 0 | **0** (0 / 0) | yes, as data | yes |
| syntok 1.4.4 | 272 (155 / 117) | 8 | 172 (64 / 108) | no | no |
| sentence-splitter 1.4 | 304 (74 / 230) | 0 | 234 (58 / 176) | writable | no |
| pysbd 0.3.4 (Russian rules) | 324 (125 / 199) | 49 | 299 (66 / 233) | no | no |
| spaCy 3.8.16 `sentencizer` | 380 (58 / 322) | 64 | 393 (50 / 343) | no | no |

The typical coarse case: *«… до кінця поточного р. Після того як …»* — the stop after `р.` ends the sentence and the next word is capitalised; every library reads `р.` as an abbreviation and continues. The typical fine case: *«… відповідно до п. 4.2.1 цього Положення …»* — every library ends a sentence after `п.`.

## References

- Originating decision-log entry: DL-0257
- `verification-plan.md` V-09
- ADR-0010 — one specification for the editor and the parser
- DL-0112 — a stored line is never re-normalised; DL-0246 — the threshold
- `technical-design.md § The constrained Markdown subset`

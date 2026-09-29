# Sentence splitter fixtures

The regression and negative cases of the normalizer's sentence splitter and its parse-preservation check (ADR-0012, `docs/verification-plan.md` V-09). Every text here is invented; no real document, organisation or person appears.

| File | Holds |
|---|---|
| `sample-ukr.marked.md` | A synthetic Ukrainian policy text, about 21,000 words, written to carry every hard case many times — abbreviations ending in a full stop, initials, clause numbers, amounts and dates, sentence-final abbreviations, quotations of several sentences, lists, callouts, spans, bold across a boundary, links with dotted destinations. Each paragraph stands on one line; the author marked every intended sentence boundary with `¦` (U+00A6), after the terminal punctuation and any closing mark, only between two sentences of one block. 1,015 marks in the body |
| `sample-eng.marked.md` | The same for English, about 27,500 words. 1,012 marks in the body |
| `sample-ukr.counts.json`, `sample-eng.counts.json` | How many times each hard case occurs in each sample, and the number of marked boundaries and words |
| `planted-breaks.json` | Six line breaks inside an inline construct — a link destination, an attribute block, an image, and before a line that would start `1. `, `# ` or `- ` — that the check must catch, and two controls — inside bold and inside a span's text — it must let through. `¦` marks where the break goes |

## Rules

- **The marks are the reference.** A disagreement is a boundary the splitter places where no mark stands, or a mark where it places none. A mark is never moved to make the splitter pass; a wrong mark found in a sample is corrected as a change to the sample, with its reason.
- **The samples carry `synthetic: true` in their frontmatter**, which the platform's frontmatter parser refuses; the tests split the body off themselves.
- **Every text is invented.** A role, a person or a document named in a sample is a synthetic example.

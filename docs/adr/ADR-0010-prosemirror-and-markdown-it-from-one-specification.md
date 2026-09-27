---
tags:
  - adr
aliases:
  - ADR-0010 ProseMirror and markdown-it from one specification
status: accepted
date: 2026-09-27
supersedes: []
superseded_by: []
---

# ADR-0010: ProseMirror in the editor, markdown-it on both sides, one specification

**Date:** 2026-09-27
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** None

## Context

The editor is the one client island in a server-rendered application (ADR-0004), with several instances on a page, one per open section (ADR-0006). What it stores is not ordinary Markdown: one sentence per line, a line break the user never sees, attributed spans for entities and underline, typed callouts, and one spelling per construct (`technical-design.md § The constrained Markdown subset`). The whitelist binds the server-side parser as well as the editor (ASR-19), and a rule enforced differently on the two sides is the same defect as having no whitelist.

Four claims had to hold before a library could be chosen (`verification-plan.md` V-01 to V-04). An existing library had to meet the editor's constraints, including licence (ASR-13) and mounting without a client framework. The whitelist had to round-trip losslessly, and everything outside it had to be refused with a message. Sentence boundaries had to survive editing. One specification had to drive both the editor and the parser.

## Decision

The editor is **ProseMirror, used directly** — its model, view, state, transform and tables packages — with **markdown-it** as its Markdown parser and a serialiser that the application writes. The server-side parser is **markdown-it-py**. Both are configured from **one machine-readable specification** of the whitelist. The rules the specification cannot express as data — the attributed-span tokenizer, the callout rule and the validator — are written once in each language. One conformance suite, run in CI, holds the two in step.

## Rationale

**The serialisation has to be ours.** The stored form is Markdown with constraints no stock serialiser follows: a canonical table row, one spelling per construct, a sentence boundary written only between two pieces of text, `<` escaped so literal text never reads as HTML. ProseMirror keeps the document model and the serialiser separate, and the serialiser is ordinary application code. The other candidates put a library's opinions between the document and the bytes on disk.

**The parser has a twin on the server.** markdown-it-py is a port of markdown-it with the same rule architecture, so both sides can run the same rules. On a 100-case conformance list — every whitelist row, every refusal, alternative spellings and edge cases chosen to make parsers disagree — they returned identical verdicts, refusal codes and line numbers on Python 3.12 / Debian. A deliberately drifted specification was caught on the one case it changed.

**It passed every claim.**
- Every whitelist row round-tripped with zero differences after canonicalisation through the editor, its DOM, its clipboard and the source view.
- Every refusal case was refused at paste, with a message naming the construct and its line.
- Sentence boundaries held as an invisible inline node that renders as the space between sentences. Every boundary outside an edited sentence came back unchanged, and undo restored the text exactly.
- Three instances ran independently on one page, each with its own source-view switch.
- On a forty-page document typed at a human pace, keystroke to screen was 27 ms at the 95th percentile, against ASR-21's 50 ms; the editor's own work per keystroke was 1 ms at the 95th percentile. Measured in Chrome on a current workstation.

**The choice is cheap to revise toward a higher-level editor.** Tiptap and Milkdown are ProseMirror underneath: the document model, schema and plugins carry over, so a later move to either keeps most of the work.

## Consequences

- The application owns more code than a packaged editor would need: the toolbar, typing shortcuts, the Markdown parser and serialiser, and table editing controls.
- The whitelist specification, the conformance suite and the three rules written per language are product code, with the conformance suite in CI. A rule changed on one side without the other fails the suite.
- Sentence boundaries are nodes in the editor's document. The serialiser writes one only between two pieces of text, or deleting a sentence would store a paragraph break.
- Alternative spellings (`*` bullets, `_italic_`, setext headings, nested marks in another order) are rewritten to the stored spelling by the normalizer (DL-0240). The editor's serialiser already writes that spelling.
- Paste interception reads the clipboard's HTML and files, not only its text. Images pasted from the clipboard are stored as files (DL-0232).
- The spike amended the whitelist: plain quotes admitted, and text on a callout's marker line moved into its first paragraph (DL-0238); tables at the top level only (DL-0239).
- ADR-0004 is accepted with this record: the chosen library runs several independent instances on one page (V-01).
- Continuous capture must not serialise a whole long document on each keystroke: serialising forty pages took 54–90 ms. It serialises on a pause, or only the changed range.
- The dependency tree is MIT, apart from `entities` (BSD-2-Clause) and `argparse` (PSF-2.0). All are redistributable in an Apache-2.0 product with their notices, which will ship in a third-party licences file.
- ProseMirror is maintained mostly by one person. It has been stable at 1.x for years, and Tiptap depends on it, which spreads the interest in keeping it maintained.
- Not measured: browsers other than Chrome, and slower hardware than a current workstation.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| ProseMirror with markdown-it; markdown-it-py on the server; one specification | agent | chosen |
| Tiptap 3 | verification plan | rejected — passed the editing trial, but its Markdown parser (marked) has no server-side twin, and it showed a paragraph's stored line breaks to the user. The runner-up, and the natural target if a higher-level API is wanted later |
| Milkdown 7 | verification plan | rejected — ProseMirror with a remark pipeline, which has no server-side twin; heading levels 1 and 2 failed from its toolbar command in the trial |
| Lexical | verification plan | rejected — pre-1.0; its stock Markdown conversion has no tables, and it showed stored line breaks |
| Slate | verification plan | rejected — its view layer needs React, against the plain-JavaScript island of ADR-0004 |
| Pandoc as the server-side parser | verification plan | rejected — gave the same reading as the editor on 67 of the conformance list's 69 accept cases, but as a second parser with its own tree the validator would be written against another model. Its callout support lacks the *example* type. Its GPL licence was not a reason: run as a separate program, as for DOCX export, it does not bind the product; it would only as a library linked into it |
| Boundaries kept outside the document as remapped positions | agent | rejected — a bold span crossing a boundary was rewritten on load, and Backspace and the arrow keys stepped over the visible space inconsistently |
| CKEditor 5, TinyMCE | agent | rejected — GPL-2+ or commercial licence (ASR-13) |
| Quill | agent | rejected — its model is text with formatting laid over it, not a document tree |
| Editor.js | agent | rejected — inline content is an HTML string inside each block |
| BlockNote | agent | rejected — React-first |
| Toast UI Editor | agent | rejected — no release since February 2023 |

## Review triggers

- A construct is added to the whitelist that markdown-it cannot tokenise with a rule of the same shape on both sides.
- The conformance suite needs a case-specific exception to pass.
- Typing latency exceeds ASR-21 on the organisation's own hardware.

## Appendix — what was compared, and how

The comparison ran in two stages. The long list screened every candidate on the three requirements that need no test: a licence the product can redistribute, a real document tree whose serialisation the application controls, and mounting without a client framework. The short list covers the candidates that passed. Each was loaded into the same small harness with the same toolbar, and one scripted trial ran on all of them in Chrome: three instances on one page, each holding one section of a synthetic document. The candidate that passed the trial then ran the full whitelist, sentence-boundary and typing-speed tests (V-02, V-03, ASR-21). Versions are those installed on 2026-09-27.

### Long list — the basic requirements

| Candidate | Version | Licence | Document tree the application serialises | Plain-JavaScript mounting | Maintained | Result |
|---|---|---|---|---|---|---|
| ProseMirror, direct | model 1.25.12, view 1.42.6 | MIT | yes — schema-typed node tree | yes | yes | short list |
| Tiptap 3 | 3.31.3 | MIT | yes — ProseMirror underneath | yes | yes | short list |
| Milkdown 7 | 7.22.2 | MIT | yes — ProseMirror underneath | yes | yes | short list |
| Lexical | 0.51.0 | MIT | yes — its own node tree | yes | yes, pre-1.0 | short list |
| Slate | 0.126.2 | MIT | yes | no — its view layer needs React | yes | out |
| BlockNote | 0.55.0 | MPL-2.0 | yes — ProseMirror underneath | no — React-first | yes | out |
| Toast UI Editor | 3.2.2 | MIT | yes | yes | no — last release February 2023 | out |
| Editor.js | 2.31.7 | Apache-2.0 | no — inline content is an HTML string per block | yes | yes | out |
| Quill | 2.0.3 | BSD-3-Clause | no — text with formatting laid over it | yes | yes | out |
| CKEditor 5 | current | GPL-2+ or commercial | yes | yes | yes | out — licence |
| TinyMCE | current | GPL-2+ or commercial | yes | yes | yes | out — licence |
| CodeMirror 6 | 6.43 | MIT | no — plain text | yes | yes | out as the rich editor; usable for a source view |

### Short list — the editing trial

Stock configuration, with no candidate yet taught the attributed spans or callouts; the same three-section synthetic sample and the same trial script throughout.

| Question | ProseMirror, direct | Tiptap 3 | Milkdown 7 | Lexical |
|---|---|---|---|---|
| Three independent instances on one page | yes | yes | yes | yes, after removing stock converters that need a code-block node |
| Typing in one section changes only that section | yes | yes | yes | yes |
| Bold, italic, link, lists, quote, undo from the toolbar | pass | pass | pass | pass |
| Headings 1 to 4 from the toolbar | pass | pass | levels 1 and 2 fail | pass |
| Insert a table, add a row | pass | pass | pass — new tables carry alignment marks | fail |
| A Markdown table loads as a table | yes, with a serialiser written for it | yes | yes | no — stock converters have no table |
| `##` typed inside a section becomes a new heading | yes | yes | yes | yes |
| Source-view switch with no edit leaves the text unchanged | yes | yes | yes | yes |
| An edit in the source view arrives in the rich view | yes | yes | yes | yes |
| Paste reaches application code before it enters the document | yes | yes | yes | yes |
| A paragraph's stored line breaks, in the rich view | hidden; written back as one paragraph | shown as visible breaks | hidden | shown as visible breaks |
| Attributed spans and callouts, before being taught | escaped as text | escaped as text | escaped as text | passed through as literal text |
| Markdown parser in the browser | markdown-it | marked | remark | its own converters |
| The same parser available on the server (Python) | yes — markdown-it-py | no | no | no |
| Stable major version | 1.x | 3.x | 7.x | pre-1.0 |
| Full whitelist, sentence boundaries, typing speed | all passed (V-02, V-03, ASR-21) | not run — not chosen at the trial; the runner-up | not run — not chosen at the trial | not run — not chosen at the trial |

## References

- Originating decision-log entry: DL-0250
- `verification-plan.md` V-01 to V-04
- ADR-0004 — server-rendered pages, the editor as the one client island
- ADR-0006 — the editing surface over one draft
- DL-0232, DL-0238, DL-0239, DL-0240
- `technical-design.md § The constrained Markdown subset`

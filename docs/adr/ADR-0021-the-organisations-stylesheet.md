---
status: accepted
last-updated: 2026-11-12
supersedes:
  - ADR-0013-one-parse-for-every-render-target.md
superseded_by: []
---

# ADR-0021: The organisation's stylesheet — one allowlist checked at every use, the platform's guard after it, the Word reference document derived

**Date:** 2026-11-12
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** ADR-0013-one-parse-for-every-render-target (in part — the reference document authored from the stylesheet)

## Context

Every render target comes from one parse (ADR-0013): the reading view is the HTML the server's parser renders, the PDF is weasyprint over that HTML, and the Word file is Pandoc over it with the platform's classes mapped to named Word styles. ADR-0013 measured structure and left the look open: typography and page layout were *not measured*, and the reference document that gives the named styles their look was to be *authored* from the organisation's stylesheet, without saying by whom or how.

This ADR replaces two phrases of ADR-0013: in § Decision, the reference document *authored from the organisation's stylesheet*; in § Consequences, the reference document *authored with the organisation's stylesheet*. The rest of ADR-0013 stands: one parse for every target, the PDF's fatal fetch failures, Pandoc over the HTML, the named Word styles and the validator that gates every export.

An organisation gives its documents its own look. That look is CSS written by the organisation's administrator, and it meets three constraints at once:

- **Stored content never executes** (ASR-19). CSS written by a tenant reaches every reader's browser and the PDF renderer. CSS can fetch, can generate text, and can hide or move what is there.
- **An export is the approved text.** A stylesheet that could add words, remove a clause from view or restyle the approval line would let an export say something the reviewer did not accept (T-23).
- **The Word file needs the same look in another form.** Pandoc takes a reference document, not CSS, and ADR-0013's third review trigger watches for the two diverging.

## Decision

An organisation has one stylesheet, with no choice per document: every document uses it, or the platform's default look while the stylesheet is empty, and the document's Info page says which applies (DL-0465). The tenant's administrators write it on the styles page, and it is held to an allowlist that one checker applies at every use (DL-0464). It applies to every read-only rendering of document text — the document page, comparisons, historical pages, appendix pages and correction notices — and to the exports, and not to the editor, which keeps the default look (DL-0464). The platform's own sheet is applied after it and outweighs it (DL-0477). The Word reference document is derived from the stylesheet by a fixed mapping, never uploaded or authored, and what cannot map is listed, never guessed (DL-0465). A stylesheet is tried before it is applied, on a built-in invented sample (DL-0466), and every change to it is on the record; a stylesheet may colour text like its background, or shade text in the colours of a change's marks, and both are accepted, with the audit record as the answer to them (DL-0477).

## Rationale

**One subset serves three purposes** (DL-0464). The allowlist keeps an export faithful to the text that was approved, keeps ASR-19 true in every reader's browser, and bounds what the derivation of the Word styles has to express. A rule that had to be justified separately for each purpose would be three lists to keep in step.

**The check belongs where the text is used, not only where it is saved.** A check at *Apply* alone protects against what the checker knew that day. When a rule tightens, the stored row predates it; checking again at serving and at export means the rule holds from the release that carries it, with no migration of stored text and no window in which an old row still reaches a reader.

**A guard that comes last makes the platform's marks independent of the allowlist.** The allowlist admits colour and background, so text can be made to look like a change, or to vanish. The checker does not try to judge that. The marks and the approval line are instead drawn by a sheet the organisation cannot outweigh, because it cannot write `!important` and cannot name the marks' classes.

**A check an author can step around adds little** (DL-0477). Refusing a colour equal to its own background catches only the plainest case, and a minimum contrast needs the cascade resolved for every element. The stylesheet is written by the organisation's own administrator and each change is recorded with its text, so the record is the control.

**One source of the look is maintained once** (DL-0465). With the reference document derived, an administrator edits one stylesheet and both exports follow; an uploaded reference document would be a second source that drifts from the first, and a file of a tenant's making read by the export. The list of what does not map is exactly what ADR-0013's third review trigger watches.

**One stylesheet leaves nothing to select** (DL-0465). A choice per document needs a place to store it and a rule for who may change it; with one stylesheet per organisation neither exists.

**A sample shows what the corpus may not** (DL-0466). Seeing a change before *Apply* is what the sample is for, and an invented text holds every construct whatever the organisation's documents hold.

## Consequences

- The look of the approval line and of a change's marks is the platform's alone, in the browser, the PDF and the Word file; no organisation can restyle them.
- The Word reference document follows the stylesheet without a second source (DL-0465). A fixed mapping takes a selector to Word's named styles — body text, headings, quotations, links, callouts, the marked roles, actions and terms, the underline, clause numbers, the title page's title and details — and a property to its form in the file; `@page` gives the section its size and margins. The derived looks are set over Pandoc's own reference document with the platform's named styles. The derivation is remembered per stylesheet text.
- The styles page exports a sample PDF or Word file of a built-in invented text in the requester's interface language — every construct the whitelist allows, a title page of invented facts in the organisation's layout, an attachment list — rendered through the export's own composition with the text in the box (DL-0466). One sample is queued or running per organisation.
- The pages link the stylesheet from the platform's own route. The address carries a digest of what is served, so it changes with the text, the checker and the guard, and the response at that address is cached for good. The served stylesheet's address changes with a release that changes the checker or the guard, so no reader keeps a cached copy from before it.
- In a PDF the organisation's stylesheet comes after the page furniture, so its page size and margins win, within the checker's bounds.
- The allowlist — elements, classes, properties, value bounds, installed fonts — is product code, and widening it is a decision about all three purposes at once. A class the platform adds to document text is not open to styling until it is added to the list.
- Tightening the checker can turn an applied stylesheet off: its documents return to the default look in every target, and the event is logged, until an administrator applies a text that passes. The styles page shows the refusals by line when the text is applied again.
- The Word file follows the stylesheet only as far as the mapping reaches. A selector of several parts, a rule inside `@media print` and a property with no Word form are each listed on the styles page by line, as what the Word files do not carry (DL-0465). Print rules are the PDF's alone. An administrator reads the difference on the styles page, not in the exported file.
- The fonts an organisation may name are the fonts installed in the image; adding one is a change to the image and to the list.
- Text hidden in its background's colour, and text shaded like a change's mark, are accepted risks, recorded in the threat model under T-23.
- The sample shares the render queue with the exports. A sample still queued and unheld after half an hour is failed, and its file is swept with the exports.
- Several stylesheets per organisation, and with them a choice per document, is a backlog row (DL-0465).

## Alternatives Rejected

- **Any CSS but what fetches**: A denylist of fetching constructs in place of the allowlist. Rejected because an export could stop being the approved text (DL-0464).
- **Requiring a minimum contrast**: The checker refuses text too close to its background. Rejected because it needs the cascade resolved per element (DL-0477).
- **Refusing a colour equal to its own background**: The checker refuses the one declaration pair. Rejected because it catches only the plainest case (DL-0477).
- **An uploaded reference `.docx`, alone or overriding the derived one**: The administrator supplies the Word reference document. Rejected because it would be a second source that drifts from the first, and a file of a tenant's making read by the export (DL-0465).
- **A stylesheet chosen per document, in the frontmatter or on the document's row**: Each document selects its look. Rejected because with one stylesheet per organisation there is nothing to select (DL-0465).
- **A sample from one of the organisation's documents at its canonical edition, alone or beside the invented one**: The sample renders real text. Rejected because an invented sample shows every construct whatever the corpus holds (DL-0466).
- **Backgrounds only on callouts, table cells, quotations and the title, or refused near the colours of the marks**: A narrower admission of `background`. Declined in DL-0477, which gives this option no reason of its own.
- **A structured style form in place of CSS**: The administrator fills fields and writes no CSS. Declined in DL-0464, which gives this option no reason of its own.
- **The stylesheet applied to exports only**: The read-only pages keep the default look. Declined in DL-0464, which gives this option no reason of its own.
- **The stylesheet applied to the editor too**: The editor takes the organisation's look. Declined in DL-0464, which gives this option no reason of its own.

### Option attribution

| Option | Raised by | Outcome |
|---|---|---|
| An allowlist of properties, selectors and values, with nothing that fetches (DL-0464) | the record | **accepted** |
| The stylesheet applied to every read-only rendering of document text and to exports, not to the editor (DL-0464) | the record | **accepted** |
| The platform's sheet applied after the organisation's; colour and background admitted on every element a selector may name; the record as the answer (DL-0477) | the record | **accepted** |
| The reference document derived by the platform through a fixed mapping (DL-0465) | the record | **accepted** |
| One stylesheet per organisation, no choice per document (DL-0465) | the record | **accepted** |
| A built-in invented sample, PDF and Word file (DL-0466) | the record | **accepted** |
| Any CSS but what fetches | the record | rejected |
| Requiring a minimum contrast | the record | rejected |
| Refusing a colour equal to its own background | the record | rejected |
| An uploaded reference `.docx`, alone or overriding the derived one | the record | rejected |
| A stylesheet chosen per document | the record | rejected |
| A sample from one of the organisation's documents | the record | rejected |
| Backgrounds only on some elements, or refused near the colours of the marks | the record | rejected |
| A structured style form in place of CSS | the record | rejected |
| The stylesheet applied to exports only | the record | rejected |
| The stylesheet applied to the editor too | the record | rejected |

## Guardrails / Conditions of validity

The decision is safe only while these controls hold.

- **The allowlist** (DL-0464). The stylesheet may set properties of type, colour, background, borders, spacing and alignment, and in `@page` the page's size and margins, each value within bounds. The only at-rules are `@page` and `@media print`. A selector names only the elements of document text and the classes the platform puts on it that are open to styling; the classes of the platform's own marks — a change's marks, the approval line — cannot be named. A `font-family` is a font installed in the image, listed on the page, or a generic. Nothing that fetches is accepted — `@import`, `@font-face`, `url()`, any function but a colour's — and neither are `content`, `display`, `visibility`, `position`, `opacity` or `!important`. The text is at most 100,000 bytes. Every refusal is named with its line.
- **One checker, run at every use.** The same check runs when the stylesheet is applied, when a sample is asked for, when the stylesheet is served to a browser and at every export. The stored text reaches a reader only through one function, which returns nothing when the text no longer passes. So a row written before a rule tightened reaches no page, no PDF and no Word file; the documents then take the default look.
- **The served stylesheet is confined** (DL-0464). The platform's route answers only a member of the organisation. Each selector is rewritten so that it is confined to the document's text, and `@page` is dropped.
- **The platform's guard comes after it** (DL-0477). A sheet of the platform's own follows the organisation's in the browser and in the PDF, with every declaration `!important`. It fixes the approval line — every property a stylesheet may set, on its own white box — and keeps a change's marks in their own colours and lines, and the words inside a mark in the platform's ink.
- **A PDF is rendered with four sheets in a fixed order** (DL-0464, DL-0477): the platform's default, the page furniture, the organisation's stylesheet as written, and the guard.
- **Only computed values reach the Word file** (DL-0465) — a colour as six hexadecimal digits, a length as an integer, a font's name from the installed list — so no character of the stylesheet's text is copied into a Word file. The approval line's style and the styles of a change's marks are outside the mapping.
- **A sample is checked first and not saved** (DL-0466). Its row is written and audited before it is queued.
- **Every change is on the record** (DL-0477). Applying a stylesheet is audited with the full text before and after. This record is the control for the two accepted risks.

## Review triggers

- A stylesheet is found to have hidden text or imitated a change's mark in a document a reader relied on: DL-0477's declined checks are weighed again.

## References

- Originating decision-log entries: DL-0464, DL-0465, DL-0466, DL-0477; DL-0498 — the sample in the requester's interface language
- ADR-0013 — one parse for every render target; ADR-0010 — one specification for the editor and the parser
- ASR-19; T-23 and `threat-model.md § Accepted risks`
- `technical-design.md § Rendering, styles and layout`, `§ Export`
- `src/rendering/stylesheet.py`, `src/rendering/reference.py`, `src/rendering/styles_views.py`, `src/rendering/sample.py`, `src/rendering/export/docx.py`, `src/rendering/export/pdf.py`, `src/rendering/urls.py`

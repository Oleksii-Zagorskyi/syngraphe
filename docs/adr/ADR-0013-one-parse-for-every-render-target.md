---
tags:
  - adr
aliases:
  - ADR-0013 One parse for every render target
status: accepted
date: 2026-09-27
supersedes: []
superseded_by: []
---

# ADR-0013: One parse for every render target — HTML from the platform's parser, PDF with fetch failures fatal, DOCX from that HTML with named styles

**Date:** 2026-09-27
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** None

## Context

A document is read on a page, exported as PDF and exported as DOCX (`technical-design.md § Rendering, styles and layout`, `§ Export`). Every target must carry the whole whitelist — headings, lists, emphasis, underline, entity spans, quotes, callouts, tables, images, links — and the clause and heading numbering, which is derived at render and never stored. Entity spans must appear as styled text and never as literal syntax. No renderer may reach the network: a document that references a remote image is refused by the parser, and a renderer left offline must fail rather than quietly produce a document with a hole in it (`verification-plan.md` V-10).

The parser is markdown-it-py, configured from the same specification as the editor (ADR-0010). The verification plan named Markdown → HTML → weasyprint PDF and Markdown → Pandoc DOCX; the owner asked for both DOCX routes to be measured and for DOCX to carry named Word styles for callouts and spans, the same names the HTML uses.

## Decision

**Every target is rendered from one parse.** markdown-it-py produces the HTML: the whitelist's elements, entity spans as `span` elements classed by type with the id as a data attribute, callouts as classed `div` elements, sentences joined by the soft-break rule, and the clause and heading numbers attached as labels in a classed `span` at render. The reading view is that HTML with the organisation's stylesheet. **PDF** is weasyprint over that HTML, run with its `fail_on_errors` setting on and a fetcher that serves repository files only, so a fetch that fails ends the render. **DOCX** is Pandoc over that HTML, with a filter that maps the platform's span classes and callout types to named Word styles — `Entity Role`, `Entity Action`, `Entity Term`, `Underline`, `Clause Number`, `Callout Note`, `Callout Warning`, `Callout Example` — and a reference document, authored from the organisation's stylesheet, that gives those styles their look. **The validator gates every export**; a renderer's warning is never a pass, and Pandoc is never asked to decide what a document contains.

## Rationale

**It passed every claim.** A synthetic conformance sample with every whitelist row, the plain quote included, and twelve hand-authored labels arrived complete and structurally correct in all three targets: headings to depth four, lists three deep, italic, bold, underline, the three entity types with ids, the quote with a list inside, the three callout types, a table with three alignments, the image, the three link kinds; all twelve labels verbatim; no literal syntax anywhere. Measured on Python 3.12 / Debian with weasyprint 70.0 and Pandoc 3.9, in a container with no network.

**One parse cannot disagree with itself.** Pandoc reading the Markdown gave the same inspection as Pandoc reading the HTML on every construct measured — and the two routes are still two parsers. Pandoc's CommonMark reader has no *example* callout type and its own reading of every edge case the conformance suite exists to pin (ADR-0010 found two on sixty-nine accept cases); the HTML route removes that surface entirely. What DOCX contains is then decided by the platform's parser and validator, which the editor is bound to, and never by a third reading.

**Offline is only safe when failure is loud.** With the network blocked, weasyprint's stock configuration logs an error for the unreachable image and writes the PDF anyway; with `fail_on_errors` on, the same render raises and writes nothing. Pandoc has no such switch: it warns, replaces the image with its description and exits 0. A renderer that can degrade quietly cannot be the control, so the validator is, and the PDF renderer is configured so that the one failure it can still meet — a fetch — is fatal.

**Named styles are what a Word user can restyle.** A span rendered as inline formatting is fixed at export; a span carrying a named character style is restyled once, in the reference document, for every export. The same names in HTML and DOCX let one stylesheet be maintained in two forms.

## Consequences

- The HTML renderer rules for spans, callouts, soft breaks and labels are a fourth piece of the specification's code, beside the three ADR-0010 names (the tokenizer, the callout rule, the validator). Unlike those three it exists server-side only: the editor renders through its own document model and needs no twin, so the conformance suite fixes the renderer's output for every accept case rather than comparing two ports.
- The reading view, the PDF and the DOCX share one HTML; a construct rendered wrongly is wrong in all three and fixed once.
- The PDF renderer runs with `fail_on_errors` on and a file-only fetcher; the container it runs in has no network as well. Both, not either.
- The DOCX filter and the mapping of classes to style names are product code in Epic 7 (export); the reference document is authored with the organisation's stylesheet (ST-0046) and carries the styles' formatting. Until it does, the styles exist in the document without formatting of their own.
- Pandoc runs as a separate program, as before; its licence does not bind the product, and its source travels with the image.
- The numbering derivation is Epic 4's; this record fixes only that the numbers are labels attached at render, never text in the source, in every target.
- Not measured: typography and page layout, which the throwaway stylesheet did not attempt (ST-0046); appendices and the title page; tables wider than a page; a document long enough to test rendering time.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| HTML from markdown-it-py; PDF from weasyprint with fetch failures fatal; DOCX from Pandoc over that HTML with named styles | agent | chosen |
| DOCX from Pandoc over the Markdown | verification plan | rejected — identical inspection on every construct, but a second parser with its own reading of the whitelist, no *example* callout without a filter, and the labels would have to be written into the Markdown as spans |
| weasyprint in its stock configuration | agent | rejected — with the network blocked it logs an error and writes the PDF anyway |
| Inline formatting for spans and callouts in DOCX (bold, colour, shading written into the runs) | agent | rejected — fixed at export; a named style is restyled in the reference document |
| A DOCX writer other than Pandoc (a Python library building the document from the HTML) | agent | not measured — Pandoc met every construct; a second writer would be a second reading of the HTML to maintain |

## Review triggers

- A whitelist construct that Pandoc's HTML reader cannot carry into DOCX.
- A weasyprint release that changes how fetch failures are reported.
- The reference document diverging from the HTML stylesheet in a way the mapping cannot express.

## Appendix — what was compared, and how

One conformance sample and one negative sample; one throwaway stylesheet with page size, margins and just enough rule to tell each construct apart; every render in a container with no network. Each target was inspected mechanically — the HTML by its elements, the PDF by its extracted text, outline and embedded images, the DOCX by `document.xml`, `styles.xml` and `numbering.xml` — for every construct, for the twelve labels verbatim, and for literal span syntax or callout markers, which must be absent. The negative sample was rendered four ways by weasyprint (stock; stock with `fail_on_errors`; a file-only fetcher; the same with `fail_on_errors`) and once by Pandoc.

| Question | HTML (markdown-it-py) | PDF (weasyprint over the HTML) | DOCX (Pandoc over the HTML) | DOCX (Pandoc over the Markdown) |
|---|---|---|---|---|
| Headings 1 to 4 | yes | yes, as outline entries too | Heading 1–4 styles | Heading 1–4 styles |
| Lists, both kinds, three deep | yes | yes | 18 items to level 2, 3 numbering definitions | same |
| Italic, bold | yes | yes | yes | yes |
| Underline | classed span | styled | `Underline` character style | same |
| Entity spans with ids | classed spans, data attribute | styled | `Entity Role/Action/Term` character styles | same |
| Quote with paragraphs and a list | yes | yes | Block Text | same |
| Callouts note / warning / example | classed divs | styled, labelled | `Callout Note/Warning/Example` paragraph styles | same, through the filter |
| Table with three alignments | yes | yes | one table, left / centre / right | same |
| Image, repository-local | yes | embedded | embedded | embedded |
| Links: https, mailto, repository path | yes | yes | three hyperlinks | three hyperlinks |
| Twelve labels verbatim | yes | yes | yes | yes |
| Literal span syntax or callout marker | none | none | none | none |
| Negative sample, network blocked | validator refuses `image-src` | stock: error logged, PDF written · `fail_on_errors`: raises, nothing written | warns, image replaced by its description, exits 0 | same |

## References

- Originating decision-log entry: DL-0258
- `verification-plan.md` V-10
- ADR-0010 — one specification for the editor and the parser
- DL-0065 — clause numbering derived at render; DL-0184 — marked text carries distinct formatting in every target; DL-0238 — the plain quote
- `technical-design.md § Rendering, styles and layout`, `§ Export`

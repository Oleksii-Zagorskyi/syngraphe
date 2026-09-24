---
tags:
  - technical-design
aliases:
  - Markdown versus LaTeX
status: draft
date: 2026-09-21
---

# Document format — Markdown or LaTeX

Decision support for Q31. Not a decision. Adopting Markdown supersedes DL-0004 and rewrites DL-0012.

## What LaTeX was actually bought for

Three things, per DL-0004 and the owner's own account: section composition through `\input`, print-grade output, and a construct set constrained enough to keep diffs reviewable.

The first no longer needs LaTeX — a web application composes sections from a manifest it owns. The second is a rendering question, not a storage question. The third is where the comparison gets interesting, because **LaTeX is a programming language and Markdown is a document format**, and a whitelist means something different in each.

## What Markdown gains

**A constrained editor becomes achievable.** WYSIWYG-to-Markdown round-tripping is a solved problem with several mature libraries. WYSIWYG-to-LaTeX is not, and DL-0012's normalizer existed largely to compensate. The normal form survives unchanged and gets easier: sentence per line, paragraphs separated by blank lines, which is Markdown's native paragraph rule rather than a convention imposed on it.

**The whitelist stops being a fence around a Turing-complete system.** A LaTeX whitelist has to keep out `\input`, `\write18`, `\def` and everything they reach — user-authored content compiled on a multi-tenant server is a sandboxing problem. A Markdown subset has no escape hatch to fence off. For a platform whose whole purpose is to accept text from many tenants and render it server-side, this is the strongest single argument, and it is a security argument rather than a convenience one.

**Styles become CSS, which is what the designer was promised.** Markdown to HTML to PDF through weasyprint makes the designer's style document a stylesheet — the analogy the owner reached for is no longer an analogy. The chain is already in the owner's toolkit.

**MS Word export becomes cheap.** Markdown to DOCX through pandoc is direct and good; LaTeX to DOCX is painful. The export that was a deferral candidate on cost grounds stops being one.

**The source is readable by the people who own the document.** A policy author can read a raw section file and recognise their own policy. They cannot read LaTeX.

**Diffs carry less markup noise**, which matters because the diff is the review surface.

## What Markdown loses

**Cross-references and numbering are ours to implement.** LaTeX has `\label` and `\ref`. This is the one real loss, and it matters for policy documents, where *"as defined in section 4.2"* is ordinary and must survive renumbering. The mitigation is the rule the writing standards already state — address content by name, not by position: a reference points at a **stable section identifier** and the renderer prints the current number. Heading numbering itself is a render rule derived from heading depth, never stored, which is exactly the table the owner drew.

**Fine typographic control goes.** Widow and orphan handling, kerning, precise page furniture. With one output design and no complex formatting, this is close to free to give up.

**Underline has no Markdown syntax.** The editor offers it, so it needs a representation — an attributed span, which is also how entities get marked.

Tables, mathematics and multi-column layout are not losses, because the document model excludes them.

## The pieces the owner sketched, with a recommendation each

**Main file.** The proposed plain list works, but a `document.yaml` manifest is machine-authoritative and just as readable:

```yaml
title: Document title
language: uk
sections:
  - section01.md
  - section02.md
  - section03.md
```

Section order lives in one place, and the manifest is its own lock unit exactly as `main.tex` was. Validation is mandatory in both directions: every file listed exists, every file present is listed.

**Entity marking.** Backticks are the wrong carrier — they mean *code* to every parser and renderer downstream, including the DOCX export. Pandoc's bracketed span with attributes is real syntax, survives every export path, and is machine-readable:

```markdown
The [CMO]{.role #cmo} is [obliged to approve]{.action} within [10 days]{.term #timeout}.
```

The editor never shows this. A user selects text and marks it as a role, an action or a term; the serialisation is internal. Definitions — what `cmo` *is* — belong in the document's YAML, with the spans marking occurrences.

**Callouts.** Blockquote with a type marker, the convention Obsidian and GitHub both use. A small closed set, styled by the designer's stylesheet.

**Numbering.** Derived at render from heading depth, precisely as tabulated: `#` becomes 1, `##` becomes 1.1, `###` becomes 2.1.1. Never written into the source, so moving a section renumbers everything and breaks nothing.

## Render chain

Markdown to HTML with a stylesheet for PDF through weasyprint; Markdown to DOCX through pandoc; Markdown to HTML for the browser reading view. One source, three targets, no LaTeX toolchain on the server.

## Recommendation

**Switch to Markdown.** The security argument alone carries it: a multi-tenant platform should not compile user-authored input in a language that can read the filesystem. The editor becomes tractable, the designer gets real CSS, Word export stops being expensive, and the only genuine loss — cross-references and numbering — is work we were going to do anyway, because stable identifiers beat stored numbers in any format.

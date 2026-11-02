---
tags:
  - adr
aliases:
  - ADR-0004 Server-rendered pages, editor island
status: accepted
date: 2026-09-24
supersedes: []
superseded_by:
  - DL-0517 (in part — one editor per section)
---

# ADR-0004: Server-rendered pages, the editor as the one client island

**Date:** 2026-09-24
**Status:** Accepted — 2026-09-27, once the editor library was chosen (ADR-0010, `verification-plan.md` V-01)
**Deciders:** Oleksii
**Supersedes:** None

## Context

The interface is a set of pages around one document: reading it, editing it whole or by section, reviewing its changes, composing an export, and administering who may do what. Almost all of it displays state that Django owns — lifecycle, rights, versions, analyses (ADR-0002).

The editor is different in kind. It holds a document tree in the browser, captures typing continuously into the server's draft (ADR-0003), and round-trips the constrained Markdown subset losslessly. Several editors may be open on one page, one per section (DL-0167), each capturing against its own range of the draft.

Changes are displayed word by word inside rendered text (DL-0170). The comparison runs over the sentence-per-line source, which lives on the server, and its output is HTML.

## Decision

Django templates render every page; htmx replaces regions in place; the editor is the only client-side application, mounted as an island in a server-rendered page, one instance per open editor. The change display is rendered on the server and delivered as an HTML fragment.

## Rationale

Rights decide what a user sees, and rights are evaluated on the server. Rendering there keeps a single place where need-to-know is applied: a control a user may not use is never sent to the browser. A client application would need the lifecycle and the rights model mirrored in the browser, and an API whose only consumer is the application itself.

The editor cannot be server-rendered, so it is bounded to an island. It reads and writes through the same endpoints as any other client, and the server-side parser stays the enforcement point for the whitelist (ASR-19).

htmx covers the interactions a full reload would spoil in a long document — opening and closing a section editor, reordering appendices and attachments, composing an export — without a client-side state model.

## Consequences

- The JavaScript build has one substantial dependency: the editor library, with its schema generated from the whitelist specification.
- Editor instances on one page share no browser state; each captures against the server's draft, and the server resolves conflicts between them (DL-0167).
- Interface strings stay in Django's translation catalogues for templates and editor labels alike (ASR-10).
- Word-level change display is a server component, tested at the integration level rather than in the browser.
- The editor library must support several independent instances on one page. V-01 measures this.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| Django templates, htmx, editor as the one client island | agent | chosen |
| Single-page application over a JSON API | agent | rejected — mirrors rights and lifecycle in the browser, and makes every page pay for a need only the editor has |
| Django templates with full page reloads | agent | rejected — opening a section editor or reordering a list would lose the reader's place in a long document |

## Review triggers

- V-01 selects a library that cannot run several independent instances on one page.
- A page other than the editor turns out to need client-side state that htmx cannot carry.

## References

- Originating decision-log entry: DL-0173
- ADR-0002 — Django owns the workflow
- ADR-0003 — linear edit history, continuous capture
- DL-0167, DL-0170
- ADR-0010 — the editor library, whose choice accepted this record

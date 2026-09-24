---
tags:
  - interface
aliases:
  - Syngraphē page wireframes
status: draft
date: 2026-09-23
---

# Pages

Wireframes of the main pages, as ASCII so they diff and review like any other text. **They are a design input, not a story:** several epics build from them, and each of those epics links here.

**Every region carries the release it belongs to**, in the table under its wireframe. A region marked for a later release is drawn so the layout has room for it — **it is not built in 0.1**, and an implementer who meets one builds the space, not the feature.

| Marker | Meaning |
|---|---|
| **0.1** | built in release 0.1, by the epic named |
| **0.2** | the AI half, release 0.2 |
| **later** | after 0.1, not yet assigned to a release |
| **not scheduled** | a scope candidate raised by the owner and not yet designed |

## Document edit page

```
+------------------------------------------------------------------+
| tenant-logo | navigation links                                   |
+------------------------------------------------------------------+
| folder-name / subfolder / document-name                          |
+------------------------------------------------------+-----------+
| {view} / {edit} / {pending-edits} / {analysis}       | companions|
|  +------------------------------------------------+  | block     |
|  | WYSIWYG toolbar; action buttons                |  |           |
|  |  +------------------------------------------+  |  +-----------+
|  |  |  document area                           |  |  | comments  |
|  |  |                                          |  |  | block     |
|  |  |                                          |  |  |           |
|  |  |                                          |  |  |           |
|  |  +------------------------------------------+  |  |           |
|  +------------------------------------------------+  +-----------+
|                                                                  |
+------------------------------------------------------------------+
| footer area                                                      |
+------------------------------------------------------------------+
```

| Region | Release | Built by |
|---|---|---|
| tenant-logo, navigation links | **0.1** | Epic 2 — the shell every page shares |
| breadcrumb — folder / subfolder / document | **0.1** — the document name in slice 1; the folder path when folders exist | Epic 4; folders Epic 10 |
| `{view}` tab | **0.1** | Epic 7 — the reading view |
| `{edit}` tab, toolbar, document area | **0.1** | Epic 4 — the constrained editor |
| action buttons | **0.1** for taking, releasing and sending; companion actions **0.2** | Epic 4 |
| `{pending-edits}` tab | **0.1** — *pending edits* is a fixed glossary term and ST-0031 is in the walking skeleton | Epic 5 — the pending view |
| `{analysis}` tab | **0.1** for the mechanical analyses; the agents' analyses **0.2** on the same tab | Epic 4 |
| companions block | **not scheduled** — see § Companions | — |
| comments block | **later** — backlog B-013 | — |
| footer area | **0.1** | Epic 2 for the frame; the document metadata it shows, Epic 7 |

## Document folder page

```
+------------------------------------------------------------------+
| tenant-logo | navigation links                                   |
+----------------+-------------------------------------------------+
| folder-name    | documents table with action buttons in rows     |
|   ..subfolder  |                                                 |
|                |                                                 |
|                |                                                 |
+------------------------------------------------------------------+
| footer area                                                      |
+------------------------------------------------------------------+
```

| Region | Release | Built by |
|---|---|---|
| tenant-logo, navigation links | **0.1** | Epic 2 |
| documents table, action buttons in rows | **0.1** — the list a created document appears in, and the buttons its viewer's rights allow and no others | Epic 3; browsing and filtering Epic 10 |
| folder tree | **0.1**, slice 3 — until then a flat list | Epic 10 |
| footer area | **0.1** | Epic 2 |

## Send for review page

```
+------------------------------------------------------------------+
| tenant-logo | navigation links                                   |
+------------------------------------------------------------------+
| folder-name / subfolder / document-name                          |
+------------------------------------------------------+-----------+
| {view} / {edit} / {pending-edits} / {analysis}       | companions|
|  +------------------------------------------------+  | block     |
|  |                                                |  |           |
|  |  {change-summary} — the editor's note          |  |           |
|  |  +------------------------------------------+  |  |           |
|  |  | editable text, committed with version    |  |  |           |
|  |  +------------------------------------------+  |  |           |
|  |     {send-for-review-button}                   |  |           |
|  |                                                |  |           |
|  | h2. analysis-1                                 |  |           |
|  |  +------------------------------------------+  |  +-----------+
|  |  |  analysis-output                         |  |  |           |
|  |  |                                          |  |  | empty     |
|  |  |                                          |  |  |           |
|  |  +------------------------------------------+  |  |           |
|  | h2. analysis-2                                 |  |           |
|  |  +------------------------------------------+  |  |           |
|  |  |  analysis-output                         |  |  |           |
|  |  |                                          |  |  |           |
|  |  |                                          |  |  |           |
|  |  +------------------------------------------+  |  |           |
|  +------------------------------------------------+  +-----------+
|                                                                  |
+------------------------------------------------------------------+
| footer area                                                      |
+------------------------------------------------------------------+
```

| Region | Release | Built by |
|---|---|---|
| shell, breadcrumb, tabs | as on the document edit page | — |
| send-for-review button, with *continue editing* beside it | **0.1** | Epic 4 — ST-0029 |
| change summary — the editor's note on what this version changes | **0.1**: the editor writes or edits it, starting from a mechanical summary; it becomes the commit message, so it travels with the version in git. From **0.2** the companion drafts it (DL-0035), and the editor still edits it | Epic 4 — ST-0029 |
| analysis sections | **0.1** for the mechanical analyses; the agents' **0.2**, on the same screen | Epic 4 |
| companions block | **not scheduled** | — |

## Page blocks

### Companions

*Status: not scheduled.* What belongs beside a document: its **attachments**, and **views derived from the document** — for example, the list of this document's internal contradictions. Designed in a focused session of its own; until then the block is a reserved column, collapsed by default.

It can be collapsed to the right, so it does not take space on the screen.

### Comments

*Status: later — backlog B-013.* A view and edit pane for comments, with nested threads.

It can be collapsed to the right, so it does not take space on the screen.

### Footer area

*Status: 0.1.* Metadata of the document.

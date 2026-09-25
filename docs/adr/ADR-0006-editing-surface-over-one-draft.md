---
tags:
  - adr
aliases:
  - ADR-0006 Editing surface over one draft
status: accepted
date: 2026-09-25
supersedes:
  - ADR-0003 (in part — hold expiry)
superseded_by: []
---

# ADR-0006: The editing surface — many editors over one draft, one hold, released on inactivity

**Date:** 2026-09-25
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** DL-0036's rule that the holder's name is shown to everyone; the fixed hold expiry of ADR-0003's consequences

## Context

ADR-0003 gives each document one editing sequence: one person holds it, edits are captured continuously into a server-side draft with no Save control, and *send for review* turns the draft into one commit. It leaves open what the editing surface looks like and how a hold ends when its holder goes quiet.

A policy runs to tens of pages. Correcting one paragraph in an editor showing all of them costs attention and risks unrelated deletions; restructuring across sections needs the whole text. Users work with several browser tabs, and editing is intellectual work with long pauses that a system cannot tell from absence.

## Decision

**Editors are views over the holder's one draft.**

- **The whole-document editor, or one editor per `#` section** — of the body or of an appendix. Several section editors may be open on one page at once; the whole-document editor opens only when none is open. A `#` typed inside a section editor becomes a section of its own once the editor is closed.
- **Opening an editor takes the hold** when nobody holds the document; there is no separate *take* action. While it is held, nobody else can open the edit tab.
- **Captures are checked per range.** Each editor remembers the text of the range it opened; the server accepts a capture only while that range of the draft is unchanged since the editor last saw it. Editors over disjoint ranges never conflict, across tabs included. An editor whose range changed underneath it stops, turns read-only, and shows its unsaved text as word-level changes against the current draft, to be carried over by hand.
- **The server knows which editors are open** by heartbeat. *Send for review* and an analysis request are refused while any is open.
- **The session ends on one screen with three choices** — continue editing, send for review, discard my edits (confirmed; it discards text and part operations alike, DL-0180). A section is never sent on its own.
- **A hold is released by inactivity**, 30 minutes by default, set per tenant. Before release the holder is asked whether they are still working, and answering resets the clock; a closed tab or a sleeping machine cannot answer, and the hold is released. The draft is preserved. On return, if the document has not moved since the draft began, the holder takes it back and continues; if it has, the draft opens read-only as changes against the current text.
- **A tenant administrator can force a release** — the only role that can end someone else's session; the draft is preserved.
- **Everyone sees that a document is held; only the tenant administrator sees by whom**, which is what a forced release needs.

## Rationale

Section editing is locality, not concurrency. Keeping one hold and one draft per document means the linear model loses nothing: a section editor is the same editor over a range, and the unit of an edit stays the document. Offering both editors serves both tasks — a local correction and a restructuring — where either alone fails one.

The per-range check is the smallest rule that makes several editors safe. A *first save wins* rule would make two section editors on one page invalidate each other on every keystroke, since capture is continuous; a check per range lets them coexist and stops only an editor that is genuinely behind.

Inactivity with a prompt answers the fact that thinking looks like absence: the person is asked rather than judged. A fixed expiry would take the document from someone mid-thought and leave it with someone long gone.

Showing only the fact of a hold tells a colleague what they need — wait — without exposing who is working on what; the administrator, who may have to free the document, is the one reader who needs the name.

## Consequences

- `OPEN_EDITOR` rows carry each editor's range, base hash and heartbeat; `HOLD` carries the last activity instead of a fixed expiry, and the tenant carries the timeout.
- The editor library must run several independent instances on one page and load a range (V-01).
- A preserved draft can go stale when someone else commits meanwhile; there is no merge, only a read-only view to copy from — the linear model's price, paid rarely.
- ST-0017 loses its *take* button; ST-0018 shows the fact of a hold, not the holder.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| Whole and section editors over one draft, per-range capture check | owner | chosen |
| Section-only editing | owner, as a question | rejected — restructuring across sections needs the whole text |
| A hold per section | agent | rejected — reopens ADR-0003: two writers, and a merge at send |
| First save wins across editors | owner | rejected after challenge — continuous capture makes editors on one page invalidate each other |
| One editor instance per user per document | agent | rejected — rules out several editors on one page, which the owner wants |
| A fixed hold expiry | existing design | rejected — takes the document from someone who is thinking |
| An explicit *take for editing* button | existing design (ST-0017) | rejected — opening an editor already states the intent |

## References

- Originating decision-log entries: DL-0167, DL-0180; promoted at DL-0185
- ADR-0003 — linear edit history
- DL-0036, DL-0170

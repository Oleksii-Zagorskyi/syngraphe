---
tags:
  - adr
aliases:
  - ADR-0005 A document is a bundle
status: accepted
date: 2026-09-25
supersedes: []
superseded_by: []
---

# ADR-0005: A document is a bundle — body, appendices and attachments in one repository

**Date:** 2026-09-25
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** the one-file half of DL-0126 (its removal of section files stands)

## Context

DL-0126 made a document one Markdown file, `document.md`, in its own repository (DL-0111). The diff a reviewer reads, the per-document export and the restore that rebuilds a document from its repository all rest on that shape.

Documents in this domain do not come alone. A policy ships with appendices that are approved with it, and with forms and templates — spreadsheets, fillable documents — that people complete elsewhere. An organisation also expects a title page on the printed document. All three are needed in release 0.1 (DL-0157, DL-0158).

Two rules the bundle must keep: nothing enters the approved state unseen (ASR-04), and a repository restored without its database row rebuilds the document from its own files (DL-0111).

## Decision

A document is **its body, zero or more appendices and zero or more attachments, in one repository**, under one linear history (ADR-0003).

- **The body** is `document.md`.
- **An appendix** is a Markdown file under `appendices/`, named by its identifier, under the same whitelist as the body and holding exactly one `#` section. Its title is entered in a field, names it in the interface and in an exported file, and is never rendered in DOCX or PDF. It numbers its own headings from 1 (DL-0177). It has no appendices or attachments of its own.
- **An attachment** is an opaque file under `attachments/`, named by its identifier, never parsed, rendered or read by an agent. It has a mandatory title; replacing it keeps earlier versions in history; its size is capped per tenant, 5 MB by default.
- **`document.md`'s frontmatter lists the parts** — appendices and attachments in display order, each with identifier and title, attachments also with original file name and SHA-256 hash (DL-0174). Parts are listed in the order they were added and reordered by hand.
- **Every operation on a part is an edit of the document**: staged in the draft, with uploaded bytes held in the database beside the draft's text (DL-0175), committed by *send for review*, reviewed with the text, revertible by the reviewer, and frozen in the edition (DL-0168).
- **The title page is not stored.** It is rendered at export from the document's metadata through the tenant's template (DL-0164).

## Rationale

An appendix that could be approved on its own would let a body and its appendix be approved against different versions of each other; one repository and one history make *the document as approved* a single fact. The reviewer keeps one run to read, and acceptance stays document-level (DL-0090).

Listing the parts in the frontmatter keeps the restore rule true without a second listing file: `document.md` already carries the document's identity, and a separate manifest would reintroduce the structure DL-0126 removed. Titles and order are reviewed like text, so they belong in git rather than in a row.

At the capped size, attachments are ordinary blobs in the repository — one history, one backup, one restore path. Holding uploads in the database until commit keeps them under the same point-in-time recovery as the draft they belong to (ADR-0003 makes the draft the only copy of a session's work).

The title page shows only facts the platform already holds — title, number, approval, edition — so storing it would create a second copy of them, wrong after the next edition.

## Consequences

- The reviewer's surface lists part operations — added, replaced, renamed, reordered, removed — beside the text diff; attachments and images show both versions, never a diff.
- Export composes scopes over the parts (DL-0172), and generates the attachment list and title page.
- Repository size grows with attachment versions; the tenant cap and ASR-23's envelope bound it, and LFS stays out until a repository's size is a measured problem (DL-0066).
- The restore procedure and the reconciler read the frontmatter's part lists; a part file present in the tree but missing from the list is an orphan to report, never to delete.
- `PART_INDEX` caches the lists per version so pages can list parts without reading git.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| Body, appendices and attachments in one repository, parts listed in the frontmatter | owner | chosen |
| Appendices as documents of their own, linked to the body | agent | rejected — separate lifecycles let a body and its appendix be approved against different versions |
| A separate listing file beside `document.md` | owner | rejected — a second file for identity reintroduces the manifest DL-0126 removed |
| Attachments in an object store outside the repository | agent | rejected — a second store to back up and restore, and a review record that points outside history |
| Attachments outside the review cycle | agent | rejected — an approved policy would point at a form nobody approved (ASR-04) |
| An authored title page | owner | rejected by the owner in favour of a generated one |

## References

- Originating decision-log entries: DL-0164, DL-0165, DL-0166, DL-0168, DL-0174, DL-0175, DL-0177; promoted at DL-0185
- ADR-0003 — linear edit history
- DL-0126, DL-0111, DL-0066

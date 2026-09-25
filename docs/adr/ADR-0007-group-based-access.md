---
tags:
- adr
aliases:
- ADR-0007 Group-based access
status: accepted
date: 2026-09-25
supersedes: []
superseded_by: []
---
# ADR-0007: Group-based access — rights held by groups, groups linked to documents

**Date:** 2026-09-25
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** DL-0089 (creator holds `edit` as an individual row); the per-user rows of ASR-08 and DL-0051; ST-0012's folder management by any user

## Context

The design held access as rows of `document, user, right`, with five rights — read, edit, accept, freeze, approve — each over a whole document (ASR-08, DL-0091). A confidential document was an ordinary one with few rows (DL-0051).

Per-user rows do not scale with an organisation: every new colleague needs a row on every document their job touches, and a role change means finding and editing all of them. Organisations already think in roles — the people who approve, the people who read — and the reading side needed finer steps than *read*: the canonical text alone, the accepted text, the pending edits, and history as a separate question.

Release 0.1 is deployed first to one organisation, with a sandbox organisation beside it for testing. Isolating administrators from content is a later concern, recorded in the roadmap.

## Decision

**Rights are held by groups; documents are linked to groups; a person holds the union of the rights of their groups linked to a document.** Nothing about documents is granted to a person directly.

**A group** belongs to one organisation, is managed by its tenant administrator, and holds any combination of:


| Kind| Rights |
| --- | --- |
| Viewing ladder — each step includes those below | view canonical · view accepted · view pending · edit · create and edit |
| History — never beyond what the ladder reaches | view previous canonical versions (the editions and the differences between them, never the edits between) · view all history |
| Acts | accept (includes the pending view and correcting before accepting, ADR-0001) · freeze and unfreeze · make canonical |
| Parts — only where the group can edit | create appendix · delete appendix · upload attachment · replace attachment · delete attachment; a new group starts with upload and replace |


*Create* is the one right not tied to a document: it lets a member create or copy documents anywhere in the organisation. Viewing a document shows all its parts (per-part visibility: B-023). A person who can see several versions can compare any two of them.

**A new or copied document** is placed in a folder by its author and starts with **no linked groups: only its author reaches it**, with edit. The tenant administrator is notified and links groups. **A document's group links cannot change while someone holds it**; the administrator, who sees who is editing, asks them outside the platform to finish, waits for the inactivity release, or — as the one role that can — forces the release, the draft preserved (ADR-0006). The moment the first group is linked, the author's individual access ends and they reach the document through their groups like anyone else.

**Held by a person, not a group:** platform administrator; tenant administrator, per organisation; membership of an organisation, active or blocked; blocking one's own account, which blocks every membership until a platform administrator lifts it.

**Administrators.** The tenant administrator manages groups, memberships and links; creates, renames and deletes folders (a folder holding anything cannot be deleted) and moves documents between them; archives and restores; forces a release; edits the template and the tenant's settings; and **reads every document of the organisation in this release**. The platform administrator can do everything a tenant administrator can, in every organisation, plus platform-wide tasks. The last platform administrator cannot be blocked or lose the role; the command line and the database are the break-glass path.

**Blocking.** A tenant administrator blocks a person only in organisations they administer, and is asked which when they administer several; the platform administrator is notified when a person is left blocked in some organisations and active in others. An active organisation always has a tenant administrator: the last one may block themselves only as its last active user, and the platform administrator is notified. The platform administrator can block an organisation, closing it to everyone else; a blocked organisation may have no users at all.

**Archive.** An archived document is visible only to administrators, cannot enter an analysis scope, and can still be exported by them. Its group links can be edited while archived and take effect on restore.

**Every change to access is history** — group membership, a group's rights, a document's links, a block — each with actor and time, so *who could read this document on a given date* is always answerable (ASR-08, ASR-18). Copying a document records its source, version number and commit, time and actor, visible to administrators.

## Rationale

Groups make the permission model readable: an administrator reasons about a handful of groups and their links instead of a grid of people and documents, and a colleague's role change is one membership. Holding roles on the group rather than per document link keeps each group's meaning stable across documents; per-document rights for a group are backlog B-021.

The viewing ladder follows what readers actually need to be kept from — pending work, then the accepted text — while history is a separate question because an auditor-like reader may need past editions without the working edits between them.

Starting a new document author-only means nothing written in the platform reaches a wider audience until an administrator decides it should; that is also what bounds the risk of copying a confidential document, which differs from copy and paste only in convenience (T-09).

## Consequences

- The data model replaces `DOCUMENT_ACCESS` with groups, their rights, memberships and document links, and `ACCESS_CHANGE` becomes their append-only history; the tenant and the membership gain a blocked state.
- Every page decides its controls from the union of the viewer's rights on that document; a right not held means a control not rendered.
- Administrators read all content of their organisations in this release — accepted for a single-organisation deployment and revisited in the roadmap before organisations that do not trust the operator are hosted.
- Folder-level access, per-document group rights and per-part visibility are backlog items, not attachment points this model forbids.

## Alternatives Rejected


| Option | Raised by | Outcome |
| --- | --- | --- |
| Rights on groups, groups linked to documents, author-only until the first link | owner | chosen |
| Per-user rows per document (the previous design) | existing design | rejected — does not scale with the organisation|
| Group rights set per document link | agent | deferred — B-021 |
| Access granted on folders and inherited | owner | deferred — moving a document would silently change its readers |
| Rights applying organisation-wide, without links | agent | rejected — nothing could be restricted |
| New document granted to the creator's group | agent | rejected by the owner — a document belongs to a folder, and access is the administrator's decision |
| Author keeps an individual right permanently | agent | rejected — a personal right on every document one ever created |


## Review triggers

- An organisation that does not trust the platform operator is to be hosted — administrator access to content is revisited (roadmap).
- An organisation creates near-duplicate groups to vary one right between documents — B-021.

## References

- Originating decision-log entry: DL-0188
- ADR-0001, ADR-0003, ADR-0005, ADR-0006
- DL-0051, DL-0084, DL-0089, DL-0091, DL-0003


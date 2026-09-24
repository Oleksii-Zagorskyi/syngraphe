---
tags:
  - concept
aliases:
  - Syngraphē concept pitch
date: 2026-09-17
language:
  - en
  - uk
status: superseded in part
supersedes-note: >
  The change-proposal model this pitch describes was abandoned for a single
  linear editing sequence per document, with no branches and no merges
  (ADR-0003). The body is the pitch as written on 2026-09-17 and is not edited.
---

# **Syngraphē**

**Syngraphē** (technical name: `syngraphe`) is an enterprise collaborative authoring platform where teams of human and AI editors create, review, approve, and maintain authoritative documents.

## **Software name**

**Syngraphē**

The name comes from Ancient Greek συγγραφή (*syngraphē*), related to συγγράφω (*syngraphō*), from *syn-* (“together, with”) and *graphō* (“write”).

*Syngraphē* refers to a written composition, document, or written record - not merely to the act of typing. This makes the name particularly relevant to a platform designed around the creation and maintenance of authoritative enterprise documents.

The name also has a useful modern technical resonance. Graph suggests the relationships and dependencies between documents, policies, clauses, revisions, sources, reviewers, and AI agents—even though this is not the historical origin of the term.

In Ukrainian, Syngraphē can be pronounced «сінграфе́», with the stress on the final syllable.

The ASCII technical name used for repositories, folders, URLs, and other system identifiers is `syngraphe`.

## **Pitch**

Syngraphē turns enterprise document authoring into a collaborative, reviewable, and AI-assisted workflow.

Multiple human editors can create and modify a document or its individual sections, with AI agents assisting throughout the authoring process.

Changes are submitted as explicit change proposals, conceptually similar to pull requests in software development. AI agents can review proposed changes, perform linked operations, identify inconsistencies, and validate changes against defined rules and related documents. Proposed revisions then proceed to human review and approval.

The result is an authoritative, versioned document with a traceable history of contributions, reviews, and approvals.

The same workflow continues as the document evolves: new revisions can be proposed against existing versions, while changes can also trigger review or updates of connected documents.

Initial use cases include enterprise policies and technical instructions, with the platform subsequently extending to other document types such as marketing materials, decision records, and legal contracts.

The core model is:

Human + AI authoring → change proposal → AI review → human review &amp; approval → authoritative document → next revision
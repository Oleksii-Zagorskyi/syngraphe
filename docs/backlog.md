---
tags:
  - backlog
aliases:
  - Syngraphē backlog
status: active
date: 2026-09-21
---

# Backlog — Syngraphē

Ideas worth keeping that are not in the current scope. An entry earns a place by being something a future session would otherwise re-derive; it leaves by becoming an epic, a decision, or an explicit rejection.

## B-001 — Work items derived from the generated views

**Idea.** The generated views — contradictions, ambiguities, blind spots, the role and control directories — are read to decide what to edit next. That makes them a natural source for a work-item feed: each unresolved finding becomes a task with an owner, a state and a link back to the passage.

**Why it is parked.** A task manager opens its own question space — assignment, states, notification, due dates, its relationship to the roles already defined, whether it is per document or per tenant. None of it is needed to prove the authoring cycle, and opening it now would fork the architecture discussion.

**What has to be true before it is taken up.** The generated views exist and are in real use (stage 2, DL-0043), and someone has been observed working from one by hand. The manual step is the specification.

**Constraint it must respect.** ASR-09 — a generated view is derived and never a source of text. A work item may *point at* a finding; it may not become the place the finding is edited.

## B-008 — English interface

The platform launches in Ukrainian; an English translation may follow (DL-0061). Nothing about it is designed now. The only thing held from the start is the invariant that interface strings live outside the code (ASR-10), which is cheap to keep and expensive to retrofit.

## B-015 — Stale cross-reference detection

An author writes *«як визначено в п. 4.2»* in the text. Somebody later inserts a section above it and the number is wrong, silently.

**Why it is a heuristic and not markup** (DL-0127). An author types the reference as plain text on day one, before any feature exists, so a markup mechanism would only ever catch references created after it shipped. A heuristic catches every one of them, including those written years earlier: *"this passage cites section 4.2 as being about asset disposal; section 4.2 is now about inventory."*

**What has to be true first.** The agents exist (stage 2), and somebody has been observed correcting a stale reference by hand — the manual step is the specification.

## B-014 — Acceptance granularity

Stage 1 accepts a whole run over a whole document (DL-0090). A reviewer may later want to accept some sections and leave others pending. **Trigger: the first time a reviewer delays a run because of one author's part.** This is about what an acceptor **chooses** to accept, not about who owns a section — section ownership was dropped entirely (DL-0091) and is not coming back with it. Needs a rule for what the accepted baseline means when it is no longer a single version.

## B-013 — Comments and the annotation surface

Deferred at DL-0083. Threads anchored to passages, nested replies, resolution that hides but keeps the record — a surface rather than a right, and the reason it left stage 1. The anchoring decision stands (DL-0027): W3C text-quote selectors against the sentence-per-line source, nothing written into the document text.

## B-010 — Disputes, the Statement of Disagreements and the decider

Deferred at DL-0076 — the largest single cut available for stage 1. Carries a state machine, a register, a role and an authority model, none of it needed to prove a document can be edited, reviewed and approved. In stage 1 a disagreement is settled by the people involved, outside the platform. ADR-0001's substance stands; only the formal escalation path waits.

## B-011 — Agent-workflow questions parked at DL-0081

Everything the agent half raises beyond what stage 1 needs: which heuristics ship seeded, how a review scope is proposed rather than chosen by hand, how standing lists are triaged, how document ADRs are drafted, how findings are re-run when a neighbouring document changes. Each is answerable and none is needed to build an editor.

## B-012 — Tenant-wide entity registry

Stage 1 declares entities per document (DL-0073). A role that appears in six policies is six declarations, and keeping them consistent is manual. A tenant-wide registry is the fix, and it is worth building once there are six policies rather than before.

## B-002 — Automatic review of connected documents

Deferred at DL-0018. Detection of cross-document conflict is in scope; notifying the other document's owners when this one changes needs a maintained dependency graph.

## B-003 — Generated views at repository scope

Deferred at DL-0044. Two policies can regulate the same role, so the role directory is more useful across the corpus than within one document. Needs the dependency graph of B-002 — **and a home**: with one repository per document (DL-0111) a cross-document view has no repository to live in, so it needs a per-tenant derived store.

## B-004 — Style linting

Deferred at DL-0004's successor. The sense-versus-style hunk split exists from the start; mechanical enforcement of the style half comes later.

## B-005 — Tenant-authored heuristics

Deferred at DL-0049. Tenants attach composed actions and side-document types; authoring the heuristics underneath stays with the platform administrator until a tenant asks.

## B-006 — MS Word import

The real accounting policy arrives once the platform is ready (DL-0002). Cheaper than it was — Markdown makes pandoc the import path as well as the export one.

## B-007 — MCP server for external agents

An external agent connects as a user and inherits exactly that user's rights. Cheap now that identity is Django's, but it is not needed to prove the cycle.

## B-009 — Per-tenant email sending domains

Stage 1 sends from one platform domain (DL-0072). Sending from each tenant's own domain needs that tenant to publish SPF and DKIM records for us, which turns onboarding into a DNS exercise. Worth it only when a tenant asks for mail that carries their own name.

## B-016 — Operator guide for the people who use it daily

**Idea.** A guide for the colleagues who will edit, review and approve in the platform, derived from the stories, the help pages and the interface rather than written from nothing — who the reader is, what they may reach, what to keep and what to drop, and an audit that every step can be reached from their own screen.

**Why it is parked.** Written before the cycle works end to end it would describe an intended interface, and every later story would make it wrong.

**What has to be true before it is taken up.** **The review cycle works end to end**: take, edit, send for review, correct, accept, freeze and approve, on the development host.

## B-017 — Data retention and erasure procedure

**Idea.** The procedure that turns the data model's erasure shape into something an administrator can carry out: who may ask, who decides, what is cleared — the tombstone keeps the identifier and clears name and address (DL-0108) — what is kept and for how long, how an export already made is treated, and how the request is recorded.

**Why it is parked.** The mechanism exists in the data model; the procedure that uses it is operational and needs no code until real people's data is held.

**What has to be true before it is taken up.** **Before the first real document is loaded.** A real document brings real authors, and an erasure request arriving before the procedure exists would be answered by improvisation.

## B-018 — Accessibility position

**Idea.** One paragraph stating what the platform commits to for users with disabilities — which standard it measures against, at what level, and what is out of reach for now — so the interface is built towards a stated target rather than reviewed against one afterwards.

**Why it is parked.** Nothing is lost by writing it once the interface has shape, and the editor library chosen in Epic 1 decides much of what is achievable inside the editing surface.

**What has to be true before it is taken up.** **Before the interface is considered complete** — at the latest, before the release's last QA pass.

## B-019 — HTML mockups from the page wireframes

**Idea.** Clickable HTML mockups generated from [`docs/interface/pages.md`](interface/pages.md), worked through with the owner, so layout and navigation are judged on a screen rather than in ASCII.

**Why it is parked.** It is a design activity of its own with the owner in the loop. Built against an editor that is later rejected, the editing surface's mockup is thrown away.

**What has to be true before it is taken up.** **The wireframes carry a release marker on every region, and the editor library is chosen** (`verification-plan.md` V-01).

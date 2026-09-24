---
tags:
  - adr
status: accepted
date: 2026-09-18
amended: 2026-09-23
title: Django owns the workflow, git is a library, and no forge remains
---

# ADR-0002 — Django owns the workflow, git is a library, and no forge remains

*Originating decision-log entries: DL-0030, DL-0042, DL-0086, DL-0103. Amended 2026-09-21 by owner override of the freeze rule, after DL-0042 removed the forge entirely and ADR-0003 removed the merge mechanics this record had listed as its main cost. Amended 2026-09-23: the operation set is listed in full — `init` and `read` had been missing (DL-0142).*

## Context

The first architecture decision made a self-hosted forge the system of record for repositories, change proposals, reviews and permissions, with Django orchestrating over its API. Every subsequent decision moved state to the Django side: editions, disputes, the entity layer, tenant configuration, the approval ledger, rejection records, comment threads, findings and their audience computation, and the role assignments themselves.

That split carried one structural cost — **two authorisation surfaces that must agree**. Role assignments in Django and repository permissions in the forge described overlapping facts, and drift between them is silent.

Two things then settled it. **Edits accumulate in the application and are committed on a user's behalf**, so a forge can neither authenticate per commit nor hold the authorisation (DL-0042); once identity left, and once the events that start agent runs became the platform's own, forge runners had nothing left to offer either. And **branching went** (ADR-0003), which removed the merge engine this record had named as the decision's largest cost.

## Decision

**Django owns the workflow. Git is a library over bare repositories Django owns. No forge is part of the system.**

- **Identity and access control are Django's**, and there is exactly one authorisation surface (ASR-07). DL-0015, which made a forge the identity provider, is superseded.
- **The git operation set is** init, commit, read, diff, blame, revert and tag. No branches, no merge, no conflict resolution, no custom ref retention.
- **Agent runs are ephemeral container jobs** started by a dedicated runner service that consumes a queue — never by the web process (DL-0086).
- **Commits carry no personal data**: the author name is the Django user identifier, the email a per-user non-routable address (DL-0088, DL-0093).

## Rationale

**Removing the second system removes the cost rather than managing it.** A derivation contract plus a reconciliation job is machinery whose only purpose is to stop two descriptions of one fact from diverging. With one authorisation surface, the divergence cannot occur.

**The decision turned out cheaper than its first statement.** That statement listed building merge mechanics as the price, and named free retention of pre-squash history as the one genuine loss. Both evaporated when the edit model went linear: there is nothing to merge and nothing is squashed. A record that overstates a cost is read as a commitment to pay it, which is why this was amended rather than left standing.

## Consequences

- **No merge engine, no conflict interface, no custom ref retention.**
- **No forge web interface** for inspecting a repository when something breaks. The replacement is `git` on the host plus read-only repository views for the platform administrator.
- **Authentication has no external provider to lean on.** The first statement assumed the forge held it; nothing replaced what lapsed. That absence became the architecture review's F-05 and is answered by DL-0107.
- **The two stores need a stated write protocol.** With Django performing every ref update and every row write, the order, the authority and the repair path between git and PostgreSQL are the platform's to define — the architecture review's F-03.

## Options considered

| Option | Raised by | Outcome |
|---|---|---|
| Forge is the system of record, Django orchestrates | agent | **Withdrawn after challenge** — every later decision moved state to Django until the description no longer matched the build |
| Re-label the split without re-architecting: forge keeps storage, identity, ACL and runners; Django owns the workflow | agent | Rejected by the owner — it keeps two authorisation surfaces and a reconciliation job permanently |
| Django owns the workflow; git as a library | owner | **Chosen**. The owner's reasoning closed it: a forge cannot authenticate a commit the platform makes on a user's behalf |
| Keep the forge for identity and runners only | owner, then withdrawn | Withdrawn at DL-0042 — with identity in Django and agent runs driven by platform events, nothing remained that a forge is specialised in |

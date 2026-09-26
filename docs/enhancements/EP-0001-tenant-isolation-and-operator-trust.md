---
tags:
  - enhancement-proposal
id: EP-0001
title: Tenant isolation and operator trust
status: provisional
horizon: later
created: 2026-09-25
last-updated: 2026-09-25
authors:
  - Oleksii
related-adrs:
  - ADR-0007
supersedes: []
superseded_by: []
---

# EP-0001: Tenant isolation and operator trust

## Summary

Release 0.1 trusts its administrators with everything: a tenant administrator reads every document of their organisation, and the platform administrator reads every organisation. That is acceptable while the platform serves one organisation and a sandbox beside it. Before it hosts organisations that are independent of whoever operates it, administering access and having access must become two different things, tenants must be isolated from each other and from the operator, and content must be protected by more than the application's own checks.

## Motivation

A tenant is a fully independent group of users or a separate business (DL-0003). An operator who can read every tenant's documents is a third party to each of them, and no organisation that stands behind its documents will accept an unaccountable third party with standing access to their text.

### Goals

- An administrator can grant, revoke and audit access without being able to read the content they govern.
- The platform operator has no standing access to any tenant's content; any access is exceptional, bounded in time and recorded.
- A person's presence in one tenant is undiscoverable from any other.
- Content at rest is unreadable without keys the tenant controls.
- Model providers never receive content a tenant has not agreed to send.
- Developer and administrator accounts — the platform's most powerful credentials — require a second factor.
- The platform can demonstrate conformance to recognised global security standards.

### Non-goals

- Business units or departments inside one organisation as a platform concept.
- Any change to release 0.1's single-organisation deployment.

## First principles

- **Administering access is not having access.** The right to decide who reads a document never implies reading it.
- **Nothing standing.** No role holds permanent access to content it does not work on; exceptional access is requested, granted for a period, and leaves a record.
- **Isolation is enforced below the application.** As tenant isolation is enforced by the database today rather than by filters, content isolation is enforced by keys, not by checks an operator could bypass.
- **Existence is information.** Whether an address, a person or a document exists in another tenant is itself confidential.

## Proposal

- **One account per tenant.** An account is keyed by tenant and email: the same address may hold separate accounts in several tenants, each with its own credentials, and a lookup never searches beyond one tenant. A person who belongs to several tenants chooses which to sign in to; nothing in one tenant reveals the others.
- **Administration without reading.** The tenant administrator manages groups, links, folders and blocks through surfaces that show metadata — titles where permitted, rights, history — never text. Reading a document requires a right held like anyone else's.
- **An operator outside the content.** Platform administration covers tenants, capacity and health. Access to a tenant's content, when support requires it, is granted by that tenant for a bounded time and recorded where the tenant can see it.
- **Encryption with tenant-held keys** for repositories and database content, so an operator with disk access reads nothing.
- **Model providers by tenant choice**, including models the tenant hosts itself, so confidential text need not leave its control.

### Notes and constraints

- ADR-0007's administrator reading rights are the state this proposal replaces; its review trigger points here.
- The accepted risk of sending content to a model provider (T-03) is decided before the AI half ships and is revisited under this proposal's goal on model providers.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Separate accounts per tenant burden people who belong to several | A tenant chooser at sign-in; credentials stay per tenant |
| Tenant-held keys make lost keys lost data | Key custody and recovery are designed before encryption ships |
| Administrators without reading access cannot resolve content problems | Bounded, recorded, tenant-granted access for exactly that case |

## Design details

*Not yet written — the proposal is provisional.*

## Alternatives considered

| Option | Raised by | Outcome |
|---|---|---|
| A distinct email address per tenant | owner | withdrawn after challenge — burdens people with one work address and adds no isolation over accounts keyed by tenant and email |
| Accounts keyed by tenant and email | agent | adopted |

## Unresolved questions

- How a person who belongs to several tenants signs in without the sign-in screen disclosing that they do.
- What the tenant administrator may see of a document they cannot read — title, type, folder, size, history of access.
- Key custody: who holds tenant keys, how they are rotated, and what recovery means.
- How support access is requested, granted and shown to the tenant.
- Which global security standards the platform measures itself against, and at what level.
- Whether search and cross-document analysis can work over encrypted content, and at what cost.

## Triggers

- **Accepted** when a tenant independent of the operator is expected.
- **Implementable** before such a tenant's first document is loaded.

## Graduation criteria

*Set when the proposal is accepted.*

## Implementation history

- 2026-09-25 — written as provisional.

## References

- ADR-0007 — group-based access
- ASR-01, ASR-17 — tenant isolation, tenants invisible to each other
- DL-0003 — what a tenant is
- `threat-model.md` — T-03, T-16

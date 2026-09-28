---
tags:
  - adr
aliases:
  - ADR-0017 Schema per tenant, resolved per request by the platform's own layer
status: accepted
date: 2026-09-28
supersedes: []
superseded_by: []
---

# ADR-0017: Schema per tenant, resolved per request by the platform's own layer

**Date:** 2026-09-28
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** None — collects DL-0029, the tenant resolution of ADR-0008 and DL-0270 into one record

## Context

A tenant is a fully independent organisation (DL-0003), and tenant isolation is the requirement the architecture may never stop meeting: a query that omits the tenant boundary must reach only the acting tenant's data, without a deliberate act (ASR-01), and no document link, search or analysis may cross the boundary (ASR-17). Every document lives in its own repository under the tenant's directory (ADR-0008), so the database is the one store where tenants could share a table.

A tenant is recognised from the host when it has its own domain, and from the session on the platform's main host (ADR-0008); a person may belong to several tenants and switch between them. Platform-level tables — people, memberships, the audit log, the allowed hosts — are written before any tenant is known and are shared by design (`data-model.md § The rule that shapes everything below`).

The first implementation epic had to choose how the schema-per-tenant decision of DL-0029 is carried in code: a package that imposes its own routing model, or a layer of the platform's own.

## Decision

**One PostgreSQL schema per tenant, plus one shared schema, with the tenant resolved once per request by the platform's own middleware and applied as the connection's `search_path`.**

- **Placement follows purpose.** Everything that identifies a person or an organisation, is deliberately cross-cutting, or is written before any tenant is known lives in the shared schema; everything scoped to one organisation's documents lives in that tenant's schema. Shared and tenant apps are two explicit lists in the settings.
- **Resolution is one middleware.** The request's host is checked against the platform's hosts and every tenant's domains first, and an unknown host is refused before any lookup; a tenant domain names its tenant; a platform host takes the tenant from the session, or none. The middleware sets `search_path = tenant_<N>, public` for the request, and nothing else sets it during a request; outside a request, only one context manager sets it — the one background work and `migrate_schemas` use.
- **A guard refuses a tenant-schema query with no tenant.** A database router raises when a model of a tenant app is queried while the connection's `search_path` is the shared schema alone; shared apps are exempt, because sign-in, the first run and platform administration run before any tenant is known.
- **Migrations run per schema** by one command, `migrate_schemas`, which applies the shared apps to the shared schema and the tenant apps to each tenant schema with the `search_path` set, so each schema keeps its own migration record. A new tenant's schema is created and migrated in the act that creates the tenant. Until its migrations are complete the tenant is not resolvable — its state is `migrating` in the data model (DL-0280), and no request reaches its schema — and `migrate_schemas`, which creates a missing schema and migrates every schema that is behind, completes one a crash left half-made.
- **A model in both schemas.** The sending address and the outbox are a tenant's own and also the platform's, for mail that belongs to no tenant (DL-0202, DL-0203). Their app is on both lists: `migrate_schemas` creates its tables in the shared schema and in every tenant schema, and the guard lets it through on the shared schema alone. With a tenant set, the unqualified name reaches the tenant's table, since the tenant schema comes first on the path; the platform's rows are reached only with the shared schema alone — in a request no tenant was resolved for, or through the context manager outside a request. So mail caused in a tenant's request is queued in that tenant's outbox, and the fallback to the platform's sender is read where mail is sent: the worker looks in the tenant's schema first and, finding no sender there, in the shared schema through the context manager.
- **Names come from the tenant's number.** The schema is `tenant_<N>`, the repository directory `tenant-<N>/`, from the tenant's platform-wide number (ADR-0008); no organisation's name reaches a schema listing.
- **No package is adopted for this.** The layer is the platform's: a connection wrapper, a middleware, a router and a management command.

## Rationale

**Isolation enforced below the application.** A tenant column in shared tables makes every query's `WHERE` clause a security control, and one forgotten filter crosses the boundary. A schema per tenant moves the control to the database: crossing requires a whole request's `search_path` to be wrong, which one place sets and a guard checks (DL-0029).

**One place to set the tenant.** ADR-0008 resolves a tenant two ways — from a domain, or from the session on the main host. `django-tenants`, the package that implements schema-per-tenant for Django, resolves a tenant from the request's host or path, never from the session, so its middleware would have been replaced by the platform's own for the main-host case, leaving the package to provide schema switching and migrations. Those two are a connection wrapper and a loop; owning them costs less than owning an exception to a package's model, and V-12 measures the platform's own loop.

**Explicit lists over convention.** The shared and tenant split is already stated per purpose in the data model. Two lists in settings make the guard derivable and the placement of every new table a decision written down where the next author reads it.

**Numbers, not names, in schema and directory.** A schema named after an organisation puts the organisation into `\dn` listings and backup manifests, as a repository named by title would put a document's title there (ADR-0008).

## Consequences

- Every tenant-scoped table is created once per tenant; a migration runs as many times as there are tenants. V-12 — ten schemas in under sixty seconds, the per-schema cost linear — is measured in the first implementation epic, with the fallback of migrating in the background behind a version check if it fails (`verification-plan.md`).
- Any code that needs a document and a user joins across the boundary deliberately, and the crossing is visible in the code that makes it.
- Background work — the authorship worker, the reconciler, the backup — sets the tenant explicitly through the context manager, since no request resolves it for them.
- The audit log is shared with a nullable tenant, by design: a platform administrator's act belongs to no tenant, and an auditor asking who created an organisation must not first have to know which schema to look in.
- Adding a tenant domain needs no redeploy: the allowed hosts are rows read at request time, cached briefly.
- A package's later improvements — its test helpers, its admin integration — are not inherited. The seam is one module; the package remains the fallback if the layer proves fiddly.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| Schema per tenant, resolved per request by the platform's own layer | owner (schema per tenant, DL-0029; the platform's own layer, DL-0270) and agent (the guard, the explicit lists, the migration command) | **chosen** |
| Schema per tenant through `django-tenants` | agent, as the alternative offered | rejected by the owner — its routing, by host or path, does not express the session-chosen tenant on the main host (ADR-0008); the platform would own a middleware of its own anyway; the package's model would be fought rather than used |
| A tenant column on shared tables, filtered by the application | the conventional Django shape | rejected at DL-0029 — a missing filter crosses the boundary; isolation would rest on every query being right |
| A database per tenant | agent, as a question | rejected — connection pools and migrations multiply per tenant, cross-tenant administration needs a second connection per act, and the platform is sized for tens of tenants on one host, not for tenants that need their own database |

## Review triggers

- V-12 fails its pass condition: migrations move behind a version check, this record gains the change.
- The platform hosts organisations that do not trust the operator (EP-0001): per-tenant credentials and administrator isolation are decided then, and a database per tenant is weighed again.
- The layer's own module grows past a connection wrapper, a middleware, a router and a command: the package is weighed again.

## References

- Originating decision-log entries: DL-0003, DL-0029, DL-0270; ADR-0008 — identity and addressing
- ASR-01, ASR-17; V-12 in `verification-plan.md`
- `technical-design.md § Tenancy`; `data-model.md § The rule that shapes everything below`

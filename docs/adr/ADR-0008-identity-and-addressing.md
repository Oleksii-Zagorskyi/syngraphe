---
tags:
  - adr
aliases:
  - ADR-0008 Identity and addressing
status: approved
date: 2026-09-26
supersedes: []
superseded_by: []
---

# ADR-0008: Identity and addressing — numbers, tenant resolution, URLs, and one answer for what may not be seen

**Date:** 2026-09-26
**Status:** Approved
**Deciders:** Oleksii
**Supersedes:** the slug as a document's identity; DL-0111's naming of repositories by internal identifier

## Context

A document was identified in the interface by a slug and on disk by an internal identifier (DL-0111). People refer to documents in meetings, letters and messages, and neither form can be said aloud or typed from memory. Numbers are the natural reference, but a number means something only inside its tenant, so every address has to say whose number it is.

Tenants are independent organisations (DL-0003). Some will want the platform on their own domain; the platform is also served on its own. A person may belong to several tenants.

Addresses built from numbers are easy to guess. Whatever a person may not open must not reveal that it exists — its title, its author, or its existence at all (ASR-16, ASR-17).

## Decision

**Numbers.** A tenant has a platform-wide number; a document has a number within its tenant, shown as `#7`; a folder has a number within its tenant, the root being `1`; appendices and attachments have numbers within their document, from 1. All are assigned in order of creation, never edited, never reused. A part's number is independent of its display order. The document number replaces the slug.

**Allowed hosts.** The application answers only on hosts it knows, each a host name with an optional port: the **main set** — the platform's own, at least one, `127.0.0.1` out of the box, replaced by the installation's real default host when it is set up — and each tenant's **own**, none, one or several. **Only a platform administrator** sets either, and every addition, removal or change is recorded in the audit log. In each set with more than one host, **one is the default**; the default builds the links in the emails sent for that tenant, or for the platform. A request for any other host is refused before any tenant is resolved.

**Tenant resolution.** A tenant with its own domain is recognised from the host, and a person signing in there lands in that tenant. On the platform's main domain the tenant is the one chosen in the session. Switching tenant moves to the other tenant's domain, or stays on the main domain, and may need signing in again.

**URLs**, within the tenant the host or session names:

```
/document/12/                       reading view
/document/12/edit/                  one segment per tab
/document/12/version/2.3/           a historical version; pending work as 2.3-1 (DL-0198)
/document/12/compare/?from=2.0&to=2.3-1
/document/12/appendix/3/
/document/12/attachment/3/
/folder/7/                          the document list with that folder selected; `/` opens /folder/1/, the root
/search/?q=…
/administration/platform/hosts/     platform administration, one segment per section
/administration/tenant/groups/      tenant administration, one segment per section
```

**One answer for what may not be seen.** A document or folder that does not exist, one the reader may not open, one archived — administrators excepted, who see archived documents — and one in another tenant all get the same response — the same not-found status, the same page, the same timing — reading *Nothing to show here*, without a title, author, version or any mention of access.

**On disk.** `tenant-N/document-M/`, from the two numbers; never a title.

## Rationale

A short number is what people use when they refer to a document; a URL built from it can be read out and typed. Resolving the tenant from the host lets a tenant's own domain carry its links without ambiguity and makes its sign-in unambiguous; the main domain keeps working for everyone, at the cost of links that depend on the chosen tenant.

Path segments are the conventional URL form for server-rendered pages: a fragment never reaches the server, and a query string names a filter, not a page. The hyphen in `2.3-1` needs no encoding.

Sequential numbers make probing trivial, so the defence cannot be obscurity: it is that every case a reader may not see answers identically, leaving nothing to distinguish.

Numbered directories tell an operator which tenant and document they hold, and let a repository restored without its row name its own document, without putting a title anywhere the access model does not govern.

## Consequences

- Tenants gain a platform number and optional domains (`TENANT_DOMAIN`); documents gain `number`; the slug is gone.
- The set of allowed hosts is the configured main set plus every tenant's domains, read at request time; adding a tenant domain needs no redeploy.
- Each tenant domain needs DNS and a certificate, configured per installation, never in code.
- On the main domain, a link opened while another tenant is chosen resolves in that tenant, or shows *Nothing to show here*. It never shows a document the reader may not open.
- The approximate number of documents a tenant has created can be read from the highest number a user sees (T-17, accepted).
- A cookie set on one domain does not reach another; moving between a tenant's domain and the main domain may ask the person to sign in again.

## Alternatives Rejected

| Option | Raised by | Outcome |
|---|---|---|
| Per-tenant numbers, tenant from its own domain or the session, path URLs, one not-found answer, numbered directories | owner and agent | chosen — numbers, domains, URLs and directory names by the owner; the uniform answer and path segments by the agent |
| A slug per document | existing design | replaced — cannot be said aloud and invites editing |
| A subdomain per tenant | agent | rejected by the owner |
| The tenant as a path prefix | agent | rejected by the owner in favour of tenant domains and the session |
| `?edit` or `#edit` for tabs | owner, as options | rejected — a fragment never reaches the server; a query names a filter |
| `2.3+1` for pending work | agent | replaced by `2.3-1` — `+` in a query reads as a space |
| A message saying the reader may not open the document | — | rejected — confirms the document exists |
| Zero-padded numbers, `#007` | agent | rejected — padding breaks at a thousand |
| Directories named by internal identifier | existing design (DL-0111) | replaced — tells an operator nothing |

## References

- Originating decision-log entries: DL-0196, DL-0199, DL-0200; notation DL-0198
- ADR-0007 — group-based access; ASR-15, ASR-16, ASR-17; T-17

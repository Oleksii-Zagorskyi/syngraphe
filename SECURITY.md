# Security

Syngraphē holds documents an organisation treats as authoritative, and parts of
what it holds are confidential to that organisation. Security reports are
welcome and are read.

## Reporting a vulnerability

Use GitHub's **private vulnerability reporting** on this repository
(*Security → Report a vulnerability*). It opens a channel visible only to the
maintainer.

Please include what you did, what happened, and what you expected. A proof of
concept helps and is not required. You will get an acknowledgement; if a fix is
warranted you will be told when it ships, and credited unless you prefer not to
be.

**Do not open a public issue for a vulnerability**, and do not test against any
installation you were not given permission to test.

## Scope

In scope: this repository's source, its configuration templates, its container
definitions, and the prompts and heuristics it ships.

Out of scope: any running installation, third-party dependencies (report those
upstream), and findings that require an attacker to already hold valid
credentials for the tenant they are attacking.

## What the design already assumes

These are recorded rather than discovered, and the reasoning is in
[`docs/threat-model.md`](docs/threat-model.md):

- **Tenant isolation is enforced by the database**, one schema per tenant, not
  by application-layer filtering.
- **Commits carry no personal data.** The git author is a user identifier and a
  non-routable address; a person's name lives only in the application.
- **Access rights are data with a full change history**, answerable for any past
  date.
- **A repository restored without its access rows grants no access at all** —
  the restore path fails closed.

The threat model also names what it does **not** solve, including prompt
injection against the AI half, whose mitigations are stated as incomplete. That
half is not in this release.

## Reporting something that is not a vulnerability

Ordinary bugs go to the issue tracker. If you are unsure which a finding is,
report it privately and it will be redirected.

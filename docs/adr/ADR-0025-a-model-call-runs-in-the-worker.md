---
status: accepted
last-updated: 2026-11-12
supersedes:
  - ADR-0002-django-owns-the-workflow.md (in part — agent runs as ephemeral container jobs)
superseded_by: []
---

# ADR-0025: A model call runs in the worker — the request is the model's only input, no container per run

**Date:** 2026-11-12
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** ADR-0002-django-owns-the-workflow (in part — *agent runs are ephemeral container jobs*)

## Context

ADR-0002 and DL-0086 made each stage-2 agent run an ephemeral container job, started by a runner service, with read-only mounts of exactly the review scope's repositories and egress only to the model endpoint. The container was there to contain an agent that reads what it chooses.

Release 0.2 has no such agent. A run is one request to a plain model API, with no tools (DL-0120), cut into one call per heuristic and per neighbour, whose sources are exactly the documents the platform put into it (ADR-0022). A mount of the whole review scope would hold more than any one call may read, and the workbench must run the code path production runs on a developer's machine (DL-0563).

## Decision

**A model call is made by the platform's existing worker. The worker reads the documents of one call from the repositories, assembles the request — base prompt, those documents, the heuristic — and sends it; the request is the model's whole input. No container is started per run, and no runner service exists.**

## Rationale

**The model cannot investigate.** It holds no file system, no tools and no second request: it answers the one request it receives. What it can read is what the call contains, so the containment is the call's assembly, recorded document by document in its trace (ADR-0024) and deciding the finding's audience (ADR-0022). A container around a request that cannot reach out contains nothing.

**The worker already reads every repository.** It commits, exports and blames in release 0.1; a call's assembly adds no reach it lacks. The risk that remains is the platform's own — an assembly that puts the wrong document in — and it is met by tests of the assembly and by the trace, which names every call's documents.

**One code path for production and the workbench** is simpler without a runner: the workbench's commands call the same assembly the worker does (DL-0563).

## Consequences

- No runner service, no container per run, no mount table to keep: less to build and operate on one host.
- The worker reaches the model's endpoint over the network, beside the mail it already sends; egress is no longer limited per run.
- A bug in the assembly could put the wrong document into a call; tests and traces are the controls.
- If a heuristic ever needs a loop with tools (ADR-0024's extension), containment comes back with it, and this decision is reopened.

## Alternatives Rejected

- **A container per run, mounting only one call's documents.** Rejected because the model reads nothing the request does not hold; the container would defend against no reach the model has.
- **The assembly in a separate process that may read only the call's documents.** It would defend against the platform's own assembly bug. Rejected for 0.2 as a second runtime to build and operate for a risk tests and traces already show.
- **The container per review scope, as ADR-0002 had it.** Rejected because a scope holds more than any call may read.

### Option attribution

| Option | Raised by | Outcome |
|---|---|---|
| The worker assembles and sends each call | owner | **accepted** |
| The request as the model's only input, no investigation | owner | **accepted** |
| A container per call | agent | rejected |
| A separate assembly process | agent | rejected |
| A container per scope | the record (ADR-0002, DL-0086) | rejected |

## Review triggers

- A heuristic needs a tool-use loop.
- An assembly error is found in a trace.

## References

- DL-0568 — the decision this ADR records.
- ADR-0002, DL-0086 — the container jobs it replaces; DL-0120, ADR-0022, ADR-0024, DL-0563.

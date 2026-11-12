---
status: accepted
last-updated: 2026-11-12
supersedes: []
superseded_by: []
---

# ADR-0024: Traces — one row per model call, references not copies, kept for good, read only from the host

**Date:** 2026-11-12
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** None

## Context

Every model call the platform makes must be explainable months later: which documents it read, which prompt it ran, which model answered, what it cost, and what came of it (DL-0554 (4)). The prompts are source in `prompts/`, measured by their evals in `evals/`, and loaded into the platform by a command (`technical-design.md § Prompts are source`). Every run already records its heuristics and their versions, and every finding names its heuristic (DL-0031, DL-0049).

Three facts shape what a trace can be. A run is one request with one result (DL-0120), not a loop of steps and tools. A committed document lives in a repository whose history is never rewritten (ADR-0003), while a draft lives in the database and is deleted when it is finished or discarded. And every organisation's data is isolated by the database, one schema each (ADR-0017).

## Decision

**Each model call writes one trace, in its organisation's schema, that names what the call read by reference — keeping text only for a draft — and records how it was asked, answered and paid for. Traces are kept for good and read only from the command line on the host.**

1. **One trace per call**, as the runtime makes it. The technical design records how a run of several steps would extend the trace — one row per step under one run — for a heuristic that one day needs its own loop; nothing of it is built now.
2. **What a trace holds:** each committed document read, by repository and commit; for a draft, its base commit and its text; the prompt version — one hash over the base prompt, the heuristic, the model and the effort; the model that answered; the provider's request identifier; the input, output, cache-read and cache-written tokens and the cost computed from them; the time taken; how the call ended — done, refused, failed, unparseable; the quotes withheld as fabricated and the injection checks' hits (ADR-0022); the stored result, by reference; any *not right* mark (DL-0554); the platform's release.
3. **Where:** a table in each organisation's schema.
4. **For how long:** for good, the draft text included — a discarded draft too — since the traces are the feedback loop that improves the agents. The erasure procedure clears what a person's request reaches.
5. **Who reads it:** whoever operates the installation, by a management command on the host. No page of the web interface shows a trace.
6. **The link to the evals:** the command that loads the prompts refuses a prompt version that has no dated result at its target in `evals/` under the same hash, so every trace's prompt version names results that exist and pass.

## Rationale

**A trace that copied what it read would be a second store of every document**, beside the repositories, readable by whoever reads the trace table and needing a retention of its own. A reference into an append-only history reproduces the same input exactly, at the size of a hash. A draft has no history to point into, and a run over it that cannot be replayed cannot be explained; it is the one exception.

**A trace of one request should not pretend to be a loop.** A structure of steps and tools would record nothing today and would be designed against a loop nobody has measured; writing down how it would extend keeps the later case cheap.

**The organisation's schema is where its data already lives.** A trace names documents and keeps drafts; isolating it any other way would make tenant isolation an application filter again.

**Keeping traces whole keeps every past result explainable** and gives the developer the material that improves the prompts: what was asked, what was marked *not right*, what an injection check found. Traces are small, because they hold references.

**Reading from the host keeps the traces behind the database's own access**, with no new surface in the application and no new right to grant.

**A gate at load makes the rule mechanical.** Without it, a prompt version could reach production with no passing results, and DL-0554 (4) would fail silently.

## Consequences

- Any analysis can be traced to its inputs at their commits, its prompt and its results, and replayed.
- Costs and failures are measured per call, per heuristic and per organisation from the traces alone.
- The text of drafts, discarded ones included, accumulates in the traces; an author's withdrawn words remain readable by the operator. Accepted for 0.2 (B-077).
- A prompt change reaches production only with its results committed first.
- The erasure procedure (B-017) has a new place to reach.

## Alternatives Rejected

- **The full assembled context stored with each call.** Rejected because it copies every document a second time; an opt-out per organisation would then have had to limit it.
- **The draft referenced by its base commit and a content hash only.** Rejected because a run over a discarded draft could not be replayed.
- **The draft text cleared when its content is committed, or after ninety days; or at discard.** Rejected by the owner: the traces are the agents' feedback loop.
- **Everything deleted after a fixed period, references included.** Rejected because past results would stop being explainable.
- **The model's raw response copied into the trace.** Rejected because the stored result already holds it, and a copy would hold quoted document text.
- **A page in Administration for the platform administrator.** Rejected because it adds a surface and a reader the need does not call for.
- **A general trace of steps and tool calls built now.** Rejected as above.
- **A load command that warns and loads anyway.** Rejected as above.

### Option attribution

| Option | Raised by | Outcome |
|---|---|---|
| One trace per call; the multi-step extension written, not built | owner | **accepted** |
| References, not copies | owner | **accepted** |
| A draft kept as text | agent | **accepted** |
| The output referenced, not copied | agent | **accepted** |
| Read from the host only | owner | **accepted** |
| The organisation's schema | owner | **accepted** |
| Kept for good, discarded drafts included | owner | **accepted** |
| The load gate on eval results | agent | **accepted** |
| The full context stored | the seed's first framing | rejected |
| An opt-out per organisation | owner | withdrawn by the owner for references |
| Draft text cleared at commit, after ninety days, or at discard | agent | rejected |
| An Administration page | agent | rejected |
| A warning load | agent | rejected |

## Review triggers

- A heuristic needs a loop of its own; the trace extends as decision 1 says.
- An organisation or a person asks that withdrawn drafts not be kept (B-077), or EP-0001's operator trust is taken up.
- The trace table's size becomes a cost the operator notices.

## References

- DL-0552, DL-0553, DL-0562 — the decisions this ADR records.
- DL-0031, DL-0049, DL-0120, DL-0554; ADR-0003, ADR-0017, ADR-0022, ADR-0023.
- `technical-design.md § Prompts are source`; backlog B-017, B-077.

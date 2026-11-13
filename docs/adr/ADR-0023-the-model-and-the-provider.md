---
status: proposed
last-updated: 2026-11-13
supersedes: []
superseded_by: []
---

# ADR-0023: The model and the provider — the Anthropic API, Claude Sonnet 5.5 per heuristic, no fallback, content leaving as an accepted risk

**Date:** 2026-11-12
**Status:** Proposed — accepted when the spike's evals have measured the model on the first cut
**Deciders:** Oleksii
**Supersedes:** None

## Context

The agents run on a plain model API behind a provider interface (DL-0120), so an adopter needs an API key, not a proprietary binary (ASR-13), and a self-hosted model can implement the same interface later. Three questions were left to release 0.2:

- **What leaves.** Document content is sent to a third party. The threat model called this the largest residual risk in the system and a business decision, to be taken before stage 2 ships (T-03). The confidential guidance is not in release 0.2 (DL-0568), so no call holds it and it does not leave.
- **Which provider and route.** The provider's own API, or a cloud platform that resells the same models in a region of the operator's choice.
- **Which model.** The owner's starting point is Claude Sonnet, to be kept or replaced on what the evals measure, not decided ahead of them.

Release 0.2 runs one heuristic per call (ADR-0022), relies on an enforced output structure and a cached prefix, and must trace every production call to its prompt version's eval results (DL-0554).

## Decision

**Release 0.2 calls the Anthropic API directly, runs every heuristic on Claude Sonnet 5.5 by default with the model and its effort bound to each heuristic's prompt version, treats a refusal as a failed run, and accepts that a document's text leaves for the provider under its commercial terms.**

1. **What leaves** (T-03, accepted): the text of each document a call reads — the document analysed and, in a cross-document call, one neighbour from the review's scope. The text leaves only for a document to which the tenant administrator has assigned a companion action or a side-document type: with none assigned, the agents never run on it, it cannot be put in a review's scope as a neighbour (DL-0571 (1)), and nothing of it is sent. That assignment is each organisation's one control, document by document (DL-0049). The confidential guidance is not in release 0.2 and is sent in no call (DL-0568).
2. **The route:** the Anthropic API, through the provider interface.
3. **The model:** `claude-sonnet-5-5` for every heuristic by default. The model and its effort level are settings of each heuristic, hashed into its prompt version and recorded in every trace (ADR-0024), so a heuristic moves to another model only on its own eval results.
4. **A refusal is a failed run**: recorded, shown to the person waiting as a failure, visible in the traces. No fallback to another model.

## Rationale

**What leaves is an owner's decision, and an organisation already controls it.** An agent can analyse only the text it is sent, so the choice is not what to send but whether to analyse at all: a document whose administrator assigned it no analysis is never sent, as itself or as another document's neighbour (DL-0571 (1)). The alternative offered — a zero-retention contract first — traded a recurring commitment nothing yet warrants for a release that needs none.

**The route is the owner's choice.** As offered, the direct API carries first the features this design uses — the enforced output structure (DL-0559) and the cached prefix that makes one call per heuristic affordable (ADR-0022); whether the same features are available through a cloud reseller, and on the same terms, was not checked, and the choice does not rest on it.

**The model is a setting of the heuristic, because the evals measure heuristics.** A heuristic that misses its target on one model may meet it on another, at another price; binding the model into the prompt version lets that move happen one heuristic at a time, with its own results, and keeps every trace exact about what answered. Claude Sonnet 5.5 is the starting point: listed on 2026-11-03 at $2 per million input tokens, $10 per million output tokens and $0.10 per million cached input tokens, with a context of a million tokens.

**A fallback would answer with a model nobody evaluated.** The provider offers to re-run a declined request on another model; that answer would come from a model never measured for the heuristic, breaking DL-0554 (4). Policies and instructions rarely trigger a refusal, so the failure is expected to be rare and is better seen than hidden.

## Consequences

- The product works with one API key per installation; no model runs on the host.
- Every organisation's documents go to one provider; an organisation that may not send its text assigns no analysis and gets none.
- A document assigned no analysis is not offered as a neighbour, so a review's cross-document findings reach only documents that are themselves assigned one (DL-0571 (1)).
- Changing a heuristic's model is a prompt change: its evals re-run, its version changes, and the load command refuses it until its results pass (ADR-0024).
- A provider outage or refusal is a failed analysis, never an empty one (ST-0094).
- Open: whether another model — cheaper or stronger — serves some heuristics better; the evals answer per heuristic.

## Alternatives Rejected

- **Nothing leaves until a zero-retention contract exists.** Rejected because it is a recurring commitment nothing yet warrants; an organisation that needs it assigns no analysis until then.
- **Any document the reviewer may read as a neighbour, assigned an analysis or not.** Rejected because a reviewer's choice would then send a text its organisation assigned nothing to, and the assignment would no longer be the one control (DL-0571 (1)).
- **Amazon Bedrock in an EU region**, the data processed in the EU. Not chosen: the owner's choice of the direct API; it stays reachable behind the same interface.
- **One model for every heuristic, changed for all at once.** Rejected because the evals measure heuristics one by one.
- **The provider's server-side fallback, the trace naming the model that answered.** Rejected as above.
- **A self-hosted model**, one of T-03's options. Not weighed for 0.2; the interface keeps it open (EP-0001).

### Option attribution

| Option | Raised by | Outcome |
|---|---|---|
| Content leaves under the provider's terms; T-03 accepted | agent, on the threat model's options | **accepted** |
| The per-document assignment of an analysis as the organisation's control | agent, from DL-0049 | **accepted** |
| The Anthropic API directly | owner | **accepted** |
| Claude Sonnet as the starting model | owner | **accepted** |
| The model and effort bound to each heuristic's prompt version | owner | **accepted** |
| No fallback on refusal | agent | **accepted** |
| A zero-retention contract first | the record (T-03) | rejected |
| A neighbour must itself be assigned an analysis | agent | **accepted** |
| Any readable document as a neighbour | the record (DL-0565) | rejected |
| Amazon Bedrock in an EU region | agent | rejected |
| One model for all heuristics | agent | rejected |
| The server-side fallback | the provider's guidance | rejected |
| A self-hosted model | the record (T-03, EP-0001) | rejected for 0.2 |

## Guardrails / Conditions of validity

- **Before this ADR is accepted, the provider's retention and training terms for API traffic are quoted here from its published text**, with the date read; the decision rests on them, not on recollection.
- The model and the price are re-read from the provider at acceptance; the figures above are those listed on 2026-11-03.
- Every model call goes through the provider interface; nothing in the platform calls the API around it.

## Review triggers

- The spike's evals: a heuristic meets its target only on another model, or meets it as well on a cheaper one.
- An organisation asks that its text not leave, or not be retained.
- The provider changes its terms for API traffic, or retires the model.
- EP-0001's providers by tenant choice are taken up.

## References

- DL-0560 — the decision this ADR records; DL-0568 — the guidance not in release 0.2; DL-0571 (1) — which documents may be neighbours.
- DL-0049, DL-0120, DL-0554; ADR-0022, ADR-0024.
- `threat-model.md` T-03; `asr.md` ASR-13; EP-0001.

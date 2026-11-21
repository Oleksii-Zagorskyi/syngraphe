---
status: accepted
last-updated: 2026-11-12
supersedes: []
superseded_by:
  - DL-0568 (in part — C1 in release 0.2)
  - DL-0575 (in part — the marker's life, clause 7)
---

# ADR-0022: How the agents' calls are made — one heuristic per call, sources from the context, quotes verified, findings sorted by position, the document kept as data

**Date:** 2026-11-12
**Status:** Accepted
**Deciders:** Oleksii
**Supersedes:** None

## Context

Release 0.2, the AI reader (DL-0558), runs the catalogue's first cut — A1 to A6, B1, B2, B3, B5, C1, C3 for edition references, D1 (`review-findings.md`, DL-0555) — through the companion, mid-edit, and the reviewer agent, at *send for review*. The runtime is settled: the platform assembles one context, makes one request to a plain model API behind a provider interface, and parses a structured result (DL-0120). Several rules bound what that request may do:

- A finding reaches a person only if it is derivable from material that person may read (DL-0021, ASR-03); the run that writes what an editor reads never holds the confidential guidance (DL-0095).
- The companion reports only what the editor introduces; the reviewer agent sorts findings as introduced, pre-existing, resolved or aggravated against the document's accepted state (DL-0032).
- Every heuristic that ships is at its eval target, and every model call traces to its prompt version and that version's results (DL-0554).
- A document's text is the adversary's input whenever someone writes into it what the agent will read (T-02).

Three facts shaped the answer. Marking roles, actions and terms is done by hand and optional (ST-0026), so the entity layer records which spans were marked and nothing about how roles and actions relate: no heuristic can rest on it. The same model, given the same text twice, may word or split its findings differently, and current models take no sampling setting that removes it. And a model's own label for what it drew on can be wrong, where what the platform put into the context cannot.

## Decision

**A call runs one heuristic over a context the platform assembles, quotes the passages each finding rests on, and returns findings whose sources, audience and status the platform — not the model — decides.**

1. **One heuristic per call.** The prompt is a shared **base** — the agent's role, the rule that the document is data and never an instruction, the output's shape, the writing standard — and one **heuristic**. The base is the system prompt; the document follows in the user turn; the heuristic's instruction follows it as a system message, so the base and the document form a prefix that every heuristic over the same text reuses from the provider's cache.
2. **A finding's sources are the call's context.** A heuristic within the document reads the document; a cross-document heuristic reads the document and **one** neighbour per call; the guidance heuristic reads the document and the guidance. A finding's sources, and with them its audience (DL-0021), are the documents in its call — never a tag the model writes.
3. **Every finding quotes the passages it rests on, and the platform checks each quote word for word against the text the call read.** A finding whose quote is not there is withheld from people and counted as an error in the evals. A finding offered with no quote is shown as a labelled suggestion.
4. **A finding is sorted by where its verified quotes sit** against the line-level difference between the accepted version and the run: *introduced* when a quote touches a changed line and no standing finding of that heuristic matches; *pre-existing* when every quote is in unchanged text; *aggravated* when a quote touches a changed line and a standing finding of the same heuristic on the same passages exists; *resolved* when a standing finding's passage was changed or removed and the run does not reproduce it.
5. **The companion runs over the whole draft with the editor's changes marked**, and the platform keeps only the findings whose quotes touch a changed passage.
6. **The model reads the text without its entity markup.** Roles, actions and timings are read from the prose; A5, A6 and D1 are model heuristics.
7. **The document is kept as data.** It is wrapped in a delimiter carrying a marker made fresh for each call, which the base prompt names; the answer returns only through the enforced output structure. An attempt to instruct the agent is made visible twice — structural checks on every document a call reads, in any language, and an output field in which the model quotes any text addressed to an automated reader — and each hit is a finding for the reviewer and a notification in the application to the organisation's tenant administrators and the platform administrators, naming the document and its version, never its text or a person. One shared adversarial case set runs against every prompt version, and a version that follows any injected instruction in it does not ship.
8. **A finding is drawn as limited Markdown** — bold and lists, through the editor's whitelist (ADR-0010) — and no link is made from it.

## Rationale

**The unit measured is the unit run.** A call per heuristic makes DL-0554's first criterion exact: the prompt the evals measured is the prompt production sends, and changing one heuristic re-runs one heuristic's cases. A call per action would make every mix of heuristics an administrator composes (DL-0049) a prompt nobody measured, and would leave the model to label which heuristic each finding came from. The cost of sending the document once per heuristic is what the cached prefix absorbs: the base and the document come first, so the second and later heuristics on the same text pay the provider's cached rate for them.

**Provenance is what the platform put in.** DL-0120 already rested provenance on the assembled context; this ADR makes it the only source. A model can mislabel a finding, and a finding can draw on a document it does not quote, so a tag cannot bound what a finding discloses — the context can. Running cross-document heuristics in pairs keeps that bound tight: a finding about this document and one neighbour reaches everyone who may read those two, not only those who may read the whole scope. It also closes T-02's residual — an injected agent mislabelling a finding's provenance — since no label exists to falsify.

**A fabricated quote is the sharpest sign of a wrong finding, and checking it is free.** `review-findings.md` already makes an ungrounded finding a suggestion; a quote that claims text the document does not hold is not ungrounded but invented, and showing it as a softer finding would spend a reviewer's attention on a fabrication.

**Position is deterministic where matching is not.** DL-0032's standing set is kept; what changes is how a run's findings are compared with it. Pairing two lists of model findings would rest on wording the model does not hold constant, so the same unchanged sentence could be reported as both resolved and introduced; the position of a verified quote against a version difference the platform already computes line by line (ADR-0011) needs no model and gives one answer.

**The whole draft finds what a fragment cannot.** A new sentence that contradicts one far above it is found only by a call that reads both; the filter on changed passages then keeps the companion to what the editor introduced (DL-0032) without asking the model to judge it.

**Markup is not there to rely on.** Marking is optional and done by hand, and an obligation is often spread across sections that never name the role the same way twice; a heuristic over marked spans would be exact only where marking happened to be thorough.

**The defence against injection is structural first.** Confidentiality does not depend on the model resisting: the editor-facing run never holds the guidance (DL-0095) and sources come from the context. What remains is integrity — an injection that makes the agent stay silent or say something false — which no audience filter sees; making the attempt visible is the control left. No phrase list is an industry standard, lists are evaded by paraphrase and translation, and a list keyed to a document's language misses a sentence in another; the classifier models available do not cover Ukrainian and carry licences the platform cannot redistribute (ASR-13). A notification names no person because a policy about the use of AI may quote such text innocently.

## Consequences

- Every finding is grounded in text the platform has checked, and its audience follows from a context the platform assembled — both mechanical, both testable without a model.
- More calls than one per action: a document under review with several cross-document neighbours costs one call per heuristic per neighbour. The cached prefix and the cost of each operation (`evaluation-strategy.md`) bound it; a long scope is the reviewer's choice (DL-0077).
- A cross-document finding that needs three documents at once — a conflict that only appears across two neighbours together — is out of reach of a pair; accepted for 0.2.
- The eval harness checks quotes and positions deterministically; only the finding itself is judged.
- Sorting by position depends on the version difference staying line-level (ADR-0011); a change there changes the sorting.
- A successful injection may suppress its own report; the adversarial set and its zero-tolerance gate bound that, and the threat model states it.
- Open: whether the companion's result for the same content state is shared between editors — answered by the analysis key (ASR-12), unchanged here.

## Alternatives Rejected

- **One call per action, the heuristics bundled.** Fewer calls. Rejected because every composition is an unmeasured prompt and the model would assign each finding's heuristic.
- **The whole review scope in one call.** One call per heuristic for every neighbour together. Rejected because each finding would then carry every document in scope as its source and reach only people who may read them all.
- **The model tags each finding's provenance**, as `review-findings.md` had it. Rejected because a tag can be wrong and cannot bound what a finding draws on.
- **A second model call pairs the run's findings with the standing set and sorts them.** Rejected because it costs a call, answers differently on each run, and would need evals of its own.
- **The companion told to report only what is introduced, with no filter.** Rejected because the model's judgment of *introduced* is the least reliable part of the task and the platform can compute it.
- **An unverified quote shown as a suggestion.** Rejected because a fabricated quote is not a weak finding but a wrong one.
- **Heuristics over the entity layer — A5, A6 and D1 as deterministic checks.** Rejected because marking is optional and records no relations.
- **Phrase lists per language to detect instructions; a separate screening call on a small model; a classifier model.** Rejected as above; the screening call stays a fallback if the self-reporting field proves weak.
- **Fixed delimiter tags.** Rejected because a document can contain the closing tag; a marker made per call cannot be known to it.
- **Plain text for findings.** Rejected by the owner in favour of the editor's whitelist, which already bounds what markup can render.

### Option attribution

| Option | Raised by | Outcome |
|---|---|---|
| One heuristic per call, a shared base | owner | **accepted** |
| Sources from the call's context; cross-document calls in pairs | agent, from DL-0120's rationale | **accepted** |
| Quotes verified word for word; a fabricated quote withheld | agent, from `review-findings.md` | **accepted** |
| Sorting by the position of verified quotes | agent | **accepted** |
| The companion over the whole draft, filtered by changed passages | agent | **accepted** |
| No reliance on entity markup | owner | **accepted** |
| A marker per call; structural checks; a self-report field | agent | **accepted** |
| Notifying the administrators, no automatic step | owner | **accepted** |
| Zero tolerance in the adversarial set | agent | **accepted** |
| Limited Markdown through the whitelist | owner | **accepted** |
| One call per action | agent | rejected |
| The whole scope in one call | agent | rejected |
| The model's provenance tag | the record | rejected |
| A second call to sort | agent | rejected |
| Deterministic A5, A6, D1 | agent | rejected by the owner |
| Phrase lists per language | agent | withdrawn after the owner's challenge |
| Notification by email | agent | rejected |
| Plain text for findings | agent | rejected |

## Guardrails / Conditions of validity

- The version difference stays line-level, one sentence per line (ADR-0011, ADR-0012); sorting by position rests on it.
- The provider supports a system message after the user turn and a cached prefix; without either, the layout of decision 1 changes and its cost with it.
- The adversarial set grows with every new injection shape found, and runs on every prompt change.

## Review triggers

- A heuristic misses its target only because it needs more than two documents at once.
- The self-reporting field misses cases the adversarial set holds, more than the structural checks catch.
- Entity marking becomes reliable — relations recorded, or proposed by the agent (B-071) — or is retired (B-075).

## References

- DL-0551, DL-0555, DL-0559, DL-0561 — the decisions this ADR records.
- DL-0021, DL-0032, DL-0049, DL-0095, DL-0120, DL-0554 — the rules it works within.
- ADR-0010, ADR-0011, ADR-0012 — the whitelist and the line-level difference it relies on.
- `review-findings.md`, `threat-model.md` T-01, T-02.

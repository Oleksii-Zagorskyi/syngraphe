---
tags:
  - technical-design
aliases:
  - Syngraphē review findings taxonomy
status: draft
date: 2026-09-18
---

# Review Findings — the heuristic catalogue

The classes of problem the agents look for, the material each is derived from, and therefore its audience.

**Each row in the tables below is a heuristic** (DL-0031, DL-0049, DL-0577) — an entry of the catalogue with an id, a slug, a title and a short explanation, the kind a finding is labelled with. Heuristics compose into **companion actions** (a user-facing analysis) and **side-document types** (a generated view); a tenant administrator assigns those by title and never sees what runs underneath. What runs is a **prompt**, which covers one heuristic or several — `P03-read-document` covers A01 to A06 in one call (ADR-0026). This file is the specification the prompts are written against. The prompt text is source in `prompts/`, registered by its own ids in `prompts/README.md`, and the platform's copy is loaded from there (`technical-design.md § Prompts are source`).

Every agent run records the prompts it ran and at which version, and every finding names its heuristic, one of those its prompt covers (ADR-0026).

## The two axes

A finding has a **provenance** and a **kind**. Provenance decides *who may see it*; kind decides *what the agent looks for*. They are independent, and conflating them is how a containment rule becomes a prompt instruction instead of a check.

**Provenance decides audience (DL-0021).** A finding reaches a recipient if and only if it is derivable from material that recipient may already read.

| Provenance | Derived from | Audience |
|---|---|---|
| **P1 — internal** | the edited document alone | everyone with read access to the document, readers of the canonical version included |
| **P2 — corpus, visible** | another document the recipient may also read | everyone who can read both documents |
| **P3 — corpus, restricted** | another document the recipient may **not** read — a different document set | behaves as P4: reviewer-eyes-only for that recipient |
| **P4 — confidential guidance** | the guidance repository | holders of the guidance grant only |
| **P5 — declared rule set** | a non-confidential rule set: organization policy, a legal corpus | everyone who may read that rule set |

P3 is the subtle one and it is not an edge case. Rights are document-scoped (DL-0091), so the boundary that produces P3 is between **documents**: a finding drawing on a neighbouring policy is P2 for a reviewer who may read both and P3 for an editor who may read only one. **Audience is computed per recipient, not per finding.**

P4 is designed and not in release 0.2: the confidential guidance is sent to no model there, so no finding of 0.2 has that provenance (DL-0568, backlog B-079).

## The kinds

These tables are the registry of the heuristics (DL-0572). The id is stable: keys, results and decision rows use it. The slug is the heuristic's short name, used beside the id in reports and in folder names such as `prompts/A01-contradiction/`. Records written before DL-0572 use the former id.

### A — internal to the document

| ID | Slug | Kind | Example | Former id |
|---|---|---|---|---|
| A01 | contradiction | Contradiction between statements | "X approves Y" in one section, "Y cannot approve Y" in another | A1 |
| A02 | ambiguity | Ambiguity | the document, read as a whole, can be acted on two ways: two passages read together give two careful readers two different actions, persons, time limits or permissions (DL-0574) | A2 |
| A03 | scope-gap | Gap inside the declared scope | approval defined for amounts above a threshold, silent below it | A3 |
| A04 | term-two-meanings | One term, two meanings | "manager" used for a role in one section and a job grade in another | A4 |
| A05 | circular-authority | Circular or self-referential authority | A approves B, B approves A; a role approving its own act | A5 |
| A06 | unowned-obligation | Unowned obligation, or a right without an accountable role | an action required with nobody assigned; a role granted a right it has no obligation to exercise | A6 |

A05 and A06 were first seen as graph checks over the entity layer (DL-0005). Marking is done by hand and optional and records no relation between a role and an action, so in release 0.2 they are model heuristics that read roles, actions and timings from the prose (DL-0551, DL-0559).

### B — against the existing document base

| ID | Slug | Kind | Example | Former id |
|---|---|---|---|---|
| B01 | cross-contradiction | Contradiction with another document | this document permits what another forbids | B1 |
| B02 | authority-override | Override of a matter another document governs | the edit legislates outside this document's remit — the authority conflict, distinct from a logical one | B2 |
| B03 | broken-reference | Broken outbound reference | this document cites a role, section, document or edition that was renamed or retired | B3 |
| B04 | inbound-breakage | Inbound breakage | this edit changes something other documents cite — the owner's API-rename case, seen from the callers' side | B4 |
| B05 | term-collision | Term collision across the base | a term introduced here already has a different definition elsewhere | B5 |
| B06 | sibling-divergence | Sibling-language divergence | a translated counterpart document no longer says the same thing | B6 |

B02 is the class the owner added, and it is worth keeping separate from B01: there need be no logical contradiction for it to matter. A document that starts regulating procurement thresholds when another document owns procurement is a governance defect even if the two happen to agree today.

### C — against constraints

| ID | Slug | Kind | Example | Former id |
|---|---|---|---|---|
| C01 | guidance-conflict | Guidance conflict | "Supplier Y may not be named a preferred vendor" against an edit listing Supplier Y as preferred | C1 |
| C02 | rule-set-conflict | Declared rule set conflict | organization policy or statute the tenant has loaded as a non-confidential rule set | C2 |
| C03 | temporal-conflict | Temporal conflict | an effective date that overlaps a rule with a different window; a reference to a period already closed; a citation of a superseded edition | C3 |

### D — impact reports, not defects

| ID | Slug | Kind | Why it matters | Former id |
|---|---|---|---|---|
| D01 | derived-view-delta | Derived-view delta | *"this edit changes the purchase manager's obligations list"* — the reviewer sees the change to the derived rights and obligations, not only the text diff | D1 |
| D02 | affected-documents | Affected-documents list | which documents will need to react once this run is accepted | D2 |

D01 is the highest-value item in this table that nobody asks for. A text diff shows a sentence changing; the derived-view delta shows that a named person's obligations changed, which is the thing a reviewer of a policy document is actually accountable for. Obligations are spread across sections and roles are not always marked, so D01 is read from the prose by a model, not computed from the marked spans (DL-0559).

## What is in the first cut (0.2)

Release 0.2, the AI reader, carries the first cut below (DL-0555, DL-0568, DL-0571). **Detecting** a cross-document conflict when a document is sent for review reads the neighbours the reviewer put in scope, one per call (DL-0077, DL-0559). **Notifying** another document's owners when this one is accepted needs a maintained dependency graph, and that stays deferred (DL-0018). Every heuristic of the first cut is a model heuristic; none is answered exactly by a deterministic check (DL-0551). Each is measured as `evaluation-strategy.md` says.

| Class | First cut | Note |
|---|---|---|
| A01, A02, A03, A04 | first cut | prose reading, the seed's original three lenses plus term drift |
| A05, A06 | first cut | prose reading; marking is not relied on (DL-0559) |
| B01, B02, B03, B05 | first cut | the document and one neighbour of the reviewer's scope per call (ADR-0022); run by the reviewer agent for each neighbour in scope (DL-0571 (2)) |
| B04, D02 | later | needs the dependency graph |
| B06 | later | needs sibling-document links |
| C01 | later | the confidential guidance is not in release 0.2, which makes no guidance call (DL-0568, backlog B-079); its design stands for when it returns — the document and the guidance in a call of their own, reviewer-eyes-only (DL-0095, ADR-0022) |
| C02 | later | needs a rule-set import surface |
| C03 | later | not in release 0.2 (DL-0571 (3), backlog B-081): a call over the document alone cannot tell that a cited edition is superseded; effective-date windows are not modelled |
| D01 | first cut | prose reading of what the run changes in each role's obligations (ADR-0022); the reviewer agent runs it (DL-0571 (2)) |

**Who runs what** (DL-0567, DL-0571 (2)). The reviewer agent runs the heuristics of the companion actions and side-document types assigned to the document. For every document assigned any analysis it also runs D01, and B01, B02, B03 and B05 for each neighbour in the reviewer's scope; these five belong to no companion action and no side-document type. The companion runs only heuristics within the document. Release 0.2 has three side-document types, one per standing list: *contradictions* — A01, A04, A05; *ambiguities* — A02; *blind spots* — A03, A06.

## Scope and lifecycle

Two separate things, and conflating them floods the wrong reader.

**Scope** — the companion is **edit-scoped**: it reports only on what this editor is introducing. A document carries known, unresolved flaws, and an editor asking for feedback on three sentences must not receive the whole backlog. The reviewer agent reports **both**, in separated groups (DL-0032).

**Lifecycle** — a **standing findings set** is maintained per document against its accepted state and refreshed when that state changes. A run's findings are computed against its latest version and sorted by where their verified quotes sit against the difference between the accepted version and the run, the standing set telling an aggravated finding from an introduced one (DL-0559):

| Status | Meaning |
|---|---|
| **introduced** | present in the run's latest version, absent from the accepted state — the editor caused it |
| **pre-existing** | present in both — the document already carried it |
| **resolved** | present in the accepted state, absent from the run's latest version — the run fixes it |
| **aggravated** | present in both, but wider or more severe in the run's latest version |

The standing set is computed once per accepted state and shared across every unaccepted run, so cost does not scale with the number of runs. It doubles as the known-open-findings list a reader sees on a canonical document. In release 0.2 it is computed at each acceptance for a document assigned at least one side-document type, and holds only findings derived from the document alone (DL-0555, DL-0567). **A cross-document finding is therefore only ever *introduced* or *pre-existing*, never *aggravated* or *resolved*** (DL-0567): no standing finding exists for it to be measured against. Where a document has no standing set, the findings of a review are sorted by position only — *introduced* or *pre-existing* — and the analysis says so (DL-0571 (6)).

**Resolved** and **aggravated** are the two nobody asks for and both change a reviewer's judgement: a run that fixes three long-standing contradictions deserves to be read differently from one that introduces none.

## Rules this table has to obey

- **The platform takes a finding's provenance from the call's context and computes its audience.** A finding's sources are the documents the call read; neither the prompt nor the model decides who sees a finding (DL-0559, ADR-0022).
- **A finding whose sources cannot be established is withheld from everyone** and counted as an error (DL-0571 (13)). Fail closed.
- **A finding quotes the passages it rests on, and each quote is checked word for word against the text.** A finding whose quote is not in the text is withheld and counted as an error; a finding the agent offers without a quote is a **suggestion**, not a finding, and is labelled as such: the reviewer agent's analysis shows suggestions in a group of their own, unsorted, and the companion shows none (DL-0571 (9)). An ungrounded contradiction claim costs a reviewer more attention than it saves (ADR-0022).
- **This file is the specification, not the prompt.** The prompts that cover its rows live in `prompts/<id>-<slug>/`, beside the shared base and the judge (DL-0570, DL-0577); this file is what their text is written against and reviewed for coverage.
- **A prompt's text is versioned.** Changing it changes what past reviews would have said, so runs record the version they used rather than the current one. No prompt is edited in place in the platform: it changes only through `prompts/`, its evals and the load, and the platform administrator may switch a heuristic off at once (DL-0567). The findings of a heuristic switched off are dropped from every new result, while its prompt still runs for the heuristics it covers that are on (ADR-0026); its stored results stay readable, and an analysis already running completes (DL-0571 (15)).

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

**Each row in the tables below is a heuristic** (DL-0031, DL-0049) — a record with a title, a short explanation and prompt text, visible only to the platform administrator. Heuristics compose into **companion actions** (a user-facing analysis) and **side-document types** (a generated view); a tenant administrator attaches those by title and never sees the text underneath. This file is the specification each heuristic's prompt text is written against. The prompt text itself is source in `prompts/`, and the platform's copy is seeded from there (`technical-design.md § Prompts are source`).

Every agent run records which heuristics it used and at which version, and every finding names the heuristic that produced it.

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

## The kinds

### A — internal to the document

| ID | Kind | Example |
|---|---|---|
| A1 | Contradiction between statements | "X approves Y" in one section, "Y cannot approve Y" in another |
| A2 | Ambiguity | a sentence that admits two readings, both operative |
| A3 | Gap inside the declared scope | approval defined for amounts above a threshold, silent below it |
| A4 | One term, two meanings | "manager" used for a role in one section and a job grade in another |
| A5 | Circular or self-referential authority | A approves B, B approves A; a role approving its own act |
| A6 | Unowned obligation, or a right without an accountable role | an action required with nobody assigned; a role granted a right it has no obligation to exercise |

A5 and A6 are graph checks over the entity layer, not prose reading — they are the first concrete payoff of the roles-and-actions YAML (DL-0005).

### B — against the existing document base

| ID | Kind | Example |
|---|---|---|
| B1 | Contradiction with another document | this document permits what another forbids |
| B2 | Override of a matter another document governs | the edit legislates outside this document's remit — the authority conflict, distinct from a logical one |
| B3 | Broken outbound reference | this document cites a role, section, document or edition that was renamed or retired |
| B4 | Inbound breakage | this edit changes something other documents cite — the owner's API-rename case, seen from the callers' side |
| B5 | Term collision across the base | a term introduced here already has a different definition elsewhere |
| B6 | Sibling-language divergence | a translated counterpart document no longer says the same thing |

B2 is the class the owner added, and it is worth keeping separate from B1: there need be no logical contradiction for it to matter. A document that starts regulating procurement thresholds when another document owns procurement is a governance defect even if the two happen to agree today.

### C — against constraints

| ID | Kind | Example |
|---|---|---|
| C1 | Guidance conflict | "Supplier Y may not be named a preferred vendor" against an edit listing Supplier Y as preferred |
| C2 | Declared rule set conflict | organization policy or statute the tenant has loaded as a non-confidential rule set |
| C3 | Temporal conflict | an effective date that overlaps a rule with a different window; a reference to a period already closed; a citation of a superseded edition |

### D — impact reports, not defects

| ID | Kind | Why it matters |
|---|---|---|
| D1 | Derived-view delta | *"this edit changes the purchase manager's obligations list"* — the reviewer sees the change to the derived rights and obligations, not only the text diff |
| D2 | Affected-documents list | which documents will need to react once this run is accepted |

D1 is the highest-value item in this table that nobody asks for. A text diff shows a sentence changing; the derived-view delta shows that a named person's obligations changed, which is the thing a reviewer of a policy document is actually accountable for.

## What is in the first cut (0.2)

The scope split follows DL-0022: **detecting** a cross-document conflict when a document is sent for review is cheap, because the agent reads the corpus the reviewer may read. **Notifying** another document's owners when this one is accepted needs a maintained dependency graph, and that stays deferred (DL-0018).

| Class | First cut | Note |
|---|---|---|
| A1, A2, A3, A4 | first cut | prose reading, the seed's original three lenses plus term drift |
| A5, A6 | first cut | graph checks over the entity layer |
| B1, B2, B3, B5 | first cut | agent reads the readable corpus when the document is sent for review |
| B4, D2 | later | needs the dependency graph |
| B6 | later | needs sibling-document links |
| C1 | first cut | the guidance document exists from 0.1 |
| C2 | later | needs a rule-set import surface |
| C3 | first cut for edition references; later for effective-date windows | edition supersession is already modelled; date windows are not |
| D1 | first cut | reads the entity layer, which is 0.1 |

## Scope and lifecycle

Two separate things, and conflating them floods the wrong reader.

**Scope** — the companion is **edit-scoped**: it reports only on what this editor is introducing. A document carries known, unresolved flaws, and an editor asking for feedback on three sentences must not receive the whole backlog. The reviewer agent reports **both**, in separated groups (DL-0032).

**Lifecycle** — a **standing findings set** is maintained per document against its accepted state and refreshed when that state changes. A run's findings are computed against its latest version and diffed against the standing set, which classifies each finding as:

| Status | Meaning |
|---|---|
| **introduced** | present in the run's latest version, absent from the accepted state — the editor caused it |
| **pre-existing** | present in both — the document already carried it |
| **resolved** | present in the accepted state, absent from the run's latest version — the run fixes it |
| **aggravated** | present in both, but wider or more severe in the run's latest version |

The standing set is computed once per accepted state and shared across every unaccepted run, so cost does not scale with the number of runs. It doubles as the known-open-findings list a reader sees on a canonical document.

**Resolved** and **aggravated** are the two nobody asks for and both change a reviewer's judgement: a run that fixes three long-standing contradictions deserves to be read differently from one that introduces none.

## Rules this table has to obey

- **The agent tags provenance; the platform computes audience.** The prompt never decides who sees a finding.
- **A finding with no provenance tag is treated as P4** — reviewer-only. Fail closed.
- **A finding the agent cannot ground in a citable passage is a suggestion, not a finding**, and is labelled as such. An ungrounded contradiction claim costs a reviewer more attention than it saves.
- **This file is the specification, not the prompt.** Each row's prompt text lives in `prompts/`, one directory per heuristic, and is seeded into its heuristic record; this file is what that text is written against and reviewed for coverage.
- **A heuristic's text is versioned.** Changing it changes what past reviews would have said, so runs record the version they used rather than the current one.

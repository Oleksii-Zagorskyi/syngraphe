# Whitelist conformance cases

`cases.json` is the conformance list for the constrained Markdown subset. The whitelist itself is defined in `docs/technical-design.md § The constrained Markdown subset`; these cases test against it and do not restate it. Both parsers — the server's and the editor's — are run over every case and must agree with it on verdict, refusal code, line and stored form.

## Shape

A JSON array; one object per case, keys in this order:

| Key | Holds |
|---|---|
| `id` | Stable kebab-case name, prefixed `accept-`, `refuse-`, `respell-` or `edge-` |
| `kind` | `accept`, `refuse` or `respell` — an `edge-` case carries one of these too |
| `input` | The Markdown submitted, ending in a newline |
| `stored` | `accept` and `respell` only: what the serialiser writes, byte for byte. For `accept` it equals `input` |
| `refusals` | `refuse` only: every refusal the input holds, as `{"code", "line"}`, sorted by line then code. The line is the first source line of the block holding the construct; for a table row wider than its header, the line of that row |
| `note` | One sentence: what the case proves |

Refusal codes are the keys of `refusals` in `src/editing/whitelist/spec.json`.

## Rules

- **A case is added for both parsers at once.** The list is the contract between them; a case one side does not run is not a case.
- **A change of expectation is a change to the specification**, made there first and reviewed as such — never an edit to make a failing side pass.
- **The `id` never changes**, so other tests may key on it.
- **Every text is invented.** No real document, organisation or person appears here.

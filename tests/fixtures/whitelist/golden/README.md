# Golden HTML for the reading view

One file per `accept` case in `../cases.json`, named by the case's `id`: the exact bytes the reading view's renderer, `rendering.renderer.render`, must return for that case's `input`. `tests/rendering/test_renderer.py` compares them byte for byte, and fails when an `accept` case has no file or a file has no case.

## How they are written

From the renderer's contract, never from the renderer. The parse is the shared recogniser's rules over markdown-it-py with raw HTML off and markdown-it's own link validation; every construct renders as markdown-it-py's default renderer renders it, except:

| Construct | Renders as |
|---|---|
| Entity span | `<span class="entity entity-{kind}" data-id="{id}">`, the `data-id` omitted when the span has no id |
| Underline | `<span class="underline">` |
| Callout | `<div class="callout callout-{type}">` and `</div>`, each followed by a newline |
| Soft break | One space |
| Image | Its alt text, escaped, and nothing else |
| Link | markdown-it's own tag, with `rel="noopener noreferrer"` after its other attributes |

Every heading, and every paragraph outside a table, opens with its clause number — `<span class="num">LABEL</span>` and one space — derived as DL-0065, DL-0327 and DL-0330 decide. A table's cells and a paragraph holding only an image take no number, and the image's paragraph does not advance the count.

## Rules

- **Never regenerated from the renderer.** A file that disagrees with the renderer is evidence, not an error to overwrite: either the renderer is wrong, or the contract changed.
- **A file changes only in a commit that says why** — the decision or contract change it follows.
- **A new `accept` case brings its file in the same commit.**
- **Every text is invented**, as in the cases themselves.

// Clause numbers in a gutter beside the text (DL-0065, DL-0327, DL-0330): `1.1-3` is the heading
// path, a hyphen, and the paragraph's index within its section; a skipped heading level counts as
// 1. Derived from the document on every change, never stored, and outside what can be edited or
// selected. A paragraph before the first heading carries its index alone; a table and an image are
// not clauses.
import { Plugin } from "prosemirror-state";
import { Decoration, DecorationSet } from "prosemirror-view";

// Every heading's and paragraph's position and its number, in document order.
export function clauseNumbers(doc) {
  const path = [];
  let index = 0;
  const found = [];
  doc.descendants((node, pos) => {
    if (node.type.name === "heading") {
      const level = node.attrs.level;
      path.length = level;
      path[level - 1] = (path[level - 1] || 0) + 1;
      for (let i = 0; i < level - 1; i++) path[i] = path[i] || 1;
      index = 0;
      found.push({ pos, label: path.join(".") });
      return false;
    }
    if (node.type.name === "table") return false;
    if (node.type.name === "paragraph") {
      const only = node.childCount === 1 ? node.firstChild : null;
      if (!only || only.type.name !== "image") {
        index += 1;
        const heading = path.join(".");
        found.push({ pos, label: heading ? `${heading}-${index}` : String(index) });
      }
      return false;
    }
    return true;
  });
  return found;
}

function decorations(doc) {
  return DecorationSet.create(
    doc,
    clauseNumbers(doc).map(({ pos, label }) =>
      Decoration.widget(
        pos + 1,
        () => {
          const span = document.createElement("span");
          span.className = "clause";
          span.contentEditable = "false";
          span.setAttribute("aria-hidden", "true");
          span.textContent = label;
          return span;
        },
        { side: -1, key: `clause-${label}`, ignoreSelection: true },
      ),
    ),
  );
}

export function gutter() {
  return new Plugin({
    state: {
      init: (_, state) => decorations(state.doc),
      apply: (tr, value, _, state) => (tr.docChanged ? decorations(state.doc) : value),
    },
    props: {
      decorations(state) {
        return this.getState(state);
      },
    },
  });
}

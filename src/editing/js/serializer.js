// The stored form: prosemirror-markdown's serialiser state with the platform's writers (DL-0240).
// `src/editing/markdown/serializer.py` ports the same state and writers, so a text reaches the same
// bytes on either side; the conformance suite's re-spelling cases hold the two in step.
import { MarkdownSerializer, MarkdownSerializerState } from "prosemirror-markdown";

const ESCAPE = /[`*\\~\[\]_|]/g;
const WORD = /[A-Za-z0-9_]/;
const EXTRA = /<|&(?=#?[A-Za-z0-9]+;)/g;
const LINE_START = /^[+\-*>]/;
const HEADING_END = /#+$/;
const LEADING_SPACE = /^[ \t]+/;
const TRAILING_SPACE = /[ \t]+$/;
const ONE_LINE = new Set(["heading", "table_cell", "table_header"]);
const HEADING_START = /^(\s*)(#{1,6})(\s|$)/;
const NUMBER_START = /^(\s*[0-9]+)([.)])(\s|$)/;
const DELIMITER = { left: ":---", right: "---:", center: ":---:" };

// Escape literal text so it never reads as markup: prosemirror-markdown's `esc`, then the
// platform's additions at a line start — `1)` as well as `1.`, and a leading `=`.
export function esc(text, startOfLine) {
  text = text.replace(ESCAPE, (character, i) =>
    character === "_" && i > 0 && i < text.length - 1 && WORD.test(text[i - 1]) && WORD.test(text[i + 1])
      ? character
      : "\\" + character,
  );
  if (startOfLine) {
    text = text.replace(LINE_START, "\\$&");
    text = text.replace(HEADING_START, "$1\\$2$3");
    text = text.replace(NUMBER_START, "$1\\$2$3");
    if (text.startsWith("=")) text = "\\" + text;
  }
  return text.replace(EXTRA, "\\$&");
}

function isPlainURL(link, parent, index) {
  if (!/^[A-Za-z0-9_]+:/.test(link.attrs.href)) return false;
  const content = parent.child(index);
  if (!content.isText || content.text !== link.attrs.href || !content.marks[content.marks.length - 1].eq(link)) {
    return false;
  }
  return index === parent.childCount - 1 || !link.isInSet(parent.child(index + 1).marks);
}

// prosemirror-markdown's `renderList`, tight, each item indented by its own marker's width.
function list(state, node, marker) {
  if (state.closed && state.closed.type === node.type) state.flushClose(3);
  else if (state.inTightList) state.flushClose(1);
  const previous = state.inTightList;
  state.inTightList = true;
  // An item with no text yet — Enter at a list's end — is not written: it would be refused.
  const items = [];
  node.forEach((child) => {
    if (child.childCount > 1 || (child.firstChild && child.firstChild.childCount > 0)) items.push(child);
  });
  items.forEach((child, i) => {
    if (i) state.flushClose(1);
    const first = marker(i);
    state.wrapBlock(" ".repeat(first.length), first, node, () => state.render(child, node, i));
  });
  state.inTightList = previous;
}

function cellText(state, cell) {
  const at = state.out.length;
  state.renderInline(cell);
  const text = state.out.slice(at);
  state.out = state.out.slice(0, at);
  return text.trim().replace(/(?<!\\)\|/g, "\\|");
}

const span = {
  open: "[",
  close: (_, mark) =>
    mark.type.name === "underline" ? "]{.underline}" : "]{." + mark.attrs.kind + (mark.attrs.id ? " #" + mark.attrs.id : "") + "}",
  mixable: true,
  expelEnclosingWhitespace: true,
};

export const serializer = new MarkdownSerializer(
  {
    paragraph(state, node) {
      state.renderInline(node);
      state.closeBlock(node);
    },
    heading(state, node) {
      state.write("#".repeat(node.attrs.level) + " ");
      state.renderInline(node, false);
      state.closeBlock(node);
    },
    quote(state, node) {
      state.wrapBlock("> ", null, node, () => state.renderContent(node));
    },
    callout(state, node) {
      state.wrapBlock("> ", null, node, () => {
        state.write(`[!${node.attrs.type}]`);
        state.ensureNewLine();
        state.renderContent(node);
      });
    },
    bullet_list(state, node) {
      list(state, node, () => "- ");
    },
    ordered_list(state, node) {
      const start = node.attrs.order;
      list(state, node, (i) => `${start + i}. `);
    },
    list_item(state, node) {
      state.renderContent(node);
    },
    table(state, node) {
      state.flushClose(2); // first: the separator the previous block owes
      node.forEach((row, _, r) => {
        const cells = [];
        row.forEach((cell) => cells.push(cellText(state, cell)));
        state.write("| " + cells.join(" | ") + " |");
        state.ensureNewLine();
        if (r === 0) {
          const delimiters = [];
          row.forEach((cell) => delimiters.push(DELIMITER[cell.attrs.align] || "---"));
          state.write("| " + delimiters.join(" | ") + " |");
          state.ensureNewLine();
        }
      });
      state.closeBlock(node);
    },
    image(state, node) {
      state.write("![" + esc(node.attrs.alt || "", false) + "](" + node.attrs.src.replace(/[()]/g, "\\$&") + ")");
    },
    // A sentence boundary is written only between two pieces of text: never first or last in its
    // block, never twice in a row.
    sb(state, node, parent, index) {
      let later = false;
      for (let j = index + 1; j < parent.childCount; j++) if (parent.child(j).type.name !== "sb") later = true;
      if (index > 0 && later && parent.child(index - 1).type.name !== "sb") {
        // A heading and a table cell hold one line: their sentences are joined by a space.
        const oneLine = state.options.oneLine || ONE_LINE.has(parent.type.name);
        state.write(oneLine ? " " : "\n");
      }
    },
    text(state, node, parent, index) {
      const afterBoundary = index > 0 && parent.child(index - 1).type.name === "sb" && state.atBlank();
      if (state.inAutolink) {
        state.text(node.text, false);
        return;
      }
      const lineStart = state.atBlockStart || afterBoundary;
      const next = index + 1 < parent.childCount ? parent.child(index + 1) : null;
      // Spaces at either end of a sentence's line would read as an indent or a line break.
      let raw = lineStart ? node.text.replace(LEADING_SPACE, "") : node.text;
      if (!next || next.type.name === "sb") raw = raw.replace(TRAILING_SPACE, "");
      if (!raw) return;
      let text = esc(raw, lineStart);
      if (parent.type.name === "heading" && index === parent.childCount - 1) {
        // A heading's closing `#`s would be read as its optional closing sequence.
        text = text.replace(HEADING_END, "\\$&");
      }
      state.write();
      state.text(text, false);
    },
  },
  {
    entity: span,
    link: {
      open(state, mark, parent, index) {
        state.inAutolink = isPlainURL(mark, parent, index);
        return state.inAutolink ? "<" : "[";
      },
      close(state, mark) {
        const autolink = state.inAutolink;
        state.inAutolink = undefined;
        return autolink ? ">" : "](" + mark.attrs.href.replace(/[()"]/g, "\\$&") + ")";
      },
      mixable: true,
    },
    underline: span,
    strong: { open: "**", close: "**", mixable: true, expelEnclosingWhitespace: true },
    em: { open: "*", close: "*", mixable: true, expelEnclosingWhitespace: true },
  },
);

// The stored form of an editor document, ending in one line break; with `oneLine`, each paragraph
// on one line, its sentences joined by a space, as the source view and a Markdown export show it.
export function serialize(doc, { oneLine = false } = {}) {
  const state = new MarkdownSerializerState(serializer.nodes, serializer.marks, { tightLists: true, oneLine });
  state.renderContent(doc);
  state.flushClose(1);
  return state.out;
}

// *Clear formatting* (DL-0531): over the selection, or the line the cursor stands in, the marks
// that format the text go — bold, italic, underline, links — while the entity marks stay, since they
// declare roles, actions and terms and point at documents; every line is lifted out of lists,
// quotes and the note blocks, and headings become paragraphs. A table keeps its shape, its cells
// cleared of marks. One transaction, so one undo restores it all.
import { NodeRange } from "prosemirror-model";
import { liftTarget } from "prosemirror-transform";

const FORMATTING = ["strong", "em", "underline", "link"];
const WRAPPERS = new Set(["bullet_list", "ordered_list", "list_item", "quote", "callout"]);

// The first textblock of the range still standing inside a wrapper, or `null`.
function wrapped(doc, from, to) {
  let found = null;
  doc.nodesBetween(from, to, (node, pos) => {
    if (found !== null) return false;
    if (!node.isTextblock) return true;
    const $inside = doc.resolve(pos + 1);
    for (let depth = $inside.depth - 1; depth > 0; depth--) {
      if (WRAPPERS.has($inside.node(depth).type.name)) {
        found = pos;
        break;
      }
    }
    return false;
  });
  return found;
}

export function clearFormatting(schema) {
  return (state, dispatch) => {
    const { selection } = state;
    const from = selection.empty ? selection.$from.start() : selection.from;
    const to = selection.empty ? selection.$from.end() : selection.to;
    if (!dispatch) return true;
    const tr = state.tr;
    for (const name of FORMATTING) {
      if (schema.marks[name]) tr.removeMark(from, to, schema.marks[name]);
    }
    const range = () => [tr.mapping.map(from, -1), tr.mapping.map(to, 1)];
    // Lift each line out of its wrappers, one step at a time, until none is left inside one; each
    // step lowers a line's depth, so the document's size bounds them.
    for (let guard = tr.doc.content.size; guard > 0; guard--) {
      const [start, end] = range();
      const pos = wrapped(tr.doc, start, end);
      if (pos === null) break;
      const $inside = tr.doc.resolve(pos + 1);
      let blocks = $inside.blockRange();
      let target = blocks && liftTarget(blocks);
      // A list item holding a nested list lifts whole, its nested list beside it.
      if (target == null && $inside.node($inside.depth - 1).type.name === "list_item") {
        const depth = $inside.depth - 1;
        blocks = new NodeRange(
          tr.doc.resolve($inside.start(depth)),
          tr.doc.resolve($inside.end(depth)),
          depth,
        );
        target = liftTarget(blocks);
      }
      if (target == null) break;
      tr.lift(blocks, target);
    }
    const [start, end] = range();
    tr.doc.nodesBetween(start, end, (node, pos) => {
      if (node.type === schema.nodes.heading) {
        tr.setNodeMarkup(pos, schema.nodes.paragraph);
        return false;
      }
      return !node.isTextblock;
    });
    dispatch(tr.scrollIntoView());
    return true;
  };
}

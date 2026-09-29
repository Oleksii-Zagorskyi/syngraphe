// The toolbar: headings, lists, bold, italic, underline, quotes, callouts, tables and links, and
// undo and redo. Buttons keep the selection through the click by refusing the mousedown's default.
import { setBlockType, toggleMark, wrapIn } from "prosemirror-commands";
import { redo, undo } from "prosemirror-history";
import { wrapInList } from "prosemirror-schema-list";
import { addRowAfter } from "prosemirror-tables";
import { insertPoint } from "prosemirror-transform";

import { spec } from "./spec.js";

// The deepest list nesting in `doc`.
function listDepth(doc) {
  let deepest = 0;
  const walk = (node, depth) => {
    const here = node.type.name.endsWith("_list") ? depth + 1 : depth;
    deepest = Math.max(deepest, here);
    node.forEach((child) => walk(child, here));
  };
  walk(doc, 0);
  return deepest;
}

// A list command that never nests a list deeper than the whitelist allows.
export function capped(command) {
  return (state, dispatch, view) =>
    command(state, dispatch && ((tr) => listDepth(tr.doc) <= spec.listMaxDepth && dispatch(tr)), view);
}

function insertTable(schema) {
  return (state, dispatch) => {
    const { table, table_row, table_header, table_cell, paragraph } = schema.nodes;
    const cell = (type) => type.createAndFill();
    const node = table.create(null, [
      table_row.create(null, [cell(table_header), cell(table_header)]),
      table_row.create(null, [cell(table_cell), cell(table_cell)]),
    ]);
    const $from = state.selection.$from;
    const after = $from.depth ? $from.after(1) : $from.pos;
    const at = insertPoint(state.doc, after, table) ?? state.doc.content.size;
    if (dispatch) {
      let tr = state.tr.insert(at, node);
      if (at + node.nodeSize >= tr.doc.content.size) tr = tr.insert(tr.doc.content.size, paragraph.create());
      dispatch(tr.scrollIntoView());
    }
    return true;
  };
}

function button(label, name, run) {
  const element = document.createElement("button");
  element.type = "button";
  element.textContent = label;
  element.dataset.command = name;
  element.addEventListener("mousedown", (event) => event.preventDefault());
  element.addEventListener("click", run);
  return element;
}

// The toolbar for `view`; `words` are the page's translated labels and notices, `report` shows one
// line under the editor.
export function toolbar(view, schema, words, report) {
  const bar = document.createElement("span");
  bar.className = "toolbar";
  bar.setAttribute("role", "toolbar");
  const labels = words.labels;
  const run = (command) => () => {
    command(view.state, view.dispatch, view);
    view.focus();
  };
  const blocks = [
    ["paragraph", setBlockType(schema.nodes.paragraph)],
    ...Array.from({ length: spec.headingMaxDepth }, (_, i) => [
      `heading${i + 1}`,
      setBlockType(schema.nodes.heading, { level: i + 1 }),
    ]),
    ["bullet_list", capped(wrapInList(schema.nodes.bullet_list))],
    ["ordered_list", capped(wrapInList(schema.nodes.ordered_list))],
    ["strong", toggleMark(schema.marks.strong)],
    ["em", toggleMark(schema.marks.em)],
    ["underline", toggleMark(schema.marks.underline)],
    ["quote", wrapIn(schema.nodes.quote)],
    ...spec.calloutTypes.map((type) => [type, wrapIn(schema.nodes.callout, { type })]),
    ["table", insertTable(schema)],
    ["add_row", addRowAfter],
    ["undo", undo],
    ["redo", redo],
  ];
  const label = (name) =>
    name.startsWith("heading") ? labels.heading.replace("%(level)s", name.slice("heading".length)) : labels[name];
  for (const [name, command] of blocks) bar.append(button(label(name), name, run(command)));

  // A link: its address typed into the toolbar, never asked for in a dialog.
  const address = document.createElement("input");
  address.type = "text";
  address.placeholder = labels.link_address;
  address.hidden = true;
  address.dataset.field = "link";
  const apply = () => {
    const href = address.value.trim();
    if (!href || /[\s<>]/.test(href) || !spec.linkSchemes.test(href)) {
      report({ kind: "link_refused" });
      return;
    }
    toggleMark(schema.marks.link, { href })(view.state, view.dispatch, view);
    address.value = "";
    address.hidden = true;
    view.focus();
  };
  address.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      apply();
    }
  });
  bar.append(
    button(labels.link, "link", () => {
      address.hidden = !address.hidden;
      if (!address.hidden) address.focus();
    }),
    address,
  );
  return bar;
}

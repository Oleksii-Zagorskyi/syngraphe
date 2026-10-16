// The toolbar: headings, lists, bold, italic, underline, quotes, callouts, tables, images and links,
// and undo and redo. Buttons keep the selection through the click by refusing the mousedown's default.
import { setBlockType, toggleMark, wrapIn } from "prosemirror-commands";
import { redo, undo } from "prosemirror-history";
import { wrapInList } from "prosemirror-schema-list";
import { addRowAfter } from "prosemirror-tables";
import { insertPoint } from "prosemirror-transform";

import { spec } from "./spec.js";
import { ICONS } from "./icons.js";

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

// An icon where one is drawn, its word the tooltip and the accessible name (DL-0365); the word
// on the button where none is.
function button(label, name, run) {
  const element = document.createElement("button");
  element.type = "button";
  if (ICONS[name]) {
    element.innerHTML = ICONS[name];
    element.title = label;
    element.setAttribute("aria-label", label);
    element.className = "icon";
  } else {
    element.textContent = label;
  }
  element.dataset.command = name;
  element.addEventListener("mousedown", (event) => event.preventDefault());
  element.addEventListener("click", run);
  return element;
}

// The toolbar for `view`; `words` are the page's translated labels and notices, `report` shows one
// line under the editor; `images`, where the page takes uploads, adds the files it is given.
export function toolbar(view, schema, words, report, images = null) {
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

  // An image: a file chosen from the person's computer, uploaded and placed alone (DL-0232).
  if (images) {
    const chooser = document.createElement("input");
    chooser.type = "file";
    chooser.accept = "image/png,image/jpeg,image/gif";
    chooser.hidden = true;
    chooser.dataset.field = "image";
    chooser.addEventListener("change", () => {
      const files = [...chooser.files];
      chooser.value = "";
      if (files.length) images.add(files);
    });
    bar.append(button(labels.image, "image", () => chooser.click()), chooser);
  }

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

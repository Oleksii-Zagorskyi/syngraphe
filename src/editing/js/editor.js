// The editor's bundle: the whole-document editor the edit tab mounts, and the conformance check
// the test page runs.
import { baseKeymap, toggleMark } from "prosemirror-commands";
import { history, redo, undo } from "prosemirror-history";
import { inputRules, textblockTypeInputRule } from "prosemirror-inputrules";
import { keymap } from "prosemirror-keymap";
import { liftListItem, sinkListItem, splitListItem } from "prosemirror-schema-list";
import { EditorState, Plugin, TextSelection } from "prosemirror-state";
import { columnResizing, tableEditing } from "prosemirror-tables";
import { EditorView } from "prosemirror-view";

import { clauseNumbers, gutter } from "./gutter.js";
import { capturing } from "./capture.js";
import { convert } from "./convert.js";
import { makeParser, tokenMap, validate } from "./parser.js";
import { pasteHandling } from "./paste.js";
import { makeSchema } from "./schema.js";
import { serialize } from "./serializer.js";
import { sourceField } from "./source.js";
import { rawSpec, spec } from "./spec.js";
import { capped, toolbar } from "./toolbar.js";

import "./editor.css";

export const schema = makeSchema(spec);
export const parser = makeParser(schema);
export { rawSpec };

// No change may leave an image beside anything else in its paragraph (DL-0253).
const imagesAlone = new Plugin({
  filterTransaction(tr, state) {
    if (!tr.docChanged) return true;
    const start = state.doc.content.findDiffStart(tr.doc.content);
    if (start == null) return true;
    const end = state.doc.content.findDiffEnd(tr.doc.content);
    const to = Math.max(start, end ? end.b : tr.doc.content.size);
    let alone = true;
    tr.doc.nodesBetween(Math.max(0, start - 1), Math.min(tr.doc.content.size, to + 1), (node) => {
      if (node.type.name !== "paragraph") return true;
      let image = false;
      node.forEach((child) => {
        if (child.type.name === "image") image = true;
      });
      if (image && node.childCount > 1) alone = false;
      return false;
    });
    return alone;
  },
});

function plugins() {
  const { heading, list_item } = schema.nodes;
  return [
    history(),
    inputRules({ rules: [textblockTypeInputRule(/^(#{1,4})\s$/, heading, (m) => ({ level: m[1].length }))] }),
    keymap({
      "Mod-z": undo,
      "Shift-Mod-z": redo,
      "Mod-y": redo,
      "Mod-b": toggleMark(schema.marks.strong),
      "Mod-i": toggleMark(schema.marks.em),
      "Mod-u": toggleMark(schema.marks.underline),
      Enter: splitListItem(list_item),
      Tab: capped(sinkListItem(list_item)),
      "Shift-Tab": liftListItem(list_item),
    }),
    keymap(baseKeymap),
    columnResizing({ cellMinWidth: 60 }),
    tableEditing(),
    gutter(),
    imagesAlone,
  ];
}

function csrfToken(element) {
  const field = element.closest("form, section, body").querySelector("input[name=csrfmiddlewaretoken]");
  return field ? field.value : "";
}

async function post(url, element, body) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": csrfToken(element), "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = response.headers.get("Content-Type")?.includes("json") ? await response.json() : null;
  return { status: response.status, data, redirected: response.redirected };
}

function format(template, values) {
  return template.replace(/%\((\w+)\)s/g, (_, key) => values[key]);
}

// One line under the editor for what a paste, a switch or a control could not do.
function reporter(status, words, helpUrl) {
  const withHelp = (line) => {
    status.append(line + " ");
    const link = document.createElement("a");
    link.href = helpUrl;
    link.textContent = words.notices.help;
    status.append(link);
  };
  return (event) => {
    status.textContent = "";
    if (event.kind === "refused") {
      const names = event.codes.map((code) => words.constructs[code] || code).join(", ");
      withHelp(format(words.notices.refused, { constructs: names }));
    } else if (event.kind === "lines") {
      if (event.text) withHelp(format(words.notices.lines, { lines: event.text }));
    } else {
      status.textContent = words.notices[event.kind] || "";
    }
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

// The editor over one draft: the rich view and the source view, one shown at a time. A draft the
// validator refuses opens in the source view, with the refusal named and nothing discarded.
function editorFor(element, draft, words, report) {
  const surface = document.createElement("div");
  surface.className = "editor-surface";
  const bar = document.createElement("div");
  bar.className = "editor-controls";
  const source = sourceField({
    words,
    validate: (text) => validate(text, spec),
    convert: (text) => convert(text, spec, schema, tokenMap, (doc) => serialize(doc, { oneLine: true })),
    refusal: (text) => report({ kind: "lines", text }),
  });
  const editor = {
    view: null,
    draft,
    mode: "rich",
    // The source view's text only once it was changed: switching alone changes nothing stored.
    markdown: () =>
      editor.mode === "source" && !(editor.view && source.field.value === shown)
        ? source.field.value
        : serialize(editor.view.state.doc),
    // For a test or a person at the console: a selection by position, and a text loaded whole.
    select: (from, to = from) => {
      const view = editor.view;
      view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, from, to)));
    },
    replace: (markdown) => {
      const view = editor.view;
      view.dispatch(view.state.tr.replaceWith(0, view.state.doc.content.size, parser.parse(markdown).content));
    },
  };
  let shown = null;
  let tools = null;
  const toggle = button(words.labels.source, "source", () => (editor.mode === "rich" ? toSource() : toRich()));

  function show(mode) {
    editor.mode = mode;
    surface.hidden = mode !== "rich";
    source.field.hidden = mode !== "source";
    if (mode === "rich") source.offer.hidden = true;
    if (tools) tools.hidden = mode !== "rich";
    toggle.textContent = mode === "rich" ? words.labels.source : words.labels.rich;
  }

  function richView(doc) {
    editor.view = new EditorView(surface, {
      state: EditorState.create({ doc, plugins: plugins() }),
      ...pasteHandling(spec, report, (doc) => validate(serialize(doc), spec)),
      dispatchTransaction(tr) {
        editor.view.updateState(editor.view.state.apply(tr));
        if (tr.docChanged && editor.capture) editor.capture.changed();
      },
    });
    editor.view.dom.addEventListener("focusout", () => editor.capture && editor.capture.flush());
    tools = toolbar(editor.view, schema, words, report);
    bar.insertBefore(tools, toggle);
  }

  function toSource() {
    shown = serialize(editor.view.state.doc, { oneLine: true });
    source.field.value = shown;
    report({ kind: "lines", text: "" });
    show("source");
    source.field.focus();
  }

  function toRich() {
    const text = source.field.value;
    if (editor.view && text === shown) {
      show("rich");
      return true;
    }
    const refusals = validate(text, spec);
    if (refusals.length) {
      report({ kind: "lines", text: source.describe(refusals) });
      return false;
    }
    if (editor.view) editor.replace(text);
    else richView(parser.parse(text));
    report({ kind: "lines", text: "" });
    show("rich");
    editor.view.focus();
    return true;
  }

  bar.append(toggle);
  element.append(bar, surface, source.field, source.offer);
  source.field.addEventListener("input", () => editor.capture && editor.capture.changed());
  source.field.addEventListener("blur", () => editor.capture && editor.capture.flush());
  if (draft.verdict.state === "refused") {
    source.field.value = draft.body;
    show("source");
    report({ kind: "lines", text: source.describe(draft.verdict.refusals) });
  } else {
    richView(parser.parse(draft.body));
    show("rich");
  }
  editor.toSource = toSource;
  editor.toRich = toRich;
  editor.capture = capturing({
    element,
    editor,
    words,
    disable() {
      if (editor.view) editor.view.setProps({ editable: () => false });
      source.field.readOnly = true;
    },
  });
  // *Finish editing*: the last text captured and this editor closed, then the finishing screen;
  // offered only while no other editor is open on the draft. While any text is not captured the
  // editor stays, and the indicator says why.
  const finish = button(words.labels.finish, "finish", async () => {
    finish.disabled = true;
    if (await editor.capture.finish()) window.location.assign(element.dataset.finish);
    else finish.disabled = false;
  });
  element.addEventListener("editor-heartbeat", (event) => {
    const others = event.detail.others;
    finish.disabled = others > 0;
    finish.title = others > 0 ? words.notices.others : "";
  });
  bar.append(finish, editor.capture.indicator);
  return editor;
}

// Mount the editor on the edit tab's element: take the hold, load the draft, and edit it. A tab
// reached from another site takes nothing until the person asks (DL-0325).
export async function mount(element) {
  const words = JSON.parse(document.getElementById("editor-words").textContent);
  const status = element.parentElement.querySelector(".editor-status");
  const report = reporter(status, words, element.dataset.help);
  if (element.dataset.takeOnMount !== "true") {
    const start = button(words.labels.start, "start", () => {});
    element.append(start);
    await new Promise((resolve) => start.addEventListener("click", resolve, { once: true }));
    start.remove();
  }
  const taken = await post(element.dataset.take, element);
  if (taken.status === 409) {
    window.location.reload();
    return null;
  }
  if (taken.status !== 200) {
    report({ kind: "busy" });
    return null;
  }
  const loaded = await post(element.dataset.load, element);
  if (loaded.status !== 200 || !loaded.data) {
    report({ kind: loaded.redirected ? "signed_out" : "busy" });
    return null;
  }
  element.editor = editorFor(element, loaded.data, words, report);
  element.dispatchEvent(new CustomEvent("editor-ready", { bubbles: true }));
  return element.editor;
}

function throughEditor(text, element) {
  const view = new EditorView(element, { state: EditorState.create({ doc: parser.parse(text) }) });
  const stored = serialize(view.state.doc);
  view.destroy();
  return stored;
}

// Each case through the editor's side: the validator's verdict, and for a text it accepts, the
// text loaded into a real editor and serialised back; and whether that stored form is itself
// accepted and written back unchanged. The browser test compares the results with the cases.
export function conformance(cases, element) {
  return cases.map((c) => {
    const refusals = validate(c.input, spec);
    const result = { id: c.id, refusals, stored: null, fixed: null };
    if (!refusals.length) {
      result.stored = throughEditor(c.input, element);
      result.fixed = !validate(result.stored, spec).length && throughEditor(result.stored, element) === result.stored;
    }
    return result;
  });
}

// Each text's labels in document order, headings and clauses, by the gutter's rule: the browser
// test holds them to the shared numbering cases and to the reading view's derivation.
export function numbering(texts) {
  return texts.map((text) => clauseNumbers(parser.parse(text)).map(({ label }) => label));
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    const element = document.getElementById("editor");
    if (element && element.dataset.load) mount(element);
  });
}

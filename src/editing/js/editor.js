// The editor's bundle: the whole document's editor on the draft's page, open on arrival — and the
// conformance check the test page runs.
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
import { addImages } from "./upload.js";

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

// One line under the editor for what a paste, a switch or a control could not do, or what the
// source view notes as the person types.
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
    } else if (event.kind === "joined") {
      const said = format(words.notices.joined, { first: event.first, last: event.last });
      status.textContent = event.more ? `${said} ${format(words.notices.joined_more, { count: event.more })}` : said;
    } else if (event.kind === "text") {
      status.textContent = event.text;
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

// The editor over the whole draft (DL-0517): the rich view and the source view, one shown at a
// time. A text the validator refuses opens in the source view, with
// the refusal named and nothing discarded.
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
    notice: report,
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
    if (tools && mode !== "rich") for (const panel of tools.panels || []) panel.hidden = true;
    toggle.textContent = mode === "rich" ? words.labels.source : words.labels.rich;
  }

  // Images are added only where the page takes uploads: the edit tab, not a test page. Each batch
  // in flight is kept, so closing the editor waits for it to be placed and captured.
  editor.uploads = new Set();
  const images = element.dataset.imageUpload
    ? {
        add: (files, pos = null) => {
          const job = addImages(files, { schema, element, editor, report, pos });
          editor.uploads.add(job);
          job.finally(() => editor.uploads.delete(job));
          return job;
        },
      }
    : null;

  // Marking where the page declares entities: the edit tab, its route on the element.
  const marking = element.dataset.entities
    ? { element, entities: draft.entities || [], editor: draft.editor }
    : null;

  function richView(doc) {
    editor.view = new EditorView(surface, {
      state: EditorState.create({ doc, plugins: plugins() }),
      ...pasteHandling(spec, report, (doc) => validate(serialize(doc), spec), images),
      dispatchTransaction(tr) {
        editor.view.updateState(editor.view.state.apply(tr));
        if (tr.docChanged && editor.capture) editor.capture.changed();
      },
    });
    editor.view.dom.addEventListener("focusout", () => editor.capture && editor.capture.flush());
    tools = toolbar(editor.view, schema, words, report, images, marking);
    bar.insertBefore(tools, toggle);
    for (const panel of tools.panels || []) bar.insertBefore(panel, toggle);
  }

  function toSource() {
    source.quiet();
    source.hold(false);
    shown = serialize(editor.view.state.doc, { oneLine: true });
    source.field.value = shown;
    report({ kind: "lines", text: "" });
    show("source");
    source.field.focus();
  }

  function toRich() {
    source.quiet();
    const text = source.field.value;
    if (editor.view && text === shown) {
      show("rich");
      return true;
    }
    const refusals = validate(text, spec);
    if (refusals.length) {
      source.hold(true);
      report({ kind: "lines", text: source.describe(refusals) });
      return false;
    }
    source.hold(false);
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
    source.hold(true);
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
  bar.append(finish, editor.capture.indicator, editor.capture.prompt);
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
  return offer(element, words, report);
}

// The draft's page as it opens (DL-0517): the whole document's editor over the draft at once —
// there is no section editor. The page's acts stand in the frame above it; each that changes the
// draft waits until this editor has captured and closed.
async function offer(element, words, report) {
  const view = element.parentElement.querySelector("[data-draft-view]");
  // The editor's opening, awaited by every act that must find it closed: an act pressed while the
  // load is in flight waits for the editor it would otherwise leave open.
  let opening = Promise.resolve(null);

  async function openWhole() {
    const loaded = await post(element.dataset.load, element, { range: "whole" });
    // The hold was released since the page was drawn: drawn again, it says how and offers the draft.
    if (loaded.status === 404) {
      redraw();
      return null;
    }
    if (loaded.status !== 200 || !loaded.data) {
      report({ kind: loaded.redirected ? "signed_out" : "busy" });
      return null;
    }
    if (view) view.hidden = true;
    element.editor = editorFor(element, loaded.data, words, report);
    switchFor(element.editor);
    element.dispatchEvent(new CustomEvent("editor-ready", { bubbles: true }));
    return element.editor;
  }

  // The page is drawn again only once the editor holds no text of its own: captured and closed
  // first, and not stopped with text still to carry over (ADR-0006).
  async function redraw() {
    await opening.catch(() => null);
    const editor = element.editor;
    if (editor && editor.capture.stopped) {
      report({ kind: "stopped_open" });
      return false;
    }
    if (editor && !(await editor.capture.finish())) {
      report({ kind: "failed" });
      return false;
    }
    window.location.reload();
    return true;
  }

  // *Back to the edit tab* from a stopped editor: drawn again only when nothing would be lost.
  element.parentElement.addEventListener("click", (event) => {
    const reopen = event.target.closest("[data-command=reopen]");
    if (!reopen) return;
    event.preventDefault();
    if (element.editor && element.editor.capture.stopped) element.editor = null;
    redraw();
  });

  // The editor captured and closed before the page posts what changes the draft: a stopped editor
  // still holds text to carry over, and one that cannot close holds text not yet captured — the
  // page says which, and posts nothing.
  async function closedEditors() {
    await opening.catch(() => null);
    const editor = element.editor;
    if (!editor) return true;
    if (editor.capture.stopped) {
      report({ kind: "stopped_open" });
      return false;
    }
    if (!(await editor.capture.finish().catch(() => false))) {
      report({ kind: "failed" });
      return false;
    }
    return true;
  }

  // *My edits*, a switch in the editor's own row (DL-0518): the draft's changes in place of the
  // editor, fetched from its address; dimmed and disabled, its reason as a tooltip, until the
  // first edit.
  function switchFor(editor) {
    const label = document.createElement("label");
    label.className = "my-edits";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.dataset.command = "my-edits";
    label.append(box, " ", words.labels.my_edits);
    const shown = document.createElement("div");
    shown.className = "my-edits-shown";
    shown.hidden = true;
    const surface = [...element.children].filter((child) => !child.classList.contains("editor-controls"));
    const enable = (edited) => {
      box.disabled = !edited;
      label.title = edited ? "" : words.notices.after_first_edit;
      label.classList.toggle("disabled", !edited);
    };
    // The page says whether the draft held edits when it was drawn; a capture that writes text
    // sets the editor's own flag, kept until the page is drawn again (DL-0518).
    let edited = element.dataset.edited === "true";
    const opened = editor.markdown();
    enable(edited);
    // A capture's own word, or a text that differs from the one the editor opened on — a retry
    // whose first answer was lost writes nothing new, yet the draft is edited.
    element.addEventListener("draft-edited", (event) => {
      edited = edited || event.detail.edited || editor.markdown() !== opened;
      enable(edited);
    });
    box.addEventListener("change", async () => {
      if (!box.checked) {
        shown.hidden = true;
        surface.forEach((node) => { node.hidden = false; });
        return;
      }
      box.disabled = true;
      // What was typed is captured first, so the changes shown are the draft as it stands.
      if (editor.capture.flush) await editor.capture.flush();
      const response = await fetch(`${element.dataset.myEdits}?fragment=1`, { credentials: "same-origin" });
      box.disabled = false;
      // A session that ended answers with the sign-in page: never drawn in the editor's place.
      if (response.redirected || !response.ok) {
        box.checked = false;
        report({ kind: response.redirected ? "signed_out" : "busy" });
        return;
      }
      shown.innerHTML = await response.text();
      surface.forEach((node) => { node.hidden = true; });
      shown.hidden = false;
    });
    element.querySelector(".editor-controls").append(label);
    element.append(shown);
  }

  // *Finish editing* and the discard, in the frame above the editor: each waits for the editor.
  document.querySelectorAll("[data-command=finish]").forEach((link) => {
    if (link.tagName !== "A") return;
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      if (await closedEditors()) window.location.assign(link.href);
    });
  });
  document.querySelectorAll("form[data-discard]").forEach((form) => {
    // Drawn hidden until the hold is taken: there is nothing to discard before.
    const box = form.closest("details");
    if (box) box.hidden = false;
    let sending = false;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (sending) return;
      sending = true;
      if (!(await closedEditors())) {
        sending = false;
        return;
      }
      form.submit();
    });
  });
  // The parts panel: drawn hidden until the hold is taken, and each of its forms posted only once
  // the editor has captured and closed, so the page drawn again holds the typed text.
  const parts = document.querySelector("[data-parts-panel]");
  if (parts) {
    parts.hidden = false;
    let posting = false;
    parts.querySelectorAll("form").forEach((form) => form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (posting) return;
      posting = true;
      if (!(await closedEditors())) {
        posting = false;
        return;
      }
      form.submit();
    }));
  }
  element.offered = { openWhole };
  element.dispatchEvent(new CustomEvent("editor-offered", { bubbles: true }));
  opening = openWhole();
  return opening;
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

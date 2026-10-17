// The editor's bundle: the edit tab's editors — the whole document's, or one section's, opened from
// the draft drawn as text — and the conformance check the test page runs.
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

// The editor over one range of the draft — the whole of it, or a section: the rich view and the
// source view, one shown at a time. A text the validator refuses opens in the source view, with
// the refusal named and nothing discarded.
function editorFor(element, draft, words, report, { onClose = null } = {}) {
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
  if (onClose) {
    // A section editor closes itself: its text captured and the editor closed, then the tab
    // drawn again, where a heading typed into it has become a section of its own (ADR-0006).
    const done = button(words.labels.close_section, "close-section", async () => {
      done.disabled = true;
      if (await editor.capture.finish()) onClose(editor);
      else done.disabled = false;
    });
    bar.append(done, editor.capture.indicator, editor.capture.prompt);
    return editor;
  }
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

const HEADING = /^H[1-6]$/;

// The drawn elements a section's heading leads: the heading and every element after it up to the
// next heading of the same or a shallower depth — the lines the server's span holds.
function sectionNodes(heading) {
  const level = +heading.tagName[1];
  const nodes = [heading];
  for (let node = heading.nextElementSibling; node; node = node.nextElementSibling) {
    if (HEADING.test(node.tagName) && +node.tagName[1] <= level) break;
    nodes.push(node);
  }
  return nodes;
}

// The tab as it opens (ADR-0006): the draft drawn as the View tab draws a version, *edit* beside
// each heading and *edit whole document* above it; no editor until one is chosen. Section editors
// may be open several at once; the whole one only while none is, and finishing only once every
// one is closed.
function offer(element, words, report) {
  const view = element.parentElement.querySelector("[data-draft-view]");
  const open = new Set();
  const actions = document.createElement("div");
  actions.className = "edit-actions";
  const whole = button(words.labels.edit_whole, "edit-whole", () => openWhole());
  const finishAll = button(words.labels.finish, "finish-all", () => window.location.assign(element.dataset.finish));
  actions.append(whole, finishAll);
  element.before(actions);

  function update() {
    const busy = open.size > 0;
    whole.disabled = busy;
    whole.title = busy ? words.notices.sections_open : "";
    finishAll.disabled = busy;
    finishAll.title = busy ? words.notices.close_sections : "";
  }

  async function openWhole() {
    whole.disabled = true;
    const loaded = await post(element.dataset.load, element, { range: "whole" });
    if (loaded.status === 409) {
      report({ kind: "sections_open" });
      update();
      return null;
    }
    // The hold was released since the tab was drawn: drawn again, it says how and offers the draft.
    if (loaded.status === 404) {
      redraw();
      return null;
    }
    if (loaded.status !== 200 || !loaded.data) {
      report({ kind: loaded.redirected ? "signed_out" : "busy" });
      update();
      return null;
    }
    actions.hidden = true;
    if (view) view.hidden = true;
    element.editor = editorFor(element, loaded.data, words, report);
    element.dispatchEvent(new CustomEvent("editor-ready", { bubbles: true }));
    return element.editor;
  }

  // The tab is drawn again only once nothing on it holds text of its own: every other editor
  // captured and closed first, and none stopped with text still to carry over (ADR-0006).
  async function redraw() {
    const editors = [...open, element.editor].filter(Boolean);
    if (editors.some((editor) => editor.capture.stopped)) {
      report({ kind: "stopped_open" });
      return false;
    }
    const finished = await Promise.all(editors.map((editor) => editor.capture.finish()));
    if (finished.some((done) => !done)) {
      report({ kind: "failed" });
      return false;
    }
    window.location.reload();
    return true;
  }

  // A section editor closed: the tab is drawn again when it was the last; otherwise its place
  // says so, and the others carry on.
  function closed(editor, container) {
    if (!open.delete(editor)) return;
    update();
    if (open.size === 0) {
      redraw();
      return;
    }
    const note = document.createElement("p");
    note.className = "muted section-closed";
    note.textContent = words.notices.section_closed;
    container.replaceChildren(note);
  }

  // After a capture added or removed a heading the page's ordinals no longer match the draft's:
  // no other section opens until the tab is drawn again.
  element.parentElement.addEventListener("sections-changed", () => {
    view?.querySelectorAll("button[data-command=edit-section]").forEach((edit) => {
      edit.disabled = true;
      edit.title = words.notices.sections_changed;
    });
  });
  // *Back to the edit tab* from a stopped editor: drawn again only when nothing else would be lost.
  element.parentElement.addEventListener("click", (event) => {
    const reopen = event.target.closest("[data-command=reopen]");
    if (!reopen) return;
    event.preventDefault();
    const stoppedHere = reopen.closest(".section-editor, #editor")?.editor;
    if (stoppedHere) open.delete(stoppedHere);
    if (stoppedHere && element.editor === stoppedHere) element.editor = null;
    redraw();
  });

  async function openSection(ordinal, heading, trigger) {
    trigger.disabled = true;
    const loaded = await post(element.dataset.load, element, { range: `section:${ordinal}` });
    if (loaded.status === 404) {
      // The section is gone, or the hold was released: the tab, drawn again, says which.
      trigger.disabled = false;
      redraw();
      return null;
    }
    if (loaded.status !== 200 || !loaded.data) {
      const refused = loaded.data || {};
      const kind = refused.overlaps
        ? "overlaps"
        : refused.too_many
          ? "too_many"
          : refused.whole_open
            ? "whole_open"
            : loaded.redirected
                ? "signed_out"
                : "busy";
      report({ kind });
      trigger.disabled = false;
      return null;
    }
    const nodes = sectionNodes(heading);
    const container = document.createElement("div");
    container.className = "section-editor";
    Object.assign(container.dataset, element.dataset, { ordinal: String(ordinal) });
    heading.before(container);
    nodes.forEach((node) => {
      node.hidden = true;
    });
    const editor = editorFor(container, loaded.data, words, report, {
      onClose: () => closed(editor, container),
    });
    container.addEventListener("editor-closed", () => closed(editor, container));
    container.editor = editor;
    open.add(editor);
    update();
    container.dispatchEvent(new CustomEvent("editor-ready", { bubbles: true }));
    return editor;
  }

  if (view) {
    const headings = [...view.children].filter((node) => HEADING.test(node.tagName));
    headings.forEach((heading, ordinal) => {
      const edit = button(words.labels.edit_section, "edit-section", () => openSection(ordinal, heading, edit));
      edit.dataset.ordinal = String(ordinal);
      edit.className = "section-edit";
      heading.append(" ", edit);
    });
  }
  update();
  // *Discard my edits* is refused while an editor is open: the page closes its own first.
  const discard = element.parentElement.querySelector("form[data-discard]");
  if (discard) {
    // Drawn hidden until the hold is taken: there is nothing to discard before.
    discard.closest("details").hidden = false;
    let sending = false;
    discard.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (sending) return;
      sending = true;
      const editors = [...open, element.editor].filter(Boolean);
      const closed = await Promise.all(editors.map((editor) => editor.capture.finish().catch(() => false)));
      // An editor that could not close still holds text: the page says why, and posts nothing.
      if (closed.some((done) => !done)) {
        report({ kind: "failed" });
        sending = false;
        return;
      }
      discard.submit();
    });
  }
  element.offered = { openWhole, openSection: (ordinal) => {
    const edit = view && view.querySelector(`[data-command=edit-section][data-ordinal="${ordinal}"]`);
    return edit ? openSection(ordinal, edit.closest("h1,h2,h3,h4,h5,h6"), edit) : null;
  } };
  element.dispatchEvent(new CustomEvent("editor-offered", { bubbles: true }));
  return null;
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

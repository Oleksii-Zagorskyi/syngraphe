// *Mark*'s picker (DL-0073): the kind, the draft's own declarations of that kind, and *Declare a new
// one*. Picking or declaring wraps the selected words in the entity's span; words already marked
// take the new one, since an entity span stands inside no other. Only the draft's own declarations
// are offered: another document's entities never reach the picker.
import { csrfToken } from "./capture.js";

const KINDS = ["role", "action", "term"];

// One list per page, by the route that declares: every editor the page opens offers what any of
// them declared, and an open picker shows it as it changes.
const shared = new Map();
const redraws = new Map();

// A newer answer for the page's list: `load` and declaring answer it whole, by one rule, so the
// newer replaces it — a span deleted since takes its entity with it.
function share(url, entities) {
  shared.set(url, entities);
  for (const redraw of redraws.get(url) || []) redraw();
}

// Whether the range holds text the mark can take; an image alone holds none.
function holdsText(view, from, to) {
  let found = false;
  view.state.doc.nodesBetween(from, to, (node) => {
    if (node.isText) found = true;
    return !found;
  });
  return found;
}

// The keys of the entities the editor's own text marks, captured or not yet: a new declaration
// takes none of them.
function keysShown(view) {
  const keys = new Set();
  view.state.doc.descendants((node) => {
    for (const mark of node.marks) if (mark.type.name === "entity" && mark.attrs.id) keys.add(mark.attrs.id);
  });
  return [...keys];
}

// The text of `from`–`to` wrapped in the entity; an image stands alone and carries no mark.
function wrap(view, schema, kind, key, from = view.state.selection.from, to = view.state.selection.to) {
  const mark = schema.marks.entity.create({ kind, id: key });
  const tr = view.state.tr;
  view.state.doc.nodesBetween(from, to, (node, pos) => {
    if (node.isText) tr.addMark(Math.max(from, pos), Math.min(to, pos + node.nodeSize), mark);
  });
  view.dispatch(tr);
  view.focus();
}

async function declared(marking, kind, label, taken) {
  const form = new FormData();
  form.append("kind", kind);
  form.append("label", label);
  form.append("taken", taken.join(" "));
  // The editor declaring, so a hold ended under it is answered as ended.
  form.append("editor", marking.editor || "");
  let response;
  try {
    response = await fetch(marking.element.dataset.entities, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(marking.element) },
      body: form,
    });
  } catch {
    return { busy: true };
  }
  const data = response.headers.get("Content-Type")?.includes("json") ? await response.json() : null;
  if (response.status === 200 && data && data.key) return data;
  if (data && data.refused) return { refused: data.refused };
  if (data && data.closed) return { closed: true };
  return { busy: true };
}

// The picker's panel and what opens it: `{ panel, toggle }`. `marking` holds the page's element,
// whose `data-entities` names the route, and the draft's declarations as `load` answered them.
export function picker({ view, schema, labels, report, marking }) {
  const panel = document.createElement("span");
  panel.className = "entity-picker";
  panel.hidden = true;
  const url = marking.element.dataset.entities;

  const kind = document.createElement("select");
  kind.dataset.field = "mark-kind";
  kind.setAttribute("aria-label", labels.mark_kind);
  for (const name of KINDS) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = labels[`mark_${name}`];
    kind.append(option);
  }
  const list = document.createElement("span");
  list.className = "entity-list";
  const label = document.createElement("input");
  label.type = "text";
  label.dataset.field = "mark-label";
  label.placeholder = labels.mark_label;
  label.setAttribute("aria-label", labels.mark_declare);
  const declaringWords = document.createElement("span");
  declaringWords.textContent = labels.mark_declare;
  const declare = document.createElement("button");
  declare.type = "button";
  declare.dataset.field = "mark-declare";
  declare.textContent = labels.declare;
  declare.addEventListener("mousedown", (event) => event.preventDefault());

  const selected = () => {
    const { from, to } = view.state.selection;
    if (!holdsText(view, from, to)) {
      report({ kind: "mark_select" });
      return false;
    }
    return true;
  };
  const close = () => {
    panel.hidden = true;
    label.value = "";
  };

  function draw() {
    list.replaceChildren();
    for (const entity of (shared.get(url) || []).filter((e) => e.kind === kind.value)) {
      const choice = document.createElement("button");
      choice.type = "button";
      choice.dataset.entity = entity.key;
      choice.textContent = entity.label;
      choice.addEventListener("mousedown", (event) => event.preventDefault());
      choice.addEventListener("click", () => {
        if (!selected()) return;
        wrap(view, schema, entity.kind, entity.key);
        close();
      });
      list.append(choice);
    }
  }

  async function add() {
    const words = label.value.trim();
    if (!selected() || !words) return;
    // What is declared and where it goes are fixed now: the request may wait for the lock.
    const chosen = kind.value;
    const { from, to } = view.state.selection;
    const before = view.state.doc;
    declare.disabled = kind.disabled = true;
    const answer = await declared(marking, chosen, words, keysShown(view));
    declare.disabled = kind.disabled = false;
    if (answer.refused) {
      report({ kind: "text", text: answer.refused });
      return;
    }
    if (answer.closed) {
      report({ kind: "released" });
      return;
    }
    if (answer.busy) {
      report({ kind: "busy" });
      return;
    }
    if (view.state.doc !== before) {
      // Typed meanwhile: the words may have moved. The declaration stands, offered in the list.
      report({ kind: "mark_moved" });
      kind.value = chosen;
      share(url, answer.entities);
      return;
    }
    share(url, answer.entities);
    wrap(view, schema, chosen, answer.key, from, to);
    close();
  }

  kind.addEventListener("change", draw);
  declare.addEventListener("click", add);
  label.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      add();
    }
  });
  const declaring = document.createElement("span");
  declaring.className = "entity-declare";
  declaring.append(declaringWords, label, declare);
  panel.append(kind, list, declaring);

  if (!redraws.has(url)) redraws.set(url, new Set());
  redraws.get(url).add(() => {
    if (!panel.hidden) draw();
  });
  share(url, marking.entities);

  const toggle = () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) draw();
  };
  return { panel, toggle };
}

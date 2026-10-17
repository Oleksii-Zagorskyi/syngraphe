// An image added to the draft (DL-0232): the file posted to the edit tab's upload address, checked
// and staged by the server; then placed as a paragraph of its own after the block holding the
// cursor — after the table when the cursor is in one — never inside a sentence or a cell.
import { TextSelection } from "prosemirror-state";
import { insertPoint } from "prosemirror-transform";

import { csrfToken } from "./capture.js";

// `{src, alt}` once the server staged it; `{refused}` with the server's words; `{closed}` once the
// hold has ended; `{busy}` while the document is being committed; `{failed}` for anything else.
export async function upload(file, { element, editor }) {
  const form = new FormData();
  form.append("file", file, file.name || "image");
  form.append("editor", editor.draft.editor || "");
  let response;
  try {
    response = await fetch(element.dataset.imageUpload, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(element) },
      body: form,
    });
  } catch {
    return { failed: true };
  }
  const data = response.headers.get("Content-Type")?.includes("json") ? await response.json() : null;
  if (response.status === 200 && data && data.src) return { src: data.src, alt: data.alt || "" };
  if (data && data.refused) return { refused: data.refused };
  if (data && data.closed) return { closed: true, released: data.released };
  if (response.status === 503) return { busy: true };
  return { failed: true };
}

// Where an image paragraph goes for a position: after the table holding it, else after the
// innermost block that holds text.
function after($pos) {
  for (let depth = $pos.depth; depth > 0; depth--) {
    if ($pos.node(depth).type.name === "table") return $pos.after(depth);
  }
  for (let depth = $pos.depth; depth > 0; depth--) {
    if ($pos.node(depth).isTextblock) return $pos.after(depth);
  }
  return $pos.depth ? $pos.after(1) : $pos.pos;
}

// Place `images` together, in their order, each in a paragraph of its own, after the block
// holding the cursor: one transaction, so nothing typed meanwhile comes between them.
export function placeAll(view, schema, images) {
  if (!images.length) return;
  const { state } = view;
  const paragraphs = images.map((image) => schema.nodes.paragraph.create(null, schema.nodes.image.create(image)));
  const target = after(state.selection.$from);
  let at = insertPoint(state.doc, target, schema.nodes.paragraph) ?? state.doc.content.size;
  const tr = state.tr;
  for (const paragraph of paragraphs) {
    tr.insert(at, paragraph);
    at += paragraph.nodeSize;
  }
  view.dispatch(tr.scrollIntoView());
}

// Upload each file in turn, then place the ones the server staged together, in the editor's view
// as it stands when the last answer arrives; a drop's position becomes the cursor before the first
// upload. `report` says what happened to each.
export async function addImages(files, { schema, element, editor, report, pos = null }) {
  if (pos != null && editor.view) {
    const view = editor.view;
    const $pos = view.state.doc.resolve(Math.min(pos, view.state.doc.content.size));
    view.dispatch(view.state.tr.setSelection(TextSelection.near($pos)));
  }
  const staged = [];
  let failed = null;
  let released = false;
  for (const file of files) {
    try {
      report({ kind: "uploading" });
      const answer = await upload(file, { element, editor });
      if (answer.src) staged.push({ src: answer.src, alt: answer.alt });
      else if (answer.refused) failed = { kind: "text", text: answer.refused };
      else if (answer.closed) {
        released = true;
        break;
      } else failed = { kind: answer.busy ? "busy" : "image_failed" };
    } catch {
      failed = { kind: "image_failed" };
    }
  }
  if (staged.length) {
    if (editor.mode === "rich" && editor.view) {
      try {
        placeAll(editor.view, schema, staged);
      } catch {
        failed = { kind: "image_failed" };
      }
    } else {
      failed = { kind: "image_failed" };
    }
  }
  report(failed || { kind: "clear" });
  // The hold has ended: the editor says so as a capture would, and keeps its text.
  if (released) editor.capture?.released();
}

// A `data:` image's bytes as a file, its type read from the address.
export function dataFile(address, index) {
  const match = /^data:(image\/(?:png|jpeg|gif));base64,([A-Za-z0-9+/=\s]*)$/.exec(address);
  if (!match) return null;
  let decoded;
  try {
    decoded = atob(match[2].replace(/\s/g, ""));
  } catch {
    // Not base64 after all: no image the paste carries, and said as one that is only an address.
    return null;
  }
  const bytes = Uint8Array.from(decoded, (c) => c.charCodeAt(0));
  const ext = { "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif" }[match[1]];
  return new File([bytes], `pasted-${index + 1}.${ext}`, { type: match[1] });
}

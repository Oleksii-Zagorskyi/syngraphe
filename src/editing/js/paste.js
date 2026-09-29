// What a paste or a drop into the formatted view may bring (DL-0171, DL-0232). HTML carrying a
// construct outside the whitelist is refused whole, the construct named; so is anything whose
// insertion would leave a text the validator refuses, however the HTML smuggled it in. An image is
// left out with a one-line notice: the editor has no image upload. Plain text is literal text;
// Markdown is read only in the source view.
import { dropPoint } from "prosemirror-transform";

// More cells than this in one paste is refused before the editor lays the table out.
const CELLS_MOST = 2000;

// The constructs a pasted HTML fragment carries that the whitelist refuses, each by its code.
function refused(root, spec) {
  const found = [];
  const add = (code) => {
    if (!found.includes(code)) found.push(code);
  };
  if (root.querySelector("table table")) add("table-nested");
  const cells = [...root.querySelectorAll("td, th")];
  if (cells.length > CELLS_MOST) add("too-large");
  const span = (cell, name) => (cell.hasAttribute(name) ? Number(cell.getAttribute(name)) : 1);
  if (cells.some((cell) => span(cell, "colspan") !== 1 || span(cell, "rowspan") !== 1)) add("table-merged");
  if (root.querySelector("li table, blockquote table")) add("table-nested");
  if (root.querySelector("blockquote blockquote, li blockquote")) add("nested-quote");
  for (let level = spec.headingMaxDepth + 1; level <= 6; level++) {
    if (root.querySelector(`h${level}`)) add("heading-depth");
  }
  if (root.querySelector("pre")) add("code");
  if (root.querySelector("script, iframe, object, embed, form, style")) add("html");
  if (root.querySelector("hr")) add("hr");
  return found;
}

// The refusal codes `tr` would add to the document, by the validator's reading of its text.
function added(state, tr, check) {
  const before = new Set(check(state.doc).map((r) => r.code));
  return [...new Set(check(tr.doc).map((r) => r.code))].filter((code) => !before.has(code));
}

// `handlePaste`, `handleDrop` and `transformPastedHTML` for the editor's view; `check` validates a
// document, `report` shows one line.
export function pasteHandling(spec, report, check) {
  function screen(html) {
    if (!html) return { codes: [], images: false };
    const doc = new DOMParser().parseFromString(html, "text/html");
    return { codes: refused(doc.body, spec), images: doc.body.querySelector("img") !== null };
  }
  return {
    transformPastedHTML(html) {
      const doc = new DOMParser().parseFromString(html, "text/html");
      doc.querySelectorAll("img, span.image").forEach((image) => image.remove());
      return doc.body.innerHTML;
    },
    handlePaste(view, event, slice) {
      const data = event.clipboardData;
      if (!data) return false;
      const html = data.getData("text/html");
      const { codes, images } = screen(html);
      if (codes.length) {
        report({ kind: "refused", codes });
        return true;
      }
      if (!html && [...data.files].some((file) => file.type.startsWith("image/"))) {
        report({ kind: "images" });
        return true;
      }
      const introduced = added(view.state, view.state.tr.replaceSelection(slice), check);
      if (introduced.length) {
        report({ kind: "refused", codes: introduced });
        return true;
      }
      // After ProseMirror has inserted the text, say whether images were left out of it.
      setTimeout(() => {
        if (images) report({ kind: "images" });
      });
      return false;
    },
    handleDrop(view, event, slice, moved) {
      if (moved) return false;
      const data = event.dataTransfer;
      const { codes } = screen(data ? data.getData("text/html") : "");
      if (codes.length) {
        report({ kind: "refused", codes });
        return true;
      }
      const target = view.posAtCoords({ left: event.clientX, top: event.clientY });
      if (!target) return false;
      const at = dropPoint(view.state.doc, target.pos, slice) ?? target.pos;
      const introduced = added(view.state, view.state.tr.replaceRange(at, at, slice), check);
      if (introduced.length) {
        report({ kind: "refused", codes: introduced });
        return true;
      }
      return false;
    },
  };
}

// What a paste or a drop into the formatted view may bring (DL-0171, DL-0232). HTML carrying a
// construct outside the whitelist is refused whole, the construct named; so is anything whose
// insertion would leave a text the validator refuses, however the HTML smuggled it in. An image
// whose bytes the transfer carries — a file, or a `data:` address in the HTML — is uploaded and
// placed as a paragraph of its own; one that is only a web address is left out with a one-line
// notice; the rest of the paste or the drop goes in. An image node as the editor draws it, wherever
// it was copied from, is kept and placed alone; one this document does not hold is refused at
// finishing. Plain text is literal text; Markdown is read only in the source view. The invisible
// format characters a paste carries are left out of it, the two joiners kept (DL-0487).
import { Fragment, Slice } from "prosemirror-model";
import { dropPoint } from "prosemirror-transform";

import { withoutInvisibles } from "./rules.js";
import { dataFile, placeAll } from "./upload.js";

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

// The editor's own image as it draws it: a `span.image` naming its stored path.
const OWN_IMAGE = "span.image[data-src]";

// The images a transfer carries: its image files, the `data:` images of its HTML as files, and
// whether the HTML holds an image that is only a web address.
function carried(data, html) {
  const files = data ? [...data.files].filter((file) => file.type.startsWith("image/")) : [];
  let remote = false;
  if (html) {
    // A copied image carries itself twice — as a file and as a `data:` address — and is one image.
    const hasFiles = files.length > 0;
    const doc = new DOMParser().parseFromString(html, "text/html");
    doc.querySelectorAll("img").forEach((image, index) => {
      if (image.closest(OWN_IMAGE)) return;
      const file = dataFile(image.getAttribute("src") || "", index);
      if (!file) remote = true;
      else if (!hasFiles) files.push(file);
    });
  }
  return { files, remote };
}

// Whether a slice brings nothing to read: no text and no image — what is left of a paste of
// images once they are taken out of it.
function bringsNothing(slice) {
  let image = false;
  slice.content.descendants((node) => {
    if (node.type.name === "image") image = true;
  });
  return !image && !slice.content.textBetween(0, slice.content.size, " ", " ").trim();
}

// The image nodes a slice holds, and the slice without them.
function imagesOf(slice) {
  const found = [];
  const strip = (fragment) => {
    const kept = [];
    fragment.forEach((node) => {
      if (node.type.name === "image") found.push(node.attrs);
      else kept.push(node.isLeaf ? node : node.copy(strip(node.content)));
    });
    return Fragment.fromArray(kept);
  };
  const rest = new Slice(strip(slice.content), slice.openStart, slice.openEnd);
  return { found, rest };
}

// A fragment's text without the invisible format characters it carries; a text node left empty
// is dropped.
function visible(fragment, schema) {
  const kept = [];
  fragment.forEach((node) => {
    if (!node.isText) kept.push(node.isLeaf ? node : node.copy(visible(node.content, schema)));
    else {
      const text = withoutInvisibles(node.text);
      if (text) kept.push(text === node.text ? node : schema.text(text, node.marks));
    }
  });
  return Fragment.fromArray(kept);
}

// `handlePaste`, `handleDrop`, `transformPastedHTML` and `transformPasted` for the editor's view; `check` validates a
// document, `report` shows one line, `images` uploads and places files where the page takes them.
export function pasteHandling(spec, report, check, images = null) {
  function screen(html) {
    if (!html) return { codes: [] };
    const doc = new DOMParser().parseFromString(html, "text/html");
    return { codes: refused(doc.body, spec) };
  }
  // The pasted files uploaded once ProseMirror has placed the text; a web address noted unless the
  // same paste carried the bytes.
  function afterwards(files, remote, pos = null) {
    setTimeout(() => {
      if (files.length && images) images.add(files, pos);
      else if (files.length || remote) report({ kind: "images" });
    });
  }
  return {
    transformPastedHTML(html) {
      const doc = new DOMParser().parseFromString(html, "text/html");
      // Every image is left out of the text but the editor's own, which keeps its stored path.
      doc.querySelectorAll("img").forEach((image) => {
        if (!image.closest(OWN_IMAGE)) image.remove();
      });
      return doc.body.innerHTML;
    },
    transformPasted(slice, view) {
      // Text dragged within the document is moved, not pasted: its stored bytes go with it.
      if (view.dragging) return slice;
      return new Slice(visible(slice.content, view.state.schema), slice.openStart, slice.openEnd);
    },
    handlePaste(view, event, slice) {
      const data = event.clipboardData;
      if (!data) return false;
      const html = data.getData("text/html");
      const { codes } = screen(html);
      if (codes.length) {
        report({ kind: "refused", codes });
        return true;
      }
      const { files, remote } = carried(data, html);
      if (bringsNothing(slice)) {
        afterwards(files, remote);
        return true;
      }
      // The editor's own images, copied within it, are kept — each placed alone after the block
      // the rest of the paste lands in, never inside a sentence.
      const { found, rest } = imagesOf(slice);
      if (found.length) {
        const text = rest.content.textBetween(0, rest.content.size, " ", " ").trim();
        if (text) {
          const introduced = added(view.state, view.state.tr.replaceSelection(rest), check);
          if (introduced.length) {
            report({ kind: "refused", codes: introduced });
            return true;
          }
          view.dispatch(view.state.tr.replaceSelection(rest));
        }
        placeAll(view, view.state.schema, found);
        afterwards(files, remote && !files.length);
        return true;
      }
      const introduced = added(view.state, view.state.tr.replaceSelection(slice), check);
      if (introduced.length) {
        report({ kind: "refused", codes: introduced });
        return true;
      }
      afterwards(files, remote && !files.length);
      return false;
    },
    handleDrop(view, event, slice, moved) {
      if (moved) return false;
      const data = event.dataTransfer;
      const html = data ? data.getData("text/html") : "";
      const { codes } = screen(html);
      if (codes.length) {
        report({ kind: "refused", codes });
        return true;
      }
      const { files, remote } = carried(data, html);
      const target = view.posAtCoords({ left: event.clientX, top: event.clientY });
      if (bringsNothing(slice)) {
        afterwards(files, remote && !files.length, target ? target.pos : null);
        return true;
      }
      if (!target) return false;
      const at = dropPoint(view.state.doc, target.pos, slice) ?? target.pos;
      const tr = view.state.tr.replaceRange(at, at, slice);
      const introduced = added(view.state, tr, check);
      if (introduced.length) {
        report({ kind: "refused", codes: introduced });
        return true;
      }
      // The text goes in where it was dropped; its images after the block it landed in.
      view.dispatch(tr);
      afterwards(files, remote && !files.length, tr.mapping.map(at));
      return true;
    },
  };
}

// The editor's document model, from the whitelist specification (ADR-0010). Group names enforce
// placement: tables, headings, quotes and callouts stand only in the document (`top`); paragraphs
// and lists also in lists, quotes and callouts (`block`). No hard break, code block or rule exists,
// so none can be made. Mark order is nesting order on disk (DL-0240).
import { Schema } from "prosemirror-model";
import { tableNodes } from "prosemirror-tables";

const IDENTIFIER = /^[A-Za-z0-9_-]+$/;
const ALIGNS = ["left", "center", "right"];

function allowedLink(spec, href) {
  return href && !/[\s<>]/.test(href) && spec.linkSchemes.test(href) ? { href } : false;
}

// Every attribute read from pasted HTML is one the specification allows, or the element is not
// read at all.
function allowedEntity(spec, kind, id) {
  if (!kind || kind === "underline" || !Object.hasOwn(spec.spans, kind)) return false;
  if (id && (!spec.spans[kind] || !IDENTIFIER.test(id))) return false;
  if (kind === "document" && !spec.mentionId.test(id || "")) return false;
  return { kind, id: id || null };
}

// The address an image of the draft is shown from: the edit tab names the draft's image route on
// its editor element; read when the image is drawn, since the schema is built before any page is.
function imageUrl(src) {
  const base = typeof document !== "undefined" ? document.getElementById("editor")?.dataset.image : null;
  const name = src.startsWith("images/") ? src.slice("images/".length) : "";
  return base && /^[0-9a-f]{64}\.(png|jpg|gif)$/.test(name) ? `${base}${name}/` : null;
}

export function makeSchema(spec) {
  const table = tableNodes({
    tableGroup: "top",
    cellContent: "inline*",
    cellAttributes: {
      align: {
        default: null,
        getFromDOM: (dom) => (ALIGNS.includes(dom.style.textAlign) ? dom.style.textAlign : null),
        setDOMAttr: (value, attrs) => {
          if (value) attrs.style = (attrs.style || "") + `text-align:${value};`;
        },
      },
    },
  });
  return new Schema({
    nodes: {
      doc: { content: "(block | top)+" },
      paragraph: {
        group: "block",
        content: "inline*",
        parseDOM: [{ tag: "p" }],
        toDOM: () => ["p", 0],
      },
      heading: {
        group: "top",
        content: "inline*",
        attrs: { level: { default: 1 } },
        defining: true,
        parseDOM: Array.from({ length: spec.headingMaxDepth }, (_, i) => ({
          tag: `h${i + 1}`,
          attrs: { level: i + 1 },
        })),
        toDOM: (node) => [`h${node.attrs.level}`, 0],
      },
      bullet_list: {
        group: "block",
        content: "list_item+",
        parseDOM: [{ tag: "ul" }],
        toDOM: () => ["ul", 0],
      },
      ordered_list: {
        group: "block",
        content: "list_item+",
        attrs: { order: { default: 1 } },
        parseDOM: [
          {
            tag: "ol",
            getAttrs: (dom) => {
              const start = dom.hasAttribute("start") ? Number(dom.getAttribute("start")) : 1;
              return { order: Number.isInteger(start) && start >= 0 && start < 1e9 ? start : 1 };
            },
          },
        ],
        toDOM: (node) => ["ol", node.attrs.order === 1 ? {} : { start: node.attrs.order }, 0],
      },
      list_item: {
        content: "paragraph block*",
        defining: true,
        parseDOM: [{ tag: "li" }],
        toDOM: () => ["li", 0],
      },
      quote: {
        group: "top",
        content: "block+",
        defining: true,
        parseDOM: [{ tag: "blockquote" }],
        toDOM: () => ["blockquote", 0],
      },
      callout: {
        group: "top",
        content: "block+",
        defining: true,
        attrs: { type: { default: spec.calloutTypes[0] } },
        parseDOM: [
          {
            tag: "div.callout",
            getAttrs: (dom) => {
              const type = dom.getAttribute("data-type");
              return spec.calloutTypes.includes(type) ? { type } : false;
            },
          },
        ],
        toDOM: (node) => ["div", { class: `callout callout-${node.attrs.type}`, "data-type": node.attrs.type }, 0],
      },
      table: table.table,
      table_row: table.table_row,
      table_cell: table.table_cell,
      table_header: table.table_header,
      // An image stands in a paragraph of its own; the editor shows it through the address the edit
      // tab gives for the draft's images, and its description where no page gives one.
      image: {
        inline: true,
        group: "inline",
        atom: true,
        draggable: false,
        attrs: { src: {}, alt: { default: "" } },
        parseDOM: [
          {
            tag: "span.image[data-src]",
            getAttrs: (dom) => {
              const src = dom.getAttribute("data-src") || "";
              return spec.imageSrc.test(src) ? { src, alt: dom.getAttribute("data-alt") || "" } : false;
            },
          },
        ],
        toDOM: (node) => {
          const attrs = { class: "image", "data-src": node.attrs.src, "data-alt": node.attrs.alt, contenteditable: "false" };
          const url = imageUrl(node.attrs.src);
          return url
            ? ["span", attrs, ["img", { src: url, alt: node.attrs.alt }]]
            : ["span", attrs, node.attrs.alt || node.attrs.src];
        },
      },
      // A sentence boundary: the space between two sentences, which is not text (V-03).
      sb: {
        inline: true,
        group: "inline",
        atom: true,
        selectable: false,
        parseDOM: [{ tag: "span.sb" }],
        toDOM: () => ["span", { class: "sb" }],
      },
      text: { group: "inline" },
    },
    marks: {
      entity: {
        attrs: { kind: {}, id: { default: null } },
        excludes: "entity",
        inclusive: false,
        parseDOM: [
          {
            tag: "span.entity[data-kind]",
            getAttrs: (dom) => allowedEntity(spec, dom.getAttribute("data-kind"), dom.getAttribute("data-id")),
          },
          // The reading view draws a followed mention as a link; copied back, it is the mention
          // again, never a link every reader could follow. Ahead of the link's own rule. A copy
          // carries the address resolved, so it is read against this page; another host's stays
          // a link.
          {
            tag: "a.mention[href]",
            priority: 60,
            getAttrs: (dom) => {
              let url;
              try {
                url = new URL(dom.getAttribute("href") || "", location.href);
              } catch {
                return false;
              }
              if (url.origin !== location.origin) return false;
              const found = /^\/document\/([^/]+)\/$/.exec(url.pathname);
              return found ? allowedEntity(spec, "document", found[1]) : false;
            },
          },
        ],
        toDOM: (mark) => [
          "span",
          {
            class: `entity entity-${mark.attrs.kind}`,
            "data-kind": mark.attrs.kind,
            ...(mark.attrs.id ? { "data-id": mark.attrs.id } : {}),
          },
          0,
        ],
      },
      // Shown as marked text that goes nowhere, and taken from pasted HTML only with an allowed
      // scheme, so the editing surface never navigates or fetches.
      link: {
        attrs: { href: {} },
        inclusive: false,
        parseDOM: [
          { tag: "span.link[data-href]", getAttrs: (dom) => allowedLink(spec, dom.getAttribute("data-href")) },
          { tag: "a[href]", getAttrs: (dom) => allowedLink(spec, dom.getAttribute("href")) },
        ],
        toDOM: (mark) => ["span", { class: "link", "data-href": mark.attrs.href, title: mark.attrs.href }, 0],
      },
      underline: {
        parseDOM: [{ tag: "span.underline" }],
        toDOM: () => ["span", { class: "underline" }, 0],
      },
      strong: {
        parseDOM: [{ tag: "strong" }, { tag: "b" }],
        toDOM: () => ["strong", 0],
      },
      em: {
        parseDOM: [{ tag: "em" }, { tag: "i" }],
        toDOM: () => ["em", 0],
      },
    },
  });
}

// markdown-it configured to recognise everything the whitelist refuses — CommonMark, pipe tables,
// raw HTML tokenised so that it can be refused by name, every link tokenised so that a refused scheme
// is named, the span and callout rules, the tidying both sides share — and the validator over it
// (ADR-0010). `src/editing/markdown/parser.py` and `validator.py` are its twin. This instance
// recognises and never renders: the editor renders through its own document model.
import MarkdownIt from "markdown-it";
import { MarkdownParser } from "prosemirror-markdown";

import { attrSpan, callout, linesOf, tidy, walk } from "./rules.js";

export function makeMarkdownIt() {
  const md = MarkdownIt("commonmark", { html: true }).enable("table");
  md.validateLink = () => true;
  md.inline.ruler.before("link", "attr_span", attrSpan);
  md.core.ruler.after("block", "callout", callout);
  md.core.ruler.after("text_join", "tidy", tidy);
  return md;
}

export const md = makeMarkdownIt();

// Every refusal in `text`, as `{ code, line }`, by line then code; empty when the text is inside
// the whitelist. A text over the specification's size is refused before it is parsed.
export function validate(text, spec) {
  if (new TextEncoder().encode(text).length > spec.maxBytes) return [{ code: "too-large", line: 1 }];
  const env = {};
  const tokens = md.parse(text, env);
  return walk(tokens, linesOf(text), env, spec).map(([code, line]) => ({ code, line }));
}

function alignFromStyle(token) {
  const m = /text-align:([A-Za-z0-9_]+)/.exec(token.attrGet("style") || "");
  return { align: m ? m[1] : null };
}

// The editor's document for a text the validator accepted.
export function makeParser(schema) {
  return new MarkdownParser(schema, md, tokenMap);
}

// markdown-it's tokens, each to the editor's node or mark; a token with no entry throws.
export const tokenMap = {
    paragraph: { block: "paragraph" },
    heading: { block: "heading", getAttrs: (t) => ({ level: +t.tag.slice(1) }) },
    blockquote: { block: "quote" },
    callout: { block: "callout", getAttrs: (t) => ({ type: t.info }) },
    bullet_list: { block: "bullet_list" },
    ordered_list: {
      block: "ordered_list",
      getAttrs: (t) => ({ order: t.attrGet("start") == null ? 1 : +t.attrGet("start") }),
    },
    list_item: { block: "list_item" },
    table: { block: "table" },
    thead: { ignore: true },
    tbody: { ignore: true },
    tr: { block: "table_row" },
    th: { block: "table_header", getAttrs: alignFromStyle },
    td: { block: "table_cell", getAttrs: alignFromStyle },
    image: {
      node: "image",
      getAttrs: (t) => ({
        src: t.attrGet("src"),
        alt: (t.children || []).map((c) => (c.type === "softbreak" ? " " : c.content)).join(""),
      }),
    },
    em: { mark: "em" },
    strong: { mark: "strong" },
    link: { mark: "link", getAttrs: (t) => ({ href: t.attrGet("href") }) },
    underline: { mark: "underline" },
    entity: { mark: "entity", getAttrs: (t) => ({ kind: t.meta.kind, id: t.meta.id }) },
    softbreak: { node: "sb" },
};

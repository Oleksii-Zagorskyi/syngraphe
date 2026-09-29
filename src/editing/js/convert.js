// The conversion offered when a paste into the source view is refused (DL-0171): each refused
// construct rewritten in one fixed way, so the preview is deterministic. The text is tokenised as
// the validator tokenises it, the tokens rewritten, read into the editor's document and written by
// the platform's serialiser; what comes out is accepted by the validator.
import Token from "markdown-it/lib/token.mjs";
import { MarkdownParser } from "prosemirror-markdown";

import { md } from "./parser.js";
import { CONTROL, linesOf } from "./rules.js";

const FOOTNOTE_DEFINITION = /^ {0,3}\[\^([^\]]+)\]:[ \t]*(.*)$/;
const FOOTNOTE_REFERENCE = /\[\^([^\]]+)\]/g;
const TASK = /^\[[ xX]\][ \t]?/;

function text(content) {
  const token = new Token("text", "", 0);
  token.content = content;
  return token;
}

function paragraph(children) {
  const inline = new Token("inline", "", 0);
  inline.children = children;
  inline.content = children.map((c) => c.content).join("");
  return [new Token("paragraph_open", "p", 1), inline, new Token("paragraph_close", "p", -1)];
}

// Footnotes as text: each reference replaced by its note in parentheses, each definition removed.
function footnotesInline(source) {
  const notes = {};
  const kept = [];
  for (const line of linesOf(source)) {
    const m = FOOTNOTE_DEFINITION.exec(line);
    if (m) notes[m[1]] = m[2].trim();
    else kept.push(line);
  }
  return kept.join("\n").replace(FOOTNOTE_REFERENCE, (_, id) => (notes[id] ? ` (${notes[id]})` : ""));
}

// The index just past the token that closes the one at `start`.
function closingIndex(tokens, start) {
  let depth = 0;
  for (let i = start; i < tokens.length; i++) {
    depth += tokens[i].nesting;
    if (depth === 0) return i + 1;
  }
  return tokens.length;
}

let leftOut = false;

function inlineChildren(children, spec, block) {
  const out = [];
  const images = [];
  let entities = 0;
  const dropped = new Set();
  children.forEach((child, i) => {
    const kind = child.type;
    if (kind === "code_inline") out.push(text(child.content));
    else if (kind === "html_inline") {
      if (/^<br\s*\/?>$/i.test(child.content.trim())) out.push(text(" "));
    }
    else if (kind === "hardbreak") out.push(text(" "));
    else if (kind === "image") {
      if (!spec.imageSrc.test(child.attrGet("src") || "")) {
        leftOut = true;
        return;
      }
      child.attrs = [["src", child.attrGet("src")], ["alt", ""]];
      // Only in a paragraph must an image stand alone; in a heading or a cell it stays in place.
      if (block === "paragraph") images.push(child);
      else out.push(child);
    } else if (kind === "link_open") {
      const href = child.attrGet("href") || "";
      const empty = children[i + 1] && children[i + 1].type === "link_close";
      if (!spec.linkSchemes.test(href) || empty) dropped.add(i), dropped.add(closeOf(children, i));
      else {
        child.attrs = [["href", href]];
        out.push(child);
      }
    } else if (kind === "entity_open" || kind === "underline_open") {
      const span = child.meta.kind;
      const close = closeOf(children, i);
      const empty = close === i + 1;
      const nested = kind === "entity_open" && entities > 0;
      if (span === null || !Object.hasOwn(spec.spans, span) || empty || nested) {
        dropped.add(i), dropped.add(close);
        return;
      }
      if (child.meta.id && !spec.spans[span]) child.meta = { ...child.meta, id: null };
      if (kind === "entity_open") entities += 1;
      out.push(child);
    } else if (dropped.has(i)) return;
    else {
      if (kind === "entity_close") entities -= 1;
      out.push(child);
    }
  });
  const filtered = out;
  // An image stands in a paragraph of its own: the text first, then each image after it.
  if (block === "paragraph" && images.length && (filtered.length || images.length > 1)) {
    return { children: filtered, after: images };
  }
  return { children: images.length && !filtered.length ? images : filtered, after: [] };
}

function closeOf(children, start) {
  const closing = children[start].type.replace("_open", "_close");
  let depth = 0;
  for (let i = start; i < children.length; i++) {
    if (children[i].type === children[start].type) depth += 1;
    if (children[i].type === closing && --depth === 0) return i;
  }
  return -1;
}

function rewrite(tokens, spec) {
  const out = [];
  const lifted = [];
  const skip = new Set();
  let lists = 0, quotes = 0, headerCells = 0, rowCells = 0, inHead = false;
  for (let i = 0; i < tokens.length; i++) {
    if (skip.has(i)) continue;
    const token = tokens[i];
    const kind = token.type;
    const nested = lists > 0 || quotes > 0;
    const lifts = ["table_open", "blockquote_open", "callout_open", "heading_open"];
    if (lifts.includes(kind) && nested) {
      // Lifted to the top level, after the block that held it.
      const end = closingIndex(tokens, i);
      lifted.push(...rewrite(tokens.slice(i, end), spec));
      i = end - 1;
      continue;
    }
    if (kind === "code_block" || kind === "fence") {
      out.push(...paragraph([text(token.content.trim().replace(/\s*\n\s*/g, " "))]));
    } else if (kind === "html_block") {
      const content = new DOMParser().parseFromString(token.content, "text/html").body.textContent.trim();
      if (content) out.push(...paragraph([text(content.replace(/\s+/g, " "))]));
    } else if (kind === "hr") {
      continue;
    } else if (kind === "heading_open" || kind === "heading_close") {
      const level = Math.min(+token.tag.slice(1), spec.headingMaxDepth);
      token.tag = `h${level}`;
      out.push(token);
    } else if (kind === "bullet_list_open" || kind === "ordered_list_open") {
      if (lists === spec.listMaxDepth) {
        // A list too deep is lifted: its items follow the item that held it, at the deepest
        // level allowed.
        const close = closingIndex(tokens, i) - 1;
        let depth = 0;
        for (let k = close + 1; k < tokens.length; k++) {
          if (tokens[k].type === "list_item_close" && depth === 0) {
            skip.add(k);
            break;
          }
          depth += tokens[k].nesting;
        }
        skip.add(close);
        out.push(new Token("list_item_close", "li", -1));
        continue;
      }
      lists += 1;
      out.push(token);
    } else if (kind === "bullet_list_close" || kind === "ordered_list_close") {
      out.push(token);
      lists -= 1;
      if (!quotes && !lists) out.push(...lifted.splice(0));
    } else if (kind === "list_item_open" || kind === "list_item_close") {
      if (kind === "list_item_open") {
        const next = tokens[i + 1];
        if (next.type === "list_item_close") {
          i += 1;
          continue;
        }
        if (next.type.endsWith("_list_open")) {
          // An item that begins with a list: its list's items take its place.
          skip.add(i + 1).add(closingIndex(tokens, i + 1) - 1).add(closingIndex(tokens, i) - 1);
          continue;
        }
        out.push(token);
      } else out.push(token);
    } else if (kind === "blockquote_open" || kind === "callout_open") {
      quotes += 1;
      if (kind === "callout_open" && !spec.calloutTypes.includes(token.info)) token.type = "blockquote_open";
      out.push(token);
    } else if (kind === "blockquote_close" || kind === "callout_close") {
      quotes -= 1;
      out.push(token);
      if (!quotes && !lists) out.push(...lifted.splice(0));
    } else if (kind === "thead_open" || kind === "thead_close") {
      inHead = kind === "thead_open";
      out.push(token);
    } else if (kind === "tr_open") {
      rowCells = 0;
      out.push(token);
    } else if (kind === "th_open" || kind === "td_open") {
      rowCells += 1;
      if (inHead) headerCells = rowCells;
      if (!inHead && rowCells > headerCells) {
        i = closingIndex(tokens, i) - 1;
        continue;
      }
      out.push(token);
    } else if (kind === "inline") {
      const block = tokens[i - 1].type.replace("_open", "");
      if (tokens[i - 2] && tokens[i - 2].type === "list_item_open" && token.children[0]?.type === "text") {
        token.children[0].content = token.children[0].content.replace(TASK, "");
      }
      const { children, after } = inlineChildren(token.children || [], spec, block);
      token.children = children;
      out.push(token);
      if (after.length) {
        out.push(tokens[i + 1]);
        for (const image of after) out.push(...paragraph([image]));
        i += 1;
      }
    } else {
      out.push(token);
      if ((kind === "bullet_list_close" || kind === "ordered_list_close" || kind === "table_close") && !quotes && !lists) {
        out.push(...lifted.splice(0));
      }
    }
  }
  out.push(...lifted.splice(0));
  return out;
}

// The text `source` converted into the whitelist, written as the source view shows it.
// `leftOut` says whether an image from outside the document was dropped.
export function convert(source, spec, schema, tokenMap, write) {
  leftOut = false;
  const cleaned = footnotesInline(source.replace(new RegExp(CONTROL.source, "g"), ""));
  const tokens = rewrite(md.parse(cleaned, {}), spec);
  const parser = new MarkdownParser(schema, { parse: () => tokens }, tokenMap);
  return { text: write(parser.parse("")), leftOut };
}

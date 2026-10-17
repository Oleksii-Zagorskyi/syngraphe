// The rules written in both languages (ADR-0010): the attributed span, the callout, the `- 1.`
// respelling, the tidying of inline text, and the validator's walk. `src/editing/markdown/rules.py` is this module's twin — the
// same functions in the same order, each named by its language's convention — and the conformance
// suite holds the two in step. A change here is a change there, in the same commit.
//
// Patterns use explicit ASCII classes only: Python's `\w` and `\s` match Unicode letters and
// spaces, JavaScript's do not.

const characters = (codes) => String.fromCharCode(...codes);
const range = (from, to) => Array.from({ length: to - from }, (_, i) => from + i);

// `.type` or `.type #id`, the only attribute blocks a span may carry.
export const ATTRS = /^[ \t]*\.([A-Za-z][A-Za-z0-9_-]*)(?:[ \t]+#([A-Za-z0-9_-]+))?[ \t]*$/;
// Matched where the label ends, never on a copy of the rest of the text, and bounded, so a long run
// of labels costs linear time.
export const BLOCK = /\{([^}\n]{0,128})\}/y;
export const MARKER = /^\[!([^\]\t\n ]+)\][ \t]*\n?/;
export const FOOTNOTE = /(^|[^\\])\[\^/;
export const TASK = /^\[[ xX]\](?:[ \t]|$)/;
export const DEFINITION = /^ {0,3}\[[^\]]+\]:/;
export const FENCE = /^ {0,3}(`{3,}|~{3,})/;
export const LINE_BREAK = /\r\n?|\n/;
export const NEWLINE = /[\r\n]/g;
// C0 and C1 controls but the tab and the line breaks, the Unicode line and paragraph separators,
// and the byte-order mark: invisible, and trimmed differently by the two languages.
export const CONTROL = new RegExp(
  "[" +
    characters([...range(0x00, 0x09), 0x0b, 0x0c, ...range(0x0e, 0x20), 0x7f, 0x85, 0x2028, 0x2029, 0xfeff]) +
    "]",
);
// JavaScript's `\s`, spelled out as the Python side spells it.
const SPACE = characters([
  0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x20, 0xa0, 0x1680, ...range(0x2000, 0x200b), 0x2028, 0x2029, 0x202f,
  0x205f, 0x3000, 0xfeff,
]);
const LEADING = new RegExp("^[" + SPACE + "]+");
const TRAILING = new RegExp("[" + SPACE + "]+$");
export const INLINE_CODES = { code_inline: "inline-code", html_inline: "html", hardbreak: "hard-break" };
// The blocks whose lines a link reference definition cannot share.
const TEXT_BLOCKS = new Set(["paragraph_open", "heading_open", "code_block", "fence", "html_block"]);

// Every token a document inside the whitelist produces; anything else is refused by name.
export const KNOWN = new Set([
  "paragraph_open", "paragraph_close", "heading_open", "heading_close", "inline", "text",
  "softbreak", "bullet_list_open", "bullet_list_close", "ordered_list_open",
  "ordered_list_close", "list_item_open", "list_item_close", "blockquote_open",
  "blockquote_close", "callout_open", "callout_close", "table_open", "table_close",
  "thead_open", "thead_close", "tbody_open", "tbody_close", "tr_open", "tr_close",
  "th_open", "th_close", "td_open", "td_close", "em_open", "em_close", "strong_open",
  "strong_close", "link_open", "link_close", "image", "entity_open", "entity_close",
  "underline_open", "underline_close",
]);

// The source lines as markdown-it counts them: `\r\n`, `\r` and `\n` each end one.
export function linesOf(text) {
  return text.split(LINE_BREAK);
}

// `[text]{.type #id}`: an entity span, or `[text]{.underline}`; any other attribute block is still
// a span, with no kind, so the validator names it rather than letting it pass as text.
export function attrSpan(state, silent) {
  if (silent || state.pos >= state.posMax || state.src[state.pos] !== "[") {
    return false; // never consume silently: a link label's scan would read it as a link
  }
  const end = state.md.helpers.parseLinkLabel(state, state.pos, false);
  if (end < 0) return false;
  BLOCK.lastIndex = end + 1;
  const m = BLOCK.exec(state.src);
  if (!m) return false;
  const after = BLOCK.lastIndex;
  const a = ATTRS.exec(m[1]);
  const kind = a ? a[1] : null;
  const kindType = kind === "underline" ? "underline" : "entity";
  const token = state.push(kindType + "_open", "span", 1);
  token.meta = { kind, id: (a ? a[2] : null) || null, raw: m[1] };
  const pos = state.pos, maximum = state.posMax;
  state.pos = pos + 1;
  state.posMax = end;
  state.md.inline.tokenize(state);
  state.pos = pos;
  state.posMax = maximum;
  // The close token says what it closes, so a rule rendering it alone — a mention's close — can.
  const close = state.push(kindType + "_close", "span", -1);
  close.meta = { kind: token.meta.kind, id: token.meta.id };
  state.pos = after;
  return true;
}

// A quote whose first line starts `[!type]` becomes a callout; text after the marker stays as its
// first paragraph (DL-0238).
export function callout(state) {
  const tokens = state.tokens;
  let i = 0;
  while (i < tokens.length) {
    if (
      tokens[i].type !== "blockquote_open" ||
      i + 2 >= tokens.length ||
      tokens[i + 1].type !== "paragraph_open" ||
      tokens[i + 2].type !== "inline"
    ) {
      i += 1;
      continue;
    }
    const m = MARKER.exec(tokens[i + 2].content);
    if (!m) {
      i += 1;
      continue;
    }
    tokens[i].type = "callout_open";
    tokens[i].info = m[1].toLowerCase();
    for (let j = i + 1; j < tokens.length; j++) {
      if (tokens[j].type === "blockquote_close" && tokens[j].level === tokens[i].level) {
        tokens[j].type = "callout_close";
        break;
      }
    }
    tokens[i + 2].content = tokens[i + 2].content.slice(m[0].length);
    if (!tokens[i + 2].content) tokens.splice(i + 1, 3);
    i += 1;
  }
}

// Strip spaces from the text at one edge of a line of inline content, passing over the marks that
// open or close there, and drop what the stripping empties.
function trim(children, index, step, strip) {
  const edge = step === 1 ? "_open" : "_close";
  while (index >= 0 && index < children.length) {
    const child = children[index];
    if (child.type.endsWith(edge)) {
      index += step;
    } else if (child.type === "text") {
      child.content = strip(child.content);
      if (child.content) return;
      children.splice(index, 1);
      if (step === -1) index -= 1;
    } else {
      return;
    }
  }
}

// The index of the token closing the one opening at `at`.
function closing(tokens, at) {
  let depth = 0;
  for (let index = at; index < tokens.length; index += 1) {
    depth += tokens[index].nesting;
    if (depth === 0) return index;
  }
  return tokens.length - 1;
}

// For the bullet list opening at `at`, each item's one numbered item — its open and close — when
// every item holds one numbered list of one item and nothing else; `null` otherwise.
function numberedItems(tokens, at) {
  const close = closing(tokens, at);
  const found = [];
  let item = at + 1;
  while (item < close) {
    const itemClose = closing(tokens, item);
    const inner = item + 1;
    if (
      tokens[item].type !== "list_item_open" ||
      tokens[inner].type !== "ordered_list_open" ||
      closing(tokens, inner) !== itemClose - 1
    ) {
      return null;
    }
    const numbered = inner + 1;
    const numberedClose = closing(tokens, numbered);
    if (numberedClose !== itemClose - 2) return null;
    found.push([numbered, numberedClose]);
    item = itemClose + 1;
  }
  return found.length ? found : null;
}

// `- 1. Text`: a bullet list each item of which holds one numbered item and nothing else is the
// numbered list its author meant (DL-0441) — one ordered list of those items, in order. Any other
// shape is left for the validator to refuse.
export function numberedBullets(state) {
  // A pass moves each such list it meets whole, and one nested in a moved list is met by the
  // next: as many passes as these lists nest deep, each about the text's length.
  while (numberedPass(state));
}

// One pass of `numberedBullets`, over the text in order; whether it moved any list.
function numberedPass(state) {
  const tokens = state.tokens;
  const out = [];
  let movedAny = false;
  let at = 0;
  while (at < tokens.length) {
    const items = tokens[at].type === "bullet_list_open" ? numberedItems(tokens, at) : null;
    if (items === null) {
      out.push(tokens[at]);
      at += 1;
      continue;
    }
    const close = closing(tokens, at);
    const first = items[0][0] - 1;
    const opening = tokens[first], closer = tokens[closing(tokens, first)];
    opening.level = tokens[at].level;
    closer.level = tokens[close].level;
    const moved = [];
    for (const [start, end] of items) {
      for (let index = start; index <= end; index += 1) {
        tokens[index].level -= 2;
        moved.push(tokens[index]);
      }
    }
    // One list is loose when any of its items is, as the stored form will read; a list
    // nested in an item keeps its own.
    const own = moved.filter((t) => t.level === opening.level + 2 && t.type.startsWith("paragraph"));
    if (own.some((t) => !t.hidden)) {
      for (const token of own) token.hidden = false;
    }
    out.push(opening);
    for (const token of moved) out.push(token);
    out.push(closer);
    movedAny = true;
    at = close + 1;
  }
  state.tokens = out;
  return movedAny;
}

// What both sides store the same way whatever the text arrived as: a line break inside text (from a
// character reference) becomes a space; a line of inline content — the start and end of a block,
// the sentences either side of a boundary — neither starts nor ends in a space; a heading's lines
// join into one; and two lists of one kind that follow each other are one.
export function tidy(state) {
  const tokens = state.tokens;
  tokens.forEach((token, position) => {
    if (token.type !== "inline" || !token.children) return;
    const children = token.children;
    const heading = position > 0 && tokens[position - 1].type === "heading_open";
    for (const child of children) {
      if (child.type === "text") {
        child.content = child.content.replace(NEWLINE, " ");
      } else if (child.type === "softbreak" && heading) {
        child.type = "text";
        child.content = " ";
      }
    }
    const starts = [0];
    children.forEach((c, i) => {
      if (c.type === "softbreak") starts.push(i + 1);
    });
    for (const start of starts.reverse()) {
      let end = start;
      while (end < children.length && children[end].type !== "softbreak") end += 1;
      trim(children, end - 1, -1, (text) => text.replace(TRAILING, ""));
      trim(children, start, 1, (text) => text.replace(LEADING, ""));
    }
    token.children = children.filter((c) => c.type !== "text" || c.content);
  });
  let i = 0;
  while (i + 1 < tokens.length) {
    const closing = tokens[i], opening = tokens[i + 1];
    if (
      (closing.type === "bullet_list_close" || closing.type === "ordered_list_close") &&
      opening.type === closing.type.replace("_close", "_open") &&
      opening.level === closing.level
    ) {
      tokens.splice(i, 2);
    } else {
      i += 1;
    }
  }
}

// The cells of one table row as markdown-it splits it: a pipe after a backslash is escaped, an
// empty first or last cell is the edge.
export function cellCount(line) {
  const cells = [""];
  let escaped = false;
  for (const character of line.replace(LEADING, "").replace(TRAILING, "")) {
    if (character === "|" && !escaped) cells.push("");
    else cells[cells.length - 1] += character;
    escaped = character === "\\";
  }
  if (cells.length && cells[0] === "") cells.shift();
  if (cells.length && cells[cells.length - 1] === "") cells.pop();
  return cells.length;
}

// The lines, from 1, that define a link reference: shaped like one, outside fenced code, and
// outside every block that holds text.
export function definitionLines(lines, tokens) {
  const covered = new Set();
  for (const token of tokens) {
    if (TEXT_BLOCKS.has(token.type) && token.map) {
      for (let l = token.map[0]; l < token.map[1]; l++) covered.add(l);
    }
  }
  const found = [];
  let fence = null;
  lines.forEach((line, index) => {
    const m = FENCE.exec(line);
    if (m) {
      const marker = m[1][0];
      fence = fence === marker ? null : fence || marker;
      return;
    }
    if (fence === null && !covered.has(index) && DEFINITION.test(line)) found.push(index + 1);
  });
  return found;
}

// Every refusal in a parsed text: `[code, line]`, sorted, each once. A line is the first line of
// the block that holds the construct.
export function walk(tokens, lines, env, spec) {
  const found = new Map();
  let line = 1;
  let lists = 0, quotes = 0;
  let headerCells = 0;
  let inHead = false;
  let itemStart = false;

  const refuse = (code, at) => {
    const refusal = [code, at === undefined ? line : at];
    found.set(refusal.join(" "), refusal);
  };

  lines.forEach((text, index) => {
    if (CONTROL.test(text)) refuse("control-character", index + 1);
  });
  if (env.references && Object.keys(env.references).length) {
    const numbers = definitionLines(lines, tokens);
    for (const number of numbers.length ? numbers : [1]) refuse("link-reference", number);
  }

  tokens.forEach((token, index) => {
    if (token.type !== "inline" && token.map) line = token.map[0] + 1;
    const kind = token.type;
    if (!KNOWN.has(kind) && !["code_block", "fence", "html_block", "hr"].includes(kind)) {
      refuse("unsupported");
    }
    if (kind === "heading_open") {
      if (+token.tag.slice(1) > spec.headingMaxDepth) refuse("heading-depth");
      if (spec.headingsTopLevelOnly && (lists || quotes)) refuse("heading-nested");
    } else if (kind === "code_block" || kind === "fence") {
      refuse("code");
    } else if (kind === "html_block") {
      refuse("html");
    } else if (kind === "hr") {
      refuse("hr");
    } else if (kind === "blockquote_open" || kind === "callout_open") {
      if (quotes || lists) refuse("nested-quote");
      if (kind === "callout_open" && !spec.calloutTypes.includes(token.info)) refuse("callout-type");
      quotes += 1;
    } else if (kind === "blockquote_close" || kind === "callout_close") {
      quotes -= 1;
    } else if (kind === "bullet_list_open" || kind === "ordered_list_open") {
      lists += 1;
      if (lists > spec.listMaxDepth) refuse("list-depth");
    } else if (kind === "bullet_list_close" || kind === "ordered_list_close") {
      lists -= 1;
    } else if (kind === "list_item_open") {
      const following = index + 1 < tokens.length ? tokens[index + 1].type : "";
      if (following === "list_item_close" || following.endsWith("_list_open")) refuse("list-item-empty");
      itemStart = true;
      return;
    } else if (kind === "table_open") {
      if (spec.tablesTopLevelOnly && (lists || quotes)) refuse("table-nested");
    } else if (kind === "thead_open") {
      inHead = true;
    } else if (kind === "thead_close") {
      inHead = false;
    } else if (kind === "tr_open" && token.map) {
      const cells = cellCount(lines[token.map[0]]);
      if (inHead) headerCells = cells;
      else if (cells > headerCells) refuse("table-row-cells");
    } else if (kind === "inline") {
      if (FOOTNOTE.test(token.content)) refuse("footnote");
      if (itemStart && TASK.test(token.content)) refuse("task-list");
      inline(token.children || [], tokens[index - 1].type, spec, refuse);
    }
    if (kind !== "paragraph_open") itemStart = false;
  });
  return [...found.values()].sort((a, b) => a[1] - b[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
}

// The refusals inside one block's inline content, an image's description included.
function inline(children, block, spec, refuse) {
  let entities = 0;
  if (spec.imageAlone && block === "paragraph_open" && children.length > 1) {
    if (children.some((child) => child.type === "image")) refuse("image-inline");
  }
  children.forEach((child, position) => {
    const kind = child.type;
    const following = position + 1 < children.length ? children[position + 1].type : null;
    if (!KNOWN.has(kind)) refuse(INLINE_CODES[kind] || "unsupported");
    if (kind === "image") {
      if (!spec.imageSrc.test(String(child.attrGet("src") || ""))) refuse("image-src");
      if (child.attrGet("title")) refuse("title");
      inline(child.children || [], "image", spec, refuse);
    } else if (kind === "link_open") {
      if (!spec.linkSchemes.test(String(child.attrGet("href") || ""))) refuse("link-scheme");
      if (child.attrGet("title")) refuse("title");
      if (following === "link_close") refuse("link-empty");
    } else if (kind === "entity_open" || kind === "underline_open") {
      const span = child.meta.kind;
      if (span === null) refuse("span-attrs");
      else if (!Object.hasOwn(spec.spans, span)) refuse("span-type");
      else if (child.meta.id && !spec.spans[span]) refuse("span-id");
      else if (span === "document" && !spec.mentionId.test(child.meta.id || "")) refuse("mention-id");
      if (following === kind.replace("_open", "_close")) refuse("span-empty");
      if (kind === "entity_open") {
        if (entities) refuse("span-nested");
        entities += 1;
      }
    } else if (kind === "entity_close") {
      entities -= 1;
    }
  });
}

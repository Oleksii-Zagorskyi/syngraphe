// The source view (DL-0171, DL-0181): the draft as Markdown in a text field, each paragraph on one
// line, over the same draft as the rich view. A paste the whitelist refuses is stopped with each
// construct and its line named, and a conversion offered, previewed before it is applied; a paste
// it accepts loses its headings' own numbers. Text typed here is read back into the rich view on
// the switch, refused there with the field kept; a paragraph typed over several lines is named as
// the person pauses, since the switch joins it (DL-0441).

import { md } from "./parser.js";

// The heading labels of the outline, for headings of these depths in order: a skipped level
// counted as 1. The twin of `rendering/numbering.py::heading_labels`.
function headingLabels(depths) {
  const path = [];
  return depths.map((level) => {
    if (path.length > level) path.length = level;
    while (path.length < level) path.push(0);
    path[level - 1] += 1;
    for (let j = 0; j < level - 1; j += 1) path[j] = path[j] || 1;
    return path.join(".");
  });
}

// The text with the headings that start on lines `from` to `to` (0-based, inclusive) losing their
// own number — exactly their label, an optional full stop, then spaces or tabs (DL-0441). The
// twin of `editing/normalizer/headings.py::strip_own_numbers`, over the lines a paste brought.
export function stripOwnNumbers(text, from, to) {
  const lines = text.split("\n");
  const headings = md.parse(text, {}).filter((t) => t.type === "heading_open" && t.map);
  const labels = headingLabels(headings.map((t) => Number(t.tag.slice(1))));
  headings.forEach((token, n) => {
    const at = token.map[0];
    if (at < from || at > to) return;
    const found = /^(#{1,6}[ \t]+)(.*)$/.exec(lines[at]);
    if (!found) return;
    const own = new RegExp(`^${labels[n].replace(/\./g, "\\.")}\\.?[ \\t]+(?=\\S)`);
    lines[at] = found[1] + found[2].replace(own, "");
  });
  return lines.join("\n");
}

// Each paragraph the text holds over several lines: its first and last line, from 1. The source
// view shows a paragraph as one line, so these are joined on the switch (DL-0441). Counted by the
// paragraph's own text, so a callout's marker line is not one of them.
function joinedParagraphs(text) {
  const tokens = md.parse(text, {});
  const found = [];
  tokens.forEach((token, i) => {
    if (token.type !== "paragraph_open" || !token.map) return;
    const lines = tokens[i + 1].content.split("\n").length;
    if (lines > 1) found.push([token.map[1] - lines + 1, token.map[1]]);
  });
  return found;
}

function describe(refusals, words) {
  return refusals
    .map(({ code, line }) =>
      words.notices.line.replace("%(line)s", line).replace("%(construct)s", words.constructs[code] || code),
    )
    .join("; ");
}

// The field, with its paste check and conversion. `validate` and `convert` read and rewrite
// Markdown; `refusal` shows a line with the constructs and the help link.
export function sourceField({ words, validate, convert, refusal, notice = () => {} }) {
  // While a refusal stands on the notice line, the joined notice waits: it never replaces it.
  let refused = false;
  const field = document.createElement("textarea");
  field.className = "source-field";
  field.spellcheck = false;
  field.dataset.field = "source";

  const offer = document.createElement("div");
  offer.className = "source-offer";
  offer.hidden = true;
  const preview = document.createElement("pre");
  const apply = document.createElement("button");
  apply.type = "button";
  apply.dataset.command = "paste-converted";
  apply.textContent = words.labels.paste_converted;
  const note = document.createElement("p");
  offer.append(preview, note, apply);
  // An offer made for one place in the text is withdrawn once the text changes.
  field.addEventListener("input", () => {
    offer.hidden = true;
  });
  // Where a paragraph is typed over several lines, the notice line says it will be joined: the
  // first such paragraph and how many more, read over the whole field once the typing pauses.
  let pause = null;
  let saying = false;
  field.addEventListener("input", () => {
    clearTimeout(pause);
    pause = setTimeout(() => {
      if (refused || field.hidden) return;
      const found = joinedParagraphs(field.value);
      if (found.length) {
        saying = true;
        notice({ kind: "joined", first: found[0][0], last: found[0][1], more: found.length - 1 });
      } else if (saying) {
        saying = false;
        notice({ kind: "text", text: "" });
      }
    }, 500);
  });

  let converted = "";
  let at = [0, 0];
  field.addEventListener("paste", (event) => {
    const pasted = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
    const refusals = pasted ? validate(pasted) : [];
    if (!refusals.length) {
      offer.hidden = true;
      // A pasted heading's own number goes, as the loader takes it away: on the lines the paste
      // begins, and on no line typed before it.
      const start = field.selectionStart;
      const end = field.selectionEnd;
      const before = field.value.slice(0, start);
      const whole = before + pasted + field.value.slice(end);
      const first = before.split("\n").length - 1;
      const from = before === "" || before.endsWith("\n") ? first : first + 1;
      // A paste ending in a break ends before the next line begins; that line is not its own.
      const to = first + pasted.split("\n").length - 1 - (pasted.endsWith("\n") ? 1 : 0);
      const stripped = from <= to ? stripOwnNumbers(whole, from, to) : whole;
      if (stripped !== whole) {
        event.preventDefault();
        // The lines the paste touched, replaced whole: a number taken from one moves nothing else.
        const lineStart = before.lastIndexOf("\n") + 1;
        const after = whole.indexOf("\n", start + pasted.length);
        const lineEnd = after < 0 ? whole.length : after;
        const shorter = whole.length - stripped.length;
        field.setRangeText(
          stripped.slice(lineStart, lineEnd - shorter),
          lineStart,
          lineEnd - pasted.length + (end - start),
        );
        // Every number taken lies on the pasted lines, before where the paste ends.
        const caret = start + pasted.length - shorter;
        field.setSelectionRange(caret, caret);
        field.dispatchEvent(new Event("input", { bubbles: true }));
      }
      return;
    }
    event.preventDefault();
    refused = true;
    refusal(describe(refusals, words));
    const result = convert(pasted);
    converted = result.text;
    at = [field.selectionStart, field.selectionEnd];
    preview.textContent = converted;
    note.textContent = result.leftOut ? words.notices.images : "";
    offer.hidden = false;
  });
  apply.addEventListener("click", () => {
    field.setRangeText(converted, at[0], at[1], "end");
    field.dispatchEvent(new Event("input", { bubbles: true }));
    offer.hidden = true;
    refused = false;
    refusal("");
    field.focus();
  });
  return {
    field,
    offer,
    describe: (refusals) => describe(refusals, words),
    // A switch ends the pause: a notice about the field never comes after it has gone.
    quiet: () => {
      clearTimeout(pause);
      saying = false;
    },
    // Whether a refusal stands on the notice line, which the joined notice leaves in place.
    hold: (standing) => {
      refused = standing;
    },
  };
}

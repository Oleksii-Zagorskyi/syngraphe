// The source view (DL-0171, DL-0181): the draft as Markdown in a text field, each paragraph on one
// line, over the same draft as the rich view. A paste the whitelist refuses is stopped with each
// construct and its line named, and a conversion offered, previewed before it is applied. Text
// typed here is read back into the rich view on the switch, refused there with the field kept.

function describe(refusals, words) {
  return refusals
    .map(({ code, line }) =>
      words.notices.line.replace("%(line)s", line).replace("%(construct)s", words.constructs[code] || code),
    )
    .join("; ");
}

// The field, with its paste check and conversion. `validate` and `convert` read and rewrite
// Markdown; `refusal` shows a line with the constructs and the help link.
export function sourceField({ words, validate, convert, refusal }) {
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

  let converted = "";
  let at = [0, 0];
  field.addEventListener("paste", (event) => {
    const pasted = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
    const refusals = pasted ? validate(pasted) : [];
    if (!refusals.length) {
      offer.hidden = true;
      return;
    }
    event.preventDefault();
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
    refusal("");
    field.focus();
  });
  return { field, offer, describe: (refusals) => describe(refusals, words) };
}

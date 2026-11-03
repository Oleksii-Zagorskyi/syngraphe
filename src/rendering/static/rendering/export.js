// The export dialog (DL-0193, DL-0207): *Export* is disabled while nothing is chosen, *Format*
// while neither the document nor its appendices are, the appendices' *embedded* and *separate*
// while the document is not — appendices alone always go separate — and the delivery line follows
// the choices: one zip with the attachments or separate appendices, or for a Markdown export of a
// text that shows images. A choice that does not apply is disabled, never hidden; the server
// refuses the same, without this script.
(() => {
  const form = document.querySelector(".export-dialog");
  if (!form) return;
  const documentBox = form.querySelector('input[name="document"]');
  const attachments = form.querySelector('input[name="attachments"]');
  const appendices = form.querySelector('input[name="appendices"]');
  const delivery = form.querySelector(".delivery");
  const submit = form.querySelector('button[type="submit"]');

  const update = () => {
    const withDocument = documentBox.checked;
    const withFiles = Boolean(attachments && attachments.checked);
    const withAppendices = Boolean(appendices && appendices.checked);
    submit.disabled = !withDocument && !withFiles && !withAppendices;
    for (const format of form.querySelectorAll('input[name="format"]')) {
      format.disabled = !withDocument && !withAppendices;
    }
    for (const mode of form.querySelectorAll('input[name="appendices_mode"]')) {
      mode.disabled = !withDocument || !withAppendices;
    }
    const mode = form.querySelector('input[name="appendices_mode"]:checked');
    const separate = withAppendices && (!withDocument || (mode && mode.value === "separate"));
    const format = form.querySelector('input[name="format"]:checked');
    const view = form.querySelector('input[name="view"]:checked, input[type="hidden"][name="view"]');
    const markdownWithImages =
      format &&
      format.value === "markdown" &&
      view &&
      ((withDocument && view.dataset.images === "true") ||
        (withAppendices && view.dataset.appendixImages === "true"));
    if (delivery && delivery.dataset.zip) {
      delivery.textContent =
        withFiles || separate || (!withDocument && !withAppendices) || markdownWithImages
          ? delivery.dataset.zip
          : delivery.dataset.file;
    }
  };

  // The heading names the version that will be exported, following the view chosen (DL-0519).
  const heading = document.querySelector("h1 .version-number");
  const following = () => {
    const view = form.querySelector('input[name="view"]:checked, input[type="hidden"][name="view"]');
    if (heading && view && view.dataset.number) heading.textContent = view.dataset.number;
  };

  form.addEventListener("change", update);
  form.addEventListener("change", following);
  update();

  // A help box closes at a click anywhere else, and one opening closes the others (DL-0233).
  document.addEventListener("click", (event) => {
    for (const hint of form.querySelectorAll("details.hint[open]")) {
      if (!hint.contains(event.target)) hint.open = false;
    }
  });
})();

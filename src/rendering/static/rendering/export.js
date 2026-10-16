// The export dialog (DL-0193, DL-0207): *Export* is disabled while nothing is chosen, *Format*
// while the document is not, and the delivery line follows the choices: one zip with the
// attachments, or for a Markdown export of a text that shows images. A choice
// that does not apply is disabled, never hidden; the server refuses the same, without this script.
(() => {
  const form = document.querySelector(".export-dialog");
  if (!form) return;
  const documentBox = form.querySelector('input[name="document"]');
  const attachments = form.querySelector('input[name="attachments"]');
  const delivery = form.querySelector(".delivery");
  const submit = form.querySelector('button[type="submit"]');

  const update = () => {
    const withDocument = documentBox.checked;
    const withFiles = Boolean(attachments && attachments.checked);
    submit.disabled = !withDocument && !withFiles;
    for (const format of form.querySelectorAll('input[name="format"]')) format.disabled = !withDocument;
    const format = form.querySelector('input[name="format"]:checked');
    const view = form.querySelector('input[name="view"]:checked, input[type="hidden"][name="view"]');
    const markdownWithImages =
      withDocument && format && format.value === "markdown" && view && view.dataset.images === "true";
    if (delivery && delivery.dataset.zip) {
      delivery.textContent =
        withFiles || !withDocument || markdownWithImages ? delivery.dataset.zip : delivery.dataset.file;
    }
  };

  form.addEventListener("change", update);
  update();

  // A help box closes at a click anywhere else, and one opening closes the others (DL-0233).
  document.addEventListener("click", (event) => {
    for (const hint of form.querySelectorAll("details.hint[open]")) {
      if (!hint.contains(event.target)) hint.open = false;
    }
  });
})();

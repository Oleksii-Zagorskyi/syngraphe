// The export dialog (DL-0193, DL-0207): *Export* is disabled while nothing is chosen, *Format*
// while the document is not, and the delivery line follows the attachments' checkbox. A choice
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
    if (delivery && delivery.dataset.zip) {
      delivery.textContent = withFiles || !withDocument ? delivery.dataset.zip : delivery.dataset.file;
    }
  };

  form.addEventListener("change", update);
  update();
})();

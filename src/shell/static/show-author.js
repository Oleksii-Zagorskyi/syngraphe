// *Show edit authors* is saved when its box changes: the form's hidden value says what the box
// now means, so the page draws again with or without the names (DL-0504). No inline handler runs
// under the content policy (DL-0493).
document.addEventListener("DOMContentLoaded", () => {
  for (const box of document.querySelectorAll("form.show-author input[type=checkbox]")) {
    box.addEventListener("change", () => box.form.requestSubmit());
  }
});

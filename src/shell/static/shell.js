// The organisation's link opens the list of a person's organisations in a window over the page
// (DL-0525); each entry is the list page's own POST form. Without this script the link opens that
// page.
(() => {
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-organisations]");
    const dialog = document.getElementById("organisations-window");
    if (link && dialog && typeof dialog.showModal === "function") {
      event.preventDefault();
      dialog.showModal();
      return;
    }
    const closer = event.target.closest("#organisations-window [data-close]");
    if (closer) closer.closest("dialog").close();
  });
})();

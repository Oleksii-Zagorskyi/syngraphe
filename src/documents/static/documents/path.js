// The path of versions: the outlined point's acts placed under it, hung from it by an elbow line
// (DL-0518), and the windows its acts open. Without this script the acts stand under the path's
// left edge and every form still posts.
(() => {
  "use strict";

  function placeElbow() {
    const row = document.querySelector("nav.path .acts-row");
    if (!row) return;
    const acts = row.querySelector(".phase-acts");
    const elbow = row.querySelector(".elbow");
    const at = document.querySelector("nav.path .cycle li.point.here");
    if (!at || !acts || !acts.children.length) {
      if (elbow) elbow.hidden = true;
      return;
    }
    elbow.hidden = false;
    row.classList.add("placed");
    const box = row.getBoundingClientRect();
    const mark = at.getBoundingClientRect();
    const x = mark.left + mark.width / 2 - box.left;
    const width = acts.getBoundingClientRect().width;
    // The line ends under its version, or starts there when the version sits too far left.
    const leftward = x - width >= 0;
    const start = leftward ? x - width : x;
    const top = mark.bottom - box.top + 2;
    acts.style.left = `${start}px`;
    elbow.classList.toggle("rightward", !leftward);
    elbow.style.left = `${start}px`;
    elbow.style.width = `${width}px`;
    elbow.style.top = `${top}px`;
    elbow.style.height = `${-top + 10}px`;
    row.style.height = `${acts.getBoundingClientRect().height + 20}px`;
  }

  // An act carrying `data-window` opens its window over the page; the window's own button
  // closes it (DL-0513). Without script the act's form opens the confirmation page.
  document.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-window]");
    if (opener) {
      const dialog = document.getElementById(opener.dataset.window);
      if (dialog && typeof dialog.showModal === "function") {
        event.preventDefault();
        dialog.showModal();
      }
      return;
    }
    const closer = event.target.closest("dialog [data-close]");
    if (closer) closer.closest("dialog").close();
  });

  window.addEventListener("resize", placeElbow);
  placeElbow();
})();

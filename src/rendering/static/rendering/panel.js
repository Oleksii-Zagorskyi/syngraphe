// The document page's right panel (DL-0356): its icon row shows one pane at a time — parts, which
// the panel opens on, or the generated views. Nothing is kept. Without this script the panel shows
// parts alone.
(() => {
  document.addEventListener("click", (event) => {
    const chosen = event.target.closest("[data-panel-switch]");
    if (!chosen) return;
    const panel = chosen.closest(".panel");
    const name = chosen.dataset.panelSwitch;
    for (const pane of panel.querySelectorAll("[data-panel-pane]")) {
      pane.hidden = pane.dataset.panelPane !== name;
    }
    for (const button of panel.querySelectorAll("[data-panel-switch]")) {
      const on = button === chosen;
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", String(on));
    }
  });
})();

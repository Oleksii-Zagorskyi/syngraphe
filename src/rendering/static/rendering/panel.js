// The right panel's sections (DL-0536): each stands under its name, which collapses and opens it.
// Every section collapsed collapses the panel to its strip, where the names stay; a name there
// opens the panel on that section alone. The panel's own collapse is `outline.js`'s, through its
// toggle. Without this script every section stands open.
(() => {
  const sections = (panel) => [...panel.querySelectorAll(":scope > [data-section]")];

  const set = (section, open) => {
    section.classList.toggle("shut", !open);
    section.querySelector("[data-section-toggle]")?.setAttribute("aria-expanded", String(open));
  };

  const toggleOf = (panel) => document.querySelector(`[data-pane-toggle="${panel.id}"]`);

  document.addEventListener("click", (event) => {
    const name = event.target.closest("[data-section-toggle]");
    if (name) {
      const section = name.closest("[data-section]");
      const panel = section.closest(".panel");
      if (panel.classList.contains("shut")) {
        for (const each of sections(panel)) set(each, each === section);
        toggleOf(panel)?.click();
        return;
      }
      set(section, section.classList.contains("shut"));
      if (sections(panel).every((each) => each.classList.contains("shut"))) toggleOf(panel)?.click();
      return;
    }
    // The panel opened by its own toggle shows its sections, not a column of closed names.
    const toggle = event.target.closest("[data-pane-toggle]");
    const panel = toggle && document.getElementById(toggle.dataset.paneToggle);
    if (panel?.matches(".panel") && !panel.classList.contains("shut")) {
      const all = sections(panel);
      if (all.every((each) => each.classList.contains("shut"))) for (const each of all) set(each, true);
    }
  });
})();

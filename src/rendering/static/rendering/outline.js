// The side panes of the document page and the document list (DL-0195): each node of the outline
// or the folder tree collapses, each pane collapses, and a pane's edge drags to a width the person
// keeps.
// Without this script the outline is a list of links and the panes stand at their widths.
(() => {
  const csrf = () => {
    const cookie = document.cookie.split("; ").find((part) => part.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.slice("csrftoken=".length)) : "";
  };

  document.addEventListener("click", (event) => {
    const toggle = event.target.closest(".outline .toggle, .folder-tree .toggle");
    if (toggle) {
      const open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      toggle.textContent = open ? "▸" : "▾";
      toggle.setAttribute("aria-label", open ? toggle.dataset.expand : toggle.dataset.collapse);
      toggle.closest("li").classList.toggle("shut", open);
      return;
    }
    const shut = event.target.closest("[data-pane-toggle]");
    for (const over of document.querySelectorAll(".panes[data-narrow] > .over")) {
      if (!over.contains(event.target) && shut?.dataset.paneToggle !== over.id) close(over);
    }
    if (!shut) return;
    const pane = document.getElementById(shut.dataset.paneToggle);
    const layout = pane.closest(".panes");
    if (layout?.hasAttribute("data-narrow")) {
      if (pane.classList.contains("over")) close(pane);
      else openOver(layout, pane);
      return;
    }
    const closed = pane.classList.toggle("shut");
    expanded(pane);
    if (shut.dataset.keepShut) keep(shut.dataset.keepShut, closed);
    if (layout && fit(layout) && !closed) openOver(layout, pane);
  });

  // An outline entry whose heading id the text does not carry — the review page's marked text,
  // the editor, a comparison — scrolls to the heading its number names, else to the heading at its
  // place in the outline, resolved when clicked, so headings typed since are counted (DL-0527). A
  // heading drawn as removed is not one of the text's.
  document.addEventListener("click", (event) => {
    const link = event.target.closest(".outline a[href^='#']");
    if (!link || document.getElementById(decodeURIComponent(link.hash.slice(1)))) return;
    const centre = link.closest(".panes")?.querySelector(":scope > .centre");
    const text =
      centre?.querySelector(".ProseMirror") ||
      centre?.querySelector(".changes") ||
      centre?.querySelector(".document-text");
    if (!text) return;
    const all = [...text.querySelectorAll("h1, h2, h3, h4, h5, h6")];
    // The editor holds its headings alone; a marked text also draws the ones removed.
    const headings = text.matches(".ProseMirror") ? all : all.filter(standing);
    const label = link.querySelector(".num")?.textContent.trim();
    let heading = label && headings.find((h) => h.querySelector(".num")?.textContent.trim() === label);
    if (!heading) {
      const entries = [...link.closest(".outline").querySelectorAll("a[href^='#']")];
      heading = headings[entries.indexOf(link)];
    }
    if (!heading) return;
    event.preventDefault();
    heading.scrollIntoView({ block: "start" });
  });

  // A heading the newer text holds carries its number, an empty one included; a removed heading,
  // drawn as its struck words, carries none.
  const standing = (heading) => {
    if (heading.querySelector(".num")) return true;
    const words = heading.cloneNode(true);
    for (const gone of words.querySelectorAll("del")) gone.remove();
    return words.textContent.trim() !== "";
  };

  // A collapsed pane is a strip, and the person's collapse is kept (DL-0526); a pane the narrow
  // window collapses is not the person's choice, so nothing is sent for it and it opens again
  // when the window allows.
  const keep = (url, shut) =>
    fetch(url, {
      method: "POST",
      body: new URLSearchParams({ shut: shut ? "on" : "off" }),
      headers: { "X-CSRFToken": csrf() },
      credentials: "same-origin",
      redirect: "manual",
      keepalive: true,
    });

  const expanded = (pane) => {
    const toggle = document.querySelector(`[data-pane-toggle="${pane.id}"]`);
    if (toggle) toggle.setAttribute("aria-expanded", String(!pane.classList.contains("shut")));
  };

  const sides = (layout) =>
    [...layout.children].filter((child) => child.matches(".outline, .panel") && !child.hidden);

  const pixels = (layout, property, fallback) =>
    parseFloat(getComputedStyle(layout).getPropertyValue(property)) || fallback;

  const kept = (layout, pane) =>
    pane.matches(".outline")
      ? pixels(layout, "--outline-kept", 250)
      : pixels(layout, "--panel-kept", 280);

  // The narrow rule: the text's own minimum, each edge, each pane the person keeps open at its
  // kept width, each pane they keep collapsed as its strip.
  const narrow = (layout) => {
    let need = pixels(layout, "--text-min", 560);
    for (const edge of layout.querySelectorAll(":scope > .edge")) {
      if (getComputedStyle(edge).display !== "none") need += 6;
    }
    for (const pane of sides(layout)) {
      const open = !pane.classList.contains("shut") || "narrowed" in pane.dataset;
      need += open ? kept(layout, pane) : pixels(layout, "--pane-strip", 36);
    }
    return layout.clientWidth < need;
  };

  // Draws the panes for the window as it is; true when it has just turned narrow.
  const fit = (layout) => {
    const was = layout.hasAttribute("data-narrow");
    const now = narrow(layout);
    if (!now && !was) return false;
    layout.toggleAttribute("data-narrow", now);
    for (const pane of sides(layout)) {
      if (now && !pane.classList.contains("shut") && !pane.classList.contains("over")) {
        pane.classList.add("shut");
        pane.dataset.narrowed = "";
      } else if (!now) {
        // A pane the person keeps collapsed goes back to its strip; a narrowed one opens, its
        // sections with it, never as a column of closed names.
        const narrowed = "narrowed" in pane.dataset;
        if (pane.classList.contains("over") && !narrowed) pane.classList.add("shut");
        pane.classList.remove("over");
        if (narrowed) {
          pane.classList.remove("shut");
          const sections = [...pane.querySelectorAll(":scope > [data-section]")];
          if (sections.every((section) => section.classList.contains("shut"))) {
            for (const section of sections) {
              section.classList.remove("shut");
              const name = section.querySelector("[data-section-toggle]");
              if (name) name.setAttribute("aria-expanded", "true");
            }
          }
        }
        delete pane.dataset.narrowed;
      }
      expanded(pane);
    }
    return now && !was;
  };

  const openOver = (layout, pane) => {
    for (const other of layout.querySelectorAll(":scope > .over")) close(other);
    layout.style.setProperty("--over-top", `${Math.max(0, -layout.getBoundingClientRect().top)}px`);
    pane.classList.remove("shut");
    pane.classList.add("over");
    expanded(pane);
  };

  const close = (pane) => {
    pane.classList.remove("over");
    pane.classList.add("shut");
    expanded(pane);
  };

  const layouts = () => document.querySelectorAll(".panes:not(.list-panes)");
  const fitAll = () => {
    for (const layout of layouts()) fit(layout);
  };
  const start = () => {
    fitAll();
    // A pane revealed later — the draft's parts panel once the hold is taken — is fitted too.
    const watch = new MutationObserver(fitAll);
    for (const layout of layouts()) {
      for (const pane of sides(layout).concat([...layout.querySelectorAll(":scope > [hidden]")])) {
        watch.observe(pane, { attributes: true, attributeFilter: ["hidden"] });
      }
    }
    window.addEventListener("resize", fitAll);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();

  document.addEventListener("pointerdown", (event) => {
    const edge = event.target.closest("[data-drag]");
    if (!edge) return;
    const layout = edge.closest(".panes");
    const property = edge.dataset.drag;
    const pane = document.getElementById(edge.dataset.pane);
    const min = Number(edge.dataset.min);
    const max = Number(edge.dataset.max);
    const start = event.clientX;
    const from = pane.getBoundingClientRect().width;
    const sign = edge.dataset.side === "right" ? -1 : 1;
    let width = from;
    edge.setPointerCapture(event.pointerId);
    const move = (moved) => {
      width = Math.round(Math.min(max, Math.max(min, from + sign * (moved.clientX - start))));
      layout.style.setProperty(property, `${width}px`);
    };
    const up = () => {
      edge.removeEventListener("pointermove", move);
      edge.removeEventListener("pointerup", up);
      if (!edge.dataset.keep || width === from) return;
      const body = new URLSearchParams({ width: String(width) });
      fetch(edge.dataset.keep, {
        method: "POST",
        body,
        headers: { "X-CSRFToken": csrf() },
        credentials: "same-origin",
        redirect: "manual",
      });
    };
    edge.addEventListener("pointermove", move);
    edge.addEventListener("pointerup", up);
  });
})();

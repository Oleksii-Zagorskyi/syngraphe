// The document page's side panes (DL-0195): each outline node collapses, each pane collapses, and
// a pane's edge drags to a width the person keeps.
// Without this script the outline is a list of links and the panes stand at their widths.
(() => {
  const csrf = () => {
    const cookie = document.cookie.split("; ").find((part) => part.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.slice("csrftoken=".length)) : "";
  };

  document.addEventListener("click", (event) => {
    const toggle = event.target.closest(".outline .toggle");
    if (toggle) {
      const open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      toggle.textContent = open ? "▸" : "▾";
      toggle.closest("li").classList.toggle("shut", open);
      return;
    }
    const shut = event.target.closest("[data-pane-toggle]");
    if (shut) {
      const pane = document.getElementById(shut.dataset.paneToggle);
      const closed = pane.classList.toggle("shut");
      shut.setAttribute("aria-expanded", String(!closed));
    }
  });

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

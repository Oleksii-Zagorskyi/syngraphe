// Capture without a Save control (ASR-22): the editor's text is posted after a pause in typing, at
// once when it loses focus or its page is hidden, and taken only while the draft still holds what
// this editor last saw. The indicator says what happened — capturing, captured, not captured and
// retrying, signed out, too large, or stopped because the draft changed elsewhere — and success is
// shown only on the server's acceptance (DL-0320, DL-0328). The text is never cleared on a failure, and the
// editor is never left for the finishing screen while text of its own is not captured.

const RETRY_FIRST_MS = 2000;
const RETRY_MOST_MS = 30000;
// A request that has not answered by then is abandoned and retried.
const REQUEST_MOST_MS = 20000;
// Browsers refuse a `keepalive` request whose body is over 64 KiB; one over this is sent plainly.
const KEEPALIVE_MOST_BYTES = 60 * 1024;

// The CSRF token as it is now: signing in again in another tab replaces it, so the cookie is read
// on every request and the page's own field is the fallback.
function csrfToken(element) {
  const cookie = document.cookie.split("; ").find((part) => part.startsWith("csrftoken="));
  if (cookie) return decodeURIComponent(cookie.slice("csrftoken=".length));
  const field = element.closest("section, body").querySelector("input[name=csrfmiddlewaretoken]");
  return field ? field.value : "";
}

// The capture of one editor: `changed` after each edit, `flush` to send now, `finish` before the
// finishing screen — true only once everything typed is captured and the editor closed.
export function capturing({ element, editor, words, disable }) {
  const settings = words.capture;
  const indicator = document.createElement("span");
  indicator.className = "capture-indicator";
  indicator.setAttribute("role", "status");
  indicator.dataset.state = "captured";
  indicator.textContent = words.notices.captured;
  const urls = element.dataset;

  let base = editor.draft.base_hash;
  let sent = editor.markdown();
  let timer = null;
  let retryIn = RETRY_FIRST_MS;
  let stopped = false;
  let inFlight = null;

  function show(state) {
    indicator.dataset.state = state;
    indicator.textContent = words.notices[state];
  }

  function post(url, body, keepalive = false) {
    const payload = JSON.stringify(body);
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      keepalive: keepalive && new Blob([payload]).size <= KEEPALIVE_MOST_BYTES,
      signal: AbortSignal.timeout(REQUEST_MOST_MS),
      headers: { "X-CSRFToken": csrfToken(element), "Content-Type": "application/json" },
      body: payload,
    });
  }

  // The editor was closed on the server — silent too long, a laptop asleep: open a new one on
  // the draft, and carry on only when the draft is still what this editor last captured.
  async function reopen() {
    let response;
    try {
      response = await post(urls.load, {});
    } catch {
      return false;
    }
    if (!response.ok) return false;
    const loaded = await response.json();
    if (loaded.base_hash !== base) return false;
    editor.draft.editor = loaded.editor;
    return true;
  }

  function stop() {
    stopped = true;
    clearTimeout(timer);
    show("stale");
    disable();
  }

  // One capture of what is typed now; its outcome.
  async function send(keepalive = false, close = false) {
    if (stopped) return "stopped";
    const text = editor.markdown();
    if (text === sent && !close) {
      if (indicator.dataset.state !== "too_large") show("captured");
      return "captured";
    }
    show("capturing");
    let response;
    try {
      const body = { editor: editor.draft.editor, base_hash: base, body: text, close };
      response = await post(urls.capture, body, keepalive);
    } catch {
      retry();
      return "failed";
    }
    if (response.redirected || response.status === 401 || response.status === 403) {
      show("signed_out");
      retry();
      return "signed_out";
    }
    if (response.status === 409) {
      const reason = await response.json().catch(() => ({}));
      if (reason.closed && !close && (await reopen())) return send(keepalive);
      stop();
      return "stale";
    }
    if (response.status === 413) {
      // Retrying cannot help: the text must shrink first, and the next edit tries again.
      clearTimeout(timer);
      show("too_large");
      return "too_large";
    }
    if (!response.ok) {
      show("failed");
      retry();
      return "failed";
    }
    base = (await response.json()).base_hash;
    sent = text;
    retryIn = RETRY_FIRST_MS;
    if (editor.markdown() === sent) {
      show("captured");
      return "captured";
    }
    show("capturing");
    schedule();
    return "failed";
  }

  function retry() {
    if (indicator.dataset.state !== "signed_out") show("failed");
    clearTimeout(timer);
    timer = setTimeout(flush, retryIn);
    retryIn = Math.min(retryIn * 2, RETRY_MOST_MS);
  }

  // Send what is typed now, one request at a time; the outcome of the last.
  function flush(keepalive = false) {
    clearTimeout(timer);
    if (inFlight) return inFlight.then(() => flush(keepalive));
    inFlight = send(keepalive).finally(() => {
      inFlight = null;
    });
    return inFlight;
  }

  function schedule() {
    if (stopped) return;
    if (indicator.dataset.state === "captured") show("capturing");
    clearTimeout(timer);
    timer = setTimeout(flush, settings.pause_seconds * 1000);
  }

  async function beat() {
    if (stopped) return;
    try {
      const response = await post(urls.heartbeat, { editor: editor.draft.editor });
      if (response.ok) {
        editor.others = (await response.json()).others;
        element.dispatchEvent(new CustomEvent("editor-heartbeat", { detail: { others: editor.others } }));
      } else if (response.status === 409) {
        if (!(await reopen())) stop();
      } else if (response.redirected) show("signed_out");
    } catch {
      // The next beat tries again; a capture failure is what the indicator reports.
    }
  }

  function close(keepalive = false) {
    stopped = true;
    clearTimeout(timer);
    return post(urls.close, { editor: editor.draft.editor }, keepalive).catch(() => null);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush(true);
  });
  // The page going away: what is typed and the editor's close travel in one request, so neither
  // waits on the other's answer, which a closing page never receives.
  window.addEventListener("pagehide", () => {
    if (stopped) return;
    stopped = true;
    clearTimeout(timer);
    if (editor.markdown() !== sent) {
      const body = { editor: editor.draft.editor, base_hash: base, body: editor.markdown(), close: true };
      post(urls.capture, body, true).catch(() => null);
    } else {
      post(urls.close, { editor: editor.draft.editor }, true).catch(() => null);
    }
  });
  // A page brought back from the browser's cache is an editor whose server side has closed.
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) window.location.reload();
  });
  const heart = setInterval(beat, settings.heartbeat_seconds * 1000);
  beat();

  return {
    indicator,
    changed: schedule,
    flush,
    async finish() {
      const outcome = await flush();
      if (outcome !== "captured" || editor.markdown() !== sent) return false;
      clearInterval(heart);
      await close();
      return true;
    },
  };
}

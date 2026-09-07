/** Shared native inbox contract. No generator/queue endpoint is called here. */
(() => {
  const labels = {
    prompt: "Prompt",
    negativePrompt: "Negative prompt",
    seed: "Seed",
    steps: "Steps",
    cfg: "CFG",
    width: "Width",
    height: "Height",
    sampler: "Sampler",
    scheduler: "Scheduler",
    clipSkip: "CLIP skip",
    shift: "Shift",
    betaAlpha: "Beta alpha",
    betaBeta: "Beta beta",
    checkpoint: "Checkpoint",
    vae: "VAE",
    modules: "VAE / Text encoder",
    loras: "LoRAs",
  };
  const errors = {
    DRAFT_PERMISSION_REQUIRED:
      "Allow generator drafts for this device in the Arc Link Hub.",
    WORKER_OFFLINE: "Reconnect Link on this generator, then refresh.",
    RECHECK_REQUIRED:
      "The source or host changed. Check and send a new draft from Arc.",
    STALE_RUNTIME:
      "This draft belongs to a previous runtime. Send it again from Arc.",
    EDITOR_ALREADY_CLAIMED: "Another editor tab already claimed this draft.",
    HANDOFF_NOT_PENDING:
      "This draft has already been handled. Refresh the inbox.",
    HANDOFF_EXPIRED: "This draft expired. Send a new draft from Arc.",
    DRAFT_UPDATE_REQUIRED:
      "Update Link to use resource selection and confirm this draft.",
    INVALID_RESOURCE_SELECTION:
      "This resource was excluded when sending. Keep it excluded or send a new draft.",
    LINK_INBOX_UNAVAILABLE:
      "The Link inbox is temporarily unavailable. Retry after reconnecting.",
  };
  const states = {
    RECEIVED: "Waiting to apply",
    CLAIMED: "Claimed by an editor",
    APPLIED: "Applied",
    UNDONE: "Previous draft restored",
    FAILED: "Import failed",
    CANCELLED: "Cancelled",
    EXPIRED: "Expired",
    INVALIDATED: "Previous runtime · inspect your editor",
  };
  const el = (tag, text, className) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (className) n.className = className;
    return n;
  };
  const icon = (name) => {
    const paths = {
      link: "M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-2 2 M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l2-2",
      refresh:
        "M20 7v5h-5 M4 17v-5h5 M6 7a7 7 0 0112-1l2 6 M4 12l2 6a7 7 0 0012-1",
      apply: "M4 12h16 M13 5l7 7-7 7",
      close: "M6 6l12 12 M6 18L18 6",
      undo: "M9 4L3 10l6 6 M3 10h11a7 7 0 017 7",
      backup: "M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5",
      clock: "M12 8v4l3 2 M21 12a9 9 0 11-18 0 9 9 0 0118 0",
    };
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "1.8");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", paths[name] || paths.apply);
    svg.append(path);
    return svg;
  };
  const button = (text, fn, symbol) => {
    const n = el("button", text);
    n.type = "button";
    if (symbol) n.prepend(icon(symbol));
    n.addEventListener("click", fn);
    return n;
  };
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const equalFields = (a, b) =>
    equal(Object.entries(a).sort(), Object.entries(b).sort());
  function resourceFields(fields, selection, before = {}, forge = false) {
    const result = { ...fields };
    if (!selection.checkpoint) delete result.checkpoint;
    if (!selection.modules) {
      delete result.modules;
      delete result.vae;
    }
    if (!selection.loras) {
      delete result.loras;
      for (const name of ["prompt", "negativePrompt"]) {
        if (typeof result[name] !== "string") continue;
        const tokens = () => /<(?:lora|lyco):[^<>\r\n]+>/gi;
        const text = result[name].replace(tokens(), "").trim();
        const kept = forge
          ? [...new Set((before[name] || "").match(tokens()) || [])]
          : [];
        result[name] = [text, ...kept].filter(Boolean).join(" ");
      }
    }
    return result;
  }
  const editorId = crypto.randomUUID();
  function save(id, data) {
    try {
      sessionStorage.setItem(
        `aec-link-draft:${id}`,
        JSON.stringify({ ...data, savedAt: new Date().toISOString() }),
      );
    } catch {
      throw new Error(
        "Your browser could not save the previous draft. Export or remove older local backups in the inbox, and allow session storage before trying again.",
      );
    }
  }
  function saved(id) {
    try {
      return JSON.parse(
        sessionStorage.getItem(`aec-link-draft:${id}`) || "null",
      );
    } catch {
      return null;
    }
  }
  const style = el(
    "style",
    `
.aec-drafts{font:14px/1.45 var(--font,system-ui,sans-serif);color:var(--body-text-color,inherit);width:100%;min-width:0;box-sizing:border-box}
#aec-link-draft-inbox{border:1px solid var(--border-color-primary,#71839960);border-radius:12px;background:var(--block-background-fill,#71839908);padding:12px;margin:8px 0}
.aec-drafts *{box-sizing:border-box}.aec-drafts svg{width:18px;height:18px;flex:none;display:inline-block;vertical-align:middle}
.aec-drafts button{font:inherit!important;display:inline-flex!important;align-items:center;justify-content:center;gap:6px;border:1px solid var(--border-color-primary,#71839960)!important;background:var(--button-secondary-background-fill,#71839918);color:inherit;padding:7px 11px!important;border-radius:8px!important;cursor:pointer;min-height:36px;line-height:1.4!important;width:auto;margin:0!important;white-space:normal}
.aec-drafts [hidden]{display:none!important}.aec-drafts .aec-short-label{display:none}.aec-drafts button:hover{background:var(--button-secondary-background-fill-hover,#71839932)}.aec-drafts button:focus-visible,.aec-drafts a:focus-visible,.aec-drafts summary:focus-visible{outline:2px solid #38bdf8;outline-offset:3px}.aec-drafts button:disabled{opacity:.5;cursor:default}
.aec-drafts button.aec-primary{background:var(--button-primary-background-fill,#0369a1);color:var(--button-primary-text-color,#fff);border-color:#38bdf866!important}
.aec-drafts h3{font-size:16px!important;font-weight:600;margin:0!important}.aec-drafts a{color:var(--link-text-color,#52bdff);text-decoration:none;overflow-wrap:anywhere}.aec-drafts a:hover{text-decoration:underline}.aec-drafts p{overflow-wrap:anywhere;margin:5px 0;font-size:13px}
.aec-drafts .aec-toolbar,.aec-drafts .aec-title,.aec-drafts .aec-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.aec-drafts .aec-toolbar{justify-content:space-between;gap:10px}.aec-drafts .aec-title>svg{color:#38bdf8}
.aec-drafts .aec-muted{opacity:.7}.aec-drafts .aec-connection{font-size:12px;padding:3px 8px;border-radius:99px;background:#71839918}.aec-drafts .aec-connection[data-ready=true]{color:#16a34a;background:#22c55e15}
.aec-drafts .aec-notice{border-left:3px solid #38bdf8;padding:6px 10px;margin:8px 0;background:#38bdf80a}.aec-drafts .aec-notice[data-error=true]{border-color:#f59e0b}.aec-drafts .aec-notice:empty{display:none}
.aec-drafts .aec-tabs{display:flex;gap:5px;margin:10px 0 4px;border-top:1px solid #71839930;padding-top:8px}.aec-drafts .aec-tabs button{font-size:12px!important;border-color:transparent!important;background:transparent;padding:5px 9px!important}.aec-drafts .aec-tabs button[aria-pressed=true]{background:#38bdf818;color:var(--link-text-color,#38bdf8)}
.aec-drafts .aec-list{max-height:340px;overflow:auto;overscroll-behavior:contain;scrollbar-gutter:stable}.aec-drafts .aec-card{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid #71839926}.aec-drafts .aec-card:last-child{border:0}.aec-drafts .aec-card-main{min-width:0}.aec-drafts .aec-card-main>a{font-weight:600}.aec-drafts .aec-card .aec-actions{flex-shrink:0}.aec-drafts .aec-card time{font-size:12px;opacity:.65}.aec-drafts .aec-empty{padding:10px 0}
.aec-drafts .aec-backups{font-size:12px;margin-top:8px}.aec-drafts summary{cursor:pointer}.aec-drafts .aec-backups article{padding:8px;border-top:1px solid #71839930}.aec-drafts .aec-more{margin-top:8px!important;font-size:12px!important}
.aec-draft-modal{border:1px solid #71839980;border-radius:14px;background:var(--background-fill-primary,#171e29);color:var(--body-text-color,#e8eef7);padding:0;width:min(720px,calc(100vw - 24px));max-height:calc(100dvh - 24px);margin:auto;overflow:hidden}
.aec-draft-modal::backdrop{background:#0009}.aec-draft-modal[open]{display:flex;flex-direction:column}.aec-draft-modal .aec-draft-header,.aec-draft-modal .aec-draft-footer{padding:14px 18px;border-block:1px solid #71839930;flex-shrink:0}.aec-draft-modal .aec-draft-body{min-height:0;padding:12px 18px;overflow-y:auto;overscroll-behavior:contain}.aec-draft-modal .aec-draft-body article{padding:10px;border:1px solid #71839940;border-radius:10px;margin:8px 0}.aec-draft-modal label{display:flex;gap:10px;align-items:start}.aec-draft-modal input[type=checkbox]{width:18px;height:18px;flex-shrink:0}.aec-draft-modal pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:110px;overflow-y:auto;font:12px/1.5 var(--font,system-ui)}.aec-draft-modal .aec-before{opacity:.65}.aec-draft-modal .aec-warning{color:var(--color-accent,#d99a30);padding:0 18px}.aec-draft-modal .aec-draft-body .aec-warning{padding:0}.aec-draft-modal .aec-draft-footer{justify-content:flex-end}
@media(min-width:601px){.aec-draft-modal .aec-draft-body{display:grid;grid-template-columns:1fr 1fr;gap:0 10px}.aec-draft-modal .aec-draft-body>p,.aec-draft-modal .aec-draft-body>button,.aec-draft-modal article[data-field=prompt],.aec-draft-modal article[data-field=negativePrompt],.aec-draft-modal article[data-field=modules]{grid-column:1/-1}}
@media(max-width:600px){.aec-drafts .aec-full-label{display:none}.aec-drafts .aec-short-label{display:inline}.aec-drafts button{min-height:44px}.aec-drafts .aec-card{align-items:flex-start;flex-wrap:wrap}.aec-drafts .aec-card>.aec-actions{width:100%}.aec-drafts .aec-card>.aec-actions>button:first-child{flex:1}.aec-drafts .aec-toolbar{align-items:flex-start}.aec-drafts .aec-title{gap:6px}.aec-drafts .aec-list{max-height:360px}.aec-draft-modal .aec-draft-footer button{flex:1}}
`,
  );
  style.textContent += `
.aec-resource-selection{border:1px solid var(--block-border-color,#475569);border-radius:10px;padding:12px;display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
.aec-draft-modal .aec-resource-selection{grid-column:1/-1}.aec-resource-selection legend{font-weight:600}.aec-resource-selection label{display:flex;align-items:center;gap:8px;min-height:44px;padding:0 8px}.aec-resource-selection p{width:100%;font-size:.85em;opacity:.75}
.aec-history-actions summary{cursor:pointer;min-height:44px;display:flex;align-items:center;padding:0 10px}.aec-history-actions[open]{max-width:100%}.aec-history-actions>.aec-actions{flex-wrap:wrap}.aec-history-actions button{min-height:44px}
#aec-link-draft-inbox.aec-drafts{border:0;padding:8px}.aec-resource-selection input{width:18px;height:18px}
`;
  if (!document.getElementById("aec-link-draft-style")) {
    style.id = "aec-link-draft-style";
    document.head.append(style);
  }
  window.AECLinkDrafts = {
    async request(action, body = {}) {
      const response = await fetch(`arcenciel-link/editor/${action}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AEC-Link-Editor": "1",
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(25000),
      });
      const data = await response.json();
      if (!response.ok)
        throw Object.assign(
          new Error(
            errors[data.code] ||
              `Link request failed (${response.status}). Refresh to check its state.`,
          ),
          { code: data.code },
        );
      return data;
    },
    mount(container, adapter) {
      container.classList.add("aec-drafts");
      let busy = false,
        disposed = false,
        reviewing = false;
      let items = [],
        view = "waiting",
        limit = 5,
        ready = !adapter.ready,
        readinessError,
        lastCheck = 0;
      let lastRendered = "";
      const reports = new Map();
      const toolbar = el("div", undefined, "aec-toolbar");
      const title = el("div", undefined, "aec-title");
      const badge = el(
        "span",
        adapter.ready ? "Checking editor…" : "Review in this editor",
        "aec-connection",
      );
      title.append(
        ...(adapter.accordion ? [] : [icon("link"), el("h3", "Link inbox")]),
        badge,
      );
      const controls = el("div", undefined, "aec-actions");
      const refreshButton = button(
        "Check connection",
        () => {
          lastCheck = 0;
          void refresh(true);
        },
        "refresh",
      );
      const reloadButton = button(
        "Reload Forge",
        () => location.reload(),
        "refresh",
      );
      reloadButton.hidden = true;
      controls.append(refreshButton, reloadButton);
      toolbar.append(title, controls);
      const status = el("p", undefined, "aec-notice");
      status.setAttribute("role", "status");
      const hint = el("p", undefined, "aec-muted");
      const tabs = el("div", undefined, "aec-tabs");
      tabs.setAttribute("aria-label", "Draft filters");
      const waitingButton = button("Waiting", () => {
        view = "waiting";
        limit = 5;
        render();
      });
      const historyButton = button(
        "History",
        () => {
          view = "history";
          limit = 5;
          render();
        },
        "clock",
      );
      tabs.append(waitingButton, historyButton);
      const list = el("div", undefined, "aec-list");
      const more = button("Show more", () => {
        limit += 5;
        render();
      });
      more.classList.add("aec-more");
      function notice(message, failure = false) {
        status.textContent = message;
        status.dataset.error = String(failure);
      }
      function exportBackup(id, data) {
        const url = URL.createObjectURL(
          new Blob([JSON.stringify(data.before, null, 2)], {
            type: "application/json",
          }),
        );
        const a = el("a");
        a.href = url;
        a.download = `link-editor-backup-${id}.json`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      function localRows() {
        const local = [];
        try {
          for (let n = 0; n < sessionStorage.length; n++) {
            const key = sessionStorage.key(n);
            if (!key?.startsWith("aec-link-draft:")) continue;
            const id = key.slice(15),
              data = saved(id);
            if (data?.before && !items.some((i) => i.id === id))
              local.push({
                id,
                imageId: data.imageId,
                createdAt: data.savedAt,
                state: "LOCAL",
                localOnly: true,
              });
          }
        } catch {
          /* Applying reports storage errors before replacing anything. */
        }
        return local;
      }
      container.replaceChildren(toolbar, status, hint, tabs, list, more);
      const visibility = () => {
        if (!document.hidden) void refresh();
      };
      document.addEventListener("visibilitychange", visibility);
      async function report(item, code) {
        if (!item || item.state !== "RECEIVED") return;
        const previous = reports.get(item.id);
        if (previous?.code === code && Date.now() - previous.at < 60000) return;
        reports.set(item.id, { code, at: Date.now() });
        try {
          await window.AECLinkDrafts.request("event", {
            id: item.id,
            editorId,
            action: "diagnostic",
            receipt: { code },
          });
          reports.set(item.id, { code, at: Date.now() });
        } catch {
          /* A legacy server or another editor may have handled it. */
        }
      }
      function reason(item) {
        if (item.localOnly)
          return "Saved in this browser tab · server entry unavailable";
        if (item.state !== "RECEIVED") return states[item.state] || item.state;
        if (readinessError) return readinessError.message;
        return ready ? "Waiting for your confirmation" : "Checking the editor…";
      }
      async function cancelItem(item, control) {
        control.disabled = true;
        try {
          await window.AECLinkDrafts.request("event", {
            id: item.id,
            editorId,
            action: "cancel",
          });
          items = items.filter((i) => i.id !== item.id);
          notice("Draft cancelled.");
          render();
        } catch (e) {
          notice(e.message, true);
        } finally {
          control.disabled = false;
        }
      }
      function render() {
        if (disposed) return;
        badge.textContent = readinessError
          ? "Editor needs attention"
          : !ready
            ? "Checking editor…"
            : "Editor connected";
        badge.dataset.ready = String(ready);
        reloadButton.hidden = readinessError?.code !== "EDITOR_STALE";
        hint.textContent =
          "Received drafts wait for your confirmation. Nothing is applied or generated automatically.";
        const waiting = items.filter((i) =>
          ["RECEIVED", "CLAIMED"].includes(i.state),
        );
        const history = [
          ...items.filter((i) => !["RECEIVED", "CLAIMED"].includes(i.state)),
          ...localRows(),
        ].sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
        adapter.status?.({
          waiting: waiting.length,
          ready,
          needsAttention: Boolean(readinessError),
        });
        waitingButton.textContent = `Waiting (${waiting.length})`;
        historyButton.replaceChildren(
          icon("clock"),
          document.createTextNode(`History (${history.length})`),
        );
        waitingButton.setAttribute("aria-pressed", String(view === "waiting"));
        historyButton.setAttribute("aria-pressed", String(view === "history"));
        const visible = (view === "waiting" ? waiting : history).slice(
          0,
          limit,
        );
        const signature =
          JSON.stringify(
            visible.map((i) => [
              i.id,
              i.state,
              reason(i),
              saved(i.id)?.stage,
              Boolean(saved(i.id)?.before),
            ]),
          ) + view;
        more.hidden = (view === "waiting" ? waiting : history).length <= limit;
        if (signature === lastRendered) return;
        lastRendered = signature;
        const scroll = list.scrollTop,
          focused = document.activeElement;
        const focusedId =
            focused?.closest?.("[data-handoff-id]")?.dataset.handoffId,
          focusedAction = focused?.textContent;
        const cards = visible.map((item) => {
          const card = el("article", undefined, "aec-card");
          card.dataset.handoffId = item.id;
          const main = el("div", undefined, "aec-card-main");
          const link = el("a", `Image #${item.imageId}`);
          link.href = `https://arcenciel.io/images/${item.imageId}`;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          const time = el("time", new Date(item.createdAt).toLocaleString());
          time.dateTime = item.createdAt;
          main.append(link, el("p", reason(item)), time);
          const actions = el("div", undefined, "aec-actions"),
            receipt = saved(item.id);
          if (item.state === "RECEIVED") {
            const apply = button(
              adapter.direct ? "Apply to txt2img" : "Review draft",
              () => void review(item),
              "apply",
            );
            apply.disabled = !ready || receipt?.stage === "applying";
            apply.classList.add("aec-primary");
            apply.setAttribute(
              "aria-label",
              adapter.direct ? "Apply to txt2img" : "Review draft",
            );
            apply.replaceChildren(
              icon("apply"),
              el(
                "span",
                adapter.direct ? "Apply to txt2img" : "Review draft",
                "aec-full-label",
              ),
              el(
                "span",
                adapter.direct ? "Apply" : "Review",
                "aec-short-label",
              ),
            );
            const cancel = button(
              "Cancel",
              () => void cancelItem(item, cancel),
              "close",
            );
            actions.append(apply, cancel);
          }
          if (receipt?.stage === "applying" && item.state === "CLAIMED") {
            actions.append(
              button(
                "Check outcome",
                async () => {
                  try {
                    const current = await adapter.snapshot();
                    const actual = await adapter.read(
                      Object.keys(receipt.fields),
                    );
                    if (!equal(actual, receipt.fields)) {
                      notice(
                        "The editor does not match this draft. Keep the backup and inspect your settings; nothing was applied again.",
                        true,
                      );
                      return;
                    }
                    save(item.id, {
                      ...receipt,
                      stage: "applied",
                      after: current,
                    });
                    await window.AECLinkDrafts.request("event", {
                      id: item.id,
                      editorId: receipt.editorId,
                      action: "applied",
                      receipt: { fields: actual },
                    });
                    notice(
                      "The editor values are confirmed. Undo is now available.",
                    );
                    await refresh(true);
                  } catch (e) {
                    notice(e.message, true);
                  }
                },
                "refresh",
              ),
            );
          }
          if (
            receipt?.stage === "applied" &&
            ["CLAIMED", "APPLIED"].includes(item.state)
          ) {
            if (item.state === "CLAIMED")
              actions.append(
                button(
                  "Confirm receipt",
                  async () => {
                    try {
                      await window.AECLinkDrafts.request("event", {
                        id: item.id,
                        editorId: receipt.editorId,
                        action: "applied",
                        receipt: { fields: receipt.fields },
                      });
                      await refresh(true);
                    } catch (e) {
                      notice(e.message, true);
                    }
                  },
                  "refresh",
                ),
              );
            actions.append(
              button(
                "Undo",
                async () => {
                  try {
                    if (!equal(await adapter.snapshot(), receipt.after))
                      throw new Error(
                        "Your editor changed since import. Export the backup to keep your newer work.",
                      );
                    if (item.state === "CLAIMED")
                      await window.AECLinkDrafts.request("event", {
                        id: item.id,
                        editorId: receipt.editorId,
                        action: "applied",
                        receipt: { fields: receipt.fields },
                      });
                    await adapter.restore(receipt.before);
                    if (!equal(await adapter.snapshot(), receipt.before))
                      throw new Error(
                        "The editor did not confirm the restored values. Keep your backup.",
                      );
                    save(item.id, { ...receipt, stage: "undone" });
                    await window.AECLinkDrafts.request("event", {
                      id: item.id,
                      editorId: receipt.editorId,
                      action: "undone",
                    });
                    notice("Previous txt2img settings restored.");
                    await refresh(true);
                  } catch (e) {
                    notice(e.message, true);
                  }
                },
                "undo",
              ),
            );
          }
          if (receipt?.before) {
            const menu = el("details", undefined, "aec-history-actions");
            menu.append(el("summary", "More"));
            const group = el("div", undefined, "aec-actions");
            const remove = button(
              "Remove backup",
              () => {
                if (remove.dataset.confirm !== "true") {
                  remove.dataset.confirm = "true";
                  remove.textContent = "Remove backup and Undo?";
                  return;
                }
                sessionStorage.removeItem(`aec-link-draft:${item.id}`);
                lastRendered = "";
                render();
              },
              "close",
            );
            remove.disabled = receipt.stage === "applying";
            group.append(
              button(
                "Export backup",
                () => exportBackup(item.id, receipt),
                "backup",
              ),
              remove,
            );
            menu.append(group);
            actions.append(menu);
          }
          card.append(main, actions);
          return card;
        });
        if (!cards.length)
          cards.push(
            el(
              "p",
              view === "waiting"
                ? "No waiting drafts. Choose “Send to Link” on an image in Arc."
                : "Applied and completed drafts will appear here.",
              "aec-empty aec-muted",
            ),
          );
        list.replaceChildren(...cards);
        list.scrollTop = scroll;
        if (focusedId && focusedAction) {
          const card = [...list.children].find(
            (c) => c.dataset.handoffId === focusedId,
          );
          [...(card?.querySelectorAll("button") || [])]
            .find((b) => b.textContent === focusedAction)
            ?.focus({ preventScroll: true });
        }
      }
      async function refresh(manual = false) {
        if (busy || reviewing || disposed) return;
        busy = true;
        if (manual) refreshButton.disabled = true;
        try {
          if (
            adapter.ready &&
            (manual ||
              (!ready && readinessError?.code !== "EDITOR_STALE") ||
              Date.now() - lastCheck > 30000)
          ) {
            lastCheck = Date.now();
            try {
              await adapter.ready();
              ready = true;
              readinessError = undefined;
            } catch (e) {
              ready = false;
              readinessError = e;
            }
          }
          const data = await window.AECLinkDrafts.request("inbox", {
            receiveOnly: true,
          });
          if (disposed) return;
          items = data.items;
          render();
          const pending = items.filter((i) => i.state === "RECEIVED");
          await Promise.all(
            pending.map((item) =>
              report(item, readinessError?.code || "WAITING_FOR_REVIEW"),
            ),
          );
          if (manual)
            notice(
              readinessError?.message ||
                "Inbox refreshed. Your current draft is preserved.",
              !!readinessError,
            );
        } catch (e) {
          if (!disposed) notice(e.message, true);
        } finally {
          busy = false;
          refreshButton.disabled = false;
          render();
        }
      }
      async function review(item, options = {}) {
        if (reviewing) return;
        reviewing = true;
        const focus = document.activeElement;
        const dialog = el("dialog", undefined, "aec-draft-modal aec-drafts");
        dialog.setAttribute("aria-label", "Review Link draft");
        const header = el("div", undefined, "aec-draft-header");
        header.append(
          el("h3", "Review before applying"),
          el("p", `Image #${item.imageId} · this editor tab`),
        );
        const main = el("div", undefined, "aec-draft-body");
        const message = el("p", undefined, "aec-warning");
        message.setAttribute("role", "status");
        const footer = el("div", undefined, "aec-actions aec-draft-footer");
        let applying = false,
          closed = false;
        const close = () => {
          if (applying) return;
          closed = true;
          dialog.close();
          dialog.remove();
          reviewing = false;
          void refresh();
          focus?.focus({ preventScroll: true });
        };
        dialog.addEventListener("cancel", (e) => {
          e.preventDefault();
          close();
        });
        const cancel = button("Close", close, "close");
        const apply = button("Save previous draft & apply", async () => {
          if (applying) return;
          let fields = Object.fromEntries(
            [...main.querySelectorAll("[data-field] input:checked")].map(
              (input) => [input.value, item.payload.fields[input.value]],
            ),
          );
          if (!Object.keys(fields).length) {
            message.textContent = "Select at least one available field.";
            return;
          }
          applying = true;
          apply.disabled = true;
          cancel.disabled = true;
          let claimed = false,
            mutated = false,
            nativeApplied = false;
          try {
            if (!equal(await adapter.snapshot(), before))
              throw new Error(
                "Your editor changed. Close and review this draft again.",
              );
            const previous = saved(item.id);
            if (previous && ["applying", "applied"].includes(previous.stage))
              throw new Error(
                "An import was already started in this tab. Refresh the inbox and inspect the editor before continuing.",
              );
            // Storage failure blocks replacement, so the previous draft is always retained.
            save(item.id, {
              imageId: item.imageId,
              before,
              fields,
              editorId,
              stage: "prepared",
            });
            const expectedFields = resourceFields(
              fields,
              selection,
              before,
              adapter.direct,
            );
            if (!Object.keys(expectedFields).length)
              throw new Error("Select at least one field to apply.");
            const claim = await window.AECLinkDrafts.request("event", {
              id: item.id,
              editorId,
              action: "claim",
              fields: Object.keys(fields),
              ...(selectionEnabled
                ? {
                    resourceSelection: selection,
                    ...(adapter.direct && !selection.loras
                      ? {
                          localPrompts: {
                            prompt: before.prompt || "",
                            negativePrompt: before.negativePrompt || "",
                          },
                        }
                      : {}),
                  }
                : {}),
            });
            claimed = true;
            if (selectionEnabled) {
              if (
                !claim.receipt?.fields ||
                !equalFields(claim.receipt.fields, expectedFields)
              )
                throw new Error(
                  "The server did not confirm the resource selection. Update Link before applying.",
                );
              fields = claim.receipt.fields;
            }
            claimed = true;
            if (!equal(await adapter.snapshot(), before))
              throw new Error(
                "Your editor changed while claiming the draft. Review a new handoff.",
              );
            save(item.id, {
              imageId: item.imageId,
              before,
              fields,
              editorId,
              stage: "applying",
            });
            mutated = true;
            await adapter.apply(fields, { ...options, before });
            nativeApplied = true;
            const actual = await adapter.read(Object.keys(fields));
            if (!equalFields(actual, fields))
              throw new Error(
                "The editor did not accept all selected values. The previous draft will be restored.",
              );
            const after = await adapter.snapshot();
            save(item.id, {
              imageId: item.imageId,
              before,
              after,
              fields: actual,
              editorId,
              stage: "applied",
            });
            try {
              await window.AECLinkDrafts.request("event", {
                id: item.id,
                editorId,
                action: "applied",
                receipt: { fields: actual },
              });
              message.textContent =
                "Settings applied for your next generation. Undo is available in History.";
            } catch {
              message.textContent =
                "Applied locally; the server receipt is pending. Close and use “Confirm editor receipt”. Do not import again.";
            }
            apply.hidden = true;
            view = "history";
          } catch (e) {
            if (
              e.uncertain ||
              (nativeApplied &&
                ["EDITOR_TIMEOUT", "BRIDGE_NOT_READY", "EDITOR_STALE"].includes(
                  e.code,
                ))
            ) {
              message.textContent =
                "Forge's confirmation is missing. Keep this backup and inspect txt2img before retrying; this draft will not be applied again automatically.";
              apply.hidden = true;
              return;
            }
            if (!claimed) void report(item, e.code || "EDITOR_IMPORT_FAILED");
            if (mutated && !e.unchanged) {
              try {
                await adapter.restore(before);
                save(item.id, {
                  imageId: item.imageId,
                  before,
                  editorId,
                  stage: "restored",
                });
              } catch {
                message.textContent =
                  "Import interrupted. Export the saved backup from the inbox before changing this editor.";
                applying = false;
                cancel.disabled = false;
                return;
              }
            }
            if (claimed) {
              try {
                await window.AECLinkDrafts.request("event", {
                  id: item.id,
                  editorId,
                  action: "failed",
                });
              } catch {
                /* No automatic second apply. */
              }
            }
            message.textContent =
              e.message +
              (e.field ? ` Field: ${labels[e.field] || e.field}.` : "");
            if (claimed) apply.hidden = true;
          } finally {
            applying = false;
            cancel.disabled = false;
            if (!apply.hidden) apply.disabled = false;
            void refresh();
          }
        });
        apply.disabled = true;
        apply.classList.add("aec-primary");
        apply.prepend(icon("apply"));
        footer.append(apply, cancel);
        dialog.append(header, main, message, footer);
        document.body.append(dialog);
        let before,
          selectionEnabled = false;
        let selection = { checkpoint: true, loras: true, modules: true };
        main.append(el("p", "Checking this draft and your editor…"));
        dialog.showModal();
        try {
          const response = await window.AECLinkDrafts.request("inbox", {
            id: item.id,
          });
          if (closed || disposed) return;
          const fresh = response.items.find((i) => i.id === item.id);
          if (!fresh?.payload || fresh.state !== "RECEIVED")
            throw new Error(
              "This draft is no longer available. Refresh the inbox to check its state.",
            );
          item = fresh;
          before = await adapter.snapshot();
          main.replaceChildren();
          selectionEnabled = item.payload.profile?.draftSelection === 1;
          selection = {
            ...(item.payload.resourceSelection || {
              checkpoint: true,
              loras: true,
              modules: true,
            }),
          };
          const resourceControls = el(
            "fieldset",
            undefined,
            "aec-resource-selection",
          );
          if (selectionEnabled) {
            resourceControls.append(el("legend", "Resources from this image"));
            for (const [key, title] of Object.entries({
              checkpoint: "Checkpoint",
              loras: "LoRAs",
              modules: "VAE / Text encoder",
            })) {
              const label = el("label"),
                input = el("input");
              input.type = "checkbox";
              input.checked = selection[key];
              input.disabled = !selection[key];
              input.setAttribute("aria-label", `Use image ${title}`);
              input.addEventListener("change", () => {
                selection[key] = input.checked;
                updatePreview();
              });
              label.append(input, el("span", title));
              resourceControls.append(label);
              input.dataset.resource = key;
            }
            resourceControls.append(
              button(
                options.newTemplate
                  ? "Exclude image resources"
                  : "Keep my resources",
                () => {
                  for (const input of resourceControls.querySelectorAll(
                    "input",
                  )) {
                    input.checked = false;
                    selection[input.dataset.resource] = false;
                  }
                  updatePreview();
                },
              ),
            );
            resourceControls.append(
              el(
                "p",
                options.newTemplate
                  ? "Excluded resources use the new workflow's defaults. Your previous workflow is saved for Undo."
                  : adapter.direct
                    ? "Excluded image resources leave your current selection unchanged. LoRA tags already in this Forge editor are kept."
                    : "Excluded image resources leave your current model and LoRA selections unchanged.",
              ),
            );
            main.append(resourceControls);
          }
          const checks = await adapter.check(item.payload.fields, options);
          if (closed || disposed) return;
          if (options.newTemplate)
            main.append(
              el(
                "p",
                "A new basic txt2img workflow will replace this canvas after saving its backup. Select a compatible checkpoint before generating.",
                "aec-warning",
              ),
            );
          for (const warning of item.payload.warnings || [])
            main.append(el("p", warning, "aec-warning"));
          main.append(
            el(
              "p",
              options.newTemplate
                ? "This basic checkpoint workflow is intended for SD 1.x and SDXL models. Other model families and advanced stages need a matching workflow; review missing resources in Arc."
                : "Only checked settings are transferred. Review additional processing stages before generating.",
              "aec-warning",
            ),
          );
          for (const [name, value] of Object.entries(item.payload.fields)) {
            const card = el("article");
            card.dataset.field = name;
            const label = el("label");
            const input = el("input");
            input.type = "checkbox";
            input.value = name;
            input.disabled = Boolean(checks[name]?.reason);
            input.checked = !input.disabled;
            label.append(input, el("strong", labels[name] || name));
            card.append(label);
            card.append(
              el(
                "pre",
                `Before: ${checks[name]?.before ?? "(not available)"}`,
                "aec-before",
              ),
              el(
                "pre",
                `After: ${value === "" ? "(empty)" : value}`,
                "aec-after",
              ),
            );
            if (checks[name]?.reason)
              card.append(el("p", checks[name].reason, "aec-warning"));
            main.append(card);
          }
          updatePreview();
          apply.disabled = false;
        } catch (e) {
          if (closed || disposed) return;
          main.replaceChildren();
          message.textContent =
            e.message +
            (e.field ? ` Field: ${labels[e.field] || e.field}.` : "");
          void report(item, e.code || "EDITOR_IMPORT_FAILED");
          apply.hidden = true;
          apply.disabled = true;
          const retry = button(
            "Check again",
            () => {
              close();
              void review(item);
            },
            "refresh",
          );
          main.append(retry);
          if (e.code === "EDITOR_STALE")
            main.append(
              button("Reload Forge", () => location.reload(), "refresh"),
            );
          if (adapter.canCreateBasic && !options.newTemplate)
            main.append(
              button("Review in a new basic workflow", () => {
                close();
                void review(item, { newTemplate: true });
              }),
            );
        }
        if (!dialog.open && !closed) dialog.showModal();
        function updatePreview() {
          if (!item.payload) return;
          const effective = resourceFields(
            item.payload.fields,
            selection,
            before,
            adapter.direct,
          );
          for (const row of main.querySelectorAll("[data-field]")) {
            const name = row.dataset.field;
            const output = row.querySelector(".aec-after");
            output.textContent =
              name in effective
                ? `After: ${effective[name] === "" ? "(empty)" : effective[name]}`
                : "Keep current selection";
          }
        }
      }
      render();
      void refresh();
      const timer = setInterval(() => {
        if (!document.hidden) {
          void refresh();
        }
      }, 3000);
      return () => {
        disposed = true;
        clearInterval(timer);
        document.removeEventListener("visibilitychange", visibility);
      };
    },
  };
})();

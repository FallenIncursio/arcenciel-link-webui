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
    LINK_INBOX_UNAVAILABLE:
      "The Link inbox is temporarily unavailable. Retry after reconnecting.",
  };
  const states = {
    RECEIVED: "Ready to review",
    CLAIMED: "Claimed by an editor",
    APPLIED: "Applied",
    UNDONE: "Previous draft restored",
    FAILED: "Import failed",
  };
  const el = (tag, text, className) => {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (className) n.className = className;
    return n;
  };
  const button = (text, fn) => {
    const n = el("button", text);
    n.type = "button";
    n.addEventListener("click", fn);
    return n;
  };
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
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
    `.aec-drafts{font:14px/1.5 system-ui,sans-serif;color:inherit;max-width:760px}.aec-drafts button{border:1px solid #71839980;background:#71839920;color:inherit;padding:10px 14px;border-radius:9px;cursor:pointer;min-height:44px}.aec-drafts button:disabled{opacity:.5;cursor:default}.aec-drafts h3{font-size:19px;margin:0 0 8px}.aec-drafts a{color:#52bdff}.aec-drafts article{border:1px solid #71839960;border-radius:12px;padding:14px;margin:12px 0}.aec-drafts p{overflow-wrap:anywhere;margin:8px 0}.aec-drafts .aec-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.aec-draft-modal{border:1px solid #71839980;border-radius:16px;background:#171e29;color:#e8eef7;padding:0;width:min(720px,calc(100vw - 16px));max-height:calc(100dvh - 24px);margin:auto;overflow:hidden}.aec-draft-modal::backdrop{background:#0009}.aec-draft-modal[open]{display:flex;flex-direction:column}.aec-draft-modal .aec-draft-header,.aec-draft-modal .aec-draft-footer{padding:16px;border-block:1px solid #71839940;flex-shrink:0}.aec-draft-modal .aec-draft-body{min-height:0;padding:16px;overflow-y:auto;overscroll-behavior:contain}.aec-draft-modal label{display:flex;gap:10px;align-items:start}.aec-draft-modal input[type=checkbox]{width:19px;height:19px;flex-shrink:0}.aec-draft-modal pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:130px;overflow-y:auto;font:13px/1.5 system-ui}.aec-draft-modal .aec-before{color:#adb8c9}.aec-draft-modal .aec-warning{color:#ffcc80}`,
  );
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
        throw new Error(
          errors[data.code] ||
            `Link request failed (${response.status}). Refresh to check its state.`,
        );
      return data;
    },
    mount(container, adapter) {
      container.classList.add("aec-drafts");
      const heading = el("h3", "Generator draft inbox");
      const help = el(
        "p",
        "Review image settings from Arc and choose which fields to apply in this editor. No generation starts.",
      );
      const status = el("p");
      status.setAttribute("role", "status");
      const list = el("div");
      let busy = false,
        disposed = false;
      const refreshButton = button("Refresh drafts", refresh);
      const backups = el("details");
      backups.append(el("summary", "Local backups in this editor tab"));
      const backupList = el("div");
      backups.append(backupList);
      backups.addEventListener("toggle", () => {
        if (!backups.open) return;
        backupList.replaceChildren(
          el(
            "p",
            "Export a backup before removing it. Removal also clears local undo and pending editor receipts; it does not change your canvas.",
          ),
        );
        const keys = [];
        for (let n = 0; n < sessionStorage.length; n++) {
          const key = sessionStorage.key(n);
          if (key?.startsWith("aec-link-draft:")) keys.push(key);
        }
        if (!keys.length)
          backupList.append(el("p", "No saved backups in this tab."));
        for (const key of keys) {
          const id = key.slice("aec-link-draft:".length),
            data = saved(id);
          if (!data?.before) continue;
          const row = el("article");
          row.append(
            el(
              "p",
              data.imageId
                ? `Image #${data.imageId}`
                : `Draft ${id.slice(0, 8)}`,
            ),
          );
          const actions = el("div", undefined, "aec-actions");
          actions.append(
            button("Export backup", () => {
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
            }),
          );
          let confirmed = false;
          const remove = button("Remove local backup", () => {
            if (!confirmed) {
              confirmed = true;
              remove.textContent = "Confirm removal";
              return;
            }
            sessionStorage.removeItem(key);
            row.remove();
            void refresh();
          });
          actions.append(remove);
          row.append(actions);
          backupList.append(row);
        }
      });
      container.replaceChildren(
        heading,
        help,
        refreshButton,
        status,
        list,
        backups,
      );
      async function refresh() {
        if (busy) return;
        busy = true;
        refreshButton.disabled = true;
        status.textContent = "Checking your device inbox…";
        try {
          const data = await window.AECLinkDrafts.request("inbox");
          if (disposed) return;
          list.replaceChildren();
          status.textContent = data.items.length
            ? `${data.items.length} drafts · saved for up to 24 hours`
            : "No waiting drafts. Choose “Send to Link” on an image in Arc.";
          for (const item of data.items) {
            const card = el("article");
            card.dataset.handoffId = item.id;
            const link = el("a", `Image #${item.imageId}`);
            link.href = `https://arcenciel.io/images/${item.imageId}`;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            card.append(link, el("p", states[item.state] || item.state));
            const actions = el("div", undefined, "aec-actions");
            if (item.state === "RECEIVED")
              actions.append(button("Review draft", () => review(item)));
            const receipt = saved(item.id);
            if (
              receipt?.stage === "applied" &&
              ["CLAIMED", "APPLIED"].includes(item.state)
            ) {
              if (item.state === "CLAIMED")
                actions.append(
                  button("Confirm editor receipt", async () => {
                    try {
                      await window.AECLinkDrafts.request("event", {
                        id: item.id,
                        editorId: receipt.editorId,
                        action: "applied",
                        receipt: { fields: receipt.fields },
                      });
                      await refresh();
                    } catch (e) {
                      status.textContent = e.message;
                    }
                  }),
                );
              actions.append(
                button("Undo import", async () => {
                  try {
                    // A changed draft needs an explicit preview, never an unconditional restore.
                    if (!equal(await adapter.snapshot(), receipt.after))
                      throw new Error(
                        "The editor changed since import. Your saved previous draft is available with “Export backup”; it will not overwrite newer work.",
                      );
                    if (item.state === "CLAIMED")
                      await window.AECLinkDrafts.request("event", {
                        id: item.id,
                        editorId: receipt.editorId,
                        action: "applied",
                        receipt: { fields: receipt.fields },
                      });
                    await adapter.restore(receipt.before);
                    save(item.id, {
                      imageId: item.imageId,
                      ...receipt,
                      stage: "undone",
                    });
                    await window.AECLinkDrafts.request("event", {
                      id: item.id,
                      editorId: receipt.editorId,
                      action: "undone",
                    });
                    await refresh();
                  } catch (e) {
                    status.textContent = e.message;
                  }
                }),
              );
            }
            if (receipt?.before)
              actions.append(
                button("Export backup", () => {
                  const url = URL.createObjectURL(
                    new Blob([JSON.stringify(receipt.before, null, 2)], {
                      type: "application/json",
                    }),
                  );
                  const a = el("a");
                  a.href = url;
                  a.download = `link-editor-backup-${item.id}.json`;
                  a.click();
                  setTimeout(() => URL.revokeObjectURL(url), 1000);
                }),
              );
            card.append(actions);
            list.append(card);
          }
        } catch (e) {
          if (!disposed) status.textContent = e.message;
        } finally {
          busy = false;
          refreshButton.disabled = false;
        }
      }
      async function review(item, options = {}) {
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
        let applying = false;
        const close = () => {
          if (applying) return;
          dialog.close();
          dialog.remove();
          focus?.focus({ preventScroll: true });
        };
        dialog.addEventListener("cancel", (e) => {
          e.preventDefault();
          close();
        });
        const cancel = button("Close", close);
        const apply = button("Save previous draft & apply", async () => {
          if (applying) return;
          const fields = Object.fromEntries(
            [...main.querySelectorAll("input:checked")].map((input) => [
              input.value,
              item.payload.fields[input.value],
            ]),
          );
          if (!Object.keys(fields).length) {
            message.textContent = "Select at least one available field.";
            return;
          }
          applying = true;
          apply.disabled = true;
          cancel.disabled = true;
          let claimed = false,
            mutated = false;
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
            await window.AECLinkDrafts.request("event", {
              id: item.id,
              editorId,
              action: "claim",
              fields: Object.keys(fields),
            });
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
            await adapter.apply(fields, options);
            const actual = await adapter.read(Object.keys(fields));
            if (!equal(actual, fields))
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
                "Applied in this editor. No generation started. Undo is available in the inbox.";
            } catch {
              message.textContent =
                "Applied locally; the server receipt is pending. Close and use “Confirm editor receipt”. Do not import again.";
            }
            apply.hidden = true;
          } catch (e) {
            if (mutated) {
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
            message.textContent = e.message;
            if (claimed) apply.hidden = true;
          } finally {
            applying = false;
            cancel.disabled = false;
            if (!apply.hidden) apply.disabled = false;
            void refresh();
          }
        });
        footer.append(apply, cancel);
        dialog.append(header, main, message, footer);
        document.body.append(dialog);
        let before;
        try {
          before = await adapter.snapshot();
          const checks = await adapter.check(item.payload.fields, options);
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
                : "Models and advanced stages remain unchanged. Review missing resources in Arc and select a compatible model before generating.",
              "aec-warning",
            ),
          );
          for (const [name, value] of Object.entries(item.payload.fields)) {
            const card = el("article");
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
              el("pre", `After: ${value === "" ? "(empty)" : value}`),
            );
            if (checks[name]?.reason)
              card.append(el("p", checks[name].reason, "aec-warning"));
            main.append(card);
          }
        } catch (e) {
          message.textContent = e.message;
          apply.disabled = true;
          if (adapter.canCreateBasic && !options.newTemplate)
            main.append(
              button("Review in a new basic workflow", () => {
                close();
                void review(item, { newTemplate: true });
              }),
            );
        }
        dialog.showModal();
      }
      void refresh();
      return () => {
        disposed = true;
      };
    },
  };
})();

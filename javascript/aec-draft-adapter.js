(() => {
  const messages = {
    BRIDGE_NOT_READY:
      "The Forge editor is not ready. Wait for startup, then check again.",
    EDITOR_STALE:
      "Forge restarted or its interface changed. Reload this page to reconnect the editor.",
    NATIVE_VALIDATION_FAILED:
      "A selected value is unavailable in this Forge editor. Review the indicated field.",
    GENERATOR_BUSY: "Wait for the current generation, then retry this draft.",
    EDITOR_CHANGED:
      "Your txt2img settings changed. Review this draft again before applying.",
    EDITOR_TIMEOUT:
      "Forge did not answer. Check the editor connection before retrying.",
  };
  const error = (code, extra = {}) =>
    Object.assign(new Error(messages[code] || messages.EDITOR_TIMEOUT), {
      code,
      ...extra,
    });
  let command,
    pending,
    uiId,
    tail = Promise.resolve();
  window.AECLinkNative = {
    // Gradio's own event passes the command and current component values together.
    take: () => JSON.stringify(command || {}),
    deliver(raw) {
      let result;
      try {
        result = JSON.parse(raw);
      } catch {
        return;
      }
      if (!pending || result.nonce !== pending.nonce) return;
      const task = pending;
      pending = null;
      clearTimeout(task.timer);
      if (result.ok) task.resolve(result.values);
      else
        task.reject(
          error(result.code, {
            unchanged: result.unchanged === true,
            field: result.field,
          }),
        );
    },
  };
  async function connection() {
    const root = gradioApp();
    if (!uiId) {
      try {
        uiId = JSON.parse(
          root.querySelector("#aec-link-native-receipt textarea")?.value ||
            "{}",
        ).uiId;
      } catch {
        /* Not mounted yet. */
      }
    }
    const response = await fetch("arcenciel-link/editor/status", {
      method: "POST",
      headers: { "X-AEC-Link-Editor": "1" },
      signal: AbortSignal.timeout(5000),
    }).catch(() => {
      throw error("BRIDGE_NOT_READY", { unchanged: true });
    });
    if (!response.ok) throw error("BRIDGE_NOT_READY", { unchanged: true });
    const status = await response.json();
    if (!uiId || status.uiId !== uiId)
      throw error("EDITOR_STALE", { unchanged: true });
    if (!status.ready) throw error("BRIDGE_NOT_READY", { unchanged: true });
  }
  async function rpc(action, fields, expected) {
    await connection();
    const submit = gradioApp().querySelector("#aec-link-native-apply");
    if (!submit) throw error("BRIDGE_NOT_READY", { unchanged: true });
    const nonce = crypto.randomUUID();
    command = { nonce, uiId, action, fields, expected };
    return new Promise((resolve, reject) => {
      pending = {
        nonce,
        resolve,
        reject,
        timer: setTimeout(() => {
          pending = null;
          reject(
            error("EDITOR_TIMEOUT", {
              unchanged: action === "read",
              uncertain: action === "apply",
            }),
          );
        }, 15000),
      };
      submit.click();
    });
  }
  const request = (...args) => {
    const next = tail.then(() => rpc(...args));
    tail = next.catch(() => {});
    return next;
  };
  const adapter = {
    direct: true,
    accordion: true,
    status({ waiting, ready, needsAttention }) {
      const accordion = gradioApp().querySelector("#aec-link-inbox-accordion");
      const header = accordion?.querySelector(".label-wrap");
      if (!header) return;
      let badge = header.querySelector(".aec-inbox-summary");
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "aec-inbox-summary";
        header.insertBefore(badge, header.querySelector(".icon"));
      }
      badge.textContent = `${waiting} waiting · ${needsAttention ? "Needs attention" : ready ? "Connected" : "Checking"}`;
      badge.style.cssText =
        "font-size:12px;margin-inline-start:auto;margin-inline-end:12px;opacity:.8";
      if (!accordion.dataset.aecRemembered) {
        accordion.dataset.aecRemembered = "1";
        const open = () => header.classList.contains("open");
        try {
          if (localStorage.getItem("aec-link-inbox-open") === "true" && !open())
            header.click();
        } catch {
          /* Optional. */
        }
        header.addEventListener("click", () =>
          setTimeout(() => {
            try {
              localStorage.setItem("aec-link-inbox-open", String(open()));
            } catch {
              /* Optional. */
            }
          }, 0),
        );
      }
    },
    isEditorInput(target) {
      return !!target?.closest?.(
        "#txt2img_prompt, #txt2img_neg_prompt, #txt2img_seed, #txt2img_steps, #txt2img_cfg_scale, #txt2img_width, #txt2img_height, #txt2img_sampling, #txt2img_scheduler, #txt2img_distilled_cfg_scale, #setting_sd_model_checkpoint, #setting_sd_modules, #setting_sd_vae, #setting_CLIP_stop_at_last_layers, #setting_beta_dist_alpha, #setting_beta_dist_beta",
      );
    },
    ready: () => request("read"),
    async read(keys) {
      const all = await request("read");
      return Object.fromEntries(
        keys.map((key) => {
          if (!(key in all))
            throw error("NATIVE_VALIDATION_FAILED", {
              field: key,
              unchanged: true,
            });
          return [key, all[key]];
        }),
      );
    },
    async apply(fields, options = {}) {
      await request("apply", fields, options.before);
      switch_to_txt2img();
    },
    snapshot: () => request("read"),
    restore: (fields) => request("apply", fields),
    async check(fields) {
      const all = await request("read");
      return Object.fromEntries(
        Object.keys(fields).map((key) => [
          key,
          {
            before: all[key],
            reason:
              key in all
                ? undefined
                : "This generator does not expose this field.",
          },
        ]),
      );
    },
  };
  let dispose, mounted;
  function mount() {
    const container = gradioApp().querySelector("#aec-link-draft-inbox");
    if (!container || !window.AECLinkDrafts || container === mounted) return;
    dispose?.();
    mounted = container;
    uiId = undefined;
    dispose = window.AECLinkDrafts.mount(container, adapter);
  }
  onUiLoaded(mount);
  if (typeof onAfterUiUpdate === "function") onAfterUiUpdate(mount);
})();

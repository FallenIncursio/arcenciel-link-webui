(() => {
  const selectors = {
    prompt: "#txt2img_prompt textarea",
    negativePrompt: "#txt2img_neg_prompt textarea",
    seed: "#txt2img_seed input[type=number]",
    steps: "#txt2img_steps input[type=number]",
    cfg: "#txt2img_cfg_scale input[type=number]",
    width: "#txt2img_width input[type=number]",
    height: "#txt2img_height input[type=number]",
    sampler: "#txt2img_sampling input",
    scheduler: "#txt2img_scheduler input",
  };
  const input = (key) => gradioApp().querySelector(selectors[key]);
  const numeric = (key) => ["steps", "cfg", "width", "height"].includes(key);
  async function read(keys) {
    return Object.fromEntries(
      keys.map((key) => {
        const e = input(key);
        if (!e) throw new Error(`This WebUI version does not expose ${key}.`);
        return [key, numeric(key) ? Number(e.value) : e.value];
      }),
    );
  }
  async function apply(fields) {
    const incoming = gradioApp().querySelector(
      "#aec-link-native-input textarea",
    );
    const submit = gradioApp().querySelector("#aec-link-native-apply");
    const receipt = gradioApp().querySelector(
      "#aec-link-native-receipt textarea",
    );
    if (!incoming || !submit || !receipt)
      throw new Error(
        "This WebUI version does not expose the native paste integration.",
      );
    const nonce = crypto.randomUUID();
    incoming.value = JSON.stringify({ nonce, fields });
    updateInput(incoming);
    await new Promise((resolve) => setTimeout(resolve, 50));
    submit.click();
    const end = Date.now() + 15000;
    while (Date.now() < end) {
      let result;
      try {
        result = JSON.parse(receipt.value);
      } catch {
        /* Native callback pending. */
      }
      if (result?.nonce === nonce) {
        if (!result.ok)
          throw new Error(
            "The native paste integration rejected an unavailable value.",
          );
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(
      "The native editor did not confirm the paste. Inspect the editor before retrying.",
    );
  }
  const adapter = {
    read,
    apply,
    async snapshot() {
      return read(Object.keys(selectors).filter((key) => input(key)));
    },
    restore: apply,
    async check(fields) {
      const values = {};
      for (const [key, value] of Object.entries(fields)) {
        const e = input(key);
        let reason = !e
          ? "This WebUI version does not expose this field."
          : undefined;
        if (
          e?.type === "number" &&
          ((e.min !== "" && Number(value) < Number(e.min)) ||
            (e.max !== "" && Number(value) > Number(e.max)))
        )
          reason = `Outside the current editor range (${e.min || "unbounded"} to ${e.max || "unbounded"}).`;
        values[key] = { before: e?.value, reason };
      }
      return values;
    },
  };
  onUiLoaded(() => {
    const container = gradioApp().querySelector("#aec-link-draft-inbox");
    if (container && window.AECLinkDrafts)
      window.AECLinkDrafts.mount(container, adapter);
  });
})();

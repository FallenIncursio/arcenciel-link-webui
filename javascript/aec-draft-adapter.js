(() => {
  async function rpc(action, fields, expected) {
    const incoming = gradioApp().querySelector(
        "#aec-link-native-input textarea",
      ),
      submit = gradioApp().querySelector("#aec-link-native-apply"),
      receipt = gradioApp().querySelector("#aec-link-native-receipt textarea");
    if (!incoming || !submit || !receipt)
      throw new Error("Open txt2img to receive Link settings.");
    const nonce = crypto.randomUUID();
    incoming.value = JSON.stringify({ nonce, action, fields, expected });
    updateInput(incoming);
    await new Promise((resolve) => setTimeout(resolve, 50));
    submit.click();
    const end = Date.now() + 15000;
    while (Date.now() < end) {
      let result;
      try {
        result = JSON.parse(receipt.value);
      } catch {
        /* waiting for native callback */
      }
      if (result?.nonce === nonce) {
        if (!result.ok)
          throw Object.assign(
            new Error(
              "The editor changed, is busy, or a selected option is no longer available. Check txt2img before retrying.",
            ),
            { unchanged: result.unchanged === true },
          );
        return result.values;
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(
      "The editor did not confirm the transfer. Inspect txt2img before retrying.",
    );
  }
  let tail = Promise.resolve();
  const request = (...args) => {
    const next = tail.then(() => rpc(...args));
    tail = next.catch(() => {});
    return next;
  };
  const adapter = {
    direct: true,
    async read(keys) {
      const all = await request("read");
      return Object.fromEntries(
        keys.map((key) => {
          if (!(key in all))
            throw new Error(`This generator does not expose ${key}.`);
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
  onUiLoaded(() => {
    const container = gradioApp().querySelector("#aec-link-draft-inbox");
    if (container && window.AECLinkDrafts)
      window.AECLinkDrafts.mount(container, adapter);
  });
})();

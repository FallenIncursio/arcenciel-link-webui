import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
const { chromium } = await import(
  process.env.AEC_PLAYWRIGHT_MODULE || "playwright"
);
const source = fs.readFileSync(
  new URL("../javascript/0-aec-draft-inbox.js", import.meta.url),
  "utf8",
);
let browser;
before(async () => {
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
});
async function fixture(
  t,
  { old = false, fail = false, selection = false } = {},
) {
  const context = await browser.newContext();
  t.after(() => context.close());
  const rows = [],
    events = [];
  const add = () => {
    const row = {
      id: crypto.randomUUID(),
      imageId: 177791,
      createdAt: new Date(Date.now() - (old ? 60000 : 0)).toISOString(),
      state: "RECEIVED",
      payload: { fields: { prompt: "from Arc", steps: 24 }, warnings: [] },
    };
    if (selection)
      row.payload = {
        profile: { host: "forge", draftSelection: 1 },
        resourceSelection: { checkpoint: true, loras: true, modules: true },
        fields: {
          prompt: "portrait <lora:image:1>",
          steps: 24,
          checkpoint: "B",
          modules: '["vae-B"]',
        },
        warnings: [],
      };
    rows.push(row);
    return row;
  };
  await context.route("http://127.0.0.1:18998/**", async (route) => {
    const request = route.request(),
      action = new URL(request.url()).pathname.split("/").at(-1);
    if (["inbox", "event"].includes(action)) {
      const data = request.postDataJSON();
      if (action === "inbox")
        return route.fulfill({
          json: {
            items: rows
              .filter(
                (r) =>
                  r.state !== "CANCELLED" && (!data.id || data.id === r.id),
              )
              .map((r) =>
                data.receiveOnly ? { ...r, payload: undefined } : r,
              ),
          },
        });
      events.push(data);
      const row = rows.find((r) => r.id === data.id);
      if (data.action === "claim") {
        if (row.state !== "RECEIVED")
          return route.fulfill({
            status: 409,
            json: { code: "HANDOFF_NOT_PENDING" },
          });
        row.state = "CLAIMED";
        row.receipt = {
          fields: Object.fromEntries(
            data.fields.map((k) => [k, row.payload.fields[k]]),
          ),
        };
        if (
          selection &&
          Object.values(data.resourceSelection).every((v) => v === false)
        )
          row.receipt = {
            fields: { prompt: "portrait <lora:local:0.5>", steps: 24 },
          };
      }
      if (data.action === "applied") row.state = "APPLIED";
      if (data.action === "undone") row.state = "UNDONE";
      if (data.action === "cancel") row.state = "CANCELLED";
      if (data.action === "failed") row.state = "FAILED";
      return route.fulfill({ json: row });
    }
    return route.fulfill({
      contentType: "text/html",
      body: '<input id="unrelated" aria-label="Search"><input id="editor-prompt" aria-label="Prompt" value="original"><div id="aec-link-draft-inbox"></div>',
    });
  });
  const open = async () => {
    const page = await context.newPage();
    await page.goto("http://127.0.0.1:18998/");
    await page.addScriptTag({ content: source });
    await page.evaluate(
      ({ fail, selection }) => {
        window.native = {
          values: { prompt: "original", steps: 20 },
          fail,
          applies: 0,
        };
        if (selection)
          Object.assign(window.native.values, {
            prompt: "my work <lora:local:0.5>",
            checkpoint: "A",
            modules: '["vae-A"]',
          });
        const snapshot = () => {
          if (window.native.fail)
            throw Object.assign(
              new Error("Editor test connection unavailable"),
              { code: "EDITOR_TIMEOUT", unchanged: true },
            );
          return structuredClone(window.native.values);
        };
        document
          .querySelector("#editor-prompt")
          .addEventListener("input", (e) => {
            window.native.values.prompt = e.target.value;
          });
        const set = (fields) => {
          Object.assign(window.native.values, fields);
          document.querySelector("#editor-prompt").value =
            window.native.values.prompt;
        };
        window.disposeInbox = window.AECLinkDrafts.mount(
          document.querySelector("#aec-link-draft-inbox"),
          {
            direct: true,
            ready: async () => snapshot(),
            isEditorInput: (t) => t.id === "editor-prompt",
            snapshot: async () => snapshot(),
            check: async (fields) =>
              Object.fromEntries(
                Object.keys(fields).map((k) => [
                  k,
                  { before: window.native.values[k] },
                ]),
              ),
            apply: async (fields) => {
              window.native.applies++;
              set(fields);
            },
            restore: async (fields) => set(fields),
            read: async (keys) => {
              if (window.native.failReadback)
                throw Object.assign(new Error("Lost native readback"), {
                  code: "EDITOR_TIMEOUT",
                  unchanged: true,
                });
              return Object.fromEntries(
                keys.map((k) => [k, window.native.values[k]]),
              );
            },
          },
        );
      },
      { fail, selection },
    );
    await page.waitForFunction(
      () =>
        !document
          .querySelector(".aec-connection")
          .textContent.includes("Checking"),
    );
    return page;
  };
  return { context, open, add, events, rows };
}
async function until(fn, message) {
  for (let n = 0; n < 100; n++) {
    if (await fn()) return;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(message);
}
async function apply(p, row) {
  const card = p.locator(`[data-handoff-id="${row.id}"]`);
  await card
    .getByRole("button", { name: "Apply to txt2img", exact: true })
    .click();
  const dialog = p.getByRole("dialog", { name: "Review Link draft" });
  await dialog
    .getByRole("button", { name: "Save previous draft & apply" })
    .click();
  await dialog
    .getByText(
      "Settings applied for your next generation. Undo is available in History.",
      { exact: true },
    )
    .waitFor();
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
}
test("fresh arrivals stay untouched until an explicit confirmation; apply and undo work", async (t) => {
  const f = await fixture(t),
    p = await f.open(),
    row = f.add();
  await p.getByText("Waiting for your confirmation", { exact: true }).waitFor();
  await p.waitForTimeout(6500);
  assert.equal(row.state, "RECEIVED");
  assert.equal(await p.evaluate(() => native.applies), 0);
  assert.equal(
    f.events.some((e) => e.action === "claim"),
    false,
  );
  await apply(p, row);
  assert.equal(row.state, "APPLIED");
  assert.equal(await p.evaluate(() => native.applies), 1);
  assert.equal(
    await p.getByText("Backups & recovery", { exact: true }).count(),
    0,
  );
  assert.equal(await p.locator(`[data-handoff-id="${row.id}"]`).count(), 1);
  await p.getByRole("button", { name: "Undo", exact: true }).click();
  await until(() => row.state === "UNDONE", "Undo missing");
  assert.deepEqual(await p.evaluate(() => native.values), {
    prompt: "original",
    steps: 20,
  });
});
test("older drafts, additional tabs and refreshing cannot apply automatically", async (t) => {
  const f = await fixture(t, { old: true }),
    row = f.add(),
    p = await f.open(),
    other = await f.open();
  await p
    .getByRole("button", { name: "Check connection", exact: true })
    .click();
  await other.bringToFront();
  await other.waitForTimeout(6500);
  assert.equal(row.state, "RECEIVED");
  assert.equal(
    f.events.some((e) => e.action === "claim"),
    false,
  );
  await apply(other, row);
  assert.equal(row.state, "APPLIED");
});
test("closing the review keeps the editor intact; concurrent edits block replacement", async (t) => {
  const f = await fixture(t),
    p = await f.open(),
    row = f.add();
  const card = p.locator(`[data-handoff-id="${row.id}"]`);
  await card
    .getByRole("button", { name: "Apply to txt2img", exact: true })
    .click();
  const d = p.getByRole("dialog");
  await d
    .getByRole("button", { name: "Save previous draft & apply" })
    .waitFor();
  // The review button exists while its native snapshot is still loading.
  await p.waitForFunction(
    () => !document.querySelector(".aec-draft-modal .aec-primary").disabled,
  );
  await p.evaluate(() => (native.values.prompt = "new work"));
  await d.getByRole("button", { name: "Save previous draft & apply" }).click();
  await d
    .getByText("Your editor changed. Close and review this draft again.", {
      exact: true,
    })
    .waitFor();
  assert.equal(row.state, "RECEIVED");
  assert.equal(await p.evaluate(() => native.applies), 0);
  await d.getByRole("button", { name: "Close", exact: true }).click();
});
test("pending entries can be cancelled and pagination keeps every entry reachable", async (t) => {
  const f = await fixture(t),
    p = await f.open();
  for (let i = 0; i < 8; i++) f.add();
  await p.getByRole("button", { name: "Show more", exact: true }).click();
  assert.equal(await p.locator("[data-handoff-id]").count(), 8);
  await p
    .locator("[data-handoff-id]")
    .last()
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await until(() => f.rows[7].state === "CANCELLED", "Cancel missing");
  assert.equal(
    f.events.some((e) => e.action === "claim"),
    false,
  );
});
test("orphaned local backups stay available once in History and can be exported or removed", async (t) => {
  const f = await fixture(t),
    p = await f.open();
  await p.evaluate(() =>
    sessionStorage.setItem(
      "aec-link-draft:orphan",
      JSON.stringify({
        imageId: 4,
        before: { prompt: "saved" },
        savedAt: new Date().toISOString(),
        stage: "applied",
      }),
    ),
  );
  await p.getByRole("button", { name: /^History/ }).click();
  const c = p.locator('[data-handoff-id="orphan"]');
  await c
    .getByText("Saved in this browser tab · server entry unavailable", {
      exact: true,
    })
    .waitFor();
  await c.locator("summary").click();
  await c.getByRole("button", { name: "Export backup", exact: true }).waitFor();
  await c.getByRole("button", { name: "Remove backup", exact: true }).click();
  await c
    .getByRole("button", { name: "Remove backup and Undo?", exact: true })
    .click();
  await c.waitFor({ state: "hidden" });
});
test("unconfirmed writes retain their claim and recovery verifies without another apply", async (t) => {
  const f = await fixture(t),
    p = await f.open(),
    row = f.add();
  await p.evaluate(() => (native.failReadback = true));
  await p
    .locator(`[data-handoff-id="${row.id}"]`)
    .getByRole("button", { name: "Apply to txt2img", exact: true })
    .click();
  const d = p.getByRole("dialog");
  await d.getByRole("button", { name: "Save previous draft & apply" }).click();
  await d.getByText(/Forge's confirmation is missing/).waitFor();
  await d.getByRole("button", { name: "Close", exact: true }).click();
  assert.equal(row.state, "CLAIMED");
  await p.evaluate(() => (native.failReadback = false));
  await p.getByRole("button", { name: "Check outcome", exact: true }).click();
  await until(() => row.state === "APPLIED", "Recovery missing");
  assert.equal(await p.evaluate(() => native.applies), 1);
});
test("mobile controls remain reachable and polling preserves focus", async (t) => {
  const f = await fixture(t),
    p = await f.open();
  await p.setViewportSize({ width: 390, height: 850 });
  const row = f.add();
  const button = p
    .locator(`[data-handoff-id="${row.id}"]`)
    .getByRole("button", { name: "Apply to txt2img", exact: true });
  await button.waitFor();
  await button.focus();
  await p.waitForTimeout(3500);
  assert.equal(
    await button.evaluate((b) => document.activeElement === b),
    true,
  );
  assert.ok((await button.boundingBox()).height >= 44);
  assert.ok(
    await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  );
  assert.equal(row.state, "RECEIVED");
});

test("resource confirmation preserves native checkpoint, modules and local prompt LoRAs", async (t) => {
  const f = await fixture(t, { selection: true }),
    p = await f.open(),
    row = f.add();
  await p
    .locator(`[data-handoff-id="${row.id}"]`)
    .getByRole("button", { name: "Apply to txt2img", exact: true })
    .click();
  const d = p.getByRole("dialog");
  await d
    .getByRole("button", { name: "Keep my resources", exact: true })
    .click();
  await d
    .getByText("After: portrait <lora:local:0.5>", { exact: true })
    .waitFor();
  await d.getByRole("button", { name: "Save previous draft & apply" }).click();
  await d
    .getByText(
      "Settings applied for your next generation. Undo is available in History.",
      { exact: true },
    )
    .waitFor();
  assert.deepEqual(await p.evaluate(() => native.values), {
    prompt: "portrait <lora:local:0.5>",
    steps: 24,
    checkpoint: "A",
    modules: '["vae-A"]',
  });
  assert.equal(row.state, "APPLIED");
  const claim = f.events.find((e) => e.action === "claim");
  assert.deepEqual(claim.resourceSelection, {
    checkpoint: false,
    loras: false,
    modules: false,
  });
  assert.equal(claim.localPrompts.prompt, "my work <lora:local:0.5>");
});

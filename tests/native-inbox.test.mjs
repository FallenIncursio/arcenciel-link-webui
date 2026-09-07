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
async function fixture(t, { old = false, fail = false } = {}) {
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
      ({ fail }) => {
        window.native = {
          values: { prompt: "original", steps: 20 },
          fail,
          applies: 0,
        };
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
      { fail },
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
test("fresh transfer applies once, preserves backup and undo; unrelated inputs do not block", async (t) => {
  const f = await fixture(t),
    p = await f.open();
  await p.getByLabel("Search").fill("searching");
  const row = f.add();
  await until(() => row.state === "APPLIED", "not automatically applied");
  assert.equal(await p.evaluate(() => window.native.applies), 1);
  await until(
    () => p.getByRole("button", { name: "Undo", exact: true }).isVisible(),
    "undo unavailable",
  );
  await p.getByRole("button", { name: "Undo", exact: true }).click();
  await until(() => row.state === "UNDONE", "undo not acknowledged");
  assert.deepEqual(await p.evaluate(() => window.native.values), {
    prompt: "original",
    steps: 20,
  });
  assert.equal(await p.getByRole("dialog").count(), 0);
});
test("generation edits and multiple pending drafts remain explicit choices, all entries accessible", async (t) => {
  const f = await fixture(t),
    p = await f.open();
  await p.getByLabel("Prompt", { exact: true }).fill("keep new work");
  for (let i = 0; i < 8; i++) f.add();
  await p
    .getByRole("button", { name: "Check connection", exact: true })
    .click();
  await until(
    () => p.getByText("Waiting (8)", { exact: true }).isVisible(),
    "missing pending count",
  );
  assert(f.rows.every((r) => r.state === "RECEIVED"));
  assert.equal(
    await p.getByLabel("Prompt", { exact: true }).inputValue(),
    "keep new work",
  );
  assert.equal(await p.locator("[data-handoff-id]").count(), 5);
  await p.getByRole("button", { name: "Show more" }).click();
  assert.equal(await p.locator("[data-handoff-id]").count(), 8);
  await p
    .locator("[data-handoff-id]")
    .first()
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await until(() => f.rows[0].state === "CANCELLED", "cancel not persisted");
});
test("a waiting tab takes over after the receiving tab closes", async (t) => {
  const f = await fixture(t),
    first = await f.open();
  await until(
    () => first.getByText("Receiving in this tab", { exact: true }).isVisible(),
    "first not receiver",
  );
  const second = await f.open();
  await until(
    () => second.getByText("Manual receiving", { exact: true }).isVisible(),
    "second incorrectly owns receiver",
  );
  await first.close();
  await until(
    () =>
      second.getByText("Receiving in this tab", { exact: true }).isVisible(),
    "receiver did not recover",
  );
  const row = f.add();
  await until(() => row.state === "APPLIED", "new receiver did not apply");
});
test("connection failure is reported without claiming and the same draft can recover", async (t) => {
  const f = await fixture(t, { old: true, fail: true }),
    row = f.add(),
    p = await f.open();
  await until(
    () =>
      f.events.some(
        (e) => e.action === "diagnostic" && e.receipt.code === "EDITOR_TIMEOUT",
      ),
    "diagnostic not reported",
  );
  assert.equal(row.state, "RECEIVED");
  assert(
    await p
      .getByRole("button", { name: "Apply to txt2img", exact: true })
      .isDisabled(),
  );
  await p.evaluate(() => {
    window.native.fail = false;
  });
  await p
    .getByRole("button", { name: "Check connection", exact: true })
    .click();
  await p
    .getByRole("button", { name: "Apply to txt2img", exact: true })
    .click();
  await p.getByRole("button", { name: "Save previous draft & apply" }).click();
  await until(() => row.state === "APPLIED", "same draft not recovered");
  assert.equal(f.events.filter((e) => e.action === "claim").length, 1);
});
test("compact inbox fits mobile and unchanged polls preserve focused actions", async (t) => {
  const f = await fixture(t, { old: true }),
    row = f.add(),
    p = await f.open();
  await p.setViewportSize({ width: 360, height: 800 });
  const apply = p.getByRole("button", {
    name: "Apply to txt2img",
    exact: true,
  });
  await apply.waitFor();
  await apply.focus();
  await p.waitForTimeout(3500);
  assert(await apply.evaluate((e) => document.activeElement === e));
  assert.equal(row.state, "RECEIVED");
  assert(
    await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  );
  assert((await apply.boundingBox()).height >= 44);
});

test("a new arrival does not depend on the computer clock matching the server", async (t) => {
  const f = await fixture(t),
    p = await f.open(),
    row = f.add();
  row.createdAt = "2020-01-01T00:00:00Z";
  await until(
    () => row.state === "APPLIED",
    "clock skew blocked fresh delivery",
  );
  assert.equal(await p.evaluate(() => window.native.applies), 1);
});
test("native changes made through another control are checked before automatic replacement", async (t) => {
  const f = await fixture(t),
    p = await f.open();
  await p.evaluate(() => {
    window.native.values.steps = 42;
  });
  const row = f.add();
  await until(
    () => p.getByRole("dialog").isVisible(),
    "changed native state was not reviewed",
  );
  assert.equal(row.state, "RECEIVED");
  assert.equal(await p.evaluate(() => window.native.applies), 0);
});
test("Receive here transfers ownership without closing the first tab", async (t) => {
  const f = await fixture(t),
    first = await f.open(),
    second = await f.open();
  await second
    .getByRole("button", { name: "Receive here", exact: true })
    .click();
  await until(
    () =>
      second.getByText("Receiving in this tab", { exact: true }).isVisible(),
    "explicit ownership request failed",
  );
  assert(
    await first.getByText("Manual receiving", { exact: true }).isVisible(),
  );
});

test("lost readback retains an uncertain claim and reconciles without applying twice", async (t) => {
  const f = await fixture(t, { old: true }),
    row = f.add(),
    p = await f.open();
  await p.evaluate(() => {
    window.native.failReadback = true;
  });
  await p
    .getByRole("button", { name: "Apply to txt2img", exact: true })
    .click();
  await p.getByRole("button", { name: "Save previous draft & apply" }).click();
  await p.getByText(/Forge's confirmation is missing/).waitFor();
  assert.equal(row.state, "CLAIMED");
  assert.equal(await p.evaluate(() => window.native.applies), 1);
  await p.getByRole("button", { name: "Close", exact: true }).click();
  await p.evaluate(() => {
    window.native.failReadback = false;
  });
  await p.getByRole("button", { name: "Check outcome", exact: true }).click();
  await until(() => row.state === "APPLIED", "outcome did not reconcile");
  assert.equal(await p.evaluate(() => window.native.applies), 1);
});

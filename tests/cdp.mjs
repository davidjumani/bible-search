// Minimal, dependency-free Chrome DevTools Protocol driver. No puppeteer/
// playwright — just the CDP HTTP + WebSocket API directly, since Node's
// built-in `fetch`/`WebSocket` are enough and this project has no
// dependencies (intentionally — see the reasoning behind not using npm
// in books/vercel.json's history).
//
// Usage:
//   import { withPage } from "./cdp.mjs";
//   await withPage("http://localhost:8935/index.html", async (page) => {
//     await page.eval(`document.title`);
//   });

const CDP_BASE = "http://localhost:9333";

export function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function ensureChrome() {
  try {
    await fetch(`${CDP_BASE}/json/version`);
    return null; // already running, caller doesn't own it
  } catch {
    const { spawn } = await import("node:child_process");
    const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
    const proc = spawn(
      chromePath,
      ["--headless=new", "--remote-debugging-port=9333", "--no-first-run", "--disable-gpu", "about:blank"],
      { stdio: "ignore", detached: true }
    );
    proc.unref();
    for (let i = 0; i < 30; i++) {
      await sleep(200);
      try {
        await fetch(`${CDP_BASE}/json/version`);
        return proc;
      } catch {}
    }
    throw new Error("headless Chrome did not come up on port 9333");
  }
}

function connectClient(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    let id = 0;
    const pending = new Map();
    const eventListeners = [];
    ws.addEventListener("open", () => {
      resolve({
        send(method, params = {}) {
          const thisId = ++id;
          return new Promise((res, rej) => {
            pending.set(thisId, { res, rej });
            ws.send(JSON.stringify({ id: thisId, method, params }));
          });
        },
        onEvent(fn) {
          eventListeners.push(fn);
        },
        close() {
          ws.close();
        },
      });
    });
    ws.addEventListener("error", reject);
    ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && pending.has(msg.id)) {
        const { res, rej } = pending.get(msg.id);
        pending.delete(msg.id);
        if (msg.error) rej(new Error(JSON.stringify(msg.error)));
        else res(msg.result);
      } else if (msg.method) {
        for (const l of eventListeners) l(msg.method, msg.params);
      }
    });
  });
}

/**
 * Opens `url` in a (possibly newly-launched) headless Chrome tab, widened
 * to desktop width by default (this project's CSS has a 760px mobile
 * breakpoint that changes behavior — tests should be explicit about which
 * layout they're exercising, not accidentally land on whichever one a
 * default headless viewport happens to be).
 */
export async function withPage(url, fn, { width = 1280, height = 900 } = {}) {
  const chromeProc = await ensureChrome();
  const tab = await (
    await fetch(`${CDP_BASE}/json/new?${encodeURIComponent(url)}`, { method: "PUT" })
  ).json();
  const client = await connectClient(tab.webSocketDebuggerUrl);

  const consoleErrors = [];
  const pageErrors = [];
  client.onEvent((method, params) => {
    if (method === "Runtime.exceptionThrown") pageErrors.push(params.exceptionDetails.text);
    if (method === "Runtime.consoleAPICalled" && params.type === "error") {
      consoleErrors.push(params.args.map((a) => a.value ?? a.description).join(" "));
    }
  });

  await client.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await client.send("Runtime.enable");

  const page = {
    async eval(expr, awaitPromise = true) {
      const result = await client.send("Runtime.evaluate", {
        expression: expr,
        returnByValue: true,
        awaitPromise,
      });
      if (result.exceptionDetails) {
        throw new Error("Page eval error: " + JSON.stringify(result.exceptionDetails));
      }
      return result.result.value;
    },
    sleep,
    consoleErrors,
    pageErrors,
  };

  try {
    return await fn(page);
  } finally {
    client.close();
    await fetch(`${CDP_BASE}/json/close/${tab.id}`).catch(() => {});
    if (chromeProc) chromeProc.kill();
  }
}

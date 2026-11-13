import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../", import.meta.url));
const ready = async () => {
  try {
    return (
      await fetch("http://127.0.0.1:1420/", {
        signal: AbortSignal.timeout(500),
      })
    ).ok;
  } catch {
    return false;
  }
};
let server;
let output = "";
try {
  if (!(await ready())) {
    server = spawn(
      process.execPath,
      ["node_modules/vite/bin/vite.js", "--host", "127.0.0.1"],
      { cwd: root, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] },
    );
    server.stdout.on("data", (chunk) => {
      output = (output + chunk).slice(-6000);
    });
    server.stderr.on("data", (chunk) => {
      output = (output + chunk).slice(-6000);
    });
    let started = false;
    for (let i = 0; i < 50; i++) {
      if (await ready()) {
        started = true;
        break;
      }
      if (server.exitCode !== null) break;
      await delay(200);
    }
    if (!started) throw Error(`UI preview server did not start: ${output}`);
  }
  const runner = spawn(
    process.execPath,
    ["node_modules/@playwright/test/cli.js", "test", ...process.argv.slice(2)],
    {
      cwd: root,
      windowsHide: true,
      stdio: "inherit",
      env: { ...process.env, STUDIO_TEST_EXTERNAL_SERVER: "1" },
    },
  );
  process.exitCode = await new Promise((resolve, reject) => {
    runner.on("error", reject);
    runner.on("exit", (code) => resolve(code ?? 1));
  });
} catch (error) {
  console.error(error);
  process.exitCode = 1;
} finally {
  if (server && server.exitCode === null) {
    server.kill();
    await new Promise((resolve) => {
      server.on("exit", resolve);
      setTimeout(resolve, 2000);
    });
  }
}

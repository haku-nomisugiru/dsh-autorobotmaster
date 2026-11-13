import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { writeFile, mkdir } from "node:fs/promises";
const b = await chromium.connectOverCDP(
  process.env.STUDIO_CDP_URL || "http://127.0.0.1:9427",
);
try {
  const p = b
    .contexts()
    .flatMap((c) => c.pages())
    .find((p) => p.url().includes("tauri"));
  assert.ok(p);
  await p.locator(".workflow-tabs").waitFor();
  const invoke = (command, args = {}) =>
    p.evaluate(
      ({ command, args }) => window.__TAURI_INTERNALS__.invoke(command, args),
      { command, args },
    );
  let s = await invoke("bootstrap");
  assert.ok(s.dataDir.includes("native-codex-integration"));
  assert.equal(s.settings.protocol, "codex");
  assert.equal(s.settings.hasApiKey, true);
  const connection = await invoke("check_connection", { kind: "api" });
  assert.equal(connection.ok, true);
  console.log("Codex native connection:", connection.message);
  s = await invoke("send_message", {
    text: "这是接入验证。用户明确要求：底盘外宽 420 mm。请调用 update_spec 把这条记录到用户明确要求，来源写为用户本轮明确要求，然后用一句话确认。不要调用 CAD，不要询问其他需求。",
    choice: null,
  });
  assert.ok(
    s.project.spec.requirements.some((i) => i.text.includes("420")),
    "Real Codex must write the requirement through the Studio tool loop",
  );
  assert.equal(s.busy, false);
  assert.equal(s.project.pending, null);
  await p.reload();
  await p.locator(".workflow-tabs").waitFor();
  s = await invoke("bootstrap");
  assert.ok(s.project.spec.requirements.some((i) => i.text.includes("420")));
  await mkdir("docs/screenshots/integrations", { recursive: true });
  await p.screenshot({
    path: "docs/screenshots/integrations/codex-desktop.png",
  });
  await writeFile(
    ".local/codex-native-result.json",
    JSON.stringify(
      {
        passed: true,
        protocol: s.settings.protocol,
        connection: connection.message,
        requirements: s.project.spec.requirements,
        messageCount: s.project.messages.length,
      },
      null,
      2,
    ),
  );
  console.log(
    "Codex native connection + real requirement/tool persistence passed",
  );
} finally {
  await b.close();
}

import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { writeFile, mkdir } from "node:fs/promises";

const browser = await chromium.connectOverCDP(
  process.env.STUDIO_CDP_URL || "http://127.0.0.1:9423",
);
try {
  const context = browser.contexts()[0];
  const page =
    context.pages().find((p) => p.url().includes("tauri")) ||
    context.pages()[0];
  await page.waitForSelector(".workflow-tabs");
  const invoke = (command, args = {}) =>
    page.evaluate(
      ({ command, args }) => window.__TAURI_INTERNALS__.invoke(command, args),
      { command, args },
    );
  const initial = await invoke("bootstrap");
  assert.equal(initial.project.tabs.length, 5);
  assert.ok(initial.dataDir.includes("native-smoke"));
  let state = await invoke("edit_workspace", {
    action: "new_project",
    payload: { name: "桌面联调项目" },
  });
  state = await invoke("edit_workspace", {
    action: "add_tab",
    payload: { stage: "requirements" },
  });
  assert.equal(state.project.tabs.length, 6);
  state = await invoke("edit_workspace", {
    action: "close_tab",
    payload: { id: state.project.activeTab },
  });
  assert.equal(state.project.tabs.length, 5);
  await assert.rejects(() =>
    invoke("edit_workspace", {
      action: "close_tab",
      payload: { id: state.project.activeTab },
    }),
  );
  state.project.spec.requirements.push({
    id: crypto.randomUUID(),
    text: "桌面持久化验证：安装空间待讨论",
    source: "本地联调输入",
  });
  await invoke("edit_workspace", {
    action: "spec",
    payload: state.project.spec,
  });
  await page.reload();
  await page.waitForSelector(".spec-item");
  const persisted = await invoke("bootstrap");
  assert.equal(persisted.project.spec.requirements.length, 1);
  const mcp = await invoke("check_connection", { kind: "mcp" });
  assert.equal(mcp.ok, true);
  const rag = await invoke("search_parts", {
    source: "local",
    query: "3508 舵轮",
  });
  assert.ok(rag.items.length > 0);
  const step = await invoke("search_parts", {
    source: "step",
    query: "bearing",
  });
  assert.ok(step.items.length > 0);
  const download = await invoke("download_part", {
    source: "step",
    partId: step.items[0].id,
    kind: "file",
  });
  assert.equal(download.verification, "file_integrity_only");
  await page.reload();
  await page.waitForSelector(".workflow-tabs");
  await mkdir("docs/screenshots", { recursive: true });
  await page.screenshot({
    path: "docs/screenshots/native-workspace.png",
    animations: "disabled",
  });
  await page.getByRole("tab", { name: "检索可复用组件" }).click();
  await page.getByRole("textbox", { name: "组件检索词" }).fill("3508 舵轮");
  await page.getByRole("button", { name: "检索", exact: true }).click();
  await page.locator(".result-card").first().waitFor({ timeout: 30000 });
  await page.screenshot({
    path: "docs/screenshots/native-retrieval.png",
    animations: "disabled",
  });
  const report = {
    native: true,
    projectId: persisted.project.id,
    windowMinimum: true,
    persistence: true,
    mcp: mcp.message,
    ragCandidates: rag.items.length,
    stepTotal: step.total,
    download: {
      id: download.id,
      bytes: download.bytes,
      sha256: download.sha256,
    },
    paidModelTested: false,
  };
  await writeFile(
    "docs/native-smoke-results.json",
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}

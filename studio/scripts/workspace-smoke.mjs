import { chromium, expect } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir, writeFile, stat } from "node:fs/promises";
import path from "node:path";

const browser = await chromium.connectOverCDP(
  process.env.STUDIO_CDP_URL || "http://127.0.0.1:9424",
);
try {
  const page = browser
    .contexts()[0]
    .pages()
    .find((p) => p.url().includes("tauri"));
  assert.ok(page);
  await page.waitForSelector(".workflow-tabs");
  const invoke = (command, args = {}) =>
    page.evaluate(
      ({ command, args }) => window.__TAURI_INTERNALS__.invoke(command, args),
      { command, args },
    );
  const initial = await invoke("bootstrap");
  assert.ok(
    initial.dataDir.includes("native-workspace-check"),
    "Use an isolated test data directory",
  );
  const selected = path.join(initial.dataDir, "模型 工作区");
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "模型工作区", exact: true }).click();
  await page.getByLabel("模型工作区路径").fill(selected);
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(page.locator(".settings-overlay")).toHaveCount(0);
  assert.ok((await stat(selected)).isDirectory());
  await writeFile(
    path.join(selected, "目录发现测试.step"),
    "File listing fixture; not a CAD model.",
  );
  await page.reload();
  await page.waitForSelector(".workflow-tabs");
  const saved = await invoke("bootstrap");
  assert.equal(saved.settings.modelWorkspace, selected);
  assert.equal(saved.modelWorkspaceDir, selected);
  const listing = await invoke("list_model_files");
  assert.ok(listing.entries.some((f) => f.name === "目录发现测试.step"));
  const mcp = await invoke("check_connection", { kind: "mcp" });
  assert.ok(mcp.ok && mcp.signature.endsWith(selected));
  const download = await invoke("download_part", {
    source: "step",
    partId: "bearing_608zz",
    kind: "file",
  });
  assert.ok(
    download.path.startsWith(
      path.join(selected, "downloads", saved.project.id),
    ),
  );
  assert.equal((await stat(download.path)).size, download.bytes);
  await assert.rejects(() =>
    invoke("save_settings", {
      settings: { ...saved.settings, modelWorkspace: "relative-folder" },
      apiKey: null,
    }),
  );
  await assert.rejects(() =>
    invoke("save_settings", {
      settings: {
        ...saved.settings,
        modelWorkspace: path.join(selected, "目录发现测试.step"),
      },
      apiKey: null,
    }),
  );
  assert.equal((await invoke("bootstrap")).settings.modelWorkspace, selected);
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "模型工作区", exact: true }).click();
  await expect(page.getByLabel("模型工作区路径")).toHaveValue(selected);
  await mkdir("docs/screenshots", { recursive: true });
  await page.screenshot({
    path: "docs/screenshots/native-model-workspace.png",
    animations: "disabled",
  });
  const reset = await invoke("save_settings", {
    settings: { ...saved.settings, modelWorkspace: "" },
    apiKey: null,
  });
  assert.equal(reset.settings.modelWorkspace, "");
  assert.equal(
    reset.modelWorkspaceDir,
    path.join(initial.dataDir, "cad", saved.project.id),
  );
  assert.ok(
    (await stat(download.path)).isFile(),
    "Changing workspace must not move existing files",
  );
  const report = {
    native: true,
    testedAt: new Date().toISOString(),
    pathInputCreatesDirectory: true,
    unicodeAndSpaces: true,
    persistedAfterReload: true,
    existingModelDiscovery: true,
    invalidPathRetainsSettings: true,
    mcp: mcp.message,
    mcpUsesSelectedWorkspace: true,
    downloadInSelectedWorkspace: true,
    downloadBytes: download.bytes,
    restoreDefault: true,
    existingFilesPreserved: true,
    cadSaveVerifiedWithFixtureOnly: true,
    folderPickerManuallyTested: false,
  };
  await writeFile(
    "docs/workspace-smoke-results.json",
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}

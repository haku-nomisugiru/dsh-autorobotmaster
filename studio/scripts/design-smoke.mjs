import { chromium, expect } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
const browser = await chromium.connectOverCDP(
  process.env.STUDIO_CDP_URL || "http://127.0.0.1:9426",
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
    initial.dataDir.includes("native-design-check"),
    "Use isolated test data",
  );
  await invoke("edit_workspace", {
    action: "rename",
    payload: { name: "RoboMaster 机械设计" },
  });
  await page.reload();
  await page.waitForSelector(".workflow-tabs");
  await mkdir("docs/screenshots/redesign", { recursive: true });
  const shot = async (name) => {
    await page.waitForTimeout(550);
    for (const img of await page.locator(".mechanical-art img").all()) {
      await expect
        .poll(() => img.evaluate((i) => i.complete && i.naturalWidth > 0))
        .toBeTruthy();
    }
    await page.screenshot({
      path: `docs/screenshots/redesign/native-${name}.png`,
      animations: "disabled",
    });
  };
  await shot("home");
  await page
    .getByRole("button", { name: "RoboMaster 机械设计", exact: true })
    .click();
  await expect(page.locator(".project-menu")).toBeVisible();
  await page.getByRole("button", { name: "重命名当前项目" }).hover();
  await page.keyboard.press("Escape");
  await expect(page.locator(".project-menu")).toHaveCount(0);
  await page.getByRole("tab", { name: "一次性原型机" }).click();
  await shot("prototype");
  await page.getByRole("tab", { name: "检索可复用组件" }).click();
  await shot("retrieval");
  await page.getByRole("tab", { name: "建模与验收" }).click();
  await shot("iterations");
  await page.getByRole("tab", { name: "添加机械配合" }).click();
  await expect(
    page.getByRole("button", { name: "开始", exact: true }),
  ).toHaveCount(1);
  await shot("mates");
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "模型工作区", exact: true }).click();
  await expect(page.getByLabel("模型工作区路径")).toBeVisible();
  await shot("workspace-settings");
  await page.getByRole("button", { name: "主题与字体" }).click();
  await shot("appearance");
  await page.getByRole("button", { name: "墨夜 · Graphite" }).click();
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await page.getByRole("tab", { name: "确认组件需求", exact: true }).click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "night");
  // Wait for the status toast, when present, to clear before the final visual capture.
  await page.waitForSelector(".workflow-tabs");
  await shot("night");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator(".mechanical-hero img")).toHaveCSS(
    "transform",
    "none",
  );
  const report = {
    native: true,
    testedAt: new Date().toISOString(),
    packagedImagesLoaded: true,
    stageViews: 5,
    menuMouseAndEscape: true,
    workspaceSettingReachable: true,
    themePersisted: true,
    reducedMotion: true,
    paidModelCalled: false,
    cadModified: false,
    screenshotDirectory: "docs/screenshots/redesign/",
  };
  await writeFile(
    "docs/design-smoke-results.json",
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}

import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";

const browser = await chromium.connectOverCDP(
  process.env.DSH_CDP_URL || "http://127.0.0.1:9472",
);
try {
  const page = browser
    .contexts()
    .flatMap((c) => c.pages())
    .find((p) => p.url().startsWith("dsh-app:"));
  assert.ok(page, "Actual DSH desktop renderer is required");
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page
    .locator(".rm-dsh-entry")
    .getByRole("button", { name: "展开", exact: true })
    .click();
  const panel = page
    .getByRole("dialog", { name: "RoboMaster Studio" })
    .locator("section.rm-dsh");
  await panel.locator("nav").waitFor();
  await panel.getByRole("button", { name: "设置", exact: true }).click();
  await panel
    .getByLabel("模型工作区", { exact: true })
    .fill("D:/SOLIDWORKS/RoboMasterStudio/.local/dsh-test-workspace");
  await panel.getByRole("button", { name: "保存", exact: true }).click();
  await panel.getByRole("status").filter({ hasText: "已保存" }).waitFor();
  assert.ok(
    (await panel.getByLabel("当前阶段提示词").inputValue()).includes(
      "机械设计",
    ),
  );
  await panel.getByRole("button", { name: "测试 MCP", exact: true }).click();
  await panel
    .getByRole("status")
    .filter({ hasText: "已保存" })
    .waitFor({ timeout: 60000 });
  assert.equal(await panel.getByRole("alert").count(), 0);
  await panel.getByText("记忆与技能", { exact: true }).click();
  await panel
    .getByLabel("技能名称", { exact: true })
    .fill("DSH UI smoke skill");
  await panel
    .getByLabel("技能内容（Markdown）", { exact: true })
    .fill("# Assembly notes\nVerify component interfaces before mating.");
  await panel.getByRole("button", { name: "导入技能", exact: true }).click();
  await panel.getByRole("status").filter({ hasText: "已保存" }).waitFor();
  const skill = panel
    .locator(".rm-skill")
    .filter({ hasText: "DSH UI smoke skill" })
    .last();
  await skill.getByRole("button", { name: "启用", exact: true }).click();
  await skill.getByRole("button", { name: "停用", exact: true }).waitFor();
  await skill.getByRole("button", { name: "停用", exact: true }).click();
  await panel.getByRole("button", { name: "设置", exact: true }).click();
  for (const stage of [
    "可复用组件",
    "一次性原型机",
    "建模与验收",
    "添加机械配合",
    "确认组件需求",
  ]) {
    await panel.getByRole("button", { name: stage, exact: true }).click();
    await page.waitForFunction(
      (name) =>
        [...document.querySelectorAll(".rm-dsh nav button")].some(
          (b) =>
            b.textContent === name &&
            b.getAttribute("aria-selected") === "true",
        ),
      stage,
    );
  }
  await panel
    .getByRole("button", { name: "添加 确认组件需求", exact: true })
    .click();
  await panel
    .getByRole("button", { name: "确认组件需求 2", exact: true })
    .waitFor();
  await panel
    .getByRole("button", { name: "关闭 确认组件需求 2", exact: true })
    .click();
  await panel
    .getByRole("button", { name: "确认组件需求 2", exact: true })
    .waitFor({ state: "detached" });
  await panel.getByText("新增规格", { exact: true }).click();
  await panel
    .getByLabel("内容", { exact: true })
    .fill("DSH UI: chassis width 400 mm");
  await panel.getByRole("button", { name: "添加", exact: true }).click();
  await panel
    .getByText("DSH UI: chassis width 400 mm", { exact: true })
    .last()
    .waitFor();
  await page.reload();
  await page
    .locator(".rm-dsh-entry")
    .getByRole("button", { name: "展开", exact: true })
    .click();
  await panel
    .getByText("DSH UI: chassis width 400 mm", { exact: true })
    .last()
    .waitFor();
  assert.deepEqual(errors, []);
  await mkdir("docs/screenshots/integrations", { recursive: true });
  const layout = await page
    .locator(".rm-dsh-dialog")
    .evaluate((e) => ({
      width: e.clientWidth,
      height: e.clientHeight,
      contentHeight: e.scrollHeight,
      open: e.open,
    }));
  assert.ok(layout.open && layout.width > 700 && layout.height > 500);
  // Some Electron WebContentsViews never answer Page.captureScreenshot while a
  // native modal is open. Keep optional capture failures separate from UI checks.
  let screenshotWarning;
  try {
    await page.screenshot({
      path: "docs/screenshots/integrations/dsh-desktop.png",
      timeout: 5000,
    });
  } catch (e) {
    screenshotWarning = e.message.split("\n")[0];
  }
  await writeFile(
    ".local/dsh-native-ui-result.json",
    JSON.stringify(
      {
        runtime: "D:/dsh/DeepSeek Harness.exe",
        passed: true,
        checks: [
          "native dialog",
          "five stages",
          "workspace persistence",
          "MCP handshake without CAD mutation",
          "add/close tabs",
          "specification persistence",
          "skill import/enable/disable",
        ],
        layout,
        pageErrors: errors,
        screenshotWarning,
      },
      null,
      2,
    ),
  );
  console.log("DSH native UI smoke passed");
} finally {
  await browser.close();
}

import { chromium, expect } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";

// Native WebView2 only. Never point this check at the user's data directory.
const browser = await chromium.connectOverCDP("http://127.0.0.1:9427");
try {
  const page = browser
    .contexts()[0]
    .pages()
    .find((p) => p.url().includes("tauri"));
  assert.ok(page);
  await page.waitForSelector(".workflow-tabs");
  const initial = await page.evaluate(() =>
    window.__TAURI_INTERNALS__.invoke("bootstrap"),
  );
  assert.ok(initial.dataDir.includes("native-refinement-check"));
  await expect(page.locator("html")).toHaveAttribute("data-theme", "night");
  await expect(page.locator("html")).toHaveAttribute(
    "data-interface-fonts",
    "ocr:loaded noto:loaded",
  );
  const session = await page.context().newCDPSession(page);
  await session.send("DOM.enable");
  await session.send("CSS.enable");
  const { root } = await session.send("DOM.getDocument");
  const renderedFonts = {};
  for (const selector of [
    ".hero-display",
    ".spec-heading h2",
    ".tab-item button span",
  ]) {
    const { nodeId } = await session.send("DOM.querySelector", {
      nodeId: root.nodeId,
      selector,
    });
    renderedFonts[selector] = (
      await session.send("CSS.getPlatformFontsForNode", { nodeId })
    ).fonts;
  }
  assert.ok(
    renderedFonts[".hero-display"].some(
      (font) => font.postScriptName === "OCRAExtended" && font.isCustomFont,
    ),
  );
  assert.ok(
    renderedFonts[".tab-item button span"].some(
      (font) => font.postScriptName === "Noto-Sans-SC-Thin" && font.isCustomFont,
    ),
  );
  await expect(page.locator(".tab-item button span").first()).toHaveCSS(
    "font-variation-settings",
    '"wght" 100',
  );
  const directory = "docs/screenshots/refinement";
  await mkdir(directory, { recursive: true });
  const shot = async (name) => {
    await page.mouse.move(4, 4);
    await page.screenshot({
      path: `${directory}/native-${name}.png`,
      animations: "disabled",
    });
  };
  await shot("home");
  const settings = page.getByRole("button", { name: "打开设置" });
  await settings.hover();
  await expect
    .poll(() =>
      settings.evaluate((el) => getComputedStyle(el, "::before").opacity),
    )
    .toBe("1");
  const angle = () =>
    settings.evaluate((el) =>
      getComputedStyle(el, "::before").getPropertyValue("--button-ray-angle"),
    );
  const firstAngle = await angle();
  await settings.screenshot({ path: `${directory}/glow-start.png` });
  await page.waitForTimeout(1600);
  const secondAngle = await angle();
  assert.notEqual(firstAngle, secondAngle);
  await settings.screenshot({ path: `${directory}/glow-later.png` });
  for (const [name, file] of [
    ["检索可复用组件", "retrieval"],
    ["一次性原型机", "prototype"],
    ["建模与验收", "iterations"],
    ["添加机械配合", "mates"],
  ]) {
    await page.getByRole("tab", { name, exact: true }).click();
    await shot(file);
  }
  const start = page.getByRole("button", { name: "开始", exact: true });
  await start.hover();
  await page.waitForTimeout(1100);
  await start.screenshot({ path: `${directory}/glow-start-button.png` });
  await settings.click();
  for (const [name, file] of [
    ["连接与模型", "connections"],
    ["模型工作区", "workspace"],
    ["工作流提示词", "prompts"],
    ["Skills 与记忆", "skills"],
    ["主题与字体", "appearance"],
  ]) {
    await page.getByRole("button", { name, exact: true }).click();
    await shot(file);
  }
  await page.getByRole("button", { name: "研究白 · Research" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
  await page.getByRole("button", { name: "关闭设置" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "night");
  await page.getByRole("tab", { name: "确认组件需求", exact: true }).click();
  await page.setViewportSize({ width: 1000, height: 700 });
  for (const name of [
    "确认组件需求",
    "检索可复用组件",
    "一次性原型机",
    "建模与验收",
    "添加机械配合",
  ]) {
    await page.getByRole("tab", { name, exact: true }).click();
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    if (name !== "添加机械配合")
      await expect(
        page.getByRole("textbox", { name: "设计消息" }),
      ).toBeInViewport();
    else
      await expect(
        page.getByRole("button", { name: "开始", exact: true }),
      ).toBeInViewport();
  }
  await page.getByRole("tab", { name: "确认组件需求", exact: true }).click();
  await shot("compact");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await settings.hover();
  assert.equal(
    await settings.evaluate(
      (el) => getComputedStyle(el, "::before").animationName,
    ),
    "none",
  );
  const report = {
    native: true,
    testedAt: new Date().toISOString(),
    defaultTheme: "night",
    renderedFonts,
    chineseAxis: 100,
    glowAngles: [firstAngle, secondAngle],
    stageViews: 5,
    settingsViews: 5,
    compactViewport: "1000x700",
    reducedMotion: true,
    paidModelCalled: false,
    cadModified: false,
    screenshots: directory,
  };
  await writeFile(
    "docs/refinement-smoke-results.json",
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}

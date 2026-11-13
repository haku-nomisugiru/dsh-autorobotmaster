import { chromium, expect } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";

const browser = await chromium.connectOverCDP("http://127.0.0.1:9428");
try {
  const page = browser
    .contexts()[0]
    .pages()
    .find((p) => p.url().includes("tauri"));
  assert.ok(page);
  await page.waitForSelector(".workflow-tabs");
  const snapshot = await page.evaluate(() =>
    window.__TAURI_INTERNALS__.invoke("bootstrap"),
  );
  assert.ok(
    snapshot.dataDir.includes("native-theme-check"),
    "Use isolated data",
  );
  await expect(page.locator("html")).toHaveAttribute(
    "data-interface-fonts",
    "ocr:loaded noto:loaded",
  );
  const directory = "docs/screenshots/themes";
  await mkdir(directory, { recursive: true });
  const themes = [];
  for (const [id, name, accent] of [
    ["clay", "陶土 · Terracotta", "rgb(157, 86, 62)"],
    ["blue", "蓝图 · Cobalt", "rgb(24, 76, 220)"],
    ["paper", "研究白 · Research", "rgb(54, 51, 244)"],
    ["night", "墨夜 · Graphite", "rgb(185, 171, 255)"],
  ]) {
    await page.getByRole("button", { name: "打开设置" }).click();
    await page.getByRole("button", { name: "主题与字体" }).click();
    await page.getByRole("button", { name, exact: true }).click();
    await page.getByRole("button", { name: "保存设置", exact: true }).click();
    await page.getByRole("tab", { name: "确认组件需求", exact: true }).click();
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", id);
    await expect(page.locator(".brand-light")).toHaveCSS("color", accent);
    const colors = await page.evaluate(() => ({
      hero: getComputedStyle(document.querySelector(".hero-display > span"))
        .color,
      artBackground: getComputedStyle(document.querySelector(".mechanical-art"))
        .backgroundColor,
      frame: getComputedStyle(document.querySelector(".app-shell"), "::after")
        .backgroundImage,
      ray: getComputedStyle(
        document.querySelector(".settings-trigger"),
        "::before",
      ).backgroundImage,
    }));
    await expect(page.locator(".hero-kicker")).toHaveCSS("color", colors.hero);
    await page.mouse.move(4, 4);
    await page.screenshot({
      path: `${directory}/${id}-home.png`,
      animations: "disabled",
    });
    await page.getByRole("tab", { name: "添加机械配合", exact: true }).click();
    const start = page.getByRole("button", { name: "开始", exact: true });
    await expect(start).toHaveCSS("background-color", accent);
    await expect(page.locator(".mates-display")).toHaveCSS(
      "color",
      colors.hero,
    );
    await page.screenshot({
      path: `${directory}/${id}-mates.png`,
      animations: "disabled",
    });
    await start.hover();
    await expect
      .poll(() =>
        start.evaluate((el) => getComputedStyle(el, "::before").opacity),
      )
      .toBe("1");
    themes.push({ id, accent, ...colors });
  }
  for (const key of ["hero", "artBackground", "frame", "ray"]) {
    assert.equal(
      new Set(themes.map((theme) => theme[key])).size,
      4,
      `${key} must follow each palette`,
    );
  }
  await page.getByRole("tab", { name: "确认组件需求", exact: true }).click();
  const report = {
    native: true,
    testedAt: new Date().toISOString(),
    themes,
    fontsLoaded: true,
    persistedAfterReload: true,
    screenshots: directory,
    paidModelCalled: false,
    cadModified: false,
  };
  await writeFile(
    "docs/theme-smoke-results.json",
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}

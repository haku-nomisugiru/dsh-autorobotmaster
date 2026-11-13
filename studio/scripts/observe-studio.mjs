import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
const browser = await chromium.connectOverCDP("http://127.0.0.1:9425");
const context = browser.contexts()[0];
let page = context.pages().find((p) => p.url().includes("127.0.0.1:1420"));
if (!page) {
  page = await context.newPage();
  await page.goto("http://127.0.0.1:1420");
}
await page.setViewportSize({ width: 1440, height: 960 });
await page.waitForSelector(".workflow-tabs");
const click = async (role, name) => {
  const target = page.getByRole(role, { name, exact: true });
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, {
    steps: 8,
  });
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
};
const action = process.argv[2] || "home";
if (action === "home") {
  await page.reload();
}
if (action === "hover") {
  await page.mouse.move(215, 710, { steps: 12 });
}
if (action === "prototype") {
  await click("tab", "一次性原型机");
}
if (action === "mates") {
  await click("tab", "添加机械配合");
  await page.mouse.move(148, 745, { steps: 10 });
}
if (action === "search") {
  await click("tab", "检索可复用组件");
}
if (action === "modeling") {
  await click("tab", "建模与验收");
}
if (action === "settings") {
  await click("button", "打开设置");
  await click("button", "主题与字体");
}
if (action === "night") {
  await click("button", "墨夜 · Graphite");
  await click("button", "保存设置");
  await click("tab", "确认组件需求");
}
if (action === "compact") {
  await page.setViewportSize({ width: 1000, height: 700 });
}
if (action === "restore") {
  await click("button", "打开设置");
  await click("button", "主题与字体");
  await click("button", "研究白 · Research");
  await click("button", "保存设置");
}
await page.waitForTimeout(550);
await mkdir("docs/screenshots/redesign", { recursive: true });
await page.screenshot({ path: `docs/screenshots/redesign/${action}.png` });
console.log(`Observed ${action}: ${page.url()}`);
process.exit(0);

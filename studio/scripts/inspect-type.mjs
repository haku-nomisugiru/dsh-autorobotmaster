import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
const browser = await chromium.connectOverCDP("http://127.0.0.1:9427");
try {
  const page = browser
    .contexts()[0]
    .pages()
    .find((p) => p.url().includes("tauri"));
  await page.waitForSelector(".mechanical-hero");
  await page.evaluate(() => document.fonts.ready);
  const session = await page.context().newCDPSession(page);
  await session.send("DOM.enable");
  await session.send("CSS.enable");
  const { root } = await session.send("DOM.getDocument");
  const fonts = {};
  for (const selector of [
    ".hero-display",
    ".spec-heading h2",
    ".tab-item button span",
  ]) {
    const { nodeId } = await session.send("DOM.querySelector", {
      nodeId: root.nodeId,
      selector,
    });
    fonts[selector] = await session.send("CSS.getPlatformFontsForNode", {
      nodeId,
    });
  }
  await mkdir("docs/screenshots/refinement", { recursive: true });
  await page.screenshot({
    path: "docs/screenshots/refinement/native-home.png",
    animations: "disabled",
  });
  await writeFile(".local/font-probe.json", JSON.stringify(fonts, null, 2));
  console.log(JSON.stringify(fonts, null, 2));
} finally {
  await browser.close();
}

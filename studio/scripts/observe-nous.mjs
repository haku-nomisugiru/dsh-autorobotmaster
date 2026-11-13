import { chromium } from "@playwright/test";
const browser = await chromium.connectOverCDP("http://127.0.0.1:9425");
const page = browser.contexts()[0].pages()[0];
await page.setViewportSize({ width: 1440, height: 1000 });
const step = process.argv[2];
if (step === "hover") {
  await page.goto("https://nousresearch.com/", {
    waitUntil: "domcontentloaded",
  });
  await page.waitForTimeout(1800);
  await page.mouse.move(192, 80);
  await page.waitForTimeout(180);
} else if (step === "menu") {
  await page.mouse.click(192, 80);
  await page.screenshot({ path: ".local/nous-reference/menu-start.png" });
  await page.waitForTimeout(350);
} else if (step === "menu-hover") {
  await page.mouse.move(385, 330);
  await page.waitForTimeout(180);
} else if (step === "scroll") {
  await page.keyboard.press("Escape");
  await page.mouse.click(1200, 500);
  await page.mouse.wheel(0, 880);
  await page.waitForTimeout(650);
} else if (step === "theme") {
  await page.keyboard.press("Home");
  await page.keyboard.press("Control+Home");
  await page.waitForTimeout(200);
  await page.mouse.click(1417, 21);
  await page.waitForTimeout(400);
} else if (step === "chat") {
  await page.mouse.click(700, 171);
  await page.screenshot({ path: ".local/nous-reference/chat-start.png" });
  await page.waitForTimeout(600);
}
await page.screenshot({
  path: `.local/nous-reference/interaction-${step}.png`,
});
console.log(
  JSON.stringify({
    step,
    url: page.url(),
    screenshot: `.local/nous-reference/interaction-${step}.png`,
  }),
);
process.exit(0);

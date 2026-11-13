import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
const dir = ".local/nous-reference";
await mkdir(dir, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH,
  headless: true,
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    ignoreHTTPSErrors: true,
  });
  await page.goto("https://nousresearch.com/", {
    waitUntil: "domcontentloaded",
    timeout: 45000,
  });
  await page.waitForTimeout(3500);
  await page.screenshot({ path: `${dir}/home.png` });
  const report = await page.evaluate(() => {
    const selectors = [
      "body",
      "header",
      "nav",
      "h1",
      "h2",
      "h3",
      "p",
      "button",
      "a",
    ];
    const styles = selectors.flatMap((selector) =>
      [...document.querySelectorAll(selector)].slice(0, 6).map((el) => {
        const s = getComputedStyle(el);
        return {
          tag: selector,
          text: el.textContent?.trim().slice(0, 100),
          class: el.className,
          font: s.fontFamily,
          size: s.fontSize,
          weight: s.fontWeight,
          color: s.color,
          background: s.backgroundColor,
          border: s.border,
          radius: s.borderRadius,
          spacing: s.letterSpacing,
          transform: s.transform,
          transition: s.transition,
          animation: s.animation,
        };
      }),
    );
    const css = [];
    for (const sheet of document.styleSheets) {
      try {
        for (const rule of sheet.cssRules) {
          if (
            /keyframes|animation|transition|:hover|font-face/.test(rule.cssText)
          )
            css.push(rule.cssText);
        }
      } catch {}
    }
    return {
      styles,
      css,
      scripts: [...document.scripts].map((s) => s.src).filter(Boolean),
      sheets: [...document.styleSheets].map((s) => s.href),
      buttons: [...document.querySelectorAll("button")].map((b) => ({
        text: b.textContent,
        label: b.getAttribute("aria-label"),
      })),
    };
  });
  await writeFile(`${dir}/design.json`, JSON.stringify(report, null, 2));
  console.log(
    JSON.stringify(
      {
        styles: report.styles.slice(0, 17),
        buttons: report.buttons,
        cssCount: report.css.length,
        scripts: report.scripts,
      },
      null,
      2,
    ),
  );
  const about = page.getByText("About Nous", { exact: true }).first();
  if (await about.count()) {
    await about.hover();
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${dir}/navigation-hover.png` });
  }
  await page.keyboard.press("Control+k");
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${dir}/command.png` });
} finally {
  await browser.close();
}

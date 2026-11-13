import { test, expect } from "@playwright/test";
test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("tab")).toHaveCount(5);
});
test("Codex connection hides API credentials and keeps an optional model", async ({page}) => {
  await page.getByRole("button", {name:"打开设置"}).click();
  await page.getByLabel("接入方式").selectOption("codex");
  await expect(page.getByLabel("Codex 程序路径")).toBeVisible();
  await expect(page.getByLabel(/^API Key/)).toHaveCount(0);
  await expect(page.getByLabel("模型 ID", {exact:true})).toHaveAttribute("placeholder", "留空使用 Codex 默认模型");
  await page.getByLabel("Codex 程序路径").fill("D:\\tools\\codex.exe");
  await page.getByRole("button", {name:"保存设置",exact:true}).click();
  await page.reload();
  await page.getByRole("button", {name:"打开设置"}).click();
  await expect(page.getByLabel("接入方式")).toHaveValue("codex");
  await expect(page.getByLabel("Codex 程序路径")).toHaveValue("D:\\tools\\codex.exe");
  await page.getByLabel("接入方式").selectOption("responses");
  await expect(page.getByLabel(/^API Key/)).toBeVisible();
});
test("five stages preserve a minimum of one window per type", async ({
  page,
}) => {
  await expect(
    page.getByRole("button", { name: /关闭确认组件需求窗口/ }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "新建确认组件需求窗口" }).click();
  await expect(page.getByRole("tab")).toHaveCount(6);
  await expect(
    page.getByRole("button", { name: /关闭确认组件需求窗口/ }),
  ).toHaveCount(2);
  await page.getByRole("button", { name: "关闭确认组件需求窗口 2" }).click();
  await expect(page.getByRole("tab")).toHaveCount(5);
  await expect(
    page.getByRole("button", { name: /关闭确认组件需求窗口/ }),
  ).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("tab")).toHaveCount(5);
});
test("independent drafts persist across stage changes and reload", async ({
  page,
}) => {
  await page.getByRole("textbox", { name: "设计消息" }).fill("底盘包络待讨论");
  await page.getByRole("tab", { name: "一次性原型机" }).click();
  await page
    .getByRole("textbox", { name: "设计消息" })
    .fill("安装板外形 80×50×6 mm");
  await page.getByRole("tab", { name: "确认组件需求", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "设计消息" })).toHaveValue(
    "底盘包络待讨论",
  );
  await page.reload();
  await expect(page.getByRole("textbox", { name: "设计消息" })).toHaveValue(
    "底盘包络待讨论",
  );
});
test("structured specification requires evidence for verified parts", async ({
  page,
}) => {
  await page.getByRole("button", { name: "添加已核实的零件信息" }).click();
  await page.getByLabel("规格内容").fill("电机安装孔距 25 mm");
  await page.getByRole("button", { name: "保存规格", exact: true }).click();
  await expect(page.getByLabel("来源 / 证据（必填）")).toBeVisible();
  await page.getByLabel("来源 / 证据（必填）").fill("用户实测记录 01");
  await page.getByRole("button", { name: "保存规格", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /电机安装孔距 25 mm/ }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByText("用户实测记录 01")).toBeVisible();
});
test("settings themes preview and persist only after save", async ({
  page,
}) => {
  await expect(page.locator("html")).toHaveAttribute("data-theme", "night");
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "主题与字体" }).click();
  await page.getByRole("button", { name: "研究白 · Research" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
  await page.getByRole("button", { name: "关闭设置" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "night");
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "主题与字体" }).click();
  await page.getByRole("button", { name: "研究白 · Research" }).click();
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "paper");
});

test("edge light follows hover, stays off when disabled, and respects reduced motion", async ({
  page,
}) => {
  const settings = page.getByRole("button", { name: "打开设置" });
  const edge = () =>
    settings.evaluate((el) => {
      const style = getComputedStyle(el, "::before");
      return {
        opacity: style.opacity,
        animation: style.animationName,
        angle: style.getPropertyValue("--button-ray-angle"),
      };
    });
  expect((await edge()).opacity).toBe("0");
  await settings.hover();
  await expect.poll(async () => (await edge()).opacity).toBe("1");
  expect((await edge()).animation).toBe("button-edge-drift");
  const firstAngle = (await edge()).angle;
  await expect.poll(async () => (await edge()).angle).not.toBe(firstAngle);
  const send = page.getByRole("button", { name: "发送消息" });
  await send.hover({ force: true });
  expect(
    await send.evaluate((el) => getComputedStyle(el, "::before").opacity),
  ).toBe("0");
  await settings.click();
  await page.getByRole("button", { name: "主题与字体" }).click();
  const font = page.getByRole("button", { name: /OCR A \+ 思源黑体/ });
  await expect(font).toHaveClass(/selected/);
  await expect(font).toHaveCSS("font-variation-settings", '"wght" 100');
  expect(
    await font.evaluate((el) => getComputedStyle(el).fontFamily),
  ).toContain('"OCR A Extended"');
  await font.hover();
  await expect
    .poll(() => font.evaluate((el) => getComputedStyle(el, "::before").opacity))
    .toBe("1");
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await font.evaluate((el) => getComputedStyle(el, "::before").animationName),
  ).toBe("none");
  await page.getByRole("button", { name: "关闭设置" }).click();
});

test("every theme updates artwork accents, frame light, and assembly controls together", async ({
  page,
}) => {
  const heroColors = new Set<string>();
  const frameColors = new Set<string>();
  const rayColors = new Set<string>();
  for (const [id, name, accent, ink] of [
    ["clay", "陶土 · Terracotta", "rgb(157, 86, 62)", "rgb(255, 247, 237)"],
    ["blue", "蓝图 · Cobalt", "rgb(24, 76, 220)", "rgb(255, 255, 255)"],
    ["paper", "研究白 · Research", "rgb(54, 51, 244)", "rgb(255, 255, 255)"],
    ["night", "墨夜 · Graphite", "rgb(185, 171, 255)", "rgb(25, 20, 44)"],
  ]) {
    await page.getByRole("button", { name: "打开设置" }).click();
    await page.getByRole("button", { name: "主题与字体" }).click();
    await page.getByRole("button", { name, exact: true }).click();
    await page.getByRole("button", { name: "保存设置", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", id);
    await page.getByRole("tab", { name: "确认组件需求", exact: true }).click();
    const hero = await page
      .locator(".hero-display > span")
      .evaluate((el) => getComputedStyle(el).color);
    heroColors.add(hero);
    await expect(page.locator(".hero-kicker")).toHaveCSS("color", hero);
    await expect(page.locator(".signal-bars i").first()).toHaveCSS(
      "background-color",
      hero,
    );
    await expect(page.locator(".mechanical-art img").first()).toHaveCSS(
      "filter",
      "grayscale(1)",
    );
    frameColors.add(
      await page
        .locator(".app-shell")
        .evaluate((el) => getComputedStyle(el, "::after").backgroundImage),
    );
    rayColors.add(
      await page
        .locator(".settings-trigger")
        .evaluate((el) => getComputedStyle(el, "::before").backgroundImage),
    );
    for (const [stage, selector] of [
      ["检索可复用组件", ".search-banner .eyebrow"],
      ["建模与验收", ".iteration-banner .eyebrow"],
      ["添加机械配合", ".mates-display"],
    ]) {
      await page.getByRole("tab", { name: stage, exact: true }).click();
      await expect(page.locator(selector)).toHaveCSS("color", hero);
    }
    const start = page.getByRole("button", { name: "开始", exact: true });
    await expect(start).toHaveCSS("background-color", accent);
    await expect(start).toHaveCSS("color", ink);
  }
  expect(heroColors.size).toBe(4);
  expect(frameColors.size).toBe(4);
  expect(rayColors.size).toBe(4);
});
test("stage prompts can be edited and retained", async ({ page }) => {
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "工作流提示词" }).click();
  await page.getByRole("button", { name: "配合", exact: true }).click();
  await page
    .getByRole("textbox", { name: "阶段提示词" })
    .fill("先读取组件，再保留转动自由度。");
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "工作流提示词" }).click();
  await page.getByRole("button", { name: "配合", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "阶段提示词" })).toHaveValue(
    "先读取组件，再保留转动自由度。",
  );
});

test("model workspace persists, can be reset, and discards unsaved changes", async ({
  page,
}) => {
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "模型工作区", exact: true }).click();
  await page.getByLabel("模型工作区路径").fill("D:\\机器人 项目\\CAD");
  await expect(
    page.getByText("路径已修改，点击右下角「保存设置」后生效。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await page.reload();
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "模型工作区", exact: true }).click();
  await expect(page.getByLabel("模型工作区路径")).toHaveValue(
    "D:\\机器人 项目\\CAD",
  );
  await expect(page.locator(".workspace-location")).toHaveText(
    "D:\\机器人 项目\\CAD",
  );
  await page.getByLabel("模型工作区路径").fill("D:\\未保存");
  await page.getByRole("button", { name: "关闭设置" }).click();
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "模型工作区", exact: true }).click();
  await expect(page.getByLabel("模型工作区路径")).toHaveValue(
    "D:\\机器人 项目\\CAD",
  );
  await page.getByRole("button", { name: "恢复默认目录" }).click();
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "模型工作区", exact: true }).click();
  await expect(page.getByLabel("模型工作区路径")).toHaveValue("");
});

test("invalid model workspace remains unsaved with feedback", async ({
  page,
}) => {
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "模型工作区", exact: true }).click();
  await page.getByLabel("模型工作区路径").fill("relative-folder");
  await page.getByRole("button", { name: "保存设置", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("完整的文件夹路径");
  await expect(page.getByLabel("模型工作区路径")).toHaveValue(
    "relative-folder",
  );
});
test("mates stage has only one start action and no composer", async ({
  page,
}) => {
  await page.getByRole("tab", { name: "添加机械配合" }).click();
  await expect(
    page.getByRole("button", { name: "开始", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("textbox", { name: "设计消息" })).toHaveCount(0);
});
test("browser preview never fabricates API or CAD success", async ({
  page,
}) => {
  await page.getByRole("textbox", { name: "设计消息" }).fill("创建测试零件");
  await page.getByRole("button", { name: "发送消息" }).click();
  await expect(page.getByRole("status")).toContainText("当前为界面预览");
  await expect(page.locator(".message.assistant")).toHaveCount(0);
});
test("search provides both retrieval entries and honest errors", async ({
  page,
}) => {
  await page.getByRole("tab", { name: "检索可复用组件" }).click();
  await expect(
    page.getByRole("button", { name: /本地 CAD RAG/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: /step.parts/ }).click();
  await page.getByRole("textbox", { name: "组件检索词" }).fill("bearing");
  await page.getByRole("button", { name: "检索", exact: true }).click();
  await expect(page.locator(".inline-error")).toContainText("界面预览");
});
test("workspace and settings render without horizontal overflow", async ({
  page,
}) => {
  await page.screenshot({
    path: "docs/screenshots/workspace.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "打开设置" }).click();
  await page.getByRole("button", { name: "主题与字体" }).click();
  await page.screenshot({
    path: "docs/screenshots/settings.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "关闭设置" }).click();
  await page.setViewportSize({ width: 1000, height: 700 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "docs/screenshots/compact.png",
    fullPage: true,
    animations: "disabled",
  });
});
test("switching stages starts at the new workspace heading", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1000, height: 700 });
  await page
    .locator(".workspace-scroll")
    .evaluate((element) => element.scrollTo({ top: 400, behavior: "instant" }));
  await page.getByRole("tab", { name: "检索可复用组件" }).click();
  await expect
    .poll(() =>
      page
        .locator(".workspace-scroll")
        .evaluate((element) => element.scrollTop),
    )
    .toBe(0);
  await expect(page.getByText("DON’T REINVENT. REDISCOVER.")).toBeInViewport();
});

test("mechanical art loads and motion respects the system preference", async ({
  page,
}) => {
  const art = page.locator(".mechanical-hero .mechanical-art");
  const picture = art.locator("img");
  await expect(picture).toHaveAttribute("alt", "轮组与悬挂机械结构爆炸图");
  await expect
    .poll(() =>
      picture.evaluate(
        (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
      ),
    )
    .toBeTruthy();
  const box = (await art.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.85, box.y + box.height * 0.6);
  await expect
    .poll(() => art.evaluate((el) => el.style.getPropertyValue("--art-x")))
    .not.toBe("");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(picture).toHaveCSS("transform", "none");
  await expect(page.locator(".stage-content")).toHaveCSS(
    "animation-name",
    "none",
  );
  expect(
    await page
      .locator(".app-shell")
      .evaluate((el) => getComputedStyle(el, "::after").animationName),
  ).toBe("none");
  await page.getByRole("tab", { name: "一次性原型机" }).click();
  await expect(
    page.getByRole("img", { name: "电机转子与定子结构爆炸图" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "检索可复用组件" }).click();
  await expect(
    page.getByRole("img", { name: "控制板与外壳结构爆炸图" }),
  ).toBeVisible();
});

test("all five redesigned stages remain usable in a compact window", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1000, height: 700 });
  for (const name of [
    "确认组件需求",
    "检索可复用组件",
    "一次性原型机",
    "建模与验收",
    "添加机械配合",
  ]) {
    await page.getByRole("tab", { name, exact: true }).click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    if (name !== "添加机械配合")
      await expect(
        page.getByRole("textbox", { name: "设计消息" }),
      ).toBeInViewport();
    else {
      const start = page.getByRole("button", { name: "开始", exact: true });
      await start.scrollIntoViewIfNeeded();
      await expect(start).toBeInViewport();
    }
  }
});

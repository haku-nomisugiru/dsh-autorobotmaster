import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/ui",
  fullyParallel: true,
  workers: 3,
  use: {
    baseURL: "http://127.0.0.1:1420",
    browserName: "chromium",
    launchOptions: { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH },
    viewport: { width: 1440, height: 960 },
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: process.env.STUDIO_TEST_EXTERNAL_SERVER
    ? undefined
    : {
        command: "npm run dev",
        url: "http://127.0.0.1:1420",
        reuseExistingServer: true,
      },
  reporter: [
    ["list"],
    ["json", { outputFile: "test-results/ui-results.json" }],
  ],
});

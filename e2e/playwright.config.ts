import { defineConfig, devices } from "@playwright/test";
import dotenv from "dotenv";
import path from "path";

dotenv.config({ path: path.resolve(__dirname, ".env.e2e") });

const FRONTEND_URL = process.env.FRONTEND_URL || "http://localhost:3049";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: 4,
  globalTimeout: 3_600_000, // 60 minutes for full suite
  reporter: process.env.CI
    ? [["html", { open: "never" }], ["github"]]
    : [["html", { open: "on-failure" }]],
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: FRONTEND_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    ...devices["Desktop Chrome"],
  },
  globalSetup: "./global-setup.ts",
  globalTeardown: "./global-teardown.ts",
  projects: [
    {
      name: "non-game",
      testMatch: ["**/auth/**", "**/smoke/**", "**/profile/**"],
    },
    {
      name: "rooms",
      testMatch: ["**/rooms/**"],
    },
    {
      name: "undercover",
      testMatch: ["**/undercover/**"],
    },
    {
      name: "codenames",
      testMatch: ["**/codenames/**"],
    },
  ],
});

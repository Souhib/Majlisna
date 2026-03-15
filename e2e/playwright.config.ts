import { defineConfig, devices } from "@playwright/test";
import dotenv from "dotenv";
import path from "path";

dotenv.config({ path: path.resolve(__dirname, ".env.e2e") });

const FRONTEND_URL = process.env.FRONTEND_URL || "http://localhost:3049";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 2,
  globalTimeout: 3_600_000, // 60 minutes for full suite
  reporter: process.env.CI
    ? [["html", { open: "never" }], ["github"]]
    : [["html", { open: "on-failure" }]],
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  use: {
    baseURL: FRONTEND_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 15_000,
    navigationTimeout: 15_000,
    ...devices["Desktop Chrome"],
    // Dismiss the first-visit language picker modal for all tests
    storageState: {
      cookies: [],
      origins: [
        {
          origin: FRONTEND_URL,
          localStorage: [
            { name: "ipg-first-visit-complete", value: "true" },
          ],
        },
      ],
    },
  },
  globalSetup: "./global-setup.ts",
  globalTeardown: "./global-teardown.ts",
  projects: [
    {
      name: "non-game",
      testMatch: [
        "**/auth/**",
        "**/smoke/**",
        "**/profile/**",
        "**/challenges/**",
        "**/friends/**",
      ],
    },
    {
      name: "rooms",
      testMatch: ["**/rooms/**", "**/chat/**"],
    },
    {
      name: "undercover",
      testMatch: ["**/undercover/**"],
      timeout: 120_000,
    },
    {
      name: "codenames",
      testMatch: ["**/codenames/**"],
      timeout: 120_000,
    },
    {
      name: "wordquiz",
      testMatch: ["**/wordquiz/**"],
      timeout: 120_000,
    },
    {
      name: "mcqquiz",
      testMatch: ["**/mcqquiz/**"],
      timeout: 120_000,
    },
    {
      name: "websocket",
      testMatch: ["**/websocket/**"],
      timeout: 120_000,
    },
    {
      name: "user-journey",
      testMatch: ["**/user-journey/**"],
      timeout: 120_000,
    },
    // Mobile viewport projects — run existing tests at iPhone 14 size (Chromium)
    {
      name: "mobile-smoke",
      testMatch: ["**/smoke/**"],
      use: {
        ...devices["iPhone 14"],
        browserName: "chromium",
      },
    },
    {
      name: "mobile-rooms",
      testMatch: ["**/rooms/**"],
      use: {
        ...devices["iPhone 14"],
        browserName: "chromium",
      },
    },
    {
      name: "mobile-wordquiz",
      testMatch: ["**/wordquiz/**"],
      timeout: 120_000,
      use: {
        ...devices["iPhone 14"],
        browserName: "chromium",
      },
    },
  ],
});

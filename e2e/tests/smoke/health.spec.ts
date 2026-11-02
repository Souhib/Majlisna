import { test, expect } from "@playwright/test";
import { test as authTest } from "../../fixtures/auth.fixture";
import { NO_SOCKET_REUSE } from "../../helpers/api-client";
import { API_URL, ROUTES } from "../../helpers/constants";

test.describe("Smoke Tests — Health", () => {
  test("backend health endpoint returns 200", async ({ request }) => {
    const response = await request.get(`${API_URL}/health`, { headers: NO_SOCKET_REUSE });
    expect(response.ok()).toBeTruthy();

    const body = await response.json();
    expect(body.status).toBe("healthy");
    expect(body.timestamp).toBeTruthy();
  });

  test("frontend loads successfully", async ({ page }) => {
    const response = await page.goto("/");
    expect(response?.ok()).toBeTruthy();
  });

  test("unauthenticated user can access login page", async ({ page }) => {
    await page.goto(ROUTES.login);
    await expect(page.locator('input[id="email"]')).toBeVisible();
    await expect(page.locator('input[id="password"]')).toBeVisible();
  });

  test("unauthenticated user can access register page", async ({ page }) => {
    await page.goto(ROUTES.register);
    await expect(page.locator('input[id="username"]')).toBeVisible();
    await expect(page.locator('input[id="email"]')).toBeVisible();
    await expect(page.locator('input[id="password"]')).toBeVisible();
  });
});

authTest.describe("Smoke Tests — Authenticated Navigation", () => {
  authTest(
    "authenticated user can navigate to rooms",
    async ({ authenticatedPage }) => {
      await authenticatedPage.goto(ROUTES.rooms);
      await authenticatedPage.waitForLoadState("domcontentloaded");
      // Rooms page should have the "Create Room" link and "Join Room" form
      await expect(authenticatedPage.locator('input[id="room-code"]')).toBeVisible();
    },
  );
});

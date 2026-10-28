import { test, expect } from "@playwright/test";
import { TEST_USER, ROUTES, STORAGE_KEYS } from "../../helpers/constants";

test.describe("Auth — Login", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(ROUTES.login);
    await page.waitForLoadState("domcontentloaded");
  });

  test("successful login navigates to home", async ({ page }) => {
    await page.locator('input[id="email"]').fill(TEST_USER.email);
    await page.locator('input[id="password"]').fill(TEST_USER.password);
    await page.locator('button[type="submit"]').click();

    // Should navigate to home page
    await page.waitForURL("/", { timeout: 15_000 });
  });

  test("successful login stores token in localStorage", async ({ page }) => {
    await page.locator('input[id="email"]').fill(TEST_USER.email);
    await page.locator('input[id="password"]').fill(TEST_USER.password);
    await page.locator('button[type="submit"]').click();

    await page.waitForURL("/", { timeout: 15_000 });

    // Verify tokens are stored in localStorage
    const token = await page.evaluate(
      (key) => localStorage.getItem(key),
      STORAGE_KEYS.token,
    );
    expect(token).toBeTruthy();
    expect(token).not.toBe("undefined");

    const refreshToken = await page.evaluate(
      (key) => localStorage.getItem(key),
      STORAGE_KEYS.refreshToken,
    );
    expect(refreshToken).toBeTruthy();

    const userData = await page.evaluate(
      (key) => localStorage.getItem(key),
      STORAGE_KEYS.userData,
    );
    expect(userData).toBeTruthy();
    const parsed = JSON.parse(userData!);
    expect(parsed.email).toBe(TEST_USER.email);
  });

  test("invalid email shows error", async ({ page }) => {
    await page.locator('input[id="email"]').fill("nonexistent@test.com");
    await page.locator('input[id="password"]').fill("wrongpassword");
    await page.locator('button[type="submit"]').click();

    // Should show error message
    const errorDiv = page.locator('[data-testid="form-error"]');
    await expect(errorDiv).toBeVisible({ timeout: 10_000 });
  });

  test("invalid password shows error", async ({ page }) => {
    await page.locator('input[id="email"]').fill(TEST_USER.email);
    await page.locator('input[id="password"]').fill("wrongpassword");
    await page.locator('button[type="submit"]').click();

    // Should show error message
    const errorDiv = page.locator('[data-testid="form-error"]');
    await expect(errorDiv).toBeVisible({ timeout: 10_000 });
  });

  test("login page has link to register page", async ({ page }) => {
    // Use the link in the main content, not the nav
    const registerLink = page.locator('#main-content a[href="/auth/register"], main a[href="/auth/register"], form ~ * a[href="/auth/register"]').first();
    await expect(registerLink).toBeVisible();

    await registerLink.click();
    await page.waitForURL(/\/auth\/register/);
  });
});

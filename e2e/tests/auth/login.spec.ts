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

  test("a login keeps the access token readable and the refresh token in an httpOnly cookie", async ({ page }) => {
    await page.locator('input[id="email"]').fill(TEST_USER.email);
    await page.locator('input[id="password"]').fill(TEST_USER.password);
    const answered = page.waitForResponse(
      (r) => new URL(r.url()).pathname === "/api/v1/auth/login" && r.request().method() === "POST",
    );
    await page.locator('button[type="submit"]').click();

    // The login's answer carries the access token and never the refresh token, which
    // travels in the cookie only (review INT-06: the body still repeated it)
    const login = await answered;
    expect(login.status()).toBe(200);
    const body = (await login.json()) as Record<string, unknown>;
    expect(body.access_token).toBeTruthy();
    expect(body).not.toHaveProperty("refresh_token");

    await page.waitForURL("/", { timeout: 15_000 });

    // The 15-minute access token and the user are in localStorage (the sockets need it)
    const stored = await page.evaluate((keys) => ({
      token: localStorage.getItem(keys.token),
      legacyRefresh: localStorage.getItem(keys.legacyRefreshToken),
      user: localStorage.getItem(keys.userData),
    }), STORAGE_KEYS);
    expect(stored.token).toBeTruthy();
    expect(stored.token).not.toBe("undefined");
    expect(JSON.parse(stored.user!).email).toBe(TEST_USER.email);

    // ...the 7-day refresh token is not, under any key (SEC F13)...
    expect(stored.legacyRefresh).toBeNull();
    const values = await page.evaluate(() => Object.keys(localStorage).map((k) => localStorage.getItem(k) ?? ""));
    const refreshCookie = (await page.context().cookies()).find((c) => c.name === "majlisna-refresh-token");
    expect(refreshCookie, "the server sets the refresh token as a cookie").toBeTruthy();
    expect(values).not.toContain(refreshCookie!.value);

    // ...it is an httpOnly cookie, scoped to the auth endpoints, that no script can read
    expect(refreshCookie!.httpOnly).toBe(true);
    expect(refreshCookie!.path).toBe("/api/v1/auth");
    expect(await page.evaluate(() => document.cookie)).not.toContain("majlisna-refresh-token");
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

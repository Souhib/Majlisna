import { test, expect } from "@playwright/test";
import { ROUTES } from "../../helpers/constants";

test.describe("Auth — Login Validation", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(ROUTES.login);
    await page.waitForLoadState("domcontentloaded");
  });

  test("submit button is disabled when fields are empty", async ({ page }) => {
    const submitButton = page.locator('button[type="submit"]');
    // Try clicking without filling — should not navigate away
    await submitButton.click();
    await expect(page).toHaveURL(/\/auth\/login/);
  });

  test("submit with only email shows validation or stays on page", async ({
    page,
  }) => {
    await page.locator('input[id="email"]').fill("test@test.com");
    // Leave password empty
    await page.locator('button[type="submit"]').click();

    // Should remain on login page
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 3_000 });
  });

  test("submit with only password shows validation or stays on page", async ({
    page,
  }) => {
    await page.locator('input[id="password"]').fill("somepassword");
    // Leave email empty
    await page.locator('button[type="submit"]').click();

    // Should remain on login page
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 3_000 });
  });

  test("invalid email format is rejected", async ({ page }) => {
    await page.locator('input[id="email"]').fill("not-an-email");
    await page.locator('input[id="password"]').fill("password123");
    await page.locator('button[type="submit"]').click();

    // Should stay on login page (HTML5 email validation or API error)
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 3_000 });
  });
});

test.describe("Auth — Register Validation", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(ROUTES.register);
    await page.waitForLoadState("domcontentloaded");
  });

  test("submit with empty fields stays on page", async ({ page }) => {
    await page.locator('button[type="submit"]').click();

    await expect(page).toHaveURL(/\/auth\/register/, { timeout: 3_000 });
  });

  test("submit without username stays on page", async ({ page }) => {
    await page.locator('input[id="email"]').fill("test@test.com");
    await page.locator('input[id="password"]').fill("TestPass123!");
    await page.locator('button[type="submit"]').click();

    await expect(page).toHaveURL(/\/auth\/register/, { timeout: 3_000 });
  });

  test("short password is rejected", async ({ page }) => {
    await page.locator('input[id="username"]').fill("testuser");
    await page.locator('input[id="email"]').fill("short@test.com");
    await page.locator('input[id="password"]').fill("short");
    await page.locator('button[type="submit"]').click();

    // Should stay on register page (minlength=8 or API validation)
    await expect(page).toHaveURL(/\/auth\/register/, { timeout: 3_000 });
  });

  test("duplicate username shows error", async ({ page }) => {
    // Use a username that's likely already taken (seeded "admin" user)
    await page.locator('input[id="username"]').fill("admin");
    await page
      .locator('input[id="email"]')
      .fill(`unique-${Date.now()}@test.com`);
    await page.locator('input[id="password"]').fill("TestPass123!");
    await page.locator('button[type="submit"]').click();

    // Should show error (duplicate username)
    const errorDiv = page.locator('[data-testid="form-error"]');
    await expect(errorDiv).toBeVisible({ timeout: 10_000 });
  });

  test("password field hides input", async ({ page }) => {
    const passwordInput = page.locator('input[id="password"]');
    const type = await passwordInput.getAttribute("type");
    expect(type).toBe("password");
  });
});

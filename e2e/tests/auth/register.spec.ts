import { test, expect } from "@playwright/test";
import { TEST_USER, ROUTES } from "../../helpers/constants";

test.describe("Auth — Register", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(ROUTES.register);
    await page.waitForLoadState("domcontentloaded");
  });

  test("successful registration", async ({ page }) => {
    const uniqueEmail = `e2e-register-${Date.now()}@test.com`;
    const uniqueUsername = `e2e_reg_${Date.now()}`;

    await page.locator('input[id="username"]').fill(uniqueUsername);
    await page.locator('input[id="email"]').fill(uniqueEmail);
    await page.locator('input[id="password"]').fill("TestPass123!");
    await page.locator('button[type="submit"]').click();

    // Registration should succeed — either redirect to home or login
    await expect(page).not.toHaveURL(/\/auth\/register/, {
      timeout: 15_000,
    });
  });

  test("duplicate email shows error", async ({ page }) => {
    await page.locator('input[id="username"]').fill("duplicate_user");
    await page.locator('input[id="email"]').fill(TEST_USER.email);
    await page.locator('input[id="password"]').fill("TestPass123!");
    await page.locator('button[type="submit"]').click();

    // Should show error (duplicate email)
    const errorDiv = page.locator('[data-testid="form-error"]');
    await expect(errorDiv).toBeVisible({ timeout: 10_000 });
  });

  test("register page has link to login page", async ({ page }) => {
    // Use the link in the main content, not the nav
    const loginLink = page.locator('#main-content a[href="/auth/login"], main a[href="/auth/login"], form ~ * a[href="/auth/login"]').first();
    await expect(loginLink).toBeVisible();

    await loginLink.click();
    await page.waitForURL(/\/auth\/login/);
  });

  test("password field has minimum length validation", async ({ page }) => {
    // HTML5 minlength=8 is set on the password field
    const passwordInput = page.locator('input[id="password"]');
    const minLength = await passwordInput.getAttribute("minLength");
    expect(minLength).toBe("8");
  });
});

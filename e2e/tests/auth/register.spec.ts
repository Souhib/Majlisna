import { test, expect } from "@playwright/test";
import { randomUUID } from "crypto";
import { TEST_USER, ROUTES } from "../../helpers/constants";
import { apiLogin, apiRegister, expectApiError, rawPost } from "../../helpers/api-client";

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

  test("a password too long for the hash is refused in its own words", async ({ page }) => {
    // 40 Arabic letters: 40 characters, 80 bytes of UTF-8. bcrypt takes 72 bytes, and the
    // server counted characters: it passed registration, then answered a 500 (SEC F10)
    const id = randomUUID().slice(0, 8);
    const registered = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v1/auth/register");
    await page.locator('input[id="username"]').fill(`e2e-long-${id}`);
    await page.locator('input[id="email"]').fill(`e2e-long-${id}@test.com`);
    await page.locator('input[id="password"]').fill("ب".repeat(40));
    await page.locator('button[type="submit"]').click();

    expect((await registered).status()).toBe(400);
    await expect(page.getByTestId("form-error")).toHaveText("This password is too long. Choose a shorter one.", { timeout: 10_000 });
    await expect(page).toHaveURL(/\/auth\/register/);
  });

  test("one account per mailbox, whatever the case: registered in capitals, signed in in lower case", async ({ page }) => {
    // Prepare — an address registered with capitals (SEC F14: "Ali@Example.com" and
    // "ali@example.com" used to be two accounts)
    const id = randomUUID().slice(0, 8);
    const mixed = `E2E-Case-${id}@Test.com`;
    await apiRegister(`e2e-case-${id}`, mixed, "TestPass123!");

    // The same mailbox in another case is refused, by name
    await expectApiError(
      await rawPost("/api/v1/auth/register", { username: `e2e-case2-${id}`, email_address: mixed.toLowerCase(), password: "TestPass123!" }),
      409,
      "errors.api.userAlreadyExists",
    );
    expect((await apiLogin(mixed.toUpperCase(), "TestPass123!")).user.username).toBe(`e2e-case-${id}`);

    // Act — the login page, in lower case
    await page.goto(ROUTES.login);
    await page.locator('input[id="email"]').fill(mixed.toLowerCase());
    await page.locator('input[id="password"]').fill("TestPass123!");
    await page.locator('button[type="submit"]').click();

    // Assert — signed in, as that one account
    await page.waitForURL("/", { timeout: 15_000 });
    await expect(page.getByTestId("user-menu-trigger")).toBeVisible({ timeout: 15_000 });
  });
});

import { test, expect } from "@playwright/test";
import { randomBytes } from "crypto";
import { FIRST_VISIT_STORAGE } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import { apiLogin, expectApiError, rawGetMe, rawPost } from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";
import { dbPasswordResetTokens, dbPlantPasswordResetToken } from "../../helpers/db";

/**
 * "Forgot password?" then the reset link: the request is answered the same whether or
 * not the address has an account, the link's token is stored only as a digest, the
 * reset page takes the token out of the address bar at once (SEC F06), the new password
 * works, the old one does not, every session the account had is signed out (SEC F01),
 * and the link works once.
 *
 * The E2E stack sends no mail, and the database holds only the token's sha256 digest,
 * so the spec stands in for the mailbox: it gives the row the page just made the digest
 * of a token it knows (`dbPlantPasswordResetToken`) and opens the link with that token.
 */
test.describe("Forgot password, then reset", () => {
  test("ask for a link, choose a new password through it, and log in with it", async ({ browser }) => {
    // Prepare — a fresh account, also signed in elsewhere
    const [account] = await generateTestAccounts(1);
    const elsewhere = await apiLogin(account.email, account.password);
    const userId = elsewhere.user.id;
    const context = await browser.newContext({ storageState: FIRST_VISIT_STORAGE });
    const page = await context.newPage();

    // Act — from the login page: "Forgot password?", the address, "Send the link"
    await page.goto(ROUTES.login);
    await page.getByRole("link", { name: "Forgot password?" }).click();
    await expect(page).toHaveURL(/\/auth\/forgot-password$/);
    await page.locator('input[id="email"]').fill(account.email);
    const asked = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v1/auth/forgot-password");
    await page.getByRole("button", { name: "Send the link" }).click();

    // Assert — the page says a link is on its way; the server issued one token, stored as a digest
    expect((await asked).status()).toBe(200);
    await expect(page.getByText("If an account exists with that email, a reset link is on its way.")).toBeVisible();
    const issued = dbPasswordResetTokens(userId);
    expect(issued).toHaveLength(1);
    expect(issued[0].used).toBe(false);
    expect(issued[0].token).toMatch(/^[0-9a-f]{64}$/);

    // An address with no account gets the very same answer (nothing to probe)
    const unknown = await rawPost("/api/v1/auth/forgot-password", { email: `nobody-${userId}@test.com` });
    expect(unknown.status).toBe(200);

    // The mail's link (see the note above)
    const token = randomBytes(24).toString("base64url");
    dbPlantPasswordResetToken(userId, token);

    // Act — open the link, choose a new password, type it twice
    const newPassword = "Reset-Pass-2026!";
    await page.goto(`/auth/reset-password?token=${token}`);
    await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
    await expect(page).toHaveURL(/\/auth\/reset-password$/); // the token left the address bar
    await page.locator("#password").fill(newPassword);
    await page.locator("#confirmPassword").fill(newPassword);
    const reset = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v1/auth/reset-password");
    await page.getByRole("button", { name: "Save the new password" }).click();

    // Assert — changed; the token is spent; the old password and the old sessions are done
    expect((await reset).status()).toBe(200);
    await expect(page.getByText("Your password has been changed. You can now log in with it.")).toBeVisible();
    expect(dbPasswordResetTokens(userId)).toEqual([]); // consumed: the user's reset tokens are dropped
    await expectApiError(
      await rawPost("/api/v1/auth/login", { email: account.email, password: account.password }),
      401,
      "errors.api.invalidCredentials",
    );
    await expectApiError(await rawGetMe(elsewhere.access_token), 401, "errors.api.sessionRevoked");

    // The link works once
    await expectApiError(
      await rawPost("/api/v1/auth/reset-password", { token, new_password: "Another-Pass-1" }),
      400,
      "errors.api.invalidOrExpiredToken",
    );

    // ...and the login page takes the new password
    await page.getByRole("main").getByRole("link", { name: "Log in", exact: true }).click();
    await expect(page).toHaveURL(/\/auth\/login/);
    await page.locator('input[id="email"]').fill(account.email);
    await page.locator('input[id="password"]').fill(newPassword);
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(new URL("/", page.url()).href, { timeout: 15_000 });
    await expect(page.getByTestId("user-menu-trigger")).toBeVisible({ timeout: 15_000 });

    await context.close();
  });

  test("a link that is not one says so and offers a new one", async ({ page }) => {
    await page.goto("/auth/reset-password?token=not-a-real-token-at-all");
    await page.locator("#password").fill("Some-Pass-2026");
    await page.locator("#confirmPassword").fill("Some-Pass-2026");
    await page.getByRole("button", { name: "Save the new password" }).click();

    const error = page.getByTestId("form-error");
    await expect(error).toContainText("This link is invalid or has expired.");
    await expect(error.getByRole("link")).toHaveAttribute("href", "/auth/forgot-password");
  });
});

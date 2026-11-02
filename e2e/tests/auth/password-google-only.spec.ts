import { test, expect, type Page } from "@playwright/test";
import { randomBytes, randomInt } from "crypto";
import { createPlayerPage, FIRST_VISIT_STORAGE } from "../../fixtures/auth.fixture";
import { generateTestAccounts, type TestAccount } from "../../helpers/test-setup";
import { apiLogin, expectApiError, rawPatch, rawPost, type LoginResponse } from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";
import { dbMakeGoogleOnly, dbPlantPasswordResetToken, dbUserSignIn } from "../../helpers/db";

/**
 * "Change password" is offered to every account, a Google-only one included: its stored
 * password is a sentinel its owner never saw, so it chooses one and confirms with Google
 * instead of typing a current password. "Forgot password?" now gives such an account a
 * password that opens it at login (it used to be stored and then refused, 401).
 *
 * The stack's Google client id is a placeholder, so no Google sign-in or popup can complete
 * here: the account is made Google-only in the database (`dbMakeGoogleOnly`, the state
 * "Continue with Google" creates), Google's script is answered locally, and the Google
 * confirmation itself is covered by the backend's tests. The 429 after five changes a
 * minute is too: the stack runs with RATE_LIMIT_ENABLED=false.
 */

const GSI = /accounts\.google\.com\/gsi\/client/;
const GSI_SCRIPT = 'script[src*="accounts.google.com/gsi/client"]';
const GOOGLE_INTRO = "Your account signs in with Google and has no password yet.";

/** A fresh account, signed in (on this page and through the API), then made Google-only. */
async function googleOnlyPlayer(page: Page | null, account: TestAccount): Promise<{ login: LoginResponse; googleSub: string }> {
  const login = await apiLogin(account.email, account.password);
  const googleSub = `${Date.now()}${randomInt(1_000_000)}`;
  dbMakeGoogleOnly(login.user.id, googleSub);
  // Google-only: the registration password no longer opens it, as a sentinel would not
  await expectApiError(
    await rawPost("/api/v1/auth/login", { email: account.email, password: account.password }),
    401,
    "errors.api.invalidCredentials",
  );
  if (page) await page.goto(ROUTES.profile);
  return { login, googleSub };
}

test.describe("Profile — Change password for a Google-only account", () => {
  test("asks for a new password and Google's confirmation, never a current password", async ({ browser }) => {
    // Prepare — signed in on this browser before the account turns Google-only (no password
    // login works afterwards); Google's script answered locally
    const [account] = await generateTestAccounts(1);
    const page = await createPlayerPage(browser, account.email, account.password);
    const gsiRequests: string[] = [];
    await page.route(GSI, (route) => route.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
    page.on("request", (r) => {
      if (GSI.test(r.url())) gsiRequests.push(r.url());
    });
    await googleOnlyPlayer(page, account);
    const open = page.getByRole("button", { name: "Change password" });
    await expect(open).toBeVisible({ timeout: 15_000 });
    // ...and Google's script is not on the profile until the form opens
    await expect(page.locator(GSI_SCRIPT)).toHaveCount(0);
    expect(gsiRequests).toEqual([]);

    // Act — open the form
    await open.click();

    // Assert — the Google form: the explanation, a new password, "Confirm with Google"
    await expect(page.getByText(GOOGLE_INTRO)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByPlaceholder("New password", { exact: true })).toBeVisible();
    await expect(page.getByPlaceholder("Current password", { exact: true })).toHaveCount(0);
    const confirm = page.getByRole("button", { name: "Confirm with Google" });
    await expect(confirm).toBeEnabled({ timeout: 15_000 }); // once Google's script has loaded
    await expect(page.locator(GSI_SCRIPT)).toHaveCount(1);
    await expect.poll(() => gsiRequests.length).toBe(1);

    // A password under 8 characters is refused before Google is asked
    await page.getByPlaceholder("New password", { exact: true }).fill("short");
    await confirm.click();
    await expect(page.getByText("Use at least 8 characters.")).toBeVisible();

    // Cancel closes the form, and Google's script goes with it
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(open).toBeVisible();
    await expect(page.getByText(GOOGLE_INTRO)).toHaveCount(0);
    await expect(page.locator(GSI_SCRIPT)).toHaveCount(0);

    await page.context().close();
  });

  test("the API takes only Google's confirmation for such an account", async () => {
    // Prepare
    const [account] = await generateTestAccounts(1);
    const { login } = await googleOnlyPlayer(null, account);
    const path = `/api/v1/users/${login.user.id}/password`;
    const newPassword = "Chosen-Pass-2026!";

    // Act + Assert — a typed "current password" is not a confirmation: Google is
    await expectApiError(
      await rawPatch(path, { current_password: account.password, new_password: newPassword }, login.access_token),
      403,
      "errors.api.googleConfirmationRequired",
    );
    // ...and the change needs exactly one confirmation: neither, or both, is malformed
    await expectApiError(await rawPatch(path, { new_password: newPassword }, login.access_token), 422, "errors.api.validation");
    await expectApiError(
      await rawPatch(
        path,
        { current_password: account.password, google_access_token: "not-a-google-token", new_password: newPassword },
        login.access_token,
      ),
      422,
      "errors.api.validation",
    );

    // Nothing changed: still Google-only, and no password opens it
    expect(dbUserSignIn(login.user.id)?.auth_provider).toBe("google");
    await expectApiError(
      await rawPost("/api/v1/auth/login", { email: account.email, password: newPassword }),
      401,
      "errors.api.invalidCredentials",
    );
  });

  test("a reset link gives it a password that opens it at login, and Google still does", async ({ browser }) => {
    // Prepare — a Google-only account that asks for a reset link
    const [account] = await generateTestAccounts(1);
    const { login, googleSub } = await googleOnlyPlayer(null, account);
    const userId = login.user.id;
    expect((await rawPost("/api/v1/auth/forgot-password", { email: account.email })).status).toBe(200);
    // The mail's link (the stack sends none: see forgot-reset.spec.ts)
    const token = randomBytes(24).toString("base64url");
    dbPlantPasswordResetToken(userId, token);
    const context = await browser.newContext({ storageState: FIRST_VISIT_STORAGE });
    const page = await context.newPage();

    // Act — choose a password through the link
    const newPassword = "Reset-Google-2026!";
    await page.goto(`/auth/reset-password?token=${token}`);
    await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
    await page.locator("#password").fill(newPassword);
    await page.locator("#confirmPassword").fill(newPassword);
    const reset = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v1/auth/reset-password");
    await page.getByRole("button", { name: "Save the new password" }).click();
    expect((await reset).status()).toBe(200);
    await expect(page.getByText("Your password has been changed. You can now log in with it.")).toBeVisible();

    // Assert — the account has a password of its own now, and keeps its Google sign-in
    expect(dbUserSignIn(userId)).toEqual({ auth_provider: "email", google_sub: googleSub });

    // ...which the login page takes (it answered 401 before)
    await page.getByRole("main").getByRole("link", { name: "Log in", exact: true }).click();
    await expect(page).toHaveURL(/\/auth\/login/);
    await page.locator('input[id="email"]').fill(account.email);
    await page.locator('input[id="password"]').fill(newPassword);
    const signedIn = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v1/auth/login");
    await page.locator('button[type="submit"]').click();
    expect((await signedIn).status()).toBe(200);
    await expect(page).toHaveURL(new URL("/", page.url()).href, { timeout: 15_000 });
    await expect(page.getByTestId("user-menu-trigger")).toBeVisible({ timeout: 15_000 });

    // ...and "Change password" now asks for that password, like any account with one
    await page.goto(ROUTES.profile);
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByPlaceholder("Current password", { exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByPlaceholder("New password", { exact: true })).toBeVisible();
    await expect(page.getByText(GOOGLE_INTRO)).toHaveCount(0);
    await expect(page.locator(GSI_SCRIPT)).toHaveCount(0);

    await context.close();
  });
});

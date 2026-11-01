import { test, expect } from "@playwright/test";
import { createPlayerPage, FIRST_VISIT_STORAGE } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import { apiLogin, expectApiError, rawGetMe, rawPost } from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";

/**
 * Changing the password from the profile: the form asks for the current one, the new
 * one works at once, the old one stops working, and every OTHER signed-in device is
 * signed out (SEC F01) while the one that changed it stays signed in.
 */
test.describe("Profile — Change password", () => {
  test("change the password, then log in with the new one only", async ({ browser }) => {
    // Prepare — a fresh player signed in on two devices: this browser, and another one
    const [account] = await generateTestAccounts(1);
    const otherDevice = await apiLogin(account.email, account.password);
    expect((await rawGetMe(otherDevice.access_token)).status).toBe(200);
    const page = await createPlayerPage(browser, account.email, account.password);
    await page.goto(ROUTES.profile);
    await page.getByRole("button", { name: "Change password" }).click();
    const newPassword = "NewPass-2026!";

    // A wrong current password is refused in the form, and nothing changes
    await page.getByPlaceholder("Current password", { exact: true }).fill("not-my-password");
    await page.getByPlaceholder("New password", { exact: true }).fill(newPassword);
    await page.getByRole("button", { name: "Save" }).click();
    // ...in the words of a form that has no email field: the login's "Please check your
    // email and password." pointed at a field this form does not have (review F6)
    await expect(page.getByRole("alert").filter({ hasText: "That password is not right." })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Please check your email and password.")).toHaveCount(0);
    // ...said in the form: a wrong password is not a lost session, the player stays here
    await expect(page).toHaveURL(new RegExp(`${ROUTES.profile}$`));
    expect((await apiLogin(account.email, account.password)).user.email).toBe(account.email);

    // Act — the right current password, and a new one
    await page.getByPlaceholder("Current password", { exact: true }).fill(account.password);
    await page.getByPlaceholder("New password", { exact: true }).fill(newPassword);
    const changed = page.waitForResponse((r) => r.url().endsWith("/password") && r.request().method() === "PATCH");
    await page.getByRole("button", { name: "Save" }).click();

    // Assert — the server took it, and the page says so
    expect((await changed).status()).toBe(200);
    await expect(page.getByText("Password changed!")).toBeVisible({ timeout: 10_000 });

    // The old password no longer opens the account; the new one does
    await expectApiError(
      await rawPost("/api/v1/auth/login", { email: account.email, password: account.password }),
      401,
      "errors.api.invalidCredentials",
    );
    expect((await apiLogin(account.email, newPassword)).user.email).toBe(account.email);

    // The other device is signed out; this one is not
    await expectApiError(await rawGetMe(otherDevice.access_token), 401, "errors.api.sessionRevoked");
    await page.reload();
    await expect(page.getByTestId("user-menu-trigger")).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveURL(new RegExp(`${ROUTES.profile}$`));

    // ...and the login page takes the new password
    const context = await browser.newContext({ storageState: FIRST_VISIT_STORAGE });
    const fresh = await context.newPage();
    await fresh.goto(ROUTES.login);
    await fresh.locator('input[id="email"]').fill(account.email);
    await fresh.locator('input[id="password"]').fill(newPassword);
    await fresh.locator('button[type="submit"]').click();
    await expect(fresh).toHaveURL(new URL("/", fresh.url()).href, { timeout: 15_000 });
    await expect(fresh.getByTestId("user-menu-trigger")).toBeVisible({ timeout: 15_000 });

    await context.close();
    await page.context().close();
  });
});

import { test, expect, type Page, type Response } from "@playwright/test";
import { test as authTest, createPlayerPage } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import { expectApiError, NO_SOCKET_REUSE, rawGetMe } from "../../helpers/api-client";
import { API_URL, STORAGE_KEYS, ROUTES } from "../../helpers/constants";

/**
 * The session as the browser holds it: the access token in localStorage (the sockets
 * read it), the refresh token in an httpOnly cookie only (SEC F13), refreshed once per
 * browser even with several tabs open, and ended on the server by a logout (SEC F01).
 */

const isRefresh = (response: Response) =>
  new URL(response.url()).pathname === "/api/v1/auth/refresh" && response.request().method() === "POST";

/** Make the stored access token stale: the next page load refreshes before anything else. */
async function staleAccessToken(page: Page): Promise<void> {
  await page.evaluate((keys) => localStorage.setItem(keys.tokenExpiry, String(Date.now() - 60_000)), STORAGE_KEYS);
}

authTest.describe("Auth — Token Management", () => {
  authTest("tokens persist across page reload", async ({ authenticatedPage }) => {
    const tokenBefore = await authenticatedPage.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.token);
    expect(tokenBefore).toBeTruthy();

    await authenticatedPage.reload();
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const tokenAfter = await authenticatedPage.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.token);
    expect(tokenAfter).toBe(tokenBefore);
  });

  authTest("user data persists across page reload", async ({ authenticatedPage }) => {
    const userDataBefore = await authenticatedPage.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.userData);
    expect(userDataBefore).toBeTruthy();

    await authenticatedPage.reload();
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const userDataAfter = await authenticatedPage.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.userData);
    expect(userDataAfter).toBe(userDataBefore);
  });

  // A returning visitor after an hour away: the access token has expired, the refresh
  // token has not. AuthProvider used to ask /auth/me first with the stale token; the 401
  // sent the visitor to the login page from any page, public ones included.
  for (const path of [ROUTES.home, "/today"]) {
    authTest(
      `an expired access token with a valid refresh token stays signed in on ${path}`,
      async ({ authenticatedPage: page }) => {
        // Prepare: a stored access token the server refuses, past its stored expiry
        await page.evaluate((keys) => {
          localStorage.setItem(keys.token, "expired-access-token");
          localStorage.setItem(keys.tokenExpiry, String(Date.now() - 60_000));
        }, STORAGE_KEYS);
        const refreshed = page.waitForResponse(isRefresh, { timeout: 15_000 });

        // Act
        await page.goto(path);

        // Assert: refreshed first (from the cookie: no refresh token is stored anywhere a
        // script reads), then still on the page, with a fresh token
        const refresh = await refreshed;
        expect(refresh.status()).toBe(200);
        expect(refresh.request().postData() ?? "").not.toContain("refresh_token");
        // ...and answered with an access token only: the rotated refresh token is set as
        // the cookie, never written into the body (review INT-06)
        const answer = (await refresh.json()) as Record<string, unknown>;
        expect(answer.access_token).toBeTruthy();
        expect(answer).not.toHaveProperty("refresh_token");
        await expect
          .poll(() => page.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.token))
          .not.toBe("expired-access-token");
        expect(await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.token)).toBeTruthy();
        expect(await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.legacyRefreshToken)).toBeNull();
        await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
        await expect(page.getByRole("link", { name: "Log in", exact: true })).toHaveCount(0);
        expect(new URL(page.url()).pathname).toBe(path);
      },
    );
  }

  authTest("clearing tokens redirects to login on protected route", async ({ authenticatedPage }) => {
    // Clear every session key the page keeps
    await authenticatedPage.evaluate((keys) => {
      for (const key of Object.values(keys)) localStorage.removeItem(key);
    }, STORAGE_KEYS);

    await authenticatedPage.goto(ROUTES.rooms);

    await expect(authenticatedPage).toHaveURL(/\/auth\/login/, { timeout: 15_000 });
  });
});

test.describe("Auth — Logout and several tabs", () => {
  test("logging out ends the session on the server, not only in the page", async ({ browser }) => {
    // Prepare — a fresh player, signed in on their profile
    const [account] = await generateTestAccounts(1);
    const page = await createPlayerPage(browser, account.email, account.password);
    await page.goto(ROUTES.profile);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
    const accessToken = await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.token);
    expect(accessToken).toBeTruthy();
    expect((await rawGetMe(accessToken!)).status).toBe(200);

    // Act — Log out, from the account menu
    const loggedOut = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v1/auth/logout");
    await page.getByTestId("user-menu-trigger").click();
    await page.getByRole("menuitem", { name: "Log out" }).click();

    // Assert — the server ended the session...
    expect((await loggedOut).status()).toBe(200);
    // ...so the access token the page held is refused, by name (it used to stay valid
    // for its whole 15 minutes: a logout only cleared cookies)
    await expectApiError(await rawGetMe(accessToken!), 401, "errors.api.sessionRevoked");
    // ...and the refresh cookie is gone, so nothing can renew the session
    expect((await page.context().cookies()).find((c) => c.name === "majlisna-refresh-token")).toBeUndefined();
    const refresh = await page.context().request.post(`${API_URL}/api/v1/auth/refresh`, { data: {}, headers: NO_SOCKET_REUSE });
    expect(refresh.status()).toBe(401);

    // ...the page forgot it and sends the player to the login page from a protected one
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 15_000 });
    const stored = await page.evaluate((keys) => Object.values(keys).map((k) => localStorage.getItem(k)), STORAGE_KEYS);
    expect(stored.every((v) => v === null)).toBe(true);
    await page.goto(ROUTES.profile);
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 15_000 });

    await page.context().close();
  });

  test("two tabs that refresh at once both stay signed in", async ({ browser }) => {
    // Prepare — one browser, two tabs on the profile, the shared access token stale
    const [account] = await generateTestAccounts(1);
    const first = await createPlayerPage(browser, account.email, account.password);
    const second = await first.context().newPage();
    for (const tab of [first, second]) {
      await tab.goto(ROUTES.profile);
      await expect(tab.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
    }
    await staleAccessToken(first);
    const refreshes: Response[] = [];
    for (const tab of [first, second]) tab.on("response", (r) => isRefresh(r) && refreshes.push(r));

    // Act — both tabs load at the same moment, both with a stale token
    await Promise.all([first.reload(), second.reload()]);

    // Assert — every refresh that went out was answered, and both tabs are signed in.
    // Each refresh rotates the single-use refresh token: two tabs spending the same one
    // used to read as a stolen token and sign the session out (SEC F01, the reuse grace
    // and the Web Lock are what keep them apart).
    await expect.poll(() => refreshes.length, { timeout: 15_000 }).toBeGreaterThanOrEqual(1);
    for (const tab of [first, second]) {
      await expect(tab.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });
      await expect(tab).toHaveURL(new RegExp(`${ROUTES.profile}$`));
      await expect(tab.getByTestId("user-menu-trigger")).toBeVisible();
    }
    expect(refreshes.map((r) => r.status())).toEqual(refreshes.map(() => 200));

    // ...and the session survived the race: the token both tabs now hold works, and the
    // next refresh (one more stale load) is answered too
    const token = await first.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.token);
    expect((await rawGetMe(token!)).status).toBe(200);
    await staleAccessToken(first);
    const again = first.waitForResponse(isRefresh, { timeout: 15_000 });
    await first.reload();
    expect((await again).status()).toBe(200);
    await expect(first.getByTestId("user-menu-trigger")).toBeVisible({ timeout: 15_000 });

    await first.context().close();
  });
});

test.describe("Auth — Token Management (Unauthenticated)", () => {
  test("accessing protected route without token redirects to login", async ({ page }) => {
    await page.goto(ROUTES.rooms);
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 15_000 });
  });
});

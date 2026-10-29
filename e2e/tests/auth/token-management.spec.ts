import { test, expect } from "@playwright/test";
import { test as authTest } from "../../fixtures/auth.fixture";
import { STORAGE_KEYS, ROUTES } from "../../helpers/constants";

authTest.describe("Auth — Token Management", () => {
  authTest(
    "tokens persist across page reload",
    async ({ authenticatedPage }) => {
      // Get token before reload
      const tokenBefore = await authenticatedPage.evaluate(
        (key) => localStorage.getItem(key),
        STORAGE_KEYS.token,
      );
      expect(tokenBefore).toBeTruthy();

      // Reload the page
      await authenticatedPage.reload();
      await authenticatedPage.waitForLoadState("domcontentloaded");

      // Token should still be present
      const tokenAfter = await authenticatedPage.evaluate(
        (key) => localStorage.getItem(key),
        STORAGE_KEYS.token,
      );
      expect(tokenAfter).toBe(tokenBefore);
    },
  );

  authTest(
    "user data persists across page reload",
    async ({ authenticatedPage }) => {
      const userDataBefore = await authenticatedPage.evaluate(
        (key) => localStorage.getItem(key),
        STORAGE_KEYS.userData,
      );
      expect(userDataBefore).toBeTruthy();

      await authenticatedPage.reload();
      await authenticatedPage.waitForLoadState("domcontentloaded");

      const userDataAfter = await authenticatedPage.evaluate(
        (key) => localStorage.getItem(key),
        STORAGE_KEYS.userData,
      );
      expect(userDataAfter).toBe(userDataBefore);
    },
  );

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
        const refreshed = page.waitForResponse(
          (response) =>
            response.url().includes("/api/v1/auth/refresh") &&
            response.request().method() === "POST",
          { timeout: 15_000 },
        );

        // Act
        await page.goto(path);

        // Assert: refreshed first, then still on the page, with a fresh token
        expect((await refreshed).status()).toBe(200);
        await expect
          .poll(() => page.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.token))
          .not.toBe("expired-access-token");
        expect(
          await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.token),
        ).toBeTruthy();
        await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
        await expect(page.getByRole("link", { name: "Log in", exact: true })).toHaveCount(0);
        expect(new URL(page.url()).pathname).toBe(path);
      },
    );
  }

  authTest(
    "clearing tokens redirects to login on protected route",
    async ({ authenticatedPage }) => {
      // Clear all auth data
      await authenticatedPage.evaluate((keys) => {
        localStorage.removeItem(keys.token);
        localStorage.removeItem(keys.refreshToken);
        localStorage.removeItem(keys.tokenExpiry);
        localStorage.removeItem(keys.userData);
      }, STORAGE_KEYS);

      // Navigate to protected route
      await authenticatedPage.goto(ROUTES.rooms);

      // Should redirect to login
      await expect(authenticatedPage).toHaveURL(/\/auth\/login/, {
        timeout: 15_000,
      });
    },
  );
});

test.describe("Auth — Token Management (Unauthenticated)", () => {
  test("accessing protected route without token redirects to login", async ({
    page,
  }) => {
    await page.goto(ROUTES.rooms);

    // Should redirect to login
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 15_000 });
  });
});

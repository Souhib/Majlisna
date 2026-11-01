import { test as base, expect, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { type LoginResponse } from "../helpers/api-client";
import { API_URL, TEST_ADMIN, TEST_USER, STORAGE_KEYS, FRONTEND_URL } from "../helpers/constants";

/** The first-visit language picker, dismissed for every context. */
export const FIRST_VISIT_STORAGE = {
  cookies: [],
  origins: [{ origin: FRONTEND_URL, localStorage: [{ name: "majlisna-first-visit-complete", value: "true" }] }],
};

/**
 * Sign a browser context in the way the login page does it.
 *
 * The login goes through the context's own request client, so the server's answer sets
 * its httpOnly refresh (and access) cookies in the context's cookie jar, exactly as a
 * browser login would; the page then keeps only what the app keeps in localStorage: the
 * 15-minute access token, its expiry, the session marker and the user. No refresh token
 * is ever written where a script can read it (SEC F13). The old fixture wrote one into
 * the legacy `majlisna-refresh-token` key, which the client only reads to migrate an old
 * session.
 */
export async function signInContext(context: BrowserContext, email: string, password: string): Promise<LoginResponse> {
  const response = await context.request.post(`${API_URL}/api/v1/auth/login`, { data: { email, password } });
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()) as LoginResponse;
}

/** Put the app's own session keys into the page's localStorage (the page must be on the app's origin). */
async function storeSession(page: Page, login: LoginResponse): Promise<void> {
  await page.goto(FRONTEND_URL, { waitUntil: "commit" });
  await page.evaluate(
    ({ tokens, keys }) => {
      localStorage.setItem("majlisna-first-visit-complete", "true");
      localStorage.setItem(keys.token, tokens.access_token);
      localStorage.setItem(keys.tokenExpiry, String(Date.now() + tokens.expires_in * 1000));
      localStorage.setItem(keys.sessionMarker, "1");
      localStorage.setItem(
        keys.userData,
        JSON.stringify({ id: tokens.user.id, username: tokens.user.username, email: tokens.user.email }),
      );
    },
    { tokens: login, keys: STORAGE_KEYS },
  );
}

/** Sign an already-open page's context in, then store the session in the page. */
export async function signInPage(page: Page, email: string, password: string): Promise<LoginResponse> {
  const login = await signInContext(page.context(), email, password);
  await storeSession(page, login);
  return login;
}

// ─── Factory: create an authenticated page in a new context ─

export async function createPlayerPage(browser: Browser, email: string, password: string): Promise<Page> {
  const context = await browser.newContext({ storageState: FIRST_VISIT_STORAGE });
  const page = await context.newPage();
  await signInPage(page, email, password);
  return page;
}

// ─── Playwright Fixtures ────────────────────────────────────

type AuthFixtures = {
  authenticatedPage: Page;
  adminPage: Page;
};

export const test = base.extend<AuthFixtures>({
  authenticatedPage: async ({ page }, use) => {
    await signInPage(page, TEST_USER.email, TEST_USER.password);
    await use(page);
  },

  adminPage: async ({ page }, use) => {
    await signInPage(page, TEST_ADMIN.email, TEST_ADMIN.password);
    await use(page);
  },
});

export { expect } from "@playwright/test";

import { test, expect, type Page } from "@playwright/test";
import { ROUTES } from "../../helpers/constants";

/**
 * The login and register forms check what they can before asking the server: each
 * field says what is missing, in place (`#<field>-error`, role=alert), and nothing is
 * sent. The old specs only checked that the URL still read /auth/login three seconds
 * later — which held for a build with no validation at all whenever the server took
 * longer than that to log the player in (TQ-08). Now each asserts the field's own error
 * AND that no request left.
 */

/** Every request to `path` the page sends from now on. */
function watchRequests(page: Page, path: string): string[] {
  const sent: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === path) sent.push(`${request.method()} ${request.url()}`);
  });
  return sent;
}

/** Nothing reached `path`: no request now, none in the second that follows. */
async function expectNoRequest(page: Page, sent: string[], path: string): Promise<void> {
  await expect(
    page.waitForRequest((request) => new URL(request.url()).pathname === path, { timeout: 1_000 }),
  ).rejects.toThrow(/Timeout/);
  expect(sent, `the form sent ${sent.join(", ")}`).toEqual([]);
}

const LOGIN_API = "/api/v1/auth/login";
const REGISTER_API = "/api/v1/auth/register";

test.describe("Auth — Login Validation", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(ROUTES.login);
    await expect(page.locator('input[id="email"]')).toBeVisible();
  });

  test("an empty form says what is missing and sends nothing", async ({ page }) => {
    const sent = watchRequests(page, LOGIN_API);

    await page.locator('button[type="submit"]').click();

    await expect(page.locator("#email-error")).toHaveText("Enter your email address.");
    await expect(page.locator("#password-error")).toHaveText("Enter your password.");
    await expect(page.locator('input[id="email"]')).toBeFocused();
    await expectNoRequest(page, sent, LOGIN_API);
    await expect(page).toHaveURL(/\/auth\/login/);
  });

  test("an email without a password asks for the password and sends nothing", async ({ page }) => {
    const sent = watchRequests(page, LOGIN_API);
    await page.locator('input[id="email"]').fill("test@test.com");

    await page.locator('button[type="submit"]').click();

    await expect(page.locator("#password-error")).toHaveText("Enter your password.");
    await expect(page.locator("#email-error")).toHaveCount(0);
    await expect(page.locator('input[id="password"]')).toBeFocused();
    await expectNoRequest(page, sent, LOGIN_API);
  });

  test("a password without an email asks for the email and sends nothing", async ({ page }) => {
    const sent = watchRequests(page, LOGIN_API);
    await page.locator('input[id="password"]').fill("somepassword");

    await page.locator('button[type="submit"]').click();

    await expect(page.locator("#email-error")).toHaveText("Enter your email address.");
    await expect(page.locator("#password-error")).toHaveCount(0);
    await expectNoRequest(page, sent, LOGIN_API);
  });

  test("an address that is not one is refused before it is sent", async ({ page }) => {
    const sent = watchRequests(page, LOGIN_API);
    await page.locator('input[id="email"]').fill("not-an-email");
    await page.locator('input[id="password"]').fill("password123");

    await page.locator('button[type="submit"]').click();

    await expect(page.locator("#email-error")).toHaveText("Enter a full email address, like name@example.com.");
    await expectNoRequest(page, sent, LOGIN_API);
  });
});

test.describe("Auth — Register Validation", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(ROUTES.register);
    await expect(page.locator('input[id="username"]')).toBeVisible();
  });

  test("an empty form says what each field needs and sends nothing", async ({ page }) => {
    const sent = watchRequests(page, REGISTER_API);

    await page.locator('button[type="submit"]').click();

    await expect(page.locator("#username-error")).toHaveText("Choose a username of 3 to 30 characters.");
    await expect(page.locator("#email-error")).toHaveText("Enter your email address.");
    await expect(page.locator("#password-error")).toHaveText("Use at least 8 characters.");
    await expectNoRequest(page, sent, REGISTER_API);
  });

  test("a missing username is asked for and nothing is sent", async ({ page }) => {
    const sent = watchRequests(page, REGISTER_API);
    await page.locator('input[id="email"]').fill("test@test.com");
    await page.locator('input[id="password"]').fill("TestPass123!");

    await page.locator('button[type="submit"]').click();

    await expect(page.locator("#username-error")).toHaveText("Choose a username of 3 to 30 characters.");
    await expect(page.locator('input[id="username"]')).toBeFocused();
    await expectNoRequest(page, sent, REGISTER_API);
  });

  test("a short password is refused before it is sent", async ({ page }) => {
    const sent = watchRequests(page, REGISTER_API);
    await page.locator('input[id="username"]').fill("testuser");
    await page.locator('input[id="email"]').fill("short@test.com");
    await page.locator('input[id="password"]').fill("short");

    await page.locator('button[type="submit"]').click();

    await expect(page.locator("#password-error")).toHaveText("Use at least 8 characters.");
    await expectNoRequest(page, sent, REGISTER_API);
  });

  test("duplicate username shows the server's refusal", async ({ page }) => {
    // The seeded "admin" account holds the name; the server answers 409 usernameAlreadyTaken
    await page.locator('input[id="username"]').fill("admin");
    await page.locator('input[id="email"]').fill(`unique-${Date.now()}@test.com`);
    await page.locator('input[id="password"]').fill("TestPass123!");
    const answered = page.waitForResponse((r) => new URL(r.url()).pathname === REGISTER_API);

    await page.locator('button[type="submit"]').click();

    expect((await answered).status()).toBe(409);
    await expect(page.getByTestId("form-error")).toContainText("The username admin is already taken");
    await expect(page).toHaveURL(/\/auth\/register/);
  });

  test("password field hides input", async ({ page }) => {
    await expect(page.locator('input[id="password"]')).toHaveAttribute("type", "password");
  });
});

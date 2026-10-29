import { test, expect } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { apiLogin, apiSeedChallenges, apiGetActiveChallenges } from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";
import en from "../../../front/src/i18n/locales/en.json";

/** What the page writes for a challenge: its code's translation, else the API's own description. */
function shownDescription(challenge: { code: string; description: string }): string {
  const items = en.challenges.items as Record<string, string>;
  return items[challenge.code] ?? challenge.description;
}

test.describe("Challenges Page", () => {
  test("challenges page loads with heading", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.challenges);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Should see the "Challenges" heading
    await expect(
      authenticatedPage.getByRole("heading", { name: "Challenges", level: 1 }),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("challenges page shows empty state when no challenges assigned", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.challenges);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // When API returns challenges, show cards; otherwise show empty state
    const challengeContent = authenticatedPage
      .getByText(/Play|Win|Daily|Weekly|No challenges/i)
      .first();
    await expect(challengeContent).toBeVisible({ timeout: 10_000 });
  });

  test("challenges are assigned via API and visible on page", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(1);
    const login = await apiLogin(accounts[0].email, accounts[0].password);

    // Seed challenges via API
    await apiSeedChallenges(login.access_token);

    // Fetch active challenges to trigger assignment
    const challenges = await apiGetActiveChallenges(login.access_token);
    expect(challenges.length).toBeGreaterThan(0);

    // Verify on UI
    const page = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await page.goto(ROUTES.challenges);
    await page.waitForLoadState("domcontentloaded");

    // Should see the challenges heading
    await expect(
      page.getByRole("heading", { name: "Challenges", level: 1 }),
    ).toBeVisible({ timeout: 10_000 });

    // The assigned challenge is on the page, worded the way the page words it: from its
    // code (challenges.items.<code>), not from the API's English description, which still
    // says "Play a Word Quiz game" where the page says "Play a game of Kalimat". The old
    // check read the API text, and reached it only when an `isVisible` that does not wait
    // came back false, so it failed only when a Kalimat challenge was drawn first.
    await expect(page.getByText(shownDescription(challenges[0])).first()).toBeVisible({ timeout: 10_000 });

    await page.context().close();
  });

  test("challenges nav link navigates to challenges page", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.home);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Click challenges link in nav
    const navLink = authenticatedPage.locator('a[href="/challenges"]').first();
    await expect(navLink).toBeVisible({ timeout: 10_000 });
    await navLink.click();

    await expect(authenticatedPage).toHaveURL(/\/challenges/, {
      timeout: 10_000,
    });
  });

  test("unauthenticated user is redirected from challenges page", async ({
    page,
  }) => {
    await page.goto(ROUTES.challenges);
    await page.waitForLoadState("domcontentloaded");

    // Should redirect to login
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 10_000 });
  });
});

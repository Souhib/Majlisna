import { test, expect } from "../../fixtures/auth.fixture";
import { ROUTES } from "../../helpers/constants";

test.describe("Leaderboard — Data Display", () => {
  test("leaderboard page loads and shows sort tabs", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.leaderboard);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Title is visible
    await expect(
      authenticatedPage.getByRole("heading", { name: "Leaderboard" }),
    ).toBeVisible({ timeout: 10_000 });

    // Sort tabs are present
    await expect(authenticatedPage.getByRole("button", { name: "Wins" })).toBeVisible();
    await expect(authenticatedPage.getByRole("button", { name: "Win Rate" })).toBeVisible();
    await expect(authenticatedPage.getByRole("button", { name: "Streak" })).toBeVisible();
  });

  test("leaderboard table has correct column headers", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.leaderboard);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Wait for the table to render
    await expect(authenticatedPage.locator("table")).toBeVisible({
      timeout: 10_000,
    });

    // Verify column headers
    const headers = authenticatedPage.locator("thead th");
    await expect(headers).toHaveCount(6);
  });

  test("clicking sort tabs changes the active tab styling", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.leaderboard);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const winRateTab = authenticatedPage.getByRole("button", {
      name: "Win Rate",
    });
    await expect(winRateTab).toBeVisible({ timeout: 10_000 });
    const ranked = authenticatedPage.waitForResponse(
      (r) => r.url().includes("/api/v1/stats/leaderboard") && r.url().includes("stat_field=win_rate"),
    );
    await winRateTab.click();

    // After clicking, Win Rate is the pressed sort (and Wins no longer is)
    await expect(winRateTab).toHaveAttribute("aria-pressed", "true");
    await expect(authenticatedPage.getByRole("button", { name: "Wins" })).toHaveAttribute("aria-pressed", "false");

    // ...and the server ranks by it (win rate is computed, not a column: it used to answer 500)
    const response = await ranked;
    expect(response.status()).toBe(200);
    const entries = (await response.json()) as { win_rate: number }[];
    expect(entries.length).toBeGreaterThan(0);
    const rates = entries.map((e) => e.win_rate);
    expect(rates).toEqual([...rates].sort((a, b) => b - a));
    await expect(authenticatedPage.locator("table tbody tr")).toHaveCount(entries.length);
  });
});

import { test as baseTest, expect as baseExpect } from "@playwright/test";
import { test, expect } from "../../fixtures/auth.fixture";
import { ROUTES } from "../../helpers/constants";

test.describe("Profile — Authenticated Navigation", () => {
  test("profile page shows user info", async ({ authenticatedPage }) => {
    await authenticatedPage.goto(ROUTES.profile);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Should see the user's username heading
    await expect(
      authenticatedPage.getByRole("heading", { level: 1 }),
    ).toBeVisible({ timeout: 10_000 });

    // Should see the "Delete Account" section (confirms profile loaded)
    await expect(
      authenticatedPage.getByRole("heading", { name: "Delete Account" }),
    ).toBeVisible();
  });

  test("profile page has links to stats, achievements, rooms", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.profile);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Stats link (in main content area, not nav)
    await expect(
      authenticatedPage.locator('main a[href="/stats"]'),
    ).toBeVisible({ timeout: 10_000 });

    // Achievements link
    await expect(
      authenticatedPage.locator('main a[href="/achievements"]'),
    ).toBeVisible();

    // Rooms link (scoped to main to avoid matching the nav link)
    await expect(
      authenticatedPage.locator('main a[href="/rooms"]'),
    ).toBeVisible();
  });

  test("clicking rooms link from profile navigates correctly", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.profile);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    await authenticatedPage.locator('main a[href="/rooms"]').click();
    await expect(authenticatedPage).toHaveURL(/\/rooms/, {
      timeout: 10_000,
    });
  });
});

test.describe("Leaderboard — Public Page", () => {
  test("leaderboard page loads and shows table structure", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.leaderboard);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Should see the leaderboard title
    await expect(
      authenticatedPage.getByRole("heading", { name: "Leaderboard" }),
    ).toBeVisible({ timeout: 10_000 });

    // Should see table headers or empty state
    const hasTable = await authenticatedPage
      .locator('[data-testid="leaderboard"]')
      .first()
      .isVisible()
      .catch(() => false);

    const hasEmptyState = await authenticatedPage
      .getByText(/No players yet/i)
      .isVisible()
      .catch(() => false);

    // Either table or empty state should be visible
    expect(hasTable || hasEmptyState).toBeTruthy();
  });
});

test.describe("Navigation — Protected Routes", () => {
  test("authenticated user can navigate between all main pages", async ({
    authenticatedPage,
  }) => {
    // Home
    await authenticatedPage.goto("/");
    await expect(authenticatedPage).toHaveURL("/");

    // Rooms
    await authenticatedPage.goto(ROUTES.rooms);
    await authenticatedPage.waitForLoadState("domcontentloaded");
    await expect(authenticatedPage).toHaveURL(/\/rooms/);

    // Create Room
    await authenticatedPage.goto(ROUTES.createRoom);
    await authenticatedPage.waitForLoadState("domcontentloaded");
    await expect(authenticatedPage).toHaveURL(/\/rooms\/create/);

    // Profile
    await authenticatedPage.goto(ROUTES.profile);
    await authenticatedPage.waitForLoadState("domcontentloaded");
    await expect(authenticatedPage).toHaveURL(/\/profile/);

    // Leaderboard
    await authenticatedPage.goto(ROUTES.leaderboard);
    await authenticatedPage.waitForLoadState("domcontentloaded");
    await expect(authenticatedPage).toHaveURL(/\/leaderboard/);
  });

  test("navigating to non-existent game ID shows error or redirect", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(
      "/game/undercover/00000000-0000-0000-0000-000000000000",
    );
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Wait for error state or content to render (not crash or show blank page)
    await expect(async () => {
      const bodyText = await authenticatedPage.locator("body").textContent();
      expect(bodyText).toBeTruthy();
      expect(bodyText!.length).toBeGreaterThan(0);
    }).toPass({ timeout: 10_000 });
  });

  test("navigating to non-existent room ID shows error or redirect", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(
      "/rooms/00000000-0000-0000-0000-000000000000",
    );
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Wait for error state or content to render (not crash)
    await expect(async () => {
      const bodyText = await authenticatedPage.locator("body").textContent();
      expect(bodyText).toBeTruthy();
    }).toPass({ timeout: 10_000 });
  });
});

baseTest.describe("Navigation — Unauthenticated Redirects", () => {
  baseTest(
    "unauthenticated user is redirected from /profile",
    async ({ page }) => {
      await page.goto("/profile");
      await baseExpect(page).toHaveURL(/\/auth\/login/, {
        timeout: 15_000,
      });
    },
  );

  baseTest(
    "unauthenticated user is redirected from /rooms/create",
    async ({ page }) => {
      await page.goto("/rooms/create");
      await baseExpect(page).toHaveURL(/\/auth\/login/, {
        timeout: 15_000,
      });
    },
  );

  baseTest(
    "unauthenticated user can access /leaderboard",
    async ({ page }) => {
      await page.goto("/leaderboard");
      await page.waitForLoadState("domcontentloaded");

      // Leaderboard is a public page — should NOT redirect to login
      await baseExpect(page).toHaveURL(/\/leaderboard/);
    },
  );
});

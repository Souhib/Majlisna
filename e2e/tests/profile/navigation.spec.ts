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
  // The seed gives the leaderboard its players: the page must list them, one row each.
  // The old check passed on `data-testid="leaderboard"`, which sits on the <table> while
  // it loads and when it is empty, and on a 500 too (TQ-08).
  test("leaderboard page lists the seeded players", async ({ authenticatedPage }) => {
    const ranked = authenticatedPage.waitForResponse((r) => r.url().includes("/api/v1/stats/leaderboard"));
    await authenticatedPage.goto(ROUTES.leaderboard);

    await expect(authenticatedPage.getByRole("heading", { name: "Leaderboard" })).toBeVisible({ timeout: 10_000 });
    const response = await ranked;
    expect(response.status()).toBe(200);
    const entries = (await response.json()) as { username: string }[];
    expect(entries.length).toBeGreaterThan(0);
    const rows = authenticatedPage.getByTestId("leaderboard-row");
    await expect(rows).toHaveCount(entries.length);
    await expect(rows.first()).toContainText(entries[0].username);
    await expect(authenticatedPage.getByTestId("leaderboard-error")).toHaveCount(0);
  });

  test("a leaderboard the server cannot read says so, never 'No players yet'", async ({ authenticatedPage }) => {
    // Prepare — the leaderboard read fails
    await authenticatedPage.route("**/api/v1/stats/leaderboard**", (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error_key: "errors.api.base" }) }),
    );

    // Act
    await authenticatedPage.goto(ROUTES.leaderboard);

    // Assert — the failure, with Retry; no empty state, no table
    const failure = authenticatedPage.getByTestId("leaderboard-error");
    await expect(failure).toBeVisible({ timeout: 15_000 });
    await expect(failure.getByRole("button", { name: "Retry" })).toBeVisible();
    await expect(authenticatedPage.getByText(/No players yet/i)).toHaveCount(0);
    await expect(authenticatedPage.getByTestId("leaderboard-row")).toHaveCount(0);

    // ...and Retry reads again: once the server answers, the rows come back
    await authenticatedPage.unroute("**/api/v1/stats/leaderboard**");
    await failure.getByRole("button", { name: "Retry" }).click();
    await expect(authenticatedPage.getByTestId("leaderboard-row").first()).toBeVisible({ timeout: 15_000 });
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

  // A game that does not exist is said ("Game not found."), then the page goes home. The
  // old checks only asked for some text in <body>, which the nav alone provides (TQ-08).
  test("a game that does not exist is said, then the page goes home", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/game/undercover/00000000-0000-0000-0000-000000000000");

    const notice = authenticatedPage.getByRole("alert").filter({ hasText: "Game not found." });
    await expect(notice).toBeVisible({ timeout: 15_000 });
    await expect(notice).toContainText("Game Over");
    await expect(authenticatedPage).toHaveURL(new URL("/", authenticatedPage.url()).href, { timeout: 15_000 });
  });

  test("a room that does not exist says it did not open, with the way back", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/rooms/00000000-0000-0000-0000-000000000000");

    await expect(authenticatedPage.getByRole("heading", { level: 1, name: "This room did not open" })).toBeVisible({ timeout: 15_000 });
    await expect(authenticatedPage.getByText("Room not found.")).toBeVisible();
    const back = authenticatedPage.getByRole("link", { name: "Back to rooms" });
    await expect(back).toBeVisible();
    await back.click();
    await expect(authenticatedPage).toHaveURL(/\/rooms$/);
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

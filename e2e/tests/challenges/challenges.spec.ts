import { test, expect } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import {
  apiLogin,
  apiGetActiveChallenges,
  apiGetUndercoverState,
  type ActiveChallenge,
} from "../../helpers/api-client";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaAPI,
  undercoverRoles,
  voteOutViaAPI,
} from "../../helpers/ui-game-setup";
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

    // The definitions are seeded with the stack (generate_fake_data --create-db).
    // POST /challenges/seed is admin-only since WP-03 (SEC F15): a player gets 403.

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

  test("a finished game moves every challenge it counts for, and only those", async ({ browser }) => {
    test.setTimeout(120_000);

    // Prepare — three fresh players play an Undercover game to its end (one vote decides it)
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);
    const roles = await undercoverRoles(players, gameId);
    await submitDescriptionsForAllPlayersViaAPI(players);
    const voting = await apiGetUndercoverState(gameId, players[0].login.access_token);
    await voteOutViaAPI(gameId, players, voting, voting.players[voting.players.length - 1].user_id);
    await expect.poll(async () => (await apiGetUndercoverState(gameId, players[0].login.access_token)).winner).toBeTruthy();
    const winner = (await apiGetUndercoverState(gameId, players[0].login.access_token)).winner;

    // The server's own rule (ChallengeController._matches_challenge): the game type, then
    // play / win / play_as_role / win_as_role, and the distinct-types challenges ("Play
    // both Undercover and Codenames", "Play 3 different games"), which both count an
    // Undercover game as one type played. Challenges are given at the game's end, then
    // counted. They used to sit at 0 for good: nothing called the progress check (owner
    // rule (g)). "Win as the Undercover agent" used to count any Undercover win, and the
    // distinct-types ones any game at all (review R7).
    const counts = (c: ActiveChallenge, role: string, won: boolean) =>
      (!c.game_type || c.game_type === "undercover") &&
      (c.condition === "play" ||
        c.condition === "play_distinct_types" ||
        (c.condition === "win" && won) ||
        (c.condition === "play_as_role" && c.role === role) ||
        (c.condition === "win_as_role" && won && c.role === role));

    for (const player of players) {
      const role = roles.get(player.login.user.id)!;
      const won = (winner === "civilians") === (role === "civilian");
      const challenges = await apiGetActiveChallenges(player.login.access_token);
      expect(challenges.length).toBeGreaterThan(0);
      for (const c of challenges) {
        expect(c.progress, `${c.code} for a ${role} who ${won ? "won" : "lost"}`).toBe(counts(c, role, won) ? 1 : 0);
        expect(c.completed, c.code).toBe(c.progress >= c.target_count);
      }

      // ...and the page shows each count
      await player.page.goto(ROUTES.challenges);
      for (const c of challenges) {
        if (c.completed) {
          // a completed one is sealed and says so, with no bar
          const row = player.page.getByRole("listitem").filter({ has: player.page.getByText(shownDescription(c), { exact: true }) });
          await expect(row.getByText("Completed", { exact: true })).toBeVisible({ timeout: 10_000 });
          continue;
        }
        await expect(
          player.page.getByRole("progressbar", { name: `${shownDescription(c)}: ${c.progress} of ${c.target_count}`, exact: true }),
        ).toBeVisible({ timeout: 10_000 });
      }
    }

    await setup.cleanup();
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

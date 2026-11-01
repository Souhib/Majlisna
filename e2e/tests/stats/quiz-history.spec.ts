import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI, type PlayerContext } from "../../helpers/ui-game-setup";
import {
  apiGetGameHistory,
  apiGetMCQQuizState,
  apiGetUserStats,
  apiMCQQuizNextRound,
  apiSubmitMCQQuizAnswer,
  apiUpdateRoomSettings,
} from "../../helpers/api-client";
import { dbMcqCorrectIndex } from "../../helpers/db";

/**
 * A quiz's result reaches the player's history (WP-03): a win reads "Won", a loss
 * "Lost" (quiz wins used to read as losses, or as nothing, everywhere but the stats
 * row), and a tie at the top is a win shared by every top scorer (owner rule (a)), said
 * on the colophon as "A and B share the win."
 */

/** A one-question Quiz for two, answered by each player: right (`true`) or wrong. */
async function playOneQuestion(browser: import("@playwright/test").Browser, right: [boolean, boolean]) {
  const accounts = await generateTestAccounts(2);
  const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
  const host = setup.players[0];
  await apiUpdateRoomSettings(setup.roomId, { mcq_quiz_rounds: 1, mcq_quiz_turn_duration: 300 }, host.login.access_token);
  const gameId = await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);
  const correct = dbMcqCorrectIndex(gameId);
  for (const [i, player] of setup.players.entries()) {
    await apiSubmitMCQQuizAnswer(gameId, right[i] ? correct : (correct + 1) % 4, player.login.access_token);
  }
  await expect.poll(async () => (await apiGetMCQQuizState(gameId, host.login.access_token)).round_phase).toBe("results");
  await apiMCQQuizNextRound(gameId, host.login.access_token);
  await expect.poll(async () => (await apiGetMCQQuizState(gameId, host.login.access_token)).game_over).toBe(true);
  return { setup, gameId };
}

/** The bars of one kind ("won" or "lost") on the player's last-30-days chart, on /stats. */
const chartBars = (page: Page, part: "won" | "lost") =>
  page.locator('[aria-labelledby="winloss-title"] li[data-day]').locator(`[data-part="${part}"]`);

/** The game's result chip on the player's own /stats page. */
async function resultChipOf(player: PlayerContext): Promise<Page> {
  await player.page.goto("/stats");
  const rows = player.page.locator('[aria-labelledby="recent-title"] li');
  await expect(rows).toHaveCount(1, { timeout: 15_000 });
  await expect(rows.first()).toContainText("The Quiz");
  return player.page;
}

test.describe("Stats — quiz results in the history", () => {
  test("the quiz's winner reads Won, the other Lost, in history and stats", async ({ browser }) => {
    const { setup, gameId } = await playOneQuestion(browser, [true, false]);
    const [winner, loser] = setup.players;

    // The colophon names the one winner
    for (const player of setup.players) {
      await expect(player.page.getByText(`${winner.login.user.username} wins.`)).toBeVisible({ timeout: 15_000 });
    }
    const state = await apiGetMCQQuizState(gameId, winner.login.access_token);
    expect(state.winner).toBe(winner.login.user.username);
    expect(state.winner_ids).toEqual([winner.login.user.id]);

    // History and stats agree
    expect((await apiGetGameHistory(winner.login.user.id, winner.login.access_token)).find((g) => g.id === gameId)?.user_won).toBe(true);
    expect((await apiGetGameHistory(loser.login.user.id, loser.login.access_token)).find((g) => g.id === gameId)?.user_won).toBe(false);
    expect(await apiGetUserStats(winner.login.user.id)).toMatchObject({ total_games_played: 1, total_games_won: 1 });
    expect(await apiGetUserStats(loser.login.user.id)).toMatchObject({ total_games_played: 1, total_games_lost: 1 });

    const winnerPage = await resultChipOf(winner);
    await expect(winnerPage.locator('[aria-labelledby="recent-title"] li').getByText("Won", { exact: true })).toBeVisible();
    // ...and so does the chart: the quiz win is a won bar (it used to be drawn as a loss)
    await expect(chartBars(winnerPage, "won")).toHaveCount(1, { timeout: 15_000 });
    await expect(chartBars(winnerPage, "lost")).toHaveCount(0);
    const loserPage = await resultChipOf(loser);
    await expect(loserPage.locator('[aria-labelledby="recent-title"] li').getByText("Lost", { exact: true })).toBeVisible();
    await expect(chartBars(loserPage, "lost")).toHaveCount(1, { timeout: 15_000 });
    await expect(chartBars(loserPage, "won")).toHaveCount(0);

    await setup.cleanup();
  });

  test("a tie at the top is a shared win: both read Won", async ({ browser }) => {
    const { setup, gameId } = await playOneQuestion(browser, [true, true]);
    const names = setup.players.map((p) => p.login.user.username);

    // The colophon says the win is shared, naming both
    for (const player of setup.players) {
      const line = player.page.getByText(/share the win\./);
      await expect(line).toBeVisible({ timeout: 15_000 });
      for (const name of names) await expect(line).toContainText(name);
      await expect(player.page.getByText(/ wins\./)).toHaveCount(0);
    }
    const state = await apiGetMCQQuizState(gameId, setup.players[0].login.access_token);
    expect(state.winner).toBeNull();
    expect([...(state.winner_ids ?? [])].sort()).toEqual(setup.players.map((p) => p.login.user.id).sort());

    for (const player of setup.players) {
      expect((await apiGetGameHistory(player.login.user.id, player.login.access_token)).find((g) => g.id === gameId)?.user_won).toBe(true);
      expect(await apiGetUserStats(player.login.user.id)).toMatchObject({ total_games_played: 1, total_games_won: 1, total_games_lost: 0 });
      const page = await resultChipOf(player);
      await expect(page.locator('[aria-labelledby="recent-title"] li').getByText("Won", { exact: true })).toBeVisible();
      await expect(chartBars(page, "won")).toHaveCount(1, { timeout: 15_000 });
    }

    await setup.cleanup();
  });

  test("a game where nobody scored has no winner, and says so", async ({ browser }) => {
    const { setup, gameId } = await playOneQuestion(browser, [false, false]);

    // The colophon says nobody won (owner rule (a): a 0-0 game has no winner; the first
    // player seated used to be named the winner at 0 points)
    for (const player of setup.players) {
      await expect(player.page.getByText("No one scored: no winner this time.")).toBeVisible({ timeout: 15_000 });
      await expect(player.page.getByText(/ wins\.| share the win\./)).toHaveCount(0);
    }
    const state = await apiGetMCQQuizState(gameId, setup.players[0].login.access_token);
    expect(state.winner).toBeNull();
    expect(state.winner_ids ?? []).toEqual([]);

    // ...and nobody's history or stats count a win
    for (const player of setup.players) {
      expect((await apiGetGameHistory(player.login.user.id, player.login.access_token)).find((g) => g.id === gameId)?.user_won).not.toBe(true);
      expect(await apiGetUserStats(player.login.user.id)).toMatchObject({ total_games_played: 1, total_games_won: 0 });
      const page = await resultChipOf(player);
      await expect(page.locator('[aria-labelledby="recent-title"] li').getByText("Won", { exact: true })).toHaveCount(0);
      await expect(chartBars(page, "won")).toHaveCount(0);
    }

    await setup.cleanup();
  });
});

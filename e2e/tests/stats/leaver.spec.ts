import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaUI,
  undercoverRoles,
  voteOut,
} from "../../helpers/ui-game-setup";
import {
  apiGetGameHistory,
  apiGetMCQQuizState,
  apiGetUndercoverState,
  apiGetUserStats,
  apiLeaveRoom,
  apiMCQQuizNextRound,
  apiSubmitMCQQuizAnswer,
  apiUpdateRoomSettings,
} from "../../helpers/api-client";
import { dbMcqCorrectIndex } from "../../helpers/db";

/**
 * A player who leaves before the end gets neither a win nor a loss (owner rule (b)): the
 * game is not counted in their stats, their history shows it without a Won/Lost chip,
 * and an Undercover drop-out never shares their side's win. The players who stayed get
 * the result they played for (WP-03, WP-04).
 */

/** The one game on a fresh player's /stats page ("Recent games"). */
async function recentGame(page: Page) {
  await page.goto("/stats");
  const recent = page.getByRole("region", { name: "Recent games" }).or(page.locator('[aria-labelledby="recent-title"]'));
  const rows = recent.first().locator("li");
  await expect(rows).toHaveCount(1, { timeout: 15_000 });
  return rows.first();
}

test.describe("Stats — a player who leaves before the end", () => {
  test("the leaver gets no result and unchanged stats; the civilians who stayed win", async ({ browser }) => {
    test.setTimeout(120_000);

    // Prepare — four players (three civilians, one undercover); a civilian who is not
    // the host leaves during round 1
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);
    const roles = await undercoverRoles(players, gameId);
    const leaver = players.slice(1).find((p) => roles.get(p.login.user.id) === "civilian")!;
    const stayers = players.filter((p) => p !== leaver);
    const undercover = stayers.find((p) => roles.get(p.login.user.id) === "undercover")!;
    const civiliansWhoStayed = stayers.filter((p) => p !== undercover);
    expect(civiliansWhoStayed).toHaveLength(2);

    // Act — the civilian leaves; the three others describe and vote the undercover out
    await apiLeaveRoom(setup.roomId, leaver.login.user.id, leaver.login.access_token);
    await submitDescriptionsForAllPlayersViaUI(stayers);
    const voting = await apiGetUndercoverState(gameId, stayers[0].login.access_token);
    const alive = voting.players.filter((p) => p.is_alive);
    expect(alive.map((p) => p.user_id).sort()).toEqual(stayers.map((p) => p.login.user.id).sort());
    const target = alive.find((p) => p.user_id === undercover.login.user.id)!;
    await voteOut(stayers, alive, target, alive.find((p) => p.user_id !== target.user_id)!);
    for (const player of stayers) {
      await expect(player.page.locator('h2:has-text("Game Over")')).toBeVisible({ timeout: 30_000 });
    }
    expect((await apiGetUndercoverState(gameId, stayers[0].login.access_token)).winner).toBe("civilians");

    // Assert — the leaver: no result in their history, nothing in their stats
    const leaverHistory = await apiGetGameHistory(leaver.login.user.id, leaver.login.access_token);
    const leaverEntry = leaverHistory.find((g) => g.id === gameId);
    expect(leaverEntry?.game_status).toBe("finished");
    expect(leaverEntry?.user_won).toBeNull();
    expect(await apiGetUserStats(leaver.login.user.id, leaver.login.access_token)).toMatchObject({
      total_games_played: 0,
      total_games_won: 0,
      total_games_lost: 0,
    });
    const leaverRow = await recentGame(leaver.page);
    await expect(leaverRow).toContainText("Undercover");
    await expect(leaverRow.getByText(/^(Won|Lost)$/)).toHaveCount(0);

    // ...the civilians who stayed won; the undercover lost
    for (const civilian of civiliansWhoStayed) {
      expect((await apiGetGameHistory(civilian.login.user.id, civilian.login.access_token)).find((g) => g.id === gameId)?.user_won).toBe(true);
      expect(await apiGetUserStats(civilian.login.user.id, civilian.login.access_token)).toMatchObject({ total_games_played: 1, total_games_won: 1 });
    }
    expect((await apiGetGameHistory(undercover.login.user.id, undercover.login.access_token)).find((g) => g.id === gameId)?.user_won).toBe(false);
    expect(await apiGetUserStats(undercover.login.user.id, undercover.login.access_token)).toMatchObject({ total_games_played: 1, total_games_lost: 1 });
    await expect((await recentGame(civiliansWhoStayed[0].page)).getByText("Won", { exact: true })).toBeVisible();
    await expect((await recentGame(undercover.page)).getByText("Lost", { exact: true })).toBeVisible();

    await setup.cleanup();
  });

  test("the player left alone when the other walks out is charged nothing: no win, no loss", async ({ browser }) => {
    // Prepare — a one-question Quiz for two
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const [stayer, leaver] = setup.players;
    await apiUpdateRoomSettings(setup.roomId, { mcq_quiz_rounds: 1, mcq_quiz_turn_duration: 300 }, stayer.login.access_token);
    const gameId = await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);

    // Act — the other player walks out before answering; the one left answers right and
    // plays the game to its end, alone
    await apiLeaveRoom(setup.roomId, leaver.login.user.id, leaver.login.access_token);
    await apiSubmitMCQQuizAnswer(gameId, dbMcqCorrectIndex(gameId), stayer.login.access_token);
    await expect.poll(async () => (await apiGetMCQQuizState(gameId, stayer.login.access_token)).round_phase).toBe("results");
    await apiMCQQuizNextRound(gameId, stayer.login.access_token);
    await expect.poll(async () => (await apiGetMCQQuizState(gameId, stayer.login.access_token)).game_over).toBe(true);

    // Assert — a game whose final roster is one player is a solo game: never a win (owner
    // rule (a)), and never a loss either — it used to count as a lost game and break the
    // win streak of the player who stayed (reviews R4, INT-03)
    const state = await apiGetMCQQuizState(gameId, stayer.login.access_token);
    expect(state.winner).toBeNull();
    expect(state.winner_ids ?? []).toEqual([]);
    expect(await apiGetUserStats(stayer.login.user.id, stayer.login.access_token)).toMatchObject({ total_games_played: 1, total_games_won: 0, total_games_lost: 0 });
    expect((await apiGetGameHistory(stayer.login.user.id, stayer.login.access_token)).find((g) => g.id === gameId)?.user_won).toBeNull();
    const stayerRow = await recentGame(stayer.page);
    await expect(stayerRow).toContainText("The Quiz");
    await expect(stayerRow.getByText(/^(Won|Lost)$/)).toHaveCount(0);

    // ...and the leaver gets nothing at all (owner rule (b))
    expect(await apiGetUserStats(leaver.login.user.id, leaver.login.access_token)).toMatchObject({ total_games_played: 0, total_games_won: 0, total_games_lost: 0 });

    await setup.cleanup();
  });
});

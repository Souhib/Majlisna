import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaUI,
  voteOut,
  waitForEliminationOrGameOver,
  startNextRoundAsHost,
  type PlayerContext,
} from "../../helpers/ui-game-setup";
import { apiGetUndercoverState } from "../../helpers/api-client";

/**
 * Undercover played to its end through the UI. These used to catch every state-API
 * error as "the game ended" (a 500 counted as a finished game) and to return early when
 * the game was not where they expected (TQ-07); every read now has to succeed.
 */

/** Play one round: everyone describes, then the table votes out the last living player. */
async function playOneRound(players: PlayerContext[], gameId: string): Promise<"elimination" | "game_over"> {
  await submitDescriptionsForAllPlayersViaUI(players);
  const state = await apiGetUndercoverState(gameId, players[0].login.access_token);
  expect(state.turn_phase).toBe("voting");
  const alive = state.players.filter((p) => p.is_alive);
  await voteOut(players, alive, alive[alive.length - 1], alive[0]);
  return (await waitForEliminationOrGameOver(players[0].page)).type;
}

test.describe("Undercover Game Completion", () => {
  test("full game: play rounds until a winner is determined", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);

    // Four players lose one per round: the game is decided within three rounds
    let outcome: "elimination" | "game_over" = "elimination";
    for (let round = 1; round <= 3 && outcome === "elimination"; round++) {
      outcome = await playOneRound(players, gameId);
      if (outcome === "elimination") await startNextRoundAsHost(setup.players[0].page, players);
    }

    // Assert — the server has a winner, and every page shows the end
    expect(outcome).toBe("game_over");
    const final = await apiGetUndercoverState(gameId, players[0].login.access_token);
    expect(["civilians", "undercovers"]).toContain(final.winner);
    for (const player of players) {
      await expect(player.page.locator('h2:has-text("Game Over")')).toBeVisible({ timeout: 30_000 });
    }

    await setup.cleanup();
  });

  test("3-player game completes in one round", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);

    // Act — one round: with three players, one elimination decides the game
    const outcome = await playOneRound(players, gameId);

    // Assert
    expect(outcome).toBe("game_over");
    const final = await apiGetUndercoverState(gameId, players[0].login.access_token);
    expect(["civilians", "undercovers"]).toContain(final.winner);

    await setup.cleanup();
  });

  test("5-player game starts with correct roles distributed", async ({ browser }) => {
    const accounts = await generateTestAccounts(5);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);

    // Each player reads their own role
    const roles: string[] = [];
    for (const player of setup.players) {
      const state = await apiGetUndercoverState(gameId, player.login.access_token);
      roles.push(state.my_role);
    }

    // Five players: three civilians, one undercover, one Mr. White (Mr. White is on by default)
    expect(roles.filter((r) => r === "civilian")).toHaveLength(3);
    expect(roles.filter((r) => r === "undercover")).toHaveLength(1);
    expect(roles.filter((r) => r === "mr_white")).toHaveLength(1);

    await setup.cleanup();
  });

  test("game over screen shows winner and back to room works", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);

    expect(await playOneRound(players, gameId)).toBe("game_over");

    // The colophon's way back: "Back to the room" returns to the lobby
    const observerPage = players[0].page;
    await expect(observerPage.locator('h2:has-text("Game Over")')).toBeVisible({ timeout: 30_000 });
    const backBtn = observerPage.getByRole("button", { name: "Back to the room" });
    await expect(backBtn).toBeVisible({ timeout: 10_000 });
    await backBtn.click();
    await expect(observerPage).toHaveURL(new RegExp(`/rooms/${setup.roomId}`), { timeout: 15_000 });
    await expect(observerPage.locator("text=Players (3)")).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });
});

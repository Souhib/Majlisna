import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  startGameViaUI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaAPI,
  voteOutViaAPI,
  gameIdFromUrl,
} from "../../helpers/ui-game-setup";
import {
  apiGetGameHistory,
  apiGetRoomState,
  apiGetUndercoverState,
  apiRematch,
} from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";
import { dbGameStatus } from "../../helpers/db";

/**
 * The host's rematch sends the room back to its lobby. A game still being played is
 * CANCELLED (closing it is the point of a rematch mid-game), a finished one stays
 * finished. The old spec asserted only the fields the server hardcodes in its answer
 * (the request's own room id and the literal "lobby") and swallowed every describe and
 * vote error: it passed on a rematch that did nothing (TQ-09).
 */
test.describe("Room Rematch", () => {
  test("a rematch mid-game cancels the running game and reopens the lobby", async ({ browser }) => {
    // Prepare — a 3-player Undercover game under way
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const host = setup.players[0];
    const oldGameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    expect(dbGameStatus(oldGameId)).toBe("IN_PROGRESS");

    // Act — the host calls a rematch while the game runs
    const answer = await apiRematch(setup.roomId, host.login.access_token);
    expect(answer).toEqual({ room_id: setup.roomId, status: "lobby" });

    // Assert — the old game is CANCELLED, in the database and in the host's history
    expect(dbGameStatus(oldGameId)).toBe("CANCELLED");
    const history = await apiGetGameHistory(host.login.user.id, host.login.access_token);
    expect(history.find((g) => g.id === oldGameId)?.game_status).toBe("cancelled");

    // ...the room has no active game any more...
    const room = await apiGetRoomState(setup.roomId, host.login.access_token);
    expect(room.active_game_id).toBeNull();
    expect(room.players.map((p) => p.user_id).sort()).toEqual(setup.players.map((p) => p.login.user.id).sort());

    // ...and the host's lobby offers to start again: the room stays on its lobby
    for (const player of setup.players) {
      await player.page.goto(ROUTES.room(setup.roomId));
      await expect(player.page.locator("text=Players (3)")).toBeVisible({ timeout: 15_000 });
    }
    await expect(host.page.locator('button:has-text("Start")')).toBeEnabled({ timeout: 10_000 });
    await expect(host.page).toHaveURL(new RegExp(`/rooms/${setup.roomId}$`));

    // The table plays again: a new game, not the cancelled one
    await startGameViaUI(setup.players, "undercover");
    const newGameId = gameIdFromUrl(host.page, "undercover");
    expect(newGameId).not.toBe(oldGameId);
    expect(dbGameStatus(newGameId)).toBe("IN_PROGRESS");

    await setup.cleanup();
  });

  test("a rematch after the end leaves the finished game as it ended", async ({ browser }) => {
    // Prepare — a 3-player game played to its end (one vote decides it)
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const host = setup.players[0];
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);
    await submitDescriptionsForAllPlayersViaAPI(players);
    const voting = await apiGetUndercoverState(gameId, host.login.access_token);
    await voteOutViaAPI(gameId, players, voting, voting.players[voting.players.length - 1].user_id);
    await expect.poll(async () => (await apiGetUndercoverState(gameId, host.login.access_token)).winner).toBeTruthy();
    const winner = (await apiGetUndercoverState(gameId, host.login.access_token)).winner;
    expect(dbGameStatus(gameId)).toBe("FINISHED");

    // Act
    await apiRematch(setup.roomId, host.login.access_token);

    // Assert — still finished, with its winner; the room is back in its lobby
    expect(dbGameStatus(gameId)).toBe("FINISHED");
    expect((await apiGetUndercoverState(gameId, host.login.access_token)).winner).toBe(winner);
    expect((await apiGetRoomState(setup.roomId, host.login.access_token)).active_game_id).toBeNull();
    await host.page.goto(ROUTES.room(setup.roomId));
    await expect(host.page.locator('button:has-text("Start")')).toBeEnabled({ timeout: 15_000 });

    await setup.cleanup();
  });
});

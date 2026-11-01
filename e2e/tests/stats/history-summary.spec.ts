import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaAPI,
  voteOutViaAPI,
} from "../../helpers/ui-game-setup";
import { apiGetUndercoverState, apiLogin, expectApiError, rawGet } from "../../helpers/api-client";

/**
 * A finished game opens its summary from the player's history: who held which role, the
 * two words, the vote. The summary is for the players of a finished game only (it holds
 * every role and both secret words): a game still running has no summary to open, and a
 * stranger is refused.
 */
test.describe("Stats — a game's summary from the history", () => {
  test("open a finished Undercover game from /stats: roles, words and players", async ({ browser }) => {
    // Prepare — a 3-player game, then a second one left running
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const [host] = setup.players;
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);
    await submitDescriptionsForAllPlayersViaAPI(players);
    const voting = await apiGetUndercoverState(gameId, host.login.access_token);
    await voteOutViaAPI(gameId, players, voting, voting.players[voting.players.length - 1].user_id);
    await expect.poll(async () => (await apiGetUndercoverState(gameId, host.login.access_token)).winner).toBeTruthy();
    const ended = await apiGetUndercoverState(gameId, host.login.access_token);
    const words = ended.word_explanations!;
    expect(words.civilian_word).toBeTruthy();

    // The summary is the players' only: a stranger is refused by name
    const [stranger] = await generateTestAccounts(1);
    const strangerLogin = await apiLogin(stranger.email, stranger.password);
    await expectApiError(await rawGet(`/api/v1/games/${gameId}/summary`, strangerLogin.access_token), 403, "errors.api.notAGameParticipant");

    // Act — the host opens it from their history
    const page = host.page;
    await page.goto("/stats");
    const row = page.locator('[aria-labelledby="recent-title"] li').first();
    await expect(row).toContainText("Undercover", { timeout: 15_000 });
    await row.getByRole("button").click();

    // Assert — the dialog: the game, both words, every player with their role
    const dialog = page.getByRole("dialog", { name: "Undercover" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText(words.civilian_word, { timeout: 15_000 });
    await expect(dialog).toContainText(words.undercover_word);
    for (const player of setup.players) await expect(dialog).toContainText(player.login.user.username);
    await expect(dialog).toContainText("Civilian");

    // Escape closes it, back on the history
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);

    await setup.cleanup();
  });

  test("a game still being played has no summary yet", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const host = setup.players[0];

    await expectApiError(await rawGet(`/api/v1/games/${gameId}/summary`, host.login.access_token), 403, "errors.api.gameStillInProgress");

    // ...and its history row is not a button: it reads "In progress"
    await host.page.goto("/stats");
    const row = host.page.locator('[aria-labelledby="recent-title"] li').first();
    await expect(row).toContainText("In progress", { timeout: 15_000 });
    await expect(row.getByRole("button")).toHaveCount(0);

    await setup.cleanup();
  });
});

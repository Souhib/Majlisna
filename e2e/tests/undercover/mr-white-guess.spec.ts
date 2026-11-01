import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaUI,
  undercoverRoles,
  voteOut,
  waitForEliminationOrGameOver,
  startNextRoundAsHost,
  type PlayerContext,
} from "../../helpers/ui-game-setup";
import { apiGetUndercoverState } from "../../helpers/api-client";

/**
 * Mr. White's last chance. Five players (three civilians, one undercover, one Mr. White):
 * the table votes the undercover out, then Mr. White. With no impostor left alive the
 * old state read "civilians win" the moment Mr. White fell, and every page (his own
 * included) showed the end and both words: he never got the guess that could reverse
 * it (BR-01). Now he is offered the guess, nobody else reads a winner or a word while
 * it is owed, and his guess decides: the civilians' word gives the impostors the game.
 */

interface Table {
  setup: Awaited<ReturnType<typeof setupRoomWithPlayers>>;
  gameId: string;
  players: PlayerContext[];
  mrWhite: PlayerContext;
  others: PlayerContext[];
  civilianWord: string;
}

/** Five players, played to the moment Mr. White is voted out (the undercover went first). */
async function upToMrWhitesGuess(browser: import("@playwright/test").Browser): Promise<Table> {
  const accounts = await generateTestAccounts(5);
  const setup = await setupRoomWithPlayers(browser, accounts);
  const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
  const players = await dismissRoleRevealAll(setup.players);
  const roles = await undercoverRoles(players, gameId);
  const idOf = (role: string) => [...roles].find(([, r]) => r === role)![0];
  const undercoverId = idOf("undercover");
  const mrWhiteId = idOf("mr_white");
  const civilian = players.find((p) => roles.get(p.login.user.id) === "civilian")!;
  const civilianWord = (await apiGetUndercoverState(gameId, civilian.login.access_token)).my_word;

  // Round 1 — the undercover goes
  await submitDescriptionsForAllPlayersViaUI(players);
  let state = await apiGetUndercoverState(gameId, players[0].login.access_token);
  let alive = state.players.filter((p) => p.is_alive);
  await voteOut(players, alive, alive.find((p) => p.user_id === undercoverId)!, alive.find((p) => p.user_id !== undercoverId)!);
  expect((await waitForEliminationOrGameOver(players[0].page)).type).toBe("elimination");
  await startNextRoundAsHost(setup.players[0].page, players);

  // Round 2 — Mr. White goes: the last impostor alive
  const living = players.filter((p) => p.login.user.id !== undercoverId);
  await submitDescriptionsForAllPlayersViaUI(living);
  state = await apiGetUndercoverState(gameId, players[0].login.access_token);
  alive = state.players.filter((p) => p.is_alive);
  expect(alive).toHaveLength(4);
  await voteOut(living, alive, alive.find((p) => p.user_id === mrWhiteId)!, alive.find((p) => p.user_id !== mrWhiteId)!);

  const mrWhite = players.find((p) => p.login.user.id === mrWhiteId)!;
  return { setup, gameId, players, mrWhite, others: players.filter((p) => p !== mrWhite), civilianWord };
}

/** While the guess is owed: Mr. White has the field, nobody reads an end or a word. */
async function expectTheGuessOwed(table: Table): Promise<void> {
  const { mrWhite, others, gameId } = table;
  await expect(mrWhite.page.getByRole("heading", { name: "Your last chance" })).toBeVisible({ timeout: 15_000 });
  await expect(mrWhite.page.getByRole("textbox", { name: "The civilians’ word" })).toBeVisible();
  for (const player of others) {
    await expect(player.page.getByText("Mr. White has one guess").first()).toBeVisible({ timeout: 15_000 });
    await expect(player.page.locator('h2:has-text("Game Over")')).toHaveCount(0);
    await expect(player.page.getByRole("textbox", { name: "The civilians’ word" })).toHaveCount(0);
  }
  for (const player of table.players) {
    const state = await apiGetUndercoverState(gameId, player.login.access_token);
    expect(state.turn_phase).toBe("mr_white_guessing");
    expect(state.winner ?? null).toBeNull();
    expect(state.word_explanations ?? null).toBeNull();
    expect(state.mr_white_guesser).toBe(table.mrWhite.login.user.id);
  }
  // Mr. White's own payload does not carry the word he is about to guess
  const his = await apiGetUndercoverState(gameId, mrWhite.login.access_token);
  expect(JSON.stringify(his)).not.toContain(table.civilianWord);
}

/** Mr. White types his guess and sends it. */
async function guess(table: Table, word: string): Promise<void> {
  const page = table.mrWhite.page;
  await page.getByRole("textbox", { name: "The civilians’ word" }).fill(word);
  await page.getByRole("button", { name: "Guess", exact: true }).click();
}

test.describe("Undercover — Mr. White's guess", () => {
  test("voted out last, Mr. White guesses the civilians' word and the impostors win", async ({ browser }) => {
    test.setTimeout(150_000);
    const table = await upToMrWhitesGuess(browser);

    await expectTheGuessOwed(table);

    // Act — the right word
    await guess(table, table.civilianWord);

    // Assert — the impostors' game, on every page, and the guess said with it
    for (const player of table.players) {
      await expect(player.page.locator('h2:has-text("Game Over")')).toBeVisible({ timeout: 30_000 });
      await expect(player.page.getByText("The impostors win.")).toBeVisible();
    }
    const final = await apiGetUndercoverState(table.gameId, table.players[0].login.access_token);
    expect(final.winner).toBe("undercovers");

    await table.setup.cleanup();
  });

  test("a wrong guess leaves the civilians the game", async ({ browser }) => {
    test.setTimeout(150_000);
    const table = await upToMrWhitesGuess(browser);

    await expectTheGuessOwed(table);

    // Act — a word that is not it
    await guess(table, "notthetablesword");

    // Assert — the civilians' game, on every page
    for (const player of table.players) {
      await expect(player.page.locator('h2:has-text("Game Over")')).toBeVisible({ timeout: 30_000 });
      await expect(player.page.getByText("Civilians win.")).toBeVisible();
    }
    expect((await apiGetUndercoverState(table.gameId, table.players[0].login.access_token)).winner).toBe("civilians");

    await table.setup.cleanup();
  });
});

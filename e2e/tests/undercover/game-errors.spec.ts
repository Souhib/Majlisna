import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaUI,
  submitDescriptionsForAllPlayersViaAPI,
  voteOut,
  waitForEliminationOrGameOver,
  submitDescriptionViaUI,
} from "../../helpers/ui-game-setup";
import { apiGetUndercoverState, expectApiError, rawPost } from "../../helpers/api-client";

/**
 * The refusals of an Undercover round, asserted by their exact status and error key.
 * These tests used to wrap their checks in try/catch and `return` early when the game
 * was not where they expected, and to accept any non-2xx (a 500 or a 422 too): they
 * passed with the state API down or the game stuck in "describing" (TQ-07).
 */
test.describe("Undercover Game Errors", () => {
  test("vote for self is rejected via API", async ({ browser }) => {
    // Prepare — a 3-player table at the vote
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const activePlayers = await dismissRoleRevealAll(setup.players);
    await submitDescriptionsForAllPlayersViaAPI(activePlayers);
    const voter = activePlayers[0];
    await expect.poll(async () => (await apiGetUndercoverState(gameId, voter.login.access_token)).turn_phase).toBe("voting");

    // Act — vote for oneself
    const res = await rawPost(`/api/v1/undercover/games/${gameId}/vote`, { voted_for: voter.login.user.id }, voter.login.access_token);

    // Assert — refused by name, and no ballot was recorded
    await expectApiError(res, 403, "errors.api.cantVoteForYourself");
    const after = await apiGetUndercoverState(gameId, voter.login.access_token);
    expect(after.has_voted).toBe(false);
    expect(after.turn_phase).toBe("voting");

    await setup.cleanup();
  });

  test("describe out of turn is rejected via API", async ({ browser }) => {
    // Prepare — a 3-player table at the first describer
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    await dismissRoleRevealAll(setup.players);
    const state = await apiGetUndercoverState(gameId, setup.players[0].login.access_token);
    expect(state.turn_phase).toBe("describing");
    const currentDescriberId = state.description_order![state.current_describer_index ?? 0].user_id;
    const wrongPlayer = setup.players.find((p) => p.login.user.id !== currentDescriberId)!;

    // Act — a player whose turn it is not describes
    const res = await rawPost(`/api/v1/undercover/games/${gameId}/describe`, { word: "wrongturn" }, wrongPlayer.login.access_token);

    // Assert — refused by name; the turn has not moved and nothing was written
    await expectApiError(res, 400, "errors.api.notYourTurnToDescribe");
    const after = await apiGetUndercoverState(gameId, setup.players[0].login.access_token);
    expect(after.current_describer_index).toBe(state.current_describer_index);
    expect(Object.values(after.descriptions ?? {})).not.toContain("wrongturn");

    await setup.cleanup();
  });

  test("a describer who gives their own word is refused in the page, and the turn waits for them", async ({ browser }) => {
    // Prepare — a 3-player table at the first describer, who holds their word
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    await dismissRoleRevealAll(setup.players);
    const state = await apiGetUndercoverState(gameId, setup.players[0].login.access_token);
    const describerId = state.description_order![state.current_describer_index ?? 0].user_id;
    const describer = setup.players.find((p) => p.login.user.id === describerId)!;
    const own = await apiGetUndercoverState(gameId, describer.login.access_token);
    expect(own.my_word).toBeTruthy();
    const input = describer.page.locator("#description-input");
    await expect(input).toBeVisible({ timeout: 15_000 });

    // Act — the describer types their own word, in capitals, as ONE word: the page and the
    // server both refuse a space (invalidDescriptionWord), and a term such as "Eid al-Fitr"
    // is drawn at random, so "EID-AL-FITR" (hyphens are spaces to the own-word comparison)
    await submitDescriptionViaUI(describer.page, own.my_word.toUpperCase().replace(/\s+/g, "-"));

    // Assert — said in the page, in the server's words; the turn is still theirs (BR-16:
    // "describing" the word by saying it handed it to the undercover)
    await expect(describer.page.getByText("Describe your word without saying it.")).toBeVisible({ timeout: 10_000 });
    await expect(input).toBeVisible();
    const after = await apiGetUndercoverState(gameId, describer.login.access_token);
    expect(after.current_describer_index).toBe(state.current_describer_index);
    expect(after.turn_phase).toBe("describing");
    // ...the server refuses it by name, whatever the case, with nothing in the error to
    // repeat the word
    const refused = await expectApiError(
      await rawPost(`/api/v1/undercover/games/${gameId}/describe`, { word: own.my_word.toLowerCase().replace(/\s+/g, "-") }, describer.login.access_token),
      400,
      "errors.api.descriptionRevealsWord",
    );
    expect(JSON.stringify(refused).toLowerCase()).not.toContain(own.my_word.toLowerCase());

    // ...and another word goes through: the turn moves on
    await submitDescriptionViaUI(describer.page, "clue");
    await expect(input).toBeHidden({ timeout: 10_000 });
    await expect
      .poll(async () => (await apiGetUndercoverState(gameId, describer.login.access_token)).current_describer_index)
      .not.toBe(state.current_describer_index);

    await setup.cleanup();
  });

  test("eliminated player is marked dead after voting", async ({ browser }) => {
    // Prepare — a 4-player table at the vote
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const activePlayers = await dismissRoleRevealAll(setup.players);
    await submitDescriptionsForAllPlayersViaUI(activePlayers);
    const state = await apiGetUndercoverState(gameId, activePlayers[0].login.access_token);
    const alive = state.players.filter((p) => p.is_alive);
    expect(alive).toHaveLength(4);
    const target = alive[1];

    // Act — the table votes the second player out
    await voteOut(activePlayers, alive, target, alive[0]);
    await waitForEliminationOrGameOver(activePlayers[0].page);

    // Assert — the server has the target dead, in their own state and in everyone's
    const targetPlayer = activePlayers.find((p) => p.login.user.id === target.user_id)!;
    const targetState = await apiGetUndercoverState(gameId, targetPlayer.login.access_token);
    expect(targetState.is_alive).toBe(false);
    const observer = await apiGetUndercoverState(gameId, activePlayers[0].login.access_token);
    expect(observer.players.find((p) => p.user_id === target.user_id)?.is_alive).toBe(false);
    expect(observer.eliminated_players.map((p) => p.user_id)).toContain(target.user_id);

    await setup.cleanup();
  });
});

import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
} from "../../helpers/ui-game-setup";
import {
  apiGetWordQuizState,
  apiWordQuizTimerExpired,
  apiWordQuizNextRound,
  apiUpdateRoomSettings,
} from "../../helpers/api-client";

test.describe("Word Quiz Single Player", () => {
  test("1-player game starts and plays", async ({ browser }) => {
    // Word Quiz supports 1 player (min_players = 1)
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);

    const player = setup.players[0];

    // Should see game header
    await expect(
      player.page.locator("h1:has-text('Word Quiz')"),
    ).toBeVisible({ timeout: 15_000 });

    // Should see round 1
    await expect(
      player.page.locator("text=Round 1/"),
    ).toBeVisible({ timeout: 5_000 });

    // Should see hints
    await expect(
      player.page.locator("text=#1"),
    ).toBeVisible({ timeout: 5_000 });

    // Should see answer input
    await expect(
      player.page.locator('input[type="text"]'),
    ).toBeVisible({ timeout: 5_000 });

    await setup.cleanup();
  });

  test("1-player game completes after all rounds via API", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const token = setup.players[0].login.access_token;

    // Set very short turn duration so timer actually expires server-side
    await apiUpdateRoomSettings(setup.roomId, { word_quiz_turn_duration: 1 }, token);

    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);

    const gameId = setup.players[0].page.url().split("/").pop()!;

    // Get initial state
    let state = await apiGetWordQuizState(gameId, token);
    const totalRounds = state.total_rounds;

    // Play through all rounds via timer expiry + next round
    for (let round = 1; round <= totalRounds; round++) {
      state = await apiGetWordQuizState(gameId, token);
      if (state.round_phase === "game_over") break;

      // Wait for the 1s timer to expire server-side
      await setup.players[0].page.waitForTimeout(2000);

      // Force timer expired to go to results
      if (state.round_phase === "playing") {
        await apiWordQuizTimerExpired(gameId, token);
      }

      // Wait for results phase
      let attempts = 0;
      state = await apiGetWordQuizState(gameId, token);
      while (state.round_phase !== "results" && state.round_phase !== "game_over" && attempts < 10) {
        await setup.players[0].page.waitForTimeout(500);
        state = await apiGetWordQuizState(gameId, token);
        attempts++;
      }

      if (state.round_phase === "game_over") break;

      // Advance to next round (or game over on last round)
      if (state.round_phase === "results") {
        await apiWordQuizNextRound(gameId, token);
      }
    }

    // Verify game over via API
    state = await apiGetWordQuizState(gameId, token);
    expect(state.game_over).toBe(true);

    // Reload page to ensure browser picks up the latest state
    // (API calls above were made outside the browser, so the query cache is stale)
    await setup.players[0].page.reload();

    // UI should show game over
    await expect(
      setup.players[0].page.locator("text=Final Scores").or(setup.players[0].page.locator("text=Scores finaux")).or(setup.players[0].page.locator("text=النتائج النهائية")),
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });
});

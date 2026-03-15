import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
} from "../../helpers/ui-game-setup";
import {
  apiGetMCQQuizState,
  apiSubmitMCQQuizAnswer,
  apiMCQQuizTimerExpired,
  apiMCQQuizNextRound,
  apiUpdateRoomSettings,
} from "../../helpers/api-client";

test.describe("MCQ Quiz Single Player", () => {
  test("1-player game starts and shows question with 4 choices", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);

    const player = setup.players[0];

    // Should see game header
    await expect(
      player.page.locator("h1:has-text('MCQ Quiz')")
        .or(player.page.locator("h1:has-text('اختبار')"))
        .or(player.page.locator("h1:has-text('QCM')")),
    ).toBeVisible({ timeout: 15_000 });

    // Should see question counter (uses "Question X/Y" from i18n)
    await expect(
      player.page.locator("text=/Question \\d+\\/\\d+/").first(),
    ).toBeVisible({ timeout: 5_000 });

    // Should see 4 choice buttons (labels A, B, C, D without period)
    const buttons = player.page.locator("button").filter({ has: player.page.locator("span") });
    await expect(buttons.first()).toBeVisible({ timeout: 5_000 });

    // Verify there are at least 4 choice buttons
    const count = await buttons.count();
    expect(count).toBeGreaterThanOrEqual(4);

    await setup.cleanup();
  });

  test("1-player can answer a question and see results", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const token = setup.players[0].login.access_token;

    await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);

    const player = setup.players[0];
    const gameId = player.page.url().split("/").pop()!;

    // Wait for question to be visible
    await expect(
      player.page.locator("h1:has-text('MCQ Quiz')")
        .or(player.page.locator("h1:has-text('اختبار')"))
        .or(player.page.locator("h1:has-text('QCM')")),
    ).toBeVisible({ timeout: 15_000 });

    // Get game state to verify we're in playing phase
    let state = await apiGetMCQQuizState(gameId, token);
    expect(state.round_phase).toBe("playing");
    expect(state.choices.length).toBe(4);

    // Submit an answer via API (choice_index 0 = first choice)
    await apiSubmitMCQQuizAnswer(gameId, 0, token);

    // With 1 player, all players have answered, so it auto-transitions to results
    // Wait for results phase
    let attempts = 0;
    state = await apiGetMCQQuizState(gameId, token);
    while (state.round_phase !== "results" && state.round_phase !== "game_over" && attempts < 10) {
      await player.page.waitForTimeout(500);
      state = await apiGetMCQQuizState(gameId, token);
      attempts++;
    }

    // Should be in results phase now
    expect(["results", "game_over"]).toContain(state.round_phase);

    // Correct answer index should be revealed
    if (state.round_phase === "results") {
      expect(state.correct_answer_index).not.toBeNull();
    }

    await setup.cleanup();
  });

  test("1-player game completes after all rounds via API", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const token = setup.players[0].login.access_token;

    // Set short rounds count for faster test
    await apiUpdateRoomSettings(setup.roomId, { mcq_quiz_turn_duration: 10, mcq_quiz_rounds: 3 }, token);

    await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);

    const gameId = setup.players[0].page.url().split("/").pop()!;

    // Get initial state
    let state = await apiGetMCQQuizState(gameId, token);
    const totalRounds = state.total_rounds;

    // Play through all rounds: answer + next-round loop
    for (let round = 1; round <= totalRounds; round++) {
      state = await apiGetMCQQuizState(gameId, token);
      if (state.round_phase === "game_over") break;

      // Submit answer (auto-transitions to results with 1 player)
      if (state.round_phase === "playing" && !state.my_answered) {
        await apiSubmitMCQQuizAnswer(gameId, 0, token);
      }

      // Wait for results phase
      let attempts = 0;
      state = await apiGetMCQQuizState(gameId, token);
      while (state.round_phase === "playing" && attempts < 20) {
        await setup.players[0].page.waitForTimeout(500);
        state = await apiGetMCQQuizState(gameId, token);
        attempts++;
      }

      if (state.round_phase === "game_over") break;

      // Advance to next round (or game over on last round)
      if (state.round_phase === "results") {
        await apiMCQQuizNextRound(gameId, token);
      }
    }

    // Verify game over
    state = await apiGetMCQQuizState(gameId, token);
    expect(state.game_over).toBe(true);

    // UI should show game over
    await expect(
      setup.players[0].page.locator("text=Final Scores")
        .or(setup.players[0].page.locator("text=Scores finaux"))
        .or(setup.players[0].page.locator("text=النتائج النهائية")),
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });
});

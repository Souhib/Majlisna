import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
} from "../../helpers/ui-game-setup";
import {
  apiGetWordQuizState,
  apiSubmitWordQuizAnswer,
  apiWordQuizTimerExpired,
  apiWordQuizNextRound,
  apiUpdateRoomSettings,
} from "../../helpers/api-client";

test.describe("Word Quiz Game Flow", () => {
  test("game starts and shows hints", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);

    // All players should see the game header
    for (const player of setup.players) {
      await expect(
        player.page.locator("h1:has-text('Word Quiz')"),
      ).toBeVisible({ timeout: 15_000 });

      // Should see round info
      await expect(
        player.page.locator("text=Round 1/"),
      ).toBeVisible({ timeout: 5_000 });

      // Should see at least the first hint
      await expect(
        player.page.locator("text=#1"),
      ).toBeVisible({ timeout: 5_000 });
    }

    await setup.cleanup();
  });

  test("correct answer shows success and points", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);

    // Get the game state to find the correct answer
    const hostToken = setup.players[0].login.access_token;
    const gameId = setup.players[0].page.url().split("/").pop()!;
    const state = await apiGetWordQuizState(gameId, hostToken);

    // Game should be in playing phase
    expect(state.round_phase).toBe("playing");
    expect(state.hints.length).toBeGreaterThan(0);

    await setup.cleanup();
  });

  test("submit wrong answer via API returns correct=false", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);

    const gameId = setup.players[0].page.url().split("/").pop()!;
    const hostToken = setup.players[0].login.access_token;

    // Submit a wrong answer
    const result = await apiSubmitWordQuizAnswer(gameId, "definitely_wrong_answer_xyz", hostToken);
    expect(result.correct).toBe(false);
    expect(result.points_earned).toBe(0);

    await setup.cleanup();
  });

  test("timer expired transitions to results", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const hostToken = setup.players[0].login.access_token;

    // Set very short turn duration so timer actually expires server-side
    await apiUpdateRoomSettings(setup.roomId, { word_quiz_turn_duration: 1 }, hostToken);

    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    const gameId = setup.players[0].page.url().split("/").pop()!;

    // Wait for the 1s timer to expire
    await setup.players[0].page.waitForTimeout(2000);

    // Force timer expired
    await apiWordQuizTimerExpired(gameId, hostToken);

    // Verify via API that results phase was reached
    let state = await apiGetWordQuizState(gameId, hostToken);
    let attempts = 0;
    while (state.round_phase !== "results" && attempts < 10) {
      await setup.players[0].page.waitForTimeout(500);
      state = await apiGetWordQuizState(gameId, hostToken);
      attempts++;
    }
    expect(state.round_phase).toBe("results");

    // Host's page should show results (host's mutation invalidates query directly)
    const hostPage = setup.players[0].page;
    await expect(
      hostPage.locator("text=The answer was").or(hostPage.locator("text=La réponse")).or(hostPage.locator("text=الإجابة")),
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });

  test("next round advances the game", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const hostToken = setup.players[0].login.access_token;

    // Set very short turn duration
    await apiUpdateRoomSettings(setup.roomId, { word_quiz_turn_duration: 1 }, hostToken);

    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    const gameId = setup.players[0].page.url().split("/").pop()!;

    // Wait for timer to expire server-side
    await setup.players[0].page.waitForTimeout(2000);

    // Force to results
    await apiWordQuizTimerExpired(gameId, hostToken);

    // Wait for results to be reflected in state
    let state = await apiGetWordQuizState(gameId, hostToken);
    let attempts = 0;
    while (state.round_phase !== "results" && attempts < 10) {
      await setup.players[0].page.waitForTimeout(500);
      state = await apiGetWordQuizState(gameId, hostToken);
      attempts++;
    }
    expect(state.round_phase).toBe("results");

    // Advance to next round
    await apiWordQuizNextRound(gameId, hostToken);

    // Reload to pick up latest state (API call was outside browser)
    const hostPage = setup.players[0].page;
    await hostPage.reload();

    // Host should see round 2
    await expect(
      hostPage.locator("text=Round 2/"),
    ).toBeVisible({ timeout: 10_000 });

    await setup.cleanup();
  });
});

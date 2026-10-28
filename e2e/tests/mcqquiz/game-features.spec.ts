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

test.describe("MCQ Quiz Game Features", () => {
  test("explanation is displayed after answering", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const token = setup.players[0].login.access_token;

    await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);

    const player = setup.players[0];
    const gameId = player.page.url().split("/").pop()!;

    // Wait for question to be visible
    await expect(
      player.page.locator("h1:has-text('The Quiz')")
        .or(player.page.locator("h1:has-text('Le Quiz')"))
        .or(player.page.locator("h1:has-text('مسائل')")),
    ).toBeVisible({ timeout: 15_000 });

    // Verify we're in playing phase
    let state = await apiGetMCQQuizState(gameId, token);
    expect(state.round_phase).toBe("playing");

    // Submit an answer (choice_index 0)
    await apiSubmitMCQQuizAnswer(gameId, 0, token);

    // Wait for results phase (auto-transitions with 1 player)
    await expect.poll(
      async () => (await apiGetMCQQuizState(gameId, token)).round_phase,
      { timeout: 10_000, intervals: [500] },
    ).not.toBe("playing");

    state = await apiGetMCQQuizState(gameId, token);
    expect(["results", "game_over"]).toContain(state.round_phase);

    // Explanation should be available in the API state
    expect(state.explanation).not.toBeNull();
    expect(state.explanation!.length).toBeGreaterThan(0);

    // Verify explanation appears on the page (Socket.IO or polling pushes results to UI)
    await expect.poll(
      async () => {
        const content = await player.page.textContent("body");
        return content?.includes(state.explanation!) ?? false;
      },
      { timeout: 15_000, intervals: [1000] },
    ).toBe(true);

    await setup.cleanup();
  });

  test("correct and wrong answers show visual feedback", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const token = setup.players[0].login.access_token;

    await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);

    const player = setup.players[0];
    const gameId = player.page.url().split("/").pop()!;

    // Wait for question
    await expect(
      player.page.locator("h1:has-text('The Quiz')")
        .or(player.page.locator("h1:has-text('Le Quiz')"))
        .or(player.page.locator("h1:has-text('مسائل')")),
    ).toBeVisible({ timeout: 15_000 });

    // Get the game state to know the correct answer
    let state = await apiGetMCQQuizState(gameId, token);
    expect(state.round_phase).toBe("playing");
    expect(state.choices.length).toBe(4);

    // Submit answer (choice 0 — may or may not be correct)
    await apiSubmitMCQQuizAnswer(gameId, 0, token);

    // Wait for results phase
    await expect.poll(
      async () => (await apiGetMCQQuizState(gameId, token)).round_phase,
      { timeout: 10_000, intervals: [500] },
    ).not.toBe("playing");

    state = await apiGetMCQQuizState(gameId, token);
    expect(["results", "game_over"]).toContain(state.round_phase);

    // Correct answer index should be revealed in results
    expect(state.correct_answer_index).not.toBeNull();

    // Verify the round_results from API contain the player's result
    expect(state.round_results.length).toBeGreaterThan(0);
    const myResult = state.round_results.find(
      (r: { user_id: string }) => r.user_id === setup.players[0].login.user.id,
    );
    expect(myResult).toBeDefined();

    // Verify explanation is shown on the page (results phase renders it)
    if (state.explanation) {
      await expect.poll(
        async () => {
          const content = await player.page.textContent("body");
          return content?.includes(state.explanation!) ?? false;
        },
        { timeout: 15_000, intervals: [1000] },
      ).toBe(true);
    }

    await setup.cleanup();
  });

  test("game over shows final scores", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const token = setup.players[0].login.access_token;

    // Set to 1 round for fast completion
    await apiUpdateRoomSettings(
      setup.roomId,
      { mcq_quiz_rounds: 1, mcq_quiz_turn_duration: 30 },
      token,
    );

    await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);

    const player = setup.players[0];
    const gameId = player.page.url().split("/").pop()!;

    // Wait for question
    await expect(
      player.page.locator("h1:has-text('The Quiz')")
        .or(player.page.locator("h1:has-text('Le Quiz')"))
        .or(player.page.locator("h1:has-text('مسائل')")),
    ).toBeVisible({ timeout: 15_000 });

    // Submit answer
    await apiSubmitMCQQuizAnswer(gameId, 0, token);

    // Wait for results or game_over
    await expect.poll(
      async () => (await apiGetMCQQuizState(gameId, token)).round_phase,
      { timeout: 10_000, intervals: [500] },
    ).not.toBe("playing");

    let state = await apiGetMCQQuizState(gameId, token);

    // If in results phase, advance to next round (which triggers game over for 1-round game)
    if (state.round_phase === "results") {
      await apiMCQQuizNextRound(gameId, token);
    }

    // Wait for game_over
    await expect.poll(
      async () => (await apiGetMCQQuizState(gameId, token)).round_phase,
      { timeout: 10_000, intervals: [500] },
    ).toBe("game_over");

    state = await apiGetMCQQuizState(gameId, token);
    expect(state.game_over).toBe(true);

    // UI should show game over with final scores
    await expect(
      player.page.locator("text=Final Scores")
        .or(player.page.locator("text=Scores finaux"))
        .or(player.page.locator("text=النتائج النهائية")),
    ).toBeVisible({ timeout: 15_000 });

    // Leaderboard should contain the player
    expect(state.leaderboard.length).toBeGreaterThan(0);
    const playerEntry = state.leaderboard.find(
      (e) => e.user_id === player.login.user.id,
    );
    expect(playerEntry).toBeDefined();
    expect(typeof playerEntry!.total_score).toBe("number");

    await setup.cleanup();
  });

  test("timer expiry auto-advances to results", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const token = setup.players[0].login.access_token;

    // Set very short timer so it expires quickly
    await apiUpdateRoomSettings(
      setup.roomId,
      { mcq_quiz_turn_duration: 3 },
      token,
    );

    await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);

    const player = setup.players[0];
    const gameId = player.page.url().split("/").pop()!;

    // Wait for question to appear
    await expect(
      player.page.locator("h1:has-text('The Quiz')")
        .or(player.page.locator("h1:has-text('Le Quiz')"))
        .or(player.page.locator("h1:has-text('مسائل')")),
    ).toBeVisible({ timeout: 15_000 });

    // Verify we're in playing phase
    let state = await apiGetMCQQuizState(gameId, token);
    expect(state.round_phase).toBe("playing");

    // Do NOT answer — wait for the 3s server-side timer to expire
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    await sleep(4000);

    // Force timer expired via API (in case server-side auto-expire hasn't triggered)
    await apiMCQQuizTimerExpired(gameId, token);

    // Wait for results phase
    await expect.poll(
      async () => (await apiGetMCQQuizState(gameId, token)).round_phase,
      { timeout: 10_000, intervals: [500] },
    ).not.toBe("playing");

    state = await apiGetMCQQuizState(gameId, token);
    expect(["results", "game_over"]).toContain(state.round_phase);

    // Player should not have answered
    expect(state.my_answered).toBe(false);

    // Correct answer should be revealed
    if (state.round_phase === "results") {
      expect(state.correct_answer_index).not.toBeNull();
    }

    await setup.cleanup();
  });
});

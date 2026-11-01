import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI } from "../../helpers/ui-game-setup";
import { apiGetWordQuizState, apiUpdateRoomSettings } from "../../helpers/api-client";
import { dbWordQuizCurrentWord } from "../../helpers/db";

test.describe("Word Quiz Single Player", () => {
  test("1-player game starts and plays", async ({ browser }) => {
    // Word Quiz supports 1 player (min_players = 1)
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    const page = setup.players[0].page;

    await expect(page.locator("h1:has-text('Kalimat')")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("text=Round 1 of")).toBeVisible({ timeout: 5_000 });
    await expect(
      page.getByRole("list", { name: "Hints, from the vaguest to the most specific" }).locator('li[aria-current="step"]'),
    ).toContainText("Hint 1 of", { timeout: 5_000 });
    await expect(page.getByRole("textbox", { name: "Your answer" })).toBeVisible({ timeout: 5_000 });

    await setup.cleanup();
  });

  test("a solo game played to its end shows the player's score, never a win", async ({ browser }) => {
    // Prepare — three rounds, each answered in the page (a solo round ends on its answer)
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const player = setup.players[0];
    const token = player.login.access_token;
    await apiUpdateRoomSettings(setup.roomId, { word_quiz_rounds: 3, word_quiz_turn_duration: 300, word_quiz_hint_interval: 120 }, token);
    const gameId = await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    const page = player.page;

    // Act — find each word, then move on ("Next round", "See the results" after the last)
    for (let round = 1; round <= 3; round++) {
      await expect(page.locator(`text=Round ${round} of 3`)).toBeVisible({ timeout: 15_000 });
      await page.getByRole("textbox", { name: "Your answer" }).fill(dbWordQuizCurrentWord(gameId));
      await page.getByRole("button", { name: "Answer", exact: true }).click();
      await expect(page.getByText("The answer was")).toBeVisible({ timeout: 15_000 });
      await page.getByRole("button", { name: round < 3 ? "Next round" : "See the results" }).click();
    }

    // Assert — the end: 18 points (6 a round, every word found at hint 1), said as a score
    await expect(page.locator('h2:has-text("Game Over")')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Final scores")).toBeVisible();
    await expect(page.getByText("You finished with 18 points.")).toBeVisible();
    await expect(page.getByText(/ wins\.| share the win\./)).toHaveCount(0);
    const state = await apiGetWordQuizState(gameId, token);
    expect(state.game_over).toBe(true);
    expect(state.leaderboard.map((e) => e.total_score)).toEqual([18]);
    expect(state.winner).toBeNull();

    await setup.cleanup();
  });
});

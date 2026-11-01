import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI, gameIdFromUrl } from "../../helpers/ui-game-setup";
import { apiGetWordQuizState, apiSubmitWordQuizAnswer, apiUpdateRoomSettings } from "../../helpers/api-client";
import { dbWordQuizCurrentWord } from "../../helpers/db";

/**
 * Kalimat through the page. The round's word is read from the game's live_state in the
 * E2E database (the API never sends it while the round is open). Round lengths have a
 * floor of 10 s (MIN_QUIZ_TURN_SECONDS: a 1 s round expired the moment it opened), so
 * a round is closed by its answers, or by its clock as every page reports it; the specs
 * poll the server, never sleep a fixed time (a guest's report comes 1–2 s late).
 */

/** The shortest round the server allows. */
const SHORTEST_ROUND_SECONDS = 10;

const answerField = (page: Page) => page.getByRole("textbox", { name: "Your answer" });

/**
 * Type the round's word in the page and send it: the page says "You found it", or, when
 * this answer was the last one the round waited for, goes straight to its results.
 */
async function answerInPage(page: Page, gameId: string): Promise<void> {
  await answerField(page).fill(dbWordQuizCurrentWord(gameId));
  await page.getByRole("button", { name: "Answer", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "You found it" }).or(page.getByText("The answer was"))).toBeVisible({
    timeout: 10_000,
  });
}

test.describe("Word Quiz Game Flow", () => {
  test("game starts and shows hints", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);

    for (const player of setup.players) {
      await expect(player.page.locator("h1:has-text('Kalimat')")).toBeVisible({ timeout: 15_000 });
      await expect(player.page.locator("text=Round 1 of")).toBeVisible({ timeout: 5_000 });
      await expect(
        player.page.getByRole("list", { name: "Hints, from the vaguest to the most specific" }).locator('li[aria-current="step"]'),
      ).toContainText("Hint 1 of", { timeout: 5_000 });
    }

    await setup.cleanup();
  });

  test("the right answer typed in the page is found, at full worth", async ({ browser }) => {
    // Prepare — the ladder stands on its first rung for the whole test
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const [host, other] = setup.players;
    await apiUpdateRoomSettings(setup.roomId, { word_quiz_turn_duration: 300, word_quiz_hint_interval: 120 }, host.login.access_token);
    const gameId = await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    await expect(host.page.getByText("Worth 6 points now")).toBeVisible({ timeout: 15_000 });

    // Act
    await answerInPage(host.page, gameId);

    // Assert — found at hint 1: 6 points, and the server agrees; the round waits for the other
    await expect(host.page.getByRole("status").filter({ hasText: "You found it" })).toContainText("+6");
    // ...the finder's page stops pricing the word (review F5), the other's still does
    await expect(host.page.getByText(/^Worth \d+ points? now$/)).toHaveCount(0);
    await expect(other.page.getByText("Worth 6 points now")).toBeVisible();
    const state = await apiGetWordQuizState(gameId, host.login.access_token);
    expect(state.my_answered).toBe(true);
    expect(state.round_phase).toBe("playing");
    const theOther = await apiGetWordQuizState(gameId, other.login.access_token);
    expect(theOther.my_answered).toBe(false);

    await setup.cleanup();
  });

  test("a wrong answer is said in the field and costs a try", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const gameId = await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    const hostToken = setup.players[0].login.access_token;

    const result = await apiSubmitWordQuizAnswer(gameId, "definitely_wrong_answer_xyz", hostToken);

    expect(result.correct).toBe(false);
    expect(result.points_earned).toBe(0);
    const state = await apiGetWordQuizState(gameId, hostToken);
    expect(state.my_answered).toBe(false);
    expect(state.my_attempts_left).toBe(state.max_attempts - 1);

    await setup.cleanup();
  });

  test("a round nobody answers is closed by its clock", async ({ browser }) => {
    // Prepare — the shortest round, and nobody answers
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const hostToken = setup.players[0].login.access_token;
    await apiUpdateRoomSettings(setup.roomId, { word_quiz_turn_duration: SHORTEST_ROUND_SECONDS }, hostToken);
    const gameId = await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    expect((await apiGetWordQuizState(gameId, hostToken)).round_phase).toBe("playing");

    // Assert — the pages report the clock themselves (the host at once, the other 1–2 s
    // later): the server moves to the results, and both pages show the answer
    await expect
      .poll(async () => (await apiGetWordQuizState(gameId, hostToken)).round_phase, {
        timeout: (SHORTEST_ROUND_SECONDS + 15) * 1000,
        intervals: [500],
      })
      .toBe("results");
    for (const player of setup.players) {
      await expect(player.page.getByText("The answer was")).toBeVisible({ timeout: 15_000 });
    }

    await setup.cleanup();
  });

  test("the host's Next round opens round 2 on every page", async ({ browser }) => {
    // Prepare — both players find the word: the round goes to its results at once
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const host = setup.players[0];
    const gameId = await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    expect(gameIdFromUrl(host.page, "wordquiz")).toBe(gameId);
    for (const player of setup.players) await answerInPage(player.page, gameId);
    await expect.poll(async () => (await apiGetWordQuizState(gameId, host.login.access_token)).round_phase).toBe("results");

    // Act — the host moves the table on, from the page
    await expect(host.page.getByText("The answer was")).toBeVisible({ timeout: 15_000 });
    await host.page.getByRole("button", { name: "Next round" }).click();

    // Assert — round 2, on every page, pushed (no reload)
    for (const player of setup.players) {
      await expect(player.page.locator("text=Round 2 of")).toBeVisible({ timeout: 15_000 });
      await expect(answerField(player.page)).toBeEnabled();
    }
    expect((await apiGetWordQuizState(gameId, host.login.access_token)).current_round).toBe(2);

    await setup.cleanup();
  });
});

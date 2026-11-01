import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI } from "../../helpers/ui-game-setup";
import { apiGetMCQQuizState, apiMCQQuizNextRound, apiSubmitMCQQuizAnswer, apiUpdateRoomSettings } from "../../helpers/api-client";
import { dbMcqCorrectIndex, dbRiddleWord } from "../../helpers/db";
import { animationsSeen, drawnOpacities, expectTextFromFirstFrame, settleAnimations, watchFrames } from "../../helpers/motion";

/**
 * The Quiz's reveal is woven: each choice draws its tally thread ("quiz-tally"), the right
 * letter is pressed ("seal-press"), then the scoreboard's rows travel to their new order,
 * their threads grow and each gain ("+3") fades in. Under reduced motion it is fades. The
 * counts ("1 player", "+3 · you") and the new totals are in the DOM from the first frame of
 * the reveal either way, and nothing is left at opacity 0 once it is over.
 *
 * Between two questions the table waits, so each player is asked a samar riddle ("The
 * answer in a moment, or after the next question."), answered at the next question's
 * results ("The last riddle, “…”, was X.").
 */

const RIDDLE = "A riddle while you wait";

async function waitForResults(gameId: string, token: string, round: number): Promise<void> {
  await expect
    .poll(async () => {
      const state = await apiGetMCQQuizState(gameId, token);
      return `${state.current_round}:${state.round_phase}`;
    }, { timeout: 15_000 })
    .toBe(`${round}:results`);
}

async function quizRiddle(page: Page, roomId: string, gameId: string): Promise<{ id: string; hint: string }> {
  const key = `majlisna-riddle:${roomId}:game:${gameId}`;
  await expect
    .poll(async () => page.evaluate((k) => JSON.parse(sessionStorage.getItem(k) ?? "null")?.current?.riddle?.id ?? null, key), { timeout: 15_000 })
    .not.toBeNull();
  return page.evaluate((k) => JSON.parse(sessionStorage.getItem(k)!).current.riddle, key);
}

test.describe("The Quiz — the reveal says it all at once", () => {
  test("the tallies and the new scores are there from the reveal's first frame, with or without motion", async ({ browser }) => {
    // Prepare — two players over two questions: one will be right (motion), one wrong (reduced motion)
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const [right, wrong] = setup.players;
    const hostToken = right.login.access_token;
    await apiUpdateRoomSettings(setup.roomId, { mcq_quiz_rounds: 2, mcq_quiz_turn_duration: 600 }, hostToken);
    const gameId = await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);
    await wrong.page.emulateMedia({ reducedMotion: "reduce" });
    const correct = dbMcqCorrectIndex(gameId);

    const choices = "ul.quiz-choices";
    const scores = '[data-testid="quiz-scoreboard"]:has(.score-gain)';
    const watches = {
      rightChoices: await watchFrames(right.page, choices),
      wrongChoices: await watchFrames(wrong.page, choices),
      rightScores: await watchFrames(right.page, scores, { durationMs: 2_000 }),
      wrongScores: await watchFrames(wrong.page, scores, { durationMs: 2_000 }),
    };

    // Act — both lock in, the right answer and a wrong one: the question resolves
    const { points_earned: points } = await apiSubmitMCQQuizAnswer(gameId, correct, right.login.access_token);
    await apiSubmitMCQQuizAnswer(gameId, (correct + 1) % 4, wrong.login.access_token);
    expect(points).toBeGreaterThan(0);

    // Assert — the tallies: each page reads its own choice and the other's from the first frame
    const rightChoices = await watches.rightChoices.frames();
    const wrongChoices = await watches.wrongChoices.frames();
    expectTextFromFirstFrame(rightChoices, [`+${points} · you`, "1 player"], "tallies (motion)");
    expectTextFromFirstFrame(wrongChoices, ["you", "1 player"], "tallies (reduced motion)");
    expect(animationsSeen(rightChoices)).toEqual(expect.arrayContaining(["quiz-tally", "seal-press"]));
    await expect(right.page.locator(choices)).toHaveAttribute("data-weave", "true");

    // ...and the scoreboard: the new total and the gain, from the first frame on both pages
    const rightScores = await watches.rightScores.frames();
    const wrongScores = await watches.wrongScores.frames();
    const gain = `${right.login.user.username}`;
    for (const [frames, what] of [
      [rightScores, "scoreboard (motion)"],
      [wrongScores, "scoreboard (reduced motion)"],
    ] as const) {
      expectTextFromFirstFrame(frames, [gain, `${points}+${points}`, wrong.login.user.username], what);
    }
    expect(animationsSeen(rightScores).length, "the scoreboard did not weave").toBeGreaterThan(0);

    // ...with nothing left hidden once the weave is over
    for (const page of [right.page, wrong.page]) {
      await settleAnimations(page);
      const parts = await drawnOpacities(page, '[data-testid="quiz-scoreboard"] .score-gain, ul.quiz-choices .choice-letter, ul.quiz-choices .choice-tag');
      expect(parts.length).toBeGreaterThanOrEqual(9);
      for (const part of parts) expect(part.opacity, `"${part.text}" drawn at ${part.opacity}`).toBe(1);
    }

    // The table waits for the next question: a riddle for each player, answer after it
    await waitForResults(gameId, hostToken, 1);
    const riddle = wrong.page.getByRole("region", { name: RIDDLE });
    await expect(riddle).toContainText("The answer in a moment, or after the next question.", { timeout: 15_000 });
    const asked = await quizRiddle(wrong.page, setup.roomId, gameId);
    const word = dbRiddleWord(asked.id);
    expect(asked.hint).toBe(word.hint1_en);
    await expect(riddle).toContainText(word.hint1_en);

    // Act — the next question, answered by both
    await apiMCQQuizNextRound(gameId, hostToken);
    await expect.poll(async () => (await apiGetMCQQuizState(gameId, hostToken)).current_round, { timeout: 15_000 }).toBe(2);
    await expect(wrong.page.getByRole("region", { name: RIDDLE })).toHaveCount(0, { timeout: 15_000 });
    const second = dbMcqCorrectIndex(gameId);
    await apiSubmitMCQQuizAnswer(gameId, second, right.login.access_token);
    await apiSubmitMCQQuizAnswer(gameId, second, wrong.login.access_token);
    await waitForResults(gameId, hostToken, 2);

    // Assert — the last question's results answer the riddle of the one before, and ask none
    await expect(riddle).toContainText(`The last riddle, “${word.hint1_en}”, was ${word.word_en}.`, { timeout: 15_000 });
    await expect(riddle).not.toContainText("The answer in a moment");

    await setup.cleanup();
  });
});

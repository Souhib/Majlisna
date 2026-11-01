import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI } from "../../helpers/ui-game-setup";
import { apiGetWordQuizState, apiUpdateRoomSettings, expectApiError, rawPost } from "../../helpers/api-client";
import { dbWordQuizCurrentWord } from "../../helpers/db";

/**
 * Kalimat's tries (owner rule (e)): a wrong try costs one rung on the answer that finds
 * the word, and a round allows five tries. The field counts them down ("5 tries left" …
 * "1 try left"), closes after the fifth miss with "You have used your 5 tries for this
 * round.", and a sixth try forced through the API is refused with that very key.
 *
 * Two players, so the round stays open while one of them is out of tries; the ladder
 * stands on its first rung for the whole test (a 120 s hint interval), so every point
 * lost is a try's.
 */

const triesLine = (page: Page) => page.getByText(/^(\d+ (tries|try) left|No tries left)$/);

/** "Worth 6 points now": what the word would pay this player if found now. */
const worthLine = (page: Page) => page.getByText(/^Worth \d+ points? now$/);

/** Type a wrong answer in the page and wait until the field has said it. */
async function missOnce(page: Page, guess: string): Promise<void> {
  await page.getByRole("textbox", { name: "Your answer" }).fill(guess);
  await page.getByRole("button", { name: "Answer", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: guess }).or(page.getByRole("alert").filter({ hasText: "You have used your 5 tries" }))).toBeVisible({
    timeout: 10_000,
  });
}

test.describe("Kalimat — tries", () => {
  test("tries count down, the field closes after the fifth miss, and a sixth is refused", async ({ browser }) => {
    // Prepare
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const [host, other] = setup.players;
    await apiUpdateRoomSettings(setup.roomId, { word_quiz_turn_duration: 300, word_quiz_hint_interval: 120 }, host.login.access_token);
    const gameId = await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    const page = other.page;
    const field = page.getByRole("textbox", { name: "Your answer" });
    await expect(triesLine(page)).toHaveText("5 tries left", { timeout: 15_000 });
    await expect(page.getByText("Worth 6 points now")).toBeVisible();
    // the count is read with the field
    const triesId = await triesLine(page).getAttribute("id");
    expect(await field.getAttribute("aria-describedby")).toContain(triesId!);

    // Act + Assert — four misses: one try and one point fewer each time, the field open
    const counts = ["4 tries left", "3 tries left", "2 tries left", "1 try left"];
    for (let miss = 1; miss <= 4; miss++) {
      await missOnce(page, `wrong${miss}`);
      await expect(triesLine(page)).toHaveText(counts[miss - 1]);
      await expect(page.getByText(`Worth ${6 - miss} point${6 - miss === 1 ? "" : "s"} now`)).toBeVisible();
      await expect(field).toBeEnabled();
    }
    const four = await apiGetWordQuizState(gameId, other.login.access_token);
    expect(four.my_attempts_left).toBe(1);
    expect(four.my_rungs_lost).toBe(4);

    // The fifth miss closes the field: it says the tries are used, and focus goes there
    await missOnce(page, "wrong5");
    await expect(page.getByRole("alert").filter({ hasText: "You have used your 5 tries for this round." })).toBeVisible();
    await expect(triesLine(page)).toHaveText("No tries left");
    await expect(triesLine(page)).toBeFocused();
    await expect(field).toBeDisabled();
    await expect(page.getByRole("button", { name: "Answer", exact: true })).toBeDisabled();
    // ...and the page no longer prices the word: nothing is left for this player to earn
    // this round (review F5: it still said "Worth 1 point now")
    await expect(worthLine(page)).toHaveCount(0);
    await expect(worthLine(host.page)).toHaveText("Worth 6 points now");

    // A sixth try, forced past the closed field, is refused by name and changes nothing
    const sixth = await rawPost(`/api/v1/wordquiz/games/${gameId}/answer`, { answer: dbWordQuizCurrentWord(gameId) }, other.login.access_token);
    const refused = await expectApiError(sixth, 409, "errors.api.answerAttemptsExhausted");
    expect(refused.message).toBeTruthy();
    const out = await apiGetWordQuizState(gameId, other.login.access_token);
    expect(out.my_attempts_left).toBe(0);
    expect(out.my_answered).toBe(false);
    // ...and the round is still open: the host has not found the word yet
    expect(out.round_phase).toBe("playing");

    // The host misses twice, then finds it: 6 at hint 1, less the two rungs lost
    const hostPage = host.page;
    await missOnce(hostPage, "nope1");
    await missOnce(hostPage, "nope2");
    await expect(hostPage.getByText("Worth 4 points now")).toBeVisible();
    await hostPage.getByRole("textbox", { name: "Your answer" }).fill(dbWordQuizCurrentWord(gameId));
    await hostPage.getByRole("button", { name: "Answer", exact: true }).click();
    // Everyone is done (one found it, one is out of tries): the round goes to its results
    // at once, with the host's 4 points
    await expect.poll(async () => (await apiGetWordQuizState(gameId, host.login.access_token)).round_phase).toBe("results");
    const results = await apiGetWordQuizState(gameId, host.login.access_token);
    const hostRow = results.round_results.find((r) => r.user_id === host.login.user.id)!;
    expect(hostRow.points).toBe(4);
    expect(hostRow.answered_at_hint).toBe(1);
    const otherRow = results.round_results.find((r) => r.user_id === other.login.user.id)!;
    expect(otherRow.points).toBe(0);
    expect(otherRow.attempts).toBe(5);
    for (const player of setup.players) {
      await expect(player.page.getByText("The answer was")).toBeVisible({ timeout: 15_000 });
    }

    await setup.cleanup();
  });
});

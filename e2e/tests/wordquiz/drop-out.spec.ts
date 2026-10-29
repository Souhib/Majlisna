import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI } from "../../helpers/ui-game-setup";
import { apiGetWordQuizState, apiKickPlayer, apiUpdateRoomSettings } from "../../helpers/api-client";
import { dbWordQuizCurrentWord } from "../../helpers/db";

/**
 * Kalimat: a player removed mid-round. The round resolves when everyone left has found
 * the word, so when the host kicks the one player still looking, it resolves at once
 * instead of running out its clock (backend `quiz_rules.settle_round_if_everyone_answered`).
 * In Kalimat only the answer that FOUND the word counts as answered: a wrong try does
 * not, so the round stays open while anyone is still looking.
 *
 * The round's word is read from the game's `live_state` in the E2E database: the API
 * never sends it while the round is open.
 */

const LONG_CLOCK_SECONDS = 300;

test.describe("Kalimat — a player is removed mid-round", () => {
  test("when everyone left has found the word, the round resolves at once", async ({ browser }) => {
    // Prepare — two players, a five-minute round
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const [host, other] = setup.players;
    const hostToken = host.login.access_token;
    await apiUpdateRoomSettings(setup.roomId, { word_quiz_turn_duration: LONG_CLOCK_SECONDS }, hostToken);
    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    const gameId = host.page.url().match(/\/game\/wordquiz\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();
    const page = host.page;
    const field = page.getByRole("textbox", { name: "Your answer" });
    await expect(field).toBeVisible({ timeout: 15_000 });

    // The host finds the word on the page; the other player is still looking
    await field.fill(dbWordQuizCurrentWord(gameId!));
    await page.getByRole("button", { name: "Answer", exact: true }).click();
    await expect(page.getByText("The round ends when everyone has found it, or when time runs out.")).toBeVisible({
      timeout: 10_000,
    });
    expect((await apiGetWordQuizState(gameId!, hostToken)).round_phase).toBe("playing");

    // Act — the host kicks the player still looking
    const kickedAt = Date.now();
    await apiKickPlayer(setup.roomId, other.login.user.id, hostToken);

    // Assert — the round is resolved without them, long before its clock runs out
    await expect
      .poll(async () => (await apiGetWordQuizState(gameId!, hostToken)).round_phase, { timeout: 10_000, intervals: [250] })
      .toBe("results");
    const resolved = await apiGetWordQuizState(gameId!, hostToken);
    expect(resolved.players.map((p) => p.user_id)).toEqual([host.login.user.id]);

    // ...and the host's page shows the round's results, pushed by the server
    await expect(page.getByText("The answer was")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("textbox", { name: "Your answer" })).toHaveCount(0);
    expect(Date.now() - kickedAt).toBeLessThan((LONG_CLOCK_SECONDS / 5) * 1000);

    await setup.cleanup();
  });
});

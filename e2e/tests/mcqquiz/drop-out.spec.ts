import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI } from "../../helpers/ui-game-setup";
import {
  apiGetMCQQuizState,
  apiLeaveRoom,
  apiSubmitMCQQuizAnswer,
  apiUpdateRoomSettings,
} from "../../helpers/api-client";

/**
 * A player who leaves mid-question. The question resolves when everyone has answered;
 * if the one who leaves was the last to answer, the others have all answered already,
 * so the question resolves at once instead of waiting for the bell
 * (backend `quiz_rules.settle_round_if_everyone_answered`, run by the leave, the kick
 * and the disconnect sweep alike). The clock here is five minutes long, so a result
 * that arrives in seconds can only come from the departure.
 */

const LONG_CLOCK_SECONDS = 300;

test.describe("The Quiz — a player leaves mid-question", () => {
  test("when everyone left has answered, the question resolves at once", async ({ browser }) => {
    // Prepare — two players, a five-minute clock; the host locks in, the other has not answered
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const [host, leaver] = setup.players;
    const hostToken = host.login.access_token;
    await apiUpdateRoomSettings(setup.roomId, { mcq_quiz_turn_duration: LONG_CLOCK_SECONDS }, hostToken);
    await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);
    const gameId = host.page.url().match(/\/game\/mcqquiz\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();
    await expect(host.page.getByText(/Question 1 of \d+/)).toBeVisible({ timeout: 15_000 });

    await apiSubmitMCQQuizAnswer(gameId!, 0, hostToken);
    const waiting = await apiGetMCQQuizState(gameId!, hostToken);
    expect(waiting.round_phase).toBe("playing");
    expect(waiting.my_answered).toBe(true);
    await expect(host.page.getByTestId("mcq-round-results")).toHaveCount(0);

    // Act — the player who had not answered leaves the room
    const leftAt = Date.now();
    await apiLeaveRoom(setup.roomId, leaver.login.user.id, leaver.login.access_token);

    // Assert — the question is resolved, without the leaver, long before the bell
    await expect
      .poll(async () => (await apiGetMCQQuizState(gameId!, hostToken)).round_phase, { timeout: 10_000, intervals: [250] })
      .toBe("results");
    const resolved = await apiGetMCQQuizState(gameId!, hostToken);
    expect(resolved.players.map((p) => p.user_id)).toEqual([host.login.user.id]);
    expect(resolved.correct_answer_index).not.toBeNull();

    // ...and the host's page shows it, pushed by the server: the results and "Next question"
    const results = host.page.getByTestId("mcq-round-results");
    await expect(results).toBeVisible({ timeout: 15_000 });
    await expect(results.getByRole("listitem")).toHaveCount(1);
    await expect(results).toContainText(host.login.user.username);
    await expect(host.page.getByRole("button", { name: "Next question" })).toBeVisible();
    expect(Date.now() - leftAt).toBeLessThan((LONG_CLOCK_SECONDS / 5) * 1000);

    await setup.cleanup();
  });
});

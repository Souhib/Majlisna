import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI } from "../../helpers/ui-game-setup";
import { apiUpdateRoomSettings } from "../../helpers/api-client";

/**
 * Focus follows the phase (WP-13, F2). A keyboard-only round of The Quiz: the player
 * picks a choice with Space and locks it in with Enter; the reveal replaces the button
 * that held focus, and focus goes to the reveal's first heading instead of falling to
 * <body> (where the next Tab restarted at the skip link). "Next question" then puts it
 * on the new question. Ported from the animations audit's p12b-focus-mcq probe.
 */

/** What holds focus: its tag and its text. */
const focused = (page: Page) =>
  page.evaluate(() => {
    const el = document.activeElement;
    return { tag: el?.tagName ?? "", text: (el?.textContent ?? "").trim(), inMain: !!el?.closest("main") };
  });

test.describe("Accessibility — focus follows the phase", () => {
  test("a keyboard-only Quiz round: the reveal, then the next question, take focus", async ({ browser }) => {
    // Prepare — a solo Quiz of two questions (a solo question is revealed on its answer)
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    await apiUpdateRoomSettings(setup.roomId, { mcq_quiz_rounds: 2, mcq_quiz_turn_duration: 30 }, setup.players[0].login.access_token);
    await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);
    const page = setup.players[0].page;
    const choices = page.getByRole("radio");
    await expect(choices).toHaveCount(4, { timeout: 15_000 });

    // Act — the keyboard only: a choice with Space, then Lock in with Enter
    await choices.nth(1).focus();
    await page.keyboard.press("Space");
    await expect(choices.nth(1)).toBeChecked();
    const lockIn = page.getByRole("button", { name: "Lock in" });
    await lockIn.focus();
    await page.keyboard.press("Enter");

    // Assert — the reveal is on screen, and focus is on its first heading (never <body>)
    const next = page.getByRole("button", { name: "Next question" });
    await expect(next).toBeVisible({ timeout: 15_000 });
    await expect.poll(async () => (await focused(page)).tag, { timeout: 5_000 }).toBe("H3");
    const onReveal = await focused(page);
    expect(onReveal.inMain).toBe(true);
    expect(["Explanation", "This question"]).toContain(onReveal.text);

    // Act — on to the next question, still by keyboard
    await next.focus();
    await page.keyboard.press("Enter");

    // Assert — the new question takes focus
    await expect(page.getByText("Question 2 of 2")).toBeVisible({ timeout: 15_000 });
    await expect.poll(async () => (await focused(page)).tag, { timeout: 5_000 }).toBe("H2");
    const question = await page.locator("h2.quiz-question").textContent();
    expect((await focused(page)).text).toBe((question ?? "").trim());

    await setup.cleanup();
  });
});

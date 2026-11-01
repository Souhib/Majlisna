import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI, findSpymaster, findOperative } from "../../helpers/ui-game-setup";
import { apiGetCodenamesBoard, apiGiveClue } from "../../helpers/api-client";
import { animationsSeen, drawnOpacities, expectTextFromFirstFrame, settleAnimations, watchFrames } from "../../helpers/motion";

/**
 * A clue lands in Codenames: the spymaster's pen writes the word in from the reading
 * start ("clue-ink") and its count is stamped ("clue-stamp"). Under reduced motion the
 * line only fades. Either way the word and the count are in the DOM from the first frame
 * the clue is drawn in (the pen moves a window over text that is already there), and the
 * ClueAnnouncer says it to screen readers at once.
 */

test.describe("Codenames — the clue says it all at once", () => {
  test("the clue's word and count are there from its first frame, with or without motion", async ({ browser }) => {
    // Prepare — the playing team's operative (motion) and the other team's operative (reduced motion)
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    const gameId = await startGameViaAPI(setup.players, "codenames", setup.roomId);
    const board = await apiGetCodenamesBoard(gameId, setup.players[0].login.access_token);
    const team = board.current_team;
    const spymaster = await findSpymaster(setup.players, gameId, team);
    const moving = await findOperative(setup.players, gameId, team);
    const still = await findOperative(setup.players, gameId, team === "red" ? "blue" : "red");
    await still.page.emulateMedia({ reducedMotion: "reduce" });
    for (const page of [moving.page, still.page]) {
      await expect(page.locator('.cn-clue[data-waiting="true"]')).toBeVisible({ timeout: 15_000 });
    }

    const landed = ".cn-clue:not([data-waiting])";
    const watchMoving = await watchFrames(moving.page, landed, { durationMs: 1_800 });
    const watchStill = await watchFrames(still.page, landed);

    // Act — the spymaster gives a clue for two cards
    await apiGiveClue(gameId, "testclue", 2, spymaster.login.access_token);

    // Assert — the word and the count, from the first frame, on both pages
    const final = [/testclue/i, "2"];
    const framesMoving = await watchMoving.frames();
    const framesStill = await watchStill.frames();
    expectTextFromFirstFrame(framesMoving, final, "clue (motion)");
    expectTextFromFirstFrame(framesStill, final, "clue (reduced motion)");
    expect(animationsSeen(framesMoving)).toEqual(expect.arrayContaining(["clue-ink", "clue-stamp"]));
    expect(animationsSeen(framesStill)).toContain("clue-ink");
    expect(animationsSeen(framesStill)).not.toContain("clue-stamp");

    // ...said at once to screen readers, and left fully drawn
    for (const page of [moving.page, still.page]) {
      await expect(page.getByRole("status").filter({ hasText: /testclue/i })).toBeAttached();
      await settleAnimations(page);
      const drawn = await drawnOpacities(page, `${landed} .cn-clue-ink, ${landed} .cn-clue-n`);
      expect(drawn.length).toBe(2);
      for (const part of drawn) expect(part.opacity, `"${part.text}" drawn at ${part.opacity}`).toBe(1);
    }

    await setup.cleanup();
  });
});

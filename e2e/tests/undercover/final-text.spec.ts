import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaAPI,
  undercoverRoles,
  voteOutViaAPI,
} from "../../helpers/ui-game-setup";
import { apiGetUndercoverState, apiLeaveRoom } from "../../helpers/api-client";
import { animationsSeen, drawnOpacities, expectTextFromFirstFrame, settleAnimations, watchFrames } from "../../helpers/motion";

/**
 * Undercover's two authored moments say everything from their first frame (DESIGN.md §7):
 *
 * - the verdict ("The table chose Bilal."): the tablet turns over (the cover parts, the
 *   role's lozenge is pressed), but the heading, the name and the role are in the DOM from
 *   the frame the verdict is first drawn in; under reduced motion the cover only fades;
 * - a seat that empties on screen (a player leaving mid-round) recedes ("seat-erase"), and
 *   its "Eliminated" line is there from the first frame the seat is out.
 *
 * Each is watched on two seats at once: one with motion, one with reduced motion
 * (`emulateMedia`), and both must read the same text at once and nothing at 0 once done.
 */

test.describe("Undercover — animated screens say it all at once", () => {
  test("the verdict's heading, name and role are there from its first frame, with or without motion", async ({ browser }) => {
    // Prepare — four players (one Undercover, three Civilians): voting a Civilian out leaves the game open
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);
    const roles = await undercoverRoles(players, gameId);
    const [moving, still] = players;
    await still.page.emulateMedia({ reducedMotion: "reduce" });
    const target = players.slice(2).find((p) => roles.get(p.login.user.id) === "civilian")!;
    expect(target, "no Civilian among the last two seats").toBeTruthy();
    await submitDescriptionsForAllPlayersViaAPI(players);
    const state = await apiGetUndercoverState(gameId, moving.login.access_token);

    const overlay = '[data-testid="elimination-overlay"]';
    const watchMoving = await watchFrames(moving.page, overlay);
    const watchStill = await watchFrames(still.page, overlay);

    // Act — the table votes the Civilian out, while both pages show the vote
    await voteOutViaAPI(gameId, players, state, target.login.user.id);

    // Assert — the verdict, its name and its role, from the first frame on both pages
    const name = target.login.user.username;
    const final = [`The table chose ${name}.`, "Civilian"];
    const framesMoving = await watchMoving.frames();
    const framesStill = await watchStill.frames();
    expectTextFromFirstFrame(framesMoving, final, "verdict (motion)");
    expectTextFromFirstFrame(framesStill, final, "verdict (reduced motion)");

    // ...while the tablet turned over on one, and only faded on the other
    await expect(moving.page.locator(overlay)).toHaveAttribute("data-turn", "turn");
    await expect(still.page.locator(overlay)).toHaveAttribute("data-turn", "fade");
    expect(animationsSeen(framesMoving)).toEqual(expect.arrayContaining(["uc-cover-part", "seal-press"]));
    expect(animationsSeen(framesStill)).toContain("uc-cover-fade");

    // ...and once it is over, nothing it moved is left hidden
    for (const page of [moving.page, still.page]) {
      await settleAnimations(page);
      const drawn = await drawnOpacities(page, `${overlay} h2, ${overlay} .lawh-role, ${overlay} .lawh-top b`);
      expect(drawn.length).toBe(3);
      for (const part of drawn) expect(part.opacity, `"${part.text}" drawn at ${part.opacity}`).toBe(1);
      await expect(page.locator(overlay).getByRole("heading", { name: `The table chose ${name}.` })).toBeVisible();
    }

    await setup.cleanup();
  });

  test("a seat emptied mid-round reads Eliminated from its first frame out, with or without motion", async ({ browser }) => {
    // Prepare — four players at the describing table; a Civilian who is not the host will leave
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);
    const roles = await undercoverRoles(players, gameId);
    const [moving, still] = players;
    await still.page.emulateMedia({ reducedMotion: "reduce" });
    const leaver = players.slice(2).find((p) => roles.get(p.login.user.id) === "civilian")!;
    expect(leaver, "no Civilian among the last two seats").toBeTruthy();

    const list = moving.page.getByRole("list", { name: "Who said what, in speaking order" });
    const seat = `[data-seat="${leaver.login.user.id}"]`;
    await expect(list.locator(seat)).toBeVisible();
    await expect(still.page.locator(seat)).toBeVisible();
    await expect(list.locator(seat)).not.toHaveAttribute("data-out", "");
    const out = `${seat}[data-out]`;
    const watchMoving = await watchFrames(moving.page, out);
    const watchStill = await watchFrames(still.page, out);

    // Act — the Civilian leaves the room mid-round
    await apiLeaveRoom(setup.roomId, leaver.login.user.id, leaver.login.access_token);

    // Assert — from the first frame the seat is out, it says so, in its place
    const final = [leaver.login.user.username, "Eliminated"];
    const framesMoving = await watchMoving.frames();
    const framesStill = await watchStill.frames();
    expectTextFromFirstFrame(framesMoving, final, "emptied seat (motion)");
    expectTextFromFirstFrame(framesStill, final, "emptied seat (reduced motion)");
    expect(animationsSeen(framesMoving)).toContain("seat-erase");
    expect(animationsSeen(framesStill)).toContain("seat-erase");

    // ...and once receded: the line at full ink, the name at the muted level, never hidden
    for (const page of [moving.page, still.page]) {
      await settleAnimations(page);
      const [note] = await drawnOpacities(page, `${out} [data-erase="note"]`);
      const [name] = await drawnOpacities(page, `${out} [data-erase="ink"]`);
      expect(note.opacity).toBe(1);
      expect(name.opacity).toBeGreaterThanOrEqual(0.7);
      await expect(page.locator(out)).toContainText("Eliminated");
    }

    await setup.cleanup();
  });
});

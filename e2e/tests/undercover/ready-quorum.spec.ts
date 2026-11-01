import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaUI,
  undercoverRoles,
  voteOut,
  waitForEliminationOrGameOver,
  waitForDescribingEverywhere,
  type PlayerContext,
} from "../../helpers/ui-game-setup";
import { apiGetUndercoverState, apiLeaveRoom, apiUpdateRoomSettings } from "../../helpers/api-client";

/**
 * Between two Undercover rounds (owner rule (d)): the host has "Next round", which opens
 * it at once; every other living player has "I’m ready", and the round opens by itself
 * once every living player but the host is ready. Everyone, the eliminated included,
 * reads the count ("1 of 2 ready"). It used to be the host's call alone: a host who
 * stopped playing held the table between rounds indefinitely (BR-23).
 */

interface RoundOver {
  setup: Awaited<ReturnType<typeof setupRoomWithPlayers>>;
  gameId: string;
  host: PlayerContext;
  /** The living players who are not the host: the ones asked. */
  asked: PlayerContext[];
  eliminated: PlayerContext;
  /** Every player's role, from their own state. */
  roles: Map<string, string>;
}

/**
 * Round 1 votes out a civilian who is not the host (so the game goes on). Four players by
 * default; five with Mr. White off (one undercover, four civilians), so that a civilian
 * can still walk out after round 1 and leave a game nobody has won yet (three civilians
 * and the undercover, minus one civilian: two against one).
 */
async function firstRoundOver(browser: import("@playwright/test").Browser, count: 4 | 5 = 4): Promise<RoundOver> {
  const accounts = await generateTestAccounts(count);
  const setup = await setupRoomWithPlayers(browser, accounts);
  if (count === 5) await apiUpdateRoomSettings(setup.roomId, { enable_mr_white: false }, setup.players[0].login.access_token);
  const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
  const players = await dismissRoleRevealAll(setup.players);
  const roles = await undercoverRoles(players, gameId);
  const host = players[0];
  const eliminated = players.slice(1).find((p) => roles.get(p.login.user.id) === "civilian")!;

  await submitDescriptionsForAllPlayersViaUI(players);
  const state = await apiGetUndercoverState(gameId, host.login.access_token);
  const alive = state.players.filter((p) => p.is_alive);
  const target = alive.find((p) => p.user_id === eliminated.login.user.id)!;
  await voteOut(players, alive, target, alive.find((p) => p.user_id === host.login.user.id)!);
  expect((await waitForEliminationOrGameOver(host.page)).type).toBe("elimination");

  const asked = players.filter((p) => p !== host && p !== eliminated);
  return { setup, gameId, host, asked, eliminated, roles };
}

const readyCount = (page: Page) => page.getByRole("status").filter({ hasText: /^\d+ of \d+ ready$/ });
const imReady = (page: Page) => page.getByRole("button", { name: "I’m ready" });

test.describe("Undercover — the ready quorum between rounds", () => {
  test("every living player but the host marks ready, and round 2 opens without the host", async ({ browser }) => {
    test.setTimeout(120_000);
    const { setup, gameId, host, asked, eliminated } = await firstRoundOver(browser);
    expect(asked).toHaveLength(2);

    // Everyone reads the count; the host has "Next round", the asked "I’m ready",
    // the eliminated player neither
    for (const player of setup.players) {
      await expect(readyCount(player.page)).toHaveText("0 of 2 ready", { timeout: 15_000 });
    }
    await expect(host.page.getByRole("button", { name: "Next round" })).toBeVisible();
    await expect(imReady(host.page)).toHaveCount(0);
    for (const player of asked) await expect(imReady(player.page)).toBeVisible();
    await expect(imReady(eliminated.page)).toHaveCount(0);
    await expect(eliminated.page.getByRole("button", { name: "Next round" })).toHaveCount(0);
    // Nothing on this screen says "Waiting for" (the vote helpers read that as "voted")
    for (const player of setup.players) await expect(player.page.getByText(/Waiting for/)).toHaveCount(0);

    // Act — the first one is ready
    await imReady(asked[0].page).click();

    // Assert — said on their page (focus moves there), counted everywhere, nothing opens yet
    const youAreReady = asked[0].page.getByText("You are ready. The next round starts when everyone is, or when the host starts it.");
    await expect(youAreReady).toBeVisible({ timeout: 10_000 });
    await expect(imReady(asked[0].page)).toHaveCount(0);
    for (const player of setup.players) await expect(readyCount(player.page)).toHaveText("1 of 2 ready", { timeout: 15_000 });
    const waiting = await apiGetUndercoverState(gameId, host.login.access_token);
    expect(waiting.turn_number).toBe(1);
    expect(waiting.ready_players).toEqual([asked[0].login.user.id]);
    expect((await apiGetUndercoverState(gameId, asked[0].login.access_token)).is_ready).toBe(true);

    // Act — the second one is ready: the quorum is complete
    await imReady(asked[1].page).click();

    // Assert — round 2 opens on every page, the host having pressed nothing
    await waitForDescribingEverywhere(setup.players);
    const opened = await apiGetUndercoverState(gameId, host.login.access_token);
    expect(opened.turn_number).toBe(2);
    expect(opened.turn_phase).toBe("describing");
    expect(opened.ready_count).toBe(0);

    await setup.cleanup();
  });

  test("the host can still open the next round before everyone is ready", async ({ browser }) => {
    test.setTimeout(120_000);
    const { setup, gameId, host, asked } = await firstRoundOver(browser);

    // One of the two is ready
    await imReady(asked[0].page).click();
    await expect(readyCount(host.page)).toHaveText("1 of 2 ready", { timeout: 15_000 });

    // Act — the host forces it
    await host.page.getByRole("button", { name: "Next round" }).click();

    // Assert — round 2, for everyone
    await waitForDescribingEverywhere(setup.players);
    expect((await apiGetUndercoverState(gameId, host.login.access_token)).turn_number).toBe(2);

    await setup.cleanup();
  });

  /**
   * Five players, round 1 over: three are asked. Two mark ready, and the third — a
   * civilian, so the game goes on — walks out instead of answering. The players still in
   * the game are all ready: the round opens without the host.
   */
  async function twoReadyAndALeaver(browser: import("@playwright/test").Browser) {
    const round = await firstRoundOver(browser, 5);
    const { setup, asked, roles } = round;
    expect(asked).toHaveLength(3);
    const leaver = asked.find((p) => roles.get(p.login.user.id) === "civilian")!;
    const ready = asked.filter((p) => p !== leaver);
    for (const player of setup.players) await expect(readyCount(player.page)).toHaveText("0 of 3 ready", { timeout: 15_000 });
    for (const [i, player] of ready.entries()) {
      await imReady(player.page).click();
      for (const seat of setup.players) await expect(readyCount(seat.page)).toHaveText(`${i + 1} of 3 ready`, { timeout: 15_000 });
    }
    // the ones still at the table once the leaver is gone
    const staying = setup.players.filter((p) => p !== leaver);
    return { ...round, leaver, ready, staying };
  }

  test("a player who walks out instead of answering completes the quorum: the round opens", async ({ browser }) => {
    test.setTimeout(120_000);
    const { setup, gameId, host, leaver, staying } = await twoReadyAndALeaver(browser);
    expect((await apiGetUndercoverState(gameId, host.login.access_token)).turn_number).toBe(1);

    // Act — the last one asked leaves the room
    await apiLeaveRoom(setup.roomId, leaver.login.user.id, leaver.login.access_token);

    // Assert — round 2 opens on every page still at the table, the host having pressed
    // nothing, and the leaver is out of it
    await waitForDescribingEverywhere(staying);
    const opened = await apiGetUndercoverState(gameId, host.login.access_token);
    expect(opened.turn_number).toBe(2);
    expect(opened.turn_phase).toBe("describing");
    expect(opened.winner ?? null).toBeNull();
    expect(opened.players.find((p) => p.user_id === leaver.login.user.id)?.is_alive ?? false).toBe(false);
    expect((opened.description_order ?? []).map((d) => d.user_id)).not.toContain(leaver.login.user.id);

    await setup.cleanup();
  });

  test("a walk-out during the prayer pause that completes the quorum opens the round at the resume", async ({ browser }) => {
    test.setTimeout(120_000);
    const { setup, gameId, host, leaver, staying } = await twoReadyAndALeaver(browser);

    // Act — the host pauses for the prayer, and the last one asked leaves under the veil
    await host.page.getByTestId("pause-game").click();
    for (const player of staying) {
      await expect(player.page.getByRole("dialog", { name: "The majlis pauses for ṣalāh" })).toBeVisible({ timeout: 15_000 });
    }
    await apiLeaveRoom(setup.roomId, leaver.login.user.id, leaver.login.access_token);

    // Assert — nothing opens while paused: the quorum is complete, the round is not
    await expect
      .poll(async () => (await apiGetUndercoverState(gameId, host.login.access_token)).ready_quorum, { timeout: 15_000 })
      .toBe(2);
    const paused = await apiGetUndercoverState(gameId, host.login.access_token);
    expect(paused.paused).toBeTruthy();
    expect(paused.turn_number).toBe(1);
    expect(paused.ready_count).toBe(2);

    // Act — the host resumes from the veil
    await host.page.getByTestId("pause-veil-resume").click();

    // Assert — the resume opens the round the departure completed: before review R6 it
    // opened nothing, and the ready players (who cannot mark again) waited for the host
    for (const player of staying) await expect(player.page.getByTestId("pause-veil")).toHaveCount(0, { timeout: 15_000 });
    await waitForDescribingEverywhere(staying);
    const opened = await apiGetUndercoverState(gameId, host.login.access_token);
    expect(opened.turn_number).toBe(2);
    expect(opened.turn_phase).toBe("describing");
    expect(opened.paused ?? null).toBeNull();

    await setup.cleanup();
  });
});

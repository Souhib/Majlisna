import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionViaUI,
  type PlayerContext,
} from "../../helpers/ui-game-setup";
import {
  apiGetUndercoverState,
  apiPauseGame,
  apiResumeGame,
  rawPost,
} from "../../helpers/api-client";

/**
 * The prayer pause (وقفة الصلاة): when the adhan comes, the host pauses the game.
 *
 * Every seat sees the veil ("The majlis pauses for ṣalāh", who paused it), the game
 * under it is inert and the server refuses every move, the clock stands still, and
 * only the host resumes (before the 45-minute mark). Resuming lifts the veil and the
 * game goes on from where it stopped. Only the host is offered "Pause".
 */

/** The game header's phase clock ("Time left: 9:58"); the veil's still clock has no "Time left". */
const headerClock = (page: Page) => page.locator('[role="timer"][aria-label^="Time left: "]');

const gameIdOf = (page: Page): string => {
  const id = page.url().match(/\/game\/undercover\/([a-f0-9-]+)/)?.[1];
  if (!id) throw new Error(`not on an Undercover game page: ${page.url()}`);
  return id;
};

async function currentDescriber(players: PlayerContext[], gameId: string): Promise<PlayerContext> {
  const state = await apiGetUndercoverState(gameId, players[0].login.access_token);
  const describerId = state.description_order?.[state.current_describer_index ?? 0]?.user_id;
  const describer = players.find((p) => p.login.user.id === describerId);
  if (!describer) throw new Error(`no describer in ${JSON.stringify(state.description_order)}`);
  return describer;
}

test.describe("Prayer pause", () => {
  test("the host pauses an Undercover game: the table waits under the veil, then plays on", async ({ browser }) => {
    // Prepare — a 3-player table at the describing phase
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);
    expect(players).toHaveLength(3);
    const host = setup.players[0];
    const guests = setup.players.slice(1);
    const hostName = host.login.user.username;
    const gameId = gameIdOf(host.page);

    // Only the host is offered "Pause", and the server agrees
    const pauseButton = host.page.getByTestId("pause-game");
    await expect(pauseButton).toBeVisible({ timeout: 15_000 });
    await expect(pauseButton).toHaveAccessibleName("Pause the game for ṣalāh");
    for (const guest of guests) {
      await expect(headerClock(guest.page)).toBeVisible({ timeout: 15_000 });
      await expect(guest.page.getByTestId("pause-game")).toHaveCount(0);
      const refused = await rawPost(`/api/v1/undercover/games/${gameId}/pause`, {}, guest.login.access_token);
      expect(refused.status).toBe(403);
    }

    // Act — the host pauses
    await pauseButton.click();

    // Assert — every seat sees the veil, the host's with Resume, the others' without
    for (const player of setup.players) {
      const veil = player.page.getByRole("dialog", { name: "The majlis pauses for ṣalāh" });
      await expect(veil).toBeVisible({ timeout: 15_000 });
      if (player === host) {
        await expect(veil).toContainText("Paused by you");
        await expect(player.page.getByTestId("pause-veil-resume")).toBeVisible();
      } else {
        await expect(veil).toContainText("Paused by");
        await expect(veil).toContainText(hostName);
        await expect(veil).toContainText("The host resumes");
        await expect(player.page.getByTestId("pause-veil-resume")).toHaveCount(0);
      }
      await expect(veil.getByTestId("pause-clock")).toBeVisible();
      // the header's own Pause is gone while paused (the veil carries the one Resume)
      await expect(player.page.getByTestId("pause-game")).toHaveCount(0);
    }

    // A move is refused: the describer's field sits in the inert game, and the server says no
    const describer = await currentDescriber(players, gameId);
    await expect(describer.page.locator("[inert] #description-input")).toHaveCount(1);
    const move = await rawPost(`/api/v1/undercover/games/${gameId}/describe`, { word: "paused" }, describer.login.access_token);
    expect(move.status).toBe(409);
    expect((await move.json()).error_key).toBe("errors.api.gamePaused");

    // The clock is frozen: the same time on screen and on the server, seconds apart
    const paused = await apiGetUndercoverState(gameId, host.login.access_token);
    expect(paused.paused?.by_username).toBe(hostName);
    expect(paused.paused?.remaining_seconds).not.toBeNull();
    const frozen = await headerClock(guests[0].page).getAttribute("aria-label");
    expect(frozen).toMatch(/^Time left: \d+:\d\d$/);
    await guests[0].page.waitForTimeout(2_500); // let real time pass: a running clock would move
    await expect(headerClock(guests[0].page)).toHaveAttribute("aria-label", frozen!);
    const stillPaused = await apiGetUndercoverState(gameId, host.login.access_token);
    expect(stillPaused.paused?.remaining_seconds).toBe(paused.paused?.remaining_seconds);

    // Act — the host resumes from the veil
    await host.page.getByTestId("pause-veil-resume").click();

    // Assert — the veil lifts everywhere and the clock runs again
    for (const player of setup.players) {
      await expect(player.page.getByTestId("pause-veil")).toHaveCount(0, { timeout: 15_000 });
    }
    await expect(host.page.getByTestId("pause-game")).toBeVisible();
    await expect.poll(async () => headerClock(guests[0].page).getAttribute("aria-label"), { timeout: 5_000 }).not.toBe(frozen);
    expect((await apiGetUndercoverState(gameId, host.login.access_token)).paused ?? null).toBeNull();

    // The game goes on: the describer gives their word and the turn moves on
    await expect(describer.page.locator("[inert] #description-input")).toHaveCount(0);
    await submitDescriptionViaUI(describer.page, "resumed");
    await expect(describer.page.locator("#description-input")).toBeHidden({ timeout: 10_000 });
    const next = await currentDescriber(players, gameId);
    expect(next.login.user.id).not.toBe(describer.login.user.id);
    await expect(next.page.locator("#description-input")).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });

  test("a pause holds across a reload and only the host's resume lifts it", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    await dismissRoleRevealAll(setup.players);
    const host = setup.players[0];
    const guest = setup.players[1];
    const gameId = gameIdOf(host.page);

    await apiPauseGame("undercover", gameId, host.login.access_token);

    // A guest who reloads during the prayer comes back to the veil, not to a running game
    await expect(guest.page.getByTestId("pause-veil")).toBeVisible({ timeout: 15_000 });
    await guest.page.reload();
    await expect(guest.page.getByRole("dialog", { name: "The majlis pauses for ṣalāh" })).toBeVisible({ timeout: 15_000 });

    // A guest cannot resume (before the 45-minute mark), a second pause is refused
    const guestResume = await rawPost(`/api/v1/undercover/games/${gameId}/resume`, {}, guest.login.access_token);
    expect(guestResume.status).toBe(403);
    const doublePause = await rawPost(`/api/v1/undercover/games/${gameId}/pause`, {}, host.login.access_token);
    expect(doublePause.status).toBe(409);

    await apiResumeGame("undercover", gameId, host.login.access_token);
    await expect(guest.page.getByTestId("pause-veil")).toHaveCount(0, { timeout: 15_000 });
    await expect(headerClock(guest.page)).toBeVisible();

    await setup.cleanup();
  });
});

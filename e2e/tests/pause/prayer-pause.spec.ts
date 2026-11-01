import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionViaUI,
  giveClue,
  guessCard,
  findSpymaster,
  findOperative,
  type PlayerContext,
} from "../../helpers/ui-game-setup";
import {
  apiGetCodenamesBoard,
  apiGetMCQQuizState,
  apiGetUndercoverState,
  apiPauseGame,
  apiResumeGame,
  apiUpdateRoomSettings,
  expectApiError,
  rawPost,
} from "../../helpers/api-client";
import { dbMcqCorrectIndex } from "../../helpers/db";

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

/** "9:58", as the clock writes a number of seconds (rounded up, like ThreadClock). */
function clockText(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** The thread clock's one animation (id "thread-clock"): its state, time and where it stands. */
const threadAnimation = (page: Page) =>
  page.evaluate(() => {
    const animation = document.getAnimations().find((a) => a.id === "thread-clock");
    const target = (animation?.effect as KeyframeEffect | null)?.target as Element | null;
    return {
      playState: animation?.playState ?? "none",
      currentTime: animation?.currentTime == null ? null : Number(animation.currentTime),
      transform: target ? getComputedStyle(target).transform : "",
    };
  });

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
    // ...exactly the server's frozen countdown (WP-18: the clock freezes from the server's
    // figure, never from the device's last tick)
    expect(frozen).toBe(`Time left: ${clockText(paused.paused!.remaining_seconds!)}`);
    const threadBefore = await threadAnimation(guests[0].page);
    expect(threadBefore.playState).toBe("paused");
    await guests[0].page.waitForTimeout(2_500); // let real time pass: a running clock would move
    await expect(headerClock(guests[0].page)).toHaveAttribute("aria-label", frozen!);
    const stillPaused = await apiGetUndercoverState(gameId, host.login.access_token);
    expect(stillPaused.paused?.remaining_seconds).toBe(paused.paused?.remaining_seconds);
    // ...and the thread stands still to the pixel: its one animation is paused, not moving
    const threadAfter = await threadAnimation(guests[0].page);
    expect(threadAfter.playState).toBe("paused");
    expect(threadAfter.currentTime).toBe(threadBefore.currentTime);
    expect(threadAfter.transform).toBe(threadBefore.transform);

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

  test("Codenames: the host pauses, a guess is refused under the veil, and play resumes", async ({ browser }) => {
    // Prepare — a 4-player Codenames game, the first clue given
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    const gameId = await startGameViaAPI(setup.players, "codenames", setup.roomId);
    const host = setup.players[0];
    const board = await apiGetCodenamesBoard(gameId, host.login.access_token);
    const spymaster = await findSpymaster(setup.players, gameId, board.current_team);
    const operative = await findOperative(setup.players, gameId, board.current_team);
    await giveClue(spymaster.page, "pause", 1);
    const spyBoard = await apiGetCodenamesBoard(gameId, spymaster.login.access_token);
    const cardIndex = spyBoard.board.findIndex((c) => c.card_type === board.current_team && !c.revealed);

    // Act — the host pauses from the header
    await host.page.getByTestId("pause-game").click();

    // Assert — the veil on every seat; the board under it is inert; the server refuses a guess
    for (const player of setup.players) {
      await expect(player.page.getByRole("dialog", { name: "The majlis pauses for ṣalāh" })).toBeVisible({ timeout: 15_000 });
    }
    await expect(operative.page.locator('[inert] [data-testid="codenames-board"]')).toHaveCount(1);
    await expectApiError(
      await rawPost(`/api/v1/codenames/games/${gameId}/guess`, { card_index: cardIndex }, operative.login.access_token),
      409,
      "errors.api.gamePaused",
    );
    expect((await apiGetCodenamesBoard(gameId, host.login.access_token)).board[cardIndex].revealed).toBe(false);

    // Act — the host resumes from the veil
    await host.page.getByTestId("pause-veil-resume").click();

    // Assert — the veil lifts everywhere, and the operative's guess now turns the card
    for (const player of setup.players) await expect(player.page.getByTestId("pause-veil")).toHaveCount(0, { timeout: 15_000 });
    await guessCard(operative.page, spyBoard.board[cardIndex].word);
    await expect.poll(async () => (await apiGetCodenamesBoard(gameId, host.login.access_token)).board[cardIndex].revealed).toBe(true);

    await setup.cleanup();
  });

  test("The Quiz: a pause freezes the question's clock and refuses answers until the resume", async ({ browser }) => {
    // Prepare — two players, a 60 s question open
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const [host, guest] = setup.players;
    await apiUpdateRoomSettings(setup.roomId, { mcq_quiz_turn_duration: 60 }, host.login.access_token);
    const gameId = await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);
    await expect(headerClock(guest.page)).toBeVisible({ timeout: 15_000 });

    // Act — the host pauses
    await apiPauseGame("mcqquiz", gameId, host.login.access_token);

    // Assert — the veil, a refused answer, and a clock that stands at the server's figure
    for (const player of setup.players) {
      await expect(player.page.getByRole("dialog", { name: "The majlis pauses for ṣalāh" })).toBeVisible({ timeout: 15_000 });
    }
    await expectApiError(
      await rawPost(`/api/v1/mcqquiz/games/${gameId}/answer`, { choice_index: 0 }, guest.login.access_token),
      409,
      "errors.api.gamePaused",
    );
    const paused = await apiGetMCQQuizState(gameId, host.login.access_token);
    const remaining = paused.paused!.remaining_seconds!;
    expect(remaining).toBeGreaterThan(30);
    await expect(headerClock(guest.page)).toHaveAttribute("aria-label", `Time left: ${clockText(remaining)}`);
    await guest.page.waitForTimeout(2_500); // let real time pass: a running clock would move
    await expect(headerClock(guest.page)).toHaveAttribute("aria-label", `Time left: ${clockText(remaining)}`);
    expect((await apiGetMCQQuizState(gameId, host.login.access_token)).paused?.remaining_seconds).toBe(remaining);

    // Act — resume; the guest answers
    await apiResumeGame("mcqquiz", gameId, host.login.access_token);
    for (const player of setup.players) await expect(player.page.getByTestId("pause-veil")).toHaveCount(0, { timeout: 15_000 });
    const answer = await rawPost(`/api/v1/mcqquiz/games/${gameId}/answer`, { choice_index: dbMcqCorrectIndex(gameId) }, guest.login.access_token);

    // Assert — taken, the clock running again from where it stood
    expect(answer.status).toBe(200);
    expect((await apiGetMCQQuizState(gameId, guest.login.access_token)).my_answered).toBe(true);
    await expect
      .poll(async () => headerClock(guest.page).getAttribute("aria-label"), { timeout: 5_000 })
      .not.toBe(`Time left: ${clockText(remaining)}`);

    await setup.cleanup();
  });
});

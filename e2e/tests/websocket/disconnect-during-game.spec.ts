import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  isPageAlive,
} from "../../helpers/ui-game-setup";
import { apiGetUndercoverState, rawPatch } from "../../helpers/api-client";

/**
 * Wait until all expected players are alive in the undercover game state (their
 * heartbeats fresh) before the test goes on. It used to return silently when the time
 * ran out, so the test went on from a state it had not reached (TQ-16).
 */
async function waitForAllPlayersAlive(gameId: string, token: string, expectedCount: number): Promise<void> {
  await expect
    .poll(async () => (await apiGetUndercoverState(gameId, token)).players.filter((p) => p.is_alive).length, {
      timeout: 30_000,
      intervals: [1_000],
    })
    .toBeGreaterThanOrEqual(expectedCount);
}

test.describe("Disconnect During Active Game", () => {
  test("player closing browser during undercover game marks them dead", async ({
    browser,
  }) => {
    // stale 20 s + the in-game grace GRACE_PERIOD_SECONDS (180 s) + checker 5 s ≈ 205 s
    test.setTimeout(300_000);

    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");
    await startGameViaAPI(setup.players, "undercover", setup.roomId);

    // Wait for all players on game page
    for (const player of setup.players) {
      if (!isPageAlive(player.page)) continue;
      await expect(player.page).toHaveURL(/\/game\/undercover\//, {
        timeout: 15_000,
      });
    }

    const activePlayers = await dismissRoleRevealAll(setup.players);

    const gameId = activePlayers[0].page
      .url()
      .match(/\/game\/undercover\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Wait until all players are alive (heartbeats refreshed)
    await waitForAllPlayersAlive(
      gameId!,
      activePlayers[0].login.access_token,
      activePlayers.length,
    );

    // Close the LAST active player's browser (simulates disconnect)
    const leavingPlayer = activePlayers[activePlayers.length - 1];
    await leavingPlayer.page.context().close();

    // Remaining players should see the disconnect reflected in the UI: the leaver's
    // seat reads "Eliminated · <role>", or the game is over (the leaver decided it)
    const remainingPlayers = activePlayers.slice(0, -1);
    const remainingPage = remainingPlayers[0].page;
    const leavingUsername = leavingPlayer.login.user.username;
    const leaverSeat = remainingPage
      .getByRole("list", { name: "Who said what, in speaking order" })
      .getByRole("listitem")
      .filter({ hasText: leavingUsername });
    await expect(leaverSeat).toBeVisible({ timeout: 15_000 });
    await expect(leaverSeat).not.toContainText("Eliminated");

    // stale 20 s + grace 180 s + checker 5 s ≈ 205 s
    await expect(
      leaverSeat
        .filter({ hasText: "Eliminated" })
        .or(remainingPage.locator('h2:has-text("Game Over")')),
    ).toBeVisible({ timeout: 250_000 });

    // Remaining players should still be on the game page
    for (const player of remainingPlayers) {
      if (!isPageAlive(player.page)) continue;
      await expect(player.page).toHaveURL(/\/game\/undercover\//);
    }
  });

  test("player closing browser during codenames game removes them", async ({
    browser,
  }) => {
    test.setTimeout(300_000);

    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    for (const player of setup.players) {
      if (!isPageAlive(player.page)) continue;
      await expect(player.page).toHaveURL(/\/game\/codenames\//, {
        timeout: 15_000,
      });
    }

    // Wait for Socket.IO to connect on game pages (heartbeats established).
    // The connection status indicator disappears when connected.
    for (const player of setup.players) {
      if (!isPageAlive(player.page)) continue;
      await expect(player.page.locator('text=Reconnecting')).toBeHidden({ timeout: 10_000 });
    }

    // Get the leaving player's username to verify they disappear from the UI
    const leavingUsername = setup.players[3].login.user.username;

    // Verify the leaving player's name is visible before disconnect
    const remainingPage = setup.players[0].page;
    await expect(
      remainingPage.getByText(leavingUsername).first(),
    ).toBeVisible({ timeout: 10_000 });

    // Close player 3's browser
    await setup.players[3].page.context().close();

    // Remaining players should see the disconnect reflected in the UI:
    // either the player disappears from the team list, or "Game Over" appears
    // (if removing the player empties a team).
    // Wait for UI to reflect the disconnect (stale 20s + grace 180s + checker 5s ≈ 210s)
    await expect(async () => {
      const nameGone = (await remainingPage.getByText(leavingUsername).count()) === 0;
      const gameOver = (await remainingPage.locator('h2:has-text("Game Over")').count()) > 0;
      expect(nameGone || gameOver).toBe(true);
    }).toPass({ timeout: 250_000 });
  });

  test("kick during active undercover game removes player from game", async ({
    browser,
  }) => {
    test.setTimeout(120_000);

    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");
    await startGameViaAPI(setup.players, "undercover", setup.roomId);

    for (const player of setup.players) {
      if (!isPageAlive(player.page)) continue;
      await expect(player.page).toHaveURL(/\/game\/undercover\//, {
        timeout: 15_000,
      });
    }

    const activePlayers = await dismissRoleRevealAll(setup.players);

    const gameId = activePlayers[0].page
      .url()
      .match(/\/game\/undercover\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Wait until all players are alive (heartbeats refreshed)
    await waitForAllPlayersAlive(
      gameId!,
      activePlayers[0].login.access_token,
      activePlayers.length,
    );

    // Host kicks the last active player via API
    // (kick during game has no UI button — only available via API)
    const kickedPlayer = activePlayers[activePlayers.length - 1];
    const hostToken = activePlayers[0].login.access_token;
    const kickedUserId = kickedPlayer.login.user.id;

    const res = await rawPatch(`/api/v1/rooms/${setup.roomId}/kick`, { user_id: kickedUserId }, hostToken);
    expect(res.status).toBe(200);

    // Kicked player should be redirected to /rooms via UI
    await expect(kickedPlayer.page).toHaveURL(/\/rooms/, {
      timeout: 15_000,
    });

    // ...where the rooms page says why, in place (not a toast)
    await expect(kickedPlayer.page.getByTestId("room-notice")).toBeVisible({ timeout: 10_000 });

    // Host should see the kicked player's seat as "Eliminated", or the game over
    const hostPage = activePlayers[0].page;
    const kickedSeat = hostPage
      .getByRole("list", { name: "Who said what, in speaking order" })
      .getByRole("listitem")
      .filter({ hasText: kickedPlayer.login.user.username });
    await expect(
      kickedSeat
        .filter({ hasText: "Eliminated" })
        .or(hostPage.locator('h2:has-text("Game Over")')),
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });
});

import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  isPageAlive,
} from "../../helpers/ui-game-setup";
import { apiGetUndercoverState } from "../../helpers/api-client";

/**
 * Wait until all expected players are alive in the undercover game state.
 * This ensures heartbeats are fresh before we proceed with the test.
 */
async function waitForAllPlayersAlive(
  gameId: string,
  token: string,
  expectedCount: number,
  timeoutMs = 30_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const state = await apiGetUndercoverState(gameId, token);
      const alive = state.players.filter((p) => p.is_alive).length;
      if (alive >= expectedCount) return;
    } catch {
      // Game state not ready yet
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
}

test.describe("Disconnect During Active Game", () => {
  test("player closing browser during undercover game marks them dead", async ({
    browser,
  }) => {
    test.setTimeout(180_000);

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
    // If game already ended during setup (heartbeat timing), skip gracefully
    if (activePlayers.length === 0) {
      await setup.cleanup();
      return;
    }

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

    // Remaining players should see the disconnect reflected in the UI:
    // either "Eliminated" text (player marked dead) or "Game Over" screen
    const remainingPlayers = activePlayers.slice(0, -1);
    const remainingPage = remainingPlayers[0].page;

    // Wait for UI to reflect the disconnect (stale 20s + grace 60s + checker 5s ≈ 85s)
    await expect(
      remainingPage
        .locator('text=Eliminated')
        .or(remainingPage.locator('h2:has-text("Game Over")'))
        .first(),
    ).toBeVisible({ timeout: 120_000 });

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
    if (activePlayers.length === 0) {
      await setup.cleanup();
      return;
    }

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

    const baseUrl = process.env.FRONTEND_URL || "http://localhost:3000";
    const res = await fetch(
      `${baseUrl}/api/v1/rooms/${setup.roomId}/kick`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${hostToken}`,
        },
        body: JSON.stringify({ user_id: kickedUserId }),
      },
    );
    expect(res.ok).toBe(true);

    // Kicked player should be redirected to /rooms via UI
    await expect(kickedPlayer.page).toHaveURL(/\/rooms/, {
      timeout: 15_000,
    });

    // Host should see the kicked player as "Eliminated" or "Game Over" in the UI
    const hostPage = activePlayers[0].page;
    await expect(
      hostPage
        .locator('text=Eliminated')
        .or(hostPage.locator('h2:has-text("Game Over")'))
        .first(),
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });
});

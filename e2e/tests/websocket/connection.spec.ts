import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaUI,
  dismissRoleRevealAll,
  isPageAlive,
} from "../../helpers/ui-game-setup";
import { apiLogin, apiCreateRoom, apiJoinRoom } from "../../helpers/api-client";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { ROUTES } from "../../helpers/constants";

test.describe("WebSocket Real-time Updates", () => {
  test("all players see each other join in real-time", async ({ browser }) => {
    // Setup room with 2 players — Socket.IO should push room_state instantly
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);

    // All 3 players should see "Players (3)" — via Socket.IO, not polling
    for (const player of setup.players) {
      await expect(player.page.locator("text=Players (3)")).toBeVisible({
        timeout: 15_000,
      });
    }

    await setup.cleanup();
  });

  test("player leaving updates other players instantly", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);

    // Verify all 3 see each other
    await expect(
      setup.players[0].page.locator("text=Players (3)")
    ).toBeVisible({ timeout: 15_000 });

    // Player 3 leaves via the Leave button
    const leaveButton = setup.players[2].page.locator("button", {
      hasText: /leave/i,
    });
    await leaveButton.click();

    // Remaining players should see "Players (2)" via Socket.IO
    await expect(
      setup.players[0].page.locator("text=Players (2)")
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      setup.players[1].page.locator("text=Players (2)")
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });

  test("game start navigates all players to game page", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    // Start game via UI (host clicks start)
    await startGameViaUI(setup.players, "undercover");

    // All players should be on the undercover game page
    for (const player of setup.players) {
      if (!isPageAlive(player.page)) continue;
      await expect(player.page).toHaveURL(/\/game\/undercover\//, {
        timeout: 15_000,
      });
    }

    await setup.cleanup();
  });

  test("host kick updates kicked player and other players", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);

    // Verify all 3 see each other
    await expect(
      setup.players[0].page.locator("text=Players (3)")
    ).toBeVisible({ timeout: 15_000 });

    // Host (player 0) kicks player 2 — find the X button next to their name
    const kickButton = setup.players[0].page
      .locator("div", {
        hasText: setup.players[2].login.user.username,
      })
      .locator('button[title="Kick"]')
      .or(
        setup.players[0].page
          .locator("div", {
            hasText: setup.players[2].login.user.username,
          })
          .locator("button svg.lucide-x")
          .locator("..")
      );

    await kickButton.first().click();

    // Host and player 1 should see "Players (2)" via Socket.IO
    await expect(
      setup.players[0].page.locator("text=Players (2)")
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      setup.players[1].page.locator("text=Players (2)")
    ).toBeVisible({ timeout: 15_000 });

    // Kicked player should be redirected to /rooms
    await expect(setup.players[2].page).toHaveURL(/\/rooms/, {
      timeout: 15_000,
    });

    await setup.cleanup();
  });

  test("player refreshes page mid-game and reconnects with current state", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    // Start game
    await startGameViaUI(setup.players, "undercover");

    // Wait for game page
    for (const player of setup.players) {
      if (!isPageAlive(player.page)) continue;
      await expect(player.page).toHaveURL(/\/game\/undercover\//, {
        timeout: 15_000,
      });
    }

    // Dismiss role reveal for all players
    const activePlayers = await dismissRoleRevealAll(setup.players);
    expect(activePlayers.length).toBeGreaterThan(0);

    // Player 1 refreshes the page
    const refreshPlayer = activePlayers[0];
    await refreshPlayer.page.reload();

    // After refresh, player should still see the game (re-fetches state via useQuery + Socket.IO reconnect)
    await expect(refreshPlayer.page).toHaveURL(/\/game\/undercover\//, {
      timeout: 15_000,
    });

    // Should see the game UI — after reload, role reveal dialog reappears
    // because roleRevealed is local React state that resets on reload
    await expect(
      refreshPlayer.page
        .locator('h2:has-text("Your Role")')
        .or(refreshPlayer.page.locator("text=Describe your word"))
        .or(refreshPlayer.page.locator("text=Discuss and vote"))
        .or(refreshPlayer.page.locator('h2:has-text("Game Over")'))
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });
});

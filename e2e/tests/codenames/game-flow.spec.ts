import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  isPageAlive,
} from "../../helpers/ui-game-setup";

test.describe("Codenames Game Flow", () => {
  test("4-player game: board visible with 25 cards", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    // All players should see the 5x5 board
    for (const player of setup.players) {
      if (!isPageAlive(player.page)) continue;
      const cards = player.page.locator('[data-testid="codenames-card"]');
      await expect(cards.first()).toBeVisible({ timeout: 15_000 });
      const count = await cards.count();
      expect(count).toBe(25);
    }

    await setup.cleanup();
  });

  test("players see their team and role assignment", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    // Each player should see their team/role info at the bottom
    for (const player of setup.players) {
      if (!isPageAlive(player.page)) continue;
      // Should show "You are" text with team and role
      await expect(player.page.locator("text=You are")).toBeVisible({ timeout: 15_000 });
    }

    await setup.cleanup();
  });

  test("player refreshes mid-game and board is recovered", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    // Verify player 1 sees the board
    await expect(
      setup.players[0].page.locator('[data-testid="codenames-card"]').first(),
    ).toBeVisible({ timeout: 15_000 });

    // Reload player 1
    await setup.players[0].page.reload();
    await setup.players[0].page.waitForLoadState("domcontentloaded");

    // Board should be recovered via polling
    await expect(
      setup.players[0].page.locator('[data-testid="codenames-card"]').first(),
    ).toBeVisible({ timeout: 15_000 });

    // Should still show 25 cards
    const count = await setup.players[0].page.locator('[data-testid="codenames-card"]').count();
    expect(count).toBe(25);

    await setup.cleanup();
  });
});

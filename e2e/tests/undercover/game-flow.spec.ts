import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaUI,
  voteForPlayer,
  verifyAllPlayersVoted,
  waitForEliminationOrGameOver,
  isPageAlive,
} from "../../helpers/ui-game-setup";

test.describe("Undercover Game Flow", () => {
  test("3-player game: role reveal shows role and word", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);

    // All players should see role reveal
    for (const player of setup.players) {
      await expect(player.page.locator("text=Your Role")).toBeVisible({ timeout: 15_000 });
      // Should show either Civilian, Undercover, or Mr. White
      const roleLabel = player.page
        .locator("text=Civilian")
        .or(player.page.locator("text=Undercover"))
        .or(player.page.locator("text=Mr. White"));
      await expect(roleLabel.first()).toBeVisible({ timeout: 5_000 });
    }

    await setup.cleanup();
  });

  test("full round: describe then vote then elimination", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const activePlayers = await dismissRoleRevealAll(setup.players);

    // Description phase via UI
    await submitDescriptionsForAllPlayersViaUI(activePlayers);

    // All players should see voting phase
    for (const player of activePlayers) {
      if (!isPageAlive(player.page)) continue;
      await expect(
        player.page.locator("text=Discuss and vote")
          .or(player.page.locator('h2:has-text("Game Over")')),
      ).toBeVisible({ timeout: 15_000 });
    }

    // Vote for the first player (who isn't the voter)
    const voteTarget = activePlayers[1].login.user.username;
    const fallback = activePlayers[0].login.user.username;

    for (const voter of activePlayers) {
      if (!isPageAlive(voter.page)) continue;
      if (voter.login.user.username === voteTarget) continue;
      await voteForPlayer(voter.page, voteTarget);
    }
    await verifyAllPlayersVoted(activePlayers, voteTarget, fallback);

    // Should see elimination or game over
    const observerPage = activePlayers.find((p) => isPageAlive(p.page))?.page;
    if (observerPage) {
      const result = await waitForEliminationOrGameOver(observerPage);
      expect(["elimination", "game_over"]).toContain(result.type);
    }

    await setup.cleanup();
  });

  test("player refreshes mid-game and state is recovered via polling", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const activePlayers = await dismissRoleRevealAll(setup.players);

    // Verify player 1 is in describing phase
    await expect(
      activePlayers[0].page.locator('h2:has-text("Describe your word")')
        .or(activePlayers[0].page.locator('h2:has-text("Discuss and vote")')),
    ).toBeVisible({ timeout: 15_000 });

    // Reload player 1
    await activePlayers[0].page.reload();
    await activePlayers[0].page.waitForLoadState("domcontentloaded");

    // Player 1 should recover state via polling
    await expect(
      activePlayers[0].page.locator("h1:has-text('Undercover')"),
    ).toBeVisible({ timeout: 15_000 });

    // Game should still be functional — use .first() to avoid strict mode violation
    // when multiple game elements are visible (e.g., "Round 1" + "Discuss and vote")
    await expect(
      activePlayers[0].page.locator('h2:has-text("Describe your word")')
        .or(activePlayers[0].page.locator('h2:has-text("Discuss and vote")'))
        .or(activePlayers[0].page.locator("text=Round"))
        .first(),
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });
});

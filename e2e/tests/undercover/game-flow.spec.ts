import { test, expect, type Page } from "@playwright/test";
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
import { apiGetUndercoverState } from "../../helpers/api-client";

function extractGameId(page: Page): string {
  const id = page.url().match(/\/game\/undercover\/([a-f0-9-]+)/)?.[1];
  if (!id) throw new Error(`not on an Undercover game page: ${page.url()}`);
  return id;
}

test.describe("Undercover Game Flow", () => {
  test("3-player game: the first reading gives each player a word, never a side", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const gameId = extractGameId(setup.players[0].page);

    for (const player of setup.players) {
      const page = player.page;
      const state = await apiGetUndercoverState(gameId, player.login.access_token);

      // The same first reading for every role: nobody's screen gives their side away
      await expect(page.getByRole("heading", { name: "Your role is in your word." })).toBeVisible({ timeout: 15_000 });

      // The tablet holds the word, covered until the player reads it
      const tablet = page.locator("button.lawh");
      await expect(tablet).toBeVisible();
      await expect(tablet).toHaveAttribute("data-state", "rest");
      await page.getByRole("button", { name: "I can’t hold: show until I hide it" }).click();
      await expect(tablet).toHaveAttribute("data-state", "shown");

      // A 3-player table has no Mr. White: everyone holds a word
      expect(state.my_role).not.toBe("mr_white");
      await expect(tablet.locator(".lawh-face")).toContainText(state.my_word);
      // ...and no side is written on it
      await expect(tablet).not.toContainText("Civilian");
      await expect(tablet).not.toContainText("Undercover");
    }

    await setup.cleanup();
  });

  test("every tablet offers the word's explanation", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const gameId = extractGameId(setup.players[0].page);

    // Offered on every tablet (a button only some players had would point at Mr. White)
    for (const player of setup.players) {
      const page = player.page;
      const state = await apiGetUndercoverState(gameId, player.login.access_token);
      await expect(page.getByRole("heading", { name: "Your role is in your word." })).toBeVisible({ timeout: 15_000 });

      const hintButton = page.getByRole("button", { name: "Show explanation" });
      await expect(hintButton).toBeVisible();
      await hintButton.click();

      const popover = page.locator("[data-radix-popper-content-wrapper]");
      await expect(popover).toBeVisible({ timeout: 3_000 });
      await expect(popover).toContainText(state.my_word_hint || "This word has no explanation yet.");
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

    for (const voter of activePlayers) {
      if (!isPageAlive(voter.page)) continue;
      if (voter.login.user.username === voteTarget) continue;
      await voteForPlayer(voter.page, voteTarget);
    }
    await verifyAllPlayersVoted(activePlayers, voteTarget, activePlayers[0].login.user.username);

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

    // Verify player 1 is in describing phase (dynamic title: "Your turn to describe!" or "X is describing...")
    await expect(
      activePlayers[0].page.locator('h2:has-text("turn to describe")')
        .or(activePlayers[0].page.locator('h2:has-text("is describing")')
        .or(activePlayers[0].page.locator('h2:has-text("Discuss and vote")'))),
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
      activePlayers[0].page.locator('h2:has-text("turn to describe")')
        .or(activePlayers[0].page.locator('h2:has-text("is describing")'))
        .or(activePlayers[0].page.locator('h2:has-text("Discuss and vote")'))
        .or(activePlayers[0].page.locator("text=Round"))
        .first(),
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });
});

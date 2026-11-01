import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaUI,
  voteOut,
  waitForEliminationOrGameOver,
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
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const activePlayers = await dismissRoleRevealAll(setup.players);

    // Description phase via UI: every page then shows the vote
    await submitDescriptionsForAllPlayersViaUI(activePlayers);
    for (const player of activePlayers) {
      await expect(player.page.locator("text=Discuss and vote")).toBeVisible({ timeout: 15_000 });
    }

    // The table votes the second player out (who votes for the first)
    const state = await apiGetUndercoverState(gameId, activePlayers[0].login.access_token);
    const alive = state.players.filter((p) => p.is_alive);
    const target = alive.find((p) => p.user_id === activePlayers[1].login.user.id)!;
    await voteOut(activePlayers, alive, target, alive.find((p) => p.user_id === activePlayers[0].login.user.id)!);

    // Three players, one elimination: the game is decided, and the target is out
    const result = await waitForEliminationOrGameOver(activePlayers[0].page);
    expect(result.type).toBe("game_over");
    const after = await apiGetUndercoverState(gameId, activePlayers[0].login.access_token);
    expect(after.players.find((p) => p.user_id === target.user_id)?.is_alive).toBe(false);

    await setup.cleanup();
  });

  test("player refreshes mid-game and state is recovered via polling", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const activePlayers = await dismissRoleRevealAll(setup.players);

    // Player 1 is in the describing phase (dynamic title: "Your turn to describe!" or "X is describing...")
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

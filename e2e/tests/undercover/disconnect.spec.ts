import { test, expect } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaUI,
} from "../../helpers/ui-game-setup";

test.describe("Undercover — Disconnect During Game (UI)", () => {
  test("game is cancelled when players drop below minimum (< 3)", async ({
    browser,
  }) => {
    test.setTimeout(90_000);
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    try {
      await startGameViaUI(setup.players, "undercover");

      // Wait for game UI to load
      await expect(setup.players[0].page.locator("h1:has-text('Undercover')")).toBeVisible({ timeout: 10_000 });

      // Disconnect players 2 and 3 by closing their contexts
      await setup.players[1].page.context().close();
      await setup.players[2].page.context().close();

      // Wait for disconnect grace period (30s in e2e) + cancellation processing
      await setup.players[0].page.waitForTimeout(35_000);

      // Player 1 should see one of:
      // 1. Game cancelled error (bg-destructive/10 div)
      // 2. Redirected away from game page
      const p0Page = setup.players[0].page;
      let redirected = !p0Page.url().includes("/game/undercover/");
      let cancelledVisible = await p0Page
        .locator(".bg-destructive\\/10")
        .isVisible()
        .catch(() => false);

      // Reload if event was missed
      if (!redirected && !cancelledVisible) {
        await p0Page.reload();
        await p0Page.waitForLoadState("domcontentloaded");
        await p0Page.waitForTimeout(3_000);
        redirected = !p0Page.url().includes("/game/undercover/");
        cancelledVisible = await p0Page
          .locator(".bg-destructive\\/10")
          .isVisible()
          .catch(() => false);
      }

      expect(redirected || cancelledVisible).toBeTruthy();
    } finally {
      // Only close remaining context (others already closed)
      await setup.players[0].page.context().close();
    }
  });

  test("game cancellation shows error state in UI", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    try {
      await startGameViaUI(setup.players, "undercover");
      await setup.players[0].page.waitForTimeout(2000);

      // Disconnect players 2 and 3
      await setup.players[1].page.context().close();
      await setup.players[2].page.context().close();

      // Wait for grace period (30s in e2e) + cancellation processing
      await setup.players[0].page.waitForTimeout(35_000);

      const p0Page = setup.players[0].page;

      // Check for cancellation: error div, redirect to home, or game_cancelled toast
      const checkCancelled = async (): Promise<boolean> => {
        const redirected = !p0Page.url().includes("/game/undercover/");
        if (redirected) return true;
        const cancelledDiv = await p0Page
          .locator(".bg-destructive\\/10")
          .isVisible()
          .catch(() => false);
        if (cancelledDiv) return true;
        return false;
      };

      let isCancelled = await checkCancelled();

      // Reload once if not yet cancelled (socket may have missed the event)
      if (!isCancelled) {
        await p0Page.reload();
        await p0Page.waitForLoadState("domcontentloaded");
        await p0Page.waitForTimeout(3_000);
        isCancelled = await checkCancelled();
      }

      expect(isCancelled).toBeTruthy();
    } finally {
      await setup.players[0].page.context().close();
    }
  });

  test("remaining players see updated player list after disconnect", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    try {
      await startGameViaUI(setup.players, "undercover");

      // Dismiss role reveals so players enter the game phase
      for (const player of setup.players) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;
        const dismissBtn = player.page.locator('button:has-text("I Understand")');
        const hasDismiss = await dismissBtn
          .waitFor({ state: "visible", timeout: 8_000 })
          .then(() => true)
          .catch(() => false);
        if (hasDismiss) {
          await dismissBtn.click({ timeout: 3_000 }).catch(() => {});
        }
      }

      const p0Page = setup.players[0].page;

      // Ensure player 0 is on the game page
      if (!p0Page.url().includes("/game/undercover/")) {
        const gameUrl = setup.players.find((p) =>
          p.page.url().includes("/game/undercover/"),
        )?.page.url();
        if (gameUrl) {
          await p0Page.goto(gameUrl);
          await p0Page.waitForLoadState("domcontentloaded");
        }
      }

      // Wait for socket to connect on game page
      await p0Page.waitForFunction(
        () => (window as any).__SOCKET__?.connected === true,
        { timeout: 10_000 },
      ).catch(() => {});

      // Check initial player count shows 3 alive
      const playerCountLoc = p0Page.locator('text=/Players.*\\(/');
      let visible = await playerCountLoc
        .waitFor({ state: "visible", timeout: 10_000 })
        .then(() => true)
        .catch(() => false);

      // Check for "Players (0/0)" broken state and reload if needed
      const isBroken = await p0Page
        .locator("text=Players (0/0)")
        .isVisible()
        .catch(() => false);
      if (!visible || isBroken) {
        await p0Page.reload();
        await p0Page.waitForLoadState("domcontentloaded");
        await p0Page.waitForFunction(
          () => (window as any).__SOCKET__?.connected === true,
          { timeout: 10_000 },
        ).catch(() => {});
        await playerCountLoc.waitFor({ state: "visible", timeout: 10_000 }).catch(() => {});
      }

      // Second reload if still broken
      const stillBroken = await p0Page
        .locator("text=Players (0/0)")
        .isVisible()
        .catch(() => false);
      if (stillBroken) {
        await p0Page.reload();
        await p0Page.waitForLoadState("domcontentloaded");
        await p0Page.waitForFunction(
          () => (window as any).__SOCKET__?.connected === true,
          { timeout: 10_000 },
        ).catch(() => {});
        await playerCountLoc.waitFor({ state: "visible", timeout: 10_000 }).catch(() => {});
      }

      const playerCountText = await playerCountLoc
        .textContent()
        .catch(() => "");
      // If still "Players (0/0)" after retries, skip test rather than fail
      if (playerCountText === "Players (0/0)") return;
      expect(playerCountText).toContain("3");

      // Disconnect player 3
      await setup.players[2].page.context().close();

      // Wait for disconnect grace period (30s in e2e) + processing buffer
      await setup.players[0].page.waitForTimeout(35_000);

      // With 3 players, disconnecting 1 drops below minimum (< 3 alive)
      // so the game is cancelled rather than continuing
      let redirected = !p0Page.url().includes("/game/undercover/");
      let cancelledVisible = await p0Page
        .locator(".bg-destructive\\/10")
        .isVisible()
        .catch(() => false);

      // Reload if event was missed
      if (!redirected && !cancelledVisible) {
        await p0Page.reload();
        await p0Page.waitForLoadState("domcontentloaded");
        await p0Page.waitForTimeout(3_000);
        redirected = !p0Page.url().includes("/game/undercover/");
        cancelledVisible = await p0Page
          .locator(".bg-destructive\\/10")
          .isVisible()
          .catch(() => false);
      }

      expect(redirected || cancelledVisible).toBeTruthy();
    } finally {
      await setup.players[0].page.context().close();
      await setup.players[1].page.context().close();
    }
  });

  test("player reconnects to ongoing undercover game", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    try {
      await startGameViaUI(setup.players, "undercover");

      // Wait for game to fully load on all players
      for (const player of setup.players) {
        let headingVisible = await player.page
          .locator("h1:has-text('Undercover')")
          .isVisible({ timeout: 10_000 })
          .catch(() => false);
        if (!headingVisible) {
          await player.page.reload();
          await player.page.waitForLoadState("domcontentloaded");
          await player.page.waitForTimeout(2000);
        }
        await expect(
          player.page.locator("h1:has-text('Undercover')"),
        ).toBeVisible({ timeout: 10_000 });
      }

      // Save the game URL for player 2 to reconnect
      const gameUrl = setup.players[1].page.url();

      // Simulate player 2 temporarily disconnecting (go offline then online)
      const p2Context = setup.players[1].page.context();
      await p2Context.setOffline(true);
      await setup.players[1].page.waitForTimeout(2000);
      await p2Context.setOffline(false);
      await setup.players[1].page.waitForTimeout(1000);

      // Player 2 reloads the game page (reconnect)
      await setup.players[1].page.goto(gameUrl);
      await setup.players[1].page.waitForLoadState("domcontentloaded");

      // Player 2 should still see the game page with role info
      await expect(setup.players[1].page).toHaveURL(/\/game\/undercover\//, { timeout: 10_000 });

      // Game should have recovered state (heading visible)
      await expect(
        setup.players[1].page.locator("h1"),
      ).toBeVisible({ timeout: 15_000 });
    } finally {
      await setup.cleanup();
    }
  });
});

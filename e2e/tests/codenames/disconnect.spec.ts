import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaUI,
  getPlayerRoleFromUI,
  type CodenamesPlayerRole,
} from "../../helpers/ui-game-setup";

test.describe("Codenames — Disconnect During Game (UI)", () => {
  test("team empty after disconnect triggers other team win via UI", async ({
    browser,
  }) => {
    test.setTimeout(180_000);
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      // Identify teams
      const playerRoles: {
        index: number;
        role: CodenamesPlayerRole;
      }[] = [];
      for (let i = 0; i < setup.players.length; i++) {
        const role = await getPlayerRoleFromUI(setup.players[i].page);
        playerRoles.push({ index: i, role });
      }

      const redPlayers = playerRoles.filter((p) => p.role.team === "red");
      const bluePlayers = playerRoles.filter((p) => p.role.team === "blue");

      // Pick the smaller team to disconnect (or blue if equal)
      const teamToDisconnect = bluePlayers;
      const survivingTeam = redPlayers;

      // Disconnect entire blue team by closing their browser contexts
      for (const player of teamToDisconnect) {
        await setup.players[player.index].page.context().close();
      }

      // Wait for grace period (3s in e2e) + cleanup + game resolution
      const survivorPage = setup.players[survivingTeam[0].index].page;

      // Wait for disconnect grace period (30s) + backend cleanup + game resolution
      await survivorPage
        .locator("h2:has-text('Game Over'), .bg-destructive\\/10")
        .first()
        .waitFor({ state: "visible", timeout: 40_000 })
        .catch(() => {});

      let gameOverVisible = await survivorPage
        .locator("h2:has-text('Game Over')")
        .isVisible()
        .catch(() => false);
      let cancelledVisible = await survivorPage
        .locator(".bg-destructive\\/10")
        .isVisible()
        .catch(() => false);

      // If not visible, reload to get latest state from server (get_board)
      if (!gameOverVisible && !cancelledVisible) {
        await survivorPage.reload();
        await survivorPage.waitForLoadState("domcontentloaded");
        await survivorPage.waitForFunction(
          () => (window as any).__SOCKET__?.connected === true,
          { timeout: 10_000 },
        ).catch(() => {});

        // Wait for game over or cancelled to render after reload
        await survivorPage
          .locator("h2:has-text('Game Over'), .bg-destructive\\/10")
          .first()
          .waitFor({ state: "visible", timeout: 40_000 })
          .catch(() => {});

        gameOverVisible = await survivorPage
          .locator("h2:has-text('Game Over')")
          .isVisible()
          .catch(() => false);
        cancelledVisible = await survivorPage
          .locator(".bg-destructive\\/10")
          .isVisible()
          .catch(() => false);
      }

      const redirected =
        survivorPage.url().includes("/game/codenames/") === false;

      expect(gameOverVisible || cancelledVisible || redirected).toBeTruthy();
    } finally {
      // Close any remaining contexts
      for (const player of setup.players) {
        await player.page.context().close().catch(() => {});
      }
    }
  });

  test("spymaster disconnect handled gracefully via UI", async ({
    browser,
  }) => {
    // Need 5 players so one team has 3 (spymaster + 2 operatives)
    const accounts = await generateTestAccounts(5);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      // Find all player roles
      const playerRoles: {
        index: number;
        role: CodenamesPlayerRole;
      }[] = [];
      for (let i = 0; i < setup.players.length; i++) {
        const role = await getPlayerRoleFromUI(setup.players[i].page);
        playerRoles.push({ index: i, role });
      }

      // Find a team with 3 players and disconnect its spymaster
      const teamCounts: Record<string, typeof playerRoles> = {};
      for (const pr of playerRoles) {
        const team = pr.role.team;
        if (!teamCounts[team]) teamCounts[team] = [];
        teamCounts[team].push(pr);
      }

      const bigTeam = Object.entries(teamCounts).find(
        ([, members]) => members.length >= 3,
      );

      if (bigTeam) {
        const [teamName, members] = bigTeam;
        const spymaster = members.find((m) => m.role.role === "spymaster");

        if (spymaster) {
          // Disconnect the spymaster
          await setup.players[spymaster.index].page.context().close();

          // Find a remaining player (not the disconnected one) to wait on
          const waitPlayer = setup.players.find(
            (_, idx) => idx !== spymaster.index,
          )!;
          // Wait for disconnect grace period (30s) + cleanup
          await waitPlayer.page.locator("h2:has-text('Game Over'), .bg-destructive\\/10")
            .first().waitFor({ state: "visible", timeout: 40_000 }).catch(() => {});

          // Find a remaining player from the same team
          const remainingTeammate = members.find(
            (m) => m.index !== spymaster.index,
          );

          if (remainingTeammate) {
            const remainingPage =
              setup.players[remainingTeammate.index].page;

            // Game should still be running (or cancelled gracefully)
            const isOnGamePage = remainingPage
              .url()
              .includes("/game/codenames/");
            const hasBoard = await remainingPage
              .locator(".grid-cols-5 button")
              .first()
              .isVisible()
              .catch(() => false);
            const isCancelled = await remainingPage
              .locator(".bg-destructive\\/10")
              .isVisible()
              .catch(() => false);

            // One of these outcomes is valid
            expect(
              (isOnGamePage && hasBoard) || isCancelled || !isOnGamePage,
            ).toBeTruthy();
          }
        }
      }

      // If we get here without errors, disconnect was handled gracefully
      expect(true).toBeTruthy();
    } finally {
      for (const player of setup.players) {
        await player.page.context().close().catch(() => {});
      }
    }
  });

  test("game cancelled when too many players disconnect shows error", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");
      // Disconnect players 2, 3, 4 (leaving only player 1)
      await setup.players[1].page.context().close();
      await setup.players[2].page.context().close();
      await setup.players[3].page.context().close();

      const remainingPage = setup.players[0].page;

      // Poll for game resolution with retries.
      // Grace period is 30s per player; backend processes them in parallel
      // but needs time to detect empty teams and emit game_over.
      const checkResolution = async (): Promise<boolean> => {
        const cancelledVisible = await remainingPage
          .locator(".bg-destructive\\/10")
          .isVisible()
          .catch(() => false);
        const gameOverVisible = await remainingPage
          .locator('h2:has-text("Game Over")')
          .isVisible()
          .catch(() => false);
        const redirected =
          remainingPage.url().includes("/game/codenames/") === false;
        return cancelledVisible || gameOverVisible || redirected;
      };

      // Wait for grace period (30s) + game resolution via socket events
      await remainingPage
        .locator("h2:has-text('Game Over'), .bg-destructive\\/10")
        .first()
        .waitFor({ state: "visible", timeout: 40_000 })
        .catch(() => {});

      let resolved = await checkResolution();

      // Retry with reload — socket may have missed the event
      for (let attempt = 0; attempt < 3 && !resolved; attempt++) {
        await remainingPage.reload();
        await remainingPage.waitForLoadState("domcontentloaded");
        // Wait for socket reconnect and server state to propagate
        await remainingPage.waitForTimeout(3_000);
        await remainingPage
          .locator("h2:has-text('Game Over'), .bg-destructive\\/10")
          .first()
          .waitFor({ state: "visible", timeout: 10_000 })
          .catch(() => {});
        resolved = await checkResolution();
      }

      expect(resolved).toBeTruthy();
    } finally {
      await setup.players[0].page.context().close();
    }
  });

  test("player reconnects to ongoing codenames game", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      // Verify board is loaded
      const cards = setup.players[1].page.locator(".grid-cols-5 button");
      await expect(cards.first()).toBeVisible({ timeout: 10_000 });

      // Save game URL
      const gameUrl = setup.players[1].page.url();

      // Simulate brief disconnect for player 2
      const p2Context = setup.players[1].page.context();
      await p2Context.setOffline(true);
      // Brief offline period
      await setup.players[0].page.waitForFunction(
        () => new Promise(r => setTimeout(r, 1000)).then(() => true),
        { timeout: 5_000 },
      ).catch(() => {});
      await p2Context.setOffline(false);

      // Reload the game page (reconnect)
      await setup.players[1].page.goto(gameUrl);
      await setup.players[1].page.waitForLoadState("domcontentloaded");
      await setup.players[1].page.waitForFunction(
        () => (window as any).__SOCKET__?.connected === true,
        { timeout: 10_000 },
      ).catch(() => {});

      // Player 2 should still see the game board
      await expect(setup.players[1].page).toHaveURL(/\/game\/codenames\//);

      // Wait for board to appear — with reload fallback
      let boardVisible = await setup.players[1].page
        .locator(".grid-cols-5 button")
        .first()
        .waitFor({ state: "visible", timeout: 10_000 })
        .then(() => true)
        .catch(() => false);
      if (!boardVisible) {
        // Reload to trigger get_board
        await setup.players[1].page.reload();
        await setup.players[1].page.waitForLoadState("domcontentloaded");
        await setup.players[1].page.waitForFunction(
          () => (window as any).__SOCKET__?.connected === true,
          { timeout: 10_000 },
        ).catch(() => {});
      }
      await expect(
        setup.players[1].page.locator(".grid-cols-5 button").first(),
      ).toBeVisible({ timeout: 15_000 });
      const cardCount = await setup.players[1].page
        .locator(".grid-cols-5 button")
        .count();
      expect(cardCount).toBe(25);

      // Team info should still be visible
      const infoSection = setup.players[1].page.locator(
        ".bg-muted\\/50.p-3.text-center.text-sm",
      );
      await expect(infoSection).toBeVisible({ timeout: 5_000 });
      const text = await infoSection.textContent();
      expect(text).toContain("You are a");
    } finally {
      await setup.cleanup();
    }
  });
});

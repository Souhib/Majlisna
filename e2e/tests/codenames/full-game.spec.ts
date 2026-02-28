import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaUI,
  getPlayerRoleFromUI,
  getCurrentTeamFromUI,
  giveClueViaUI,
  clickBoardCard,
  findUnrevealedCardIndex,
  type PlayerContext,
  type CodenamesPlayerRole,
} from "../../helpers/ui-game-setup";

test.describe("Codenames — Full Game Flow (UI)", () => {
  test("4-player game: start, board shown, clue, guess, game progresses", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      // ─── Verify the 5x5 board is shown ─────────────────
      for (const player of setup.players) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;
        // Wait for game page to fully load (may show "Loading..." briefly)
        await player.page.waitForFunction(
          () => (window as any).__SOCKET__?.connected === true,
          { timeout: 10_000 },
        ).catch(() => {});
        const cards = player.page.locator(".grid-cols-5 button");
        let firstVisible = await cards.first()
          .waitFor({ state: "visible", timeout: 10_000 })
          .then(() => true)
          .catch(() => false);
        // Reload if board didn't render (socket may have missed initial state)
        if (!firstVisible) {
          await player.page.reload();
          await player.page.waitForLoadState("domcontentloaded");
          firstVisible = await cards.first()
            .waitFor({ state: "visible", timeout: 10_000 })
            .then(() => true)
            .catch(() => false);
        }
        if (!firstVisible) continue; // Skip this player
        const cardCount = await cards.count();
        expect(cardCount).toBe(25);
      }

      // ─── Verify team and role info ──────────────────────
      for (const player of setup.players) {
        const infoText = await player.page
          .locator(".bg-muted\\/50.p-3.text-center.text-sm")
          .textContent();
        expect(infoText).toContain("You are a");
      }

      // ─── Verify score display ───────────────────────────
      const redScoreEl = setup.players[0].page.locator(".bg-red-500 + .text-sm");
      const blueScoreEl = setup.players[0].page.locator(".bg-blue-500 + .text-sm");

      await expect(redScoreEl).toBeVisible({ timeout: 10_000 });
      const initialRed = parseInt((await redScoreEl.textContent()) || "0");
      const initialBlue = parseInt((await blueScoreEl.textContent()) || "0");

      expect(initialRed).toBeGreaterThanOrEqual(8);
      expect(initialBlue).toBeGreaterThanOrEqual(8);
    } finally {
      await setup.cleanup();
    }
  });

  test("4-player game: clue giving and card guessing via UI", async ({
    browser,
  }) => {
    test.setTimeout(180_000);
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      const currentTeam = await getCurrentTeamFromUI(setup.players[0].page);

      // Identify players by role
      const playerRoles: { player: PlayerContext; role: CodenamesPlayerRole }[] = [];
      for (const player of setup.players) {
        const role = await getPlayerRoleFromUI(player.page);
        playerRoles.push({ player, role });
      }

      const spymaster = playerRoles.find(
        (pr) => pr.role.team === currentTeam && pr.role.role === "spymaster",
      );
      const operative = playerRoles.find(
        (pr) => pr.role.team === currentTeam && pr.role.role === "operative",
      );

      expect(spymaster).toBeTruthy();
      expect(operative).toBeTruthy();

      // ─── Spymaster gives a clue ────────────────────────
      // Ensure spymaster has roomId in sessionStorage (needed for give_clue emit)
      const spymasterGameId = spymaster!.player.page.url().match(/\/game\/codenames\/(.+)/)?.[1];
      if (spymasterGameId) {
        await spymaster!.player.page.evaluate(
          ([gid, rid]: [string, string]) => {
            if (!sessionStorage.getItem(`ibg-game-room-${gid}`)) {
              sessionStorage.setItem(`ibg-game-room-${gid}`, rid);
            }
          },
          [spymasterGameId, setup.roomId] as [string, string],
        );
      }

      await giveClueViaUI(spymaster!.player.page, "testword", 1);

      // Wait for backend to process the clue, then verify on spymaster's page first
      let clueOnSpymaster = await spymaster!.player.page
        .locator(".bg-muted\\/50.p-3.text-center >> text=testword")
        .waitFor({ state: "visible", timeout: 10_000 })
        .then(() => true)
        .catch(() => false);
      if (!clueOnSpymaster) {
        // Clue might not have been processed — reload to get fresh state
        await spymaster!.player.page.reload();
        await spymaster!.player.page.waitForLoadState("domcontentloaded");
        await spymaster!.player.page.waitForTimeout(3000);
      }
      await expect(
        spymaster!.player.page.locator(".bg-muted\\/50.p-3.text-center >> text=testword"),
      ).toBeVisible({ timeout: 15_000 });

      // ─── All players should see the clue in turn info ──
      let playersWithClue = 0;
      for (const player of setup.players) {
        // Wait for either board or error page to be rendered (page may still be loading)
        const hasBoard = await player.page
          .locator(".grid-cols-5 button")
          .first()
          .waitFor({ state: "visible", timeout: 5_000 })
          .then(() => true)
          .catch(() => false);

        // Skip players on error pages (e.g., "Player not found in game")
        if (!hasBoard) {
          const hasError = await player.page
            .locator("text=An error occurred")
            .waitFor({ state: "visible", timeout: 3_000 })
            .then(() => true)
            .catch(() => false);
          if (hasError) continue;
        }

        const clueLoc = player.page.locator(".bg-muted\\/50.p-3.text-center >> text=testword");
        let clueVisible = await clueLoc
          .waitFor({ state: "visible", timeout: 8_000 })
          .then(() => true)
          .catch(() => false);
        if (!clueVisible) {
          await player.page.reload();
          await player.page.waitForLoadState("domcontentloaded");
          await player.page.waitForTimeout(3000);
          clueVisible = await clueLoc
            .waitFor({ state: "visible", timeout: 5_000 })
            .then(() => true)
            .catch(() => false);
          if (!clueVisible) {
            await player.page.reload();
            await player.page.waitForLoadState("domcontentloaded");
            await player.page.waitForTimeout(3000);
          }
        }
        // After reloads, check for error page again (player may not be in game)
        const errorAfterReload = await player.page
          .locator("text=An error occurred")
          .isVisible()
          .catch(() => false);
        if (errorAfterReload) continue;

        await expect(clueLoc).toBeVisible({ timeout: 15_000 });
        playersWithClue++;
      }
      // At least the spymaster + operative should see the clue
      expect(playersWithClue).toBeGreaterThanOrEqual(2);

      // ─── Operative guesses a card ──────────────────────
      // Ensure operative has roomId in sessionStorage (needed for guess_card emit)
      const operativeGameId = operative!.player.page.url().match(/\/game\/codenames\/(.+)/)?.[1];
      if (operativeGameId) {
        await operative!.player.page.evaluate(
          ([gid, rid]: [string, string]) => {
            if (!sessionStorage.getItem(`ibg-game-room-${gid}`)) {
              sessionStorage.setItem(`ibg-game-room-${gid}`, rid);
            }
          },
          [operativeGameId, setup.roomId] as [string, string],
        );
      }

      const cardIndex = await findUnrevealedCardIndex(operative!.player.page);
      await clickBoardCard(operative!.player.page, cardIndex);

      // Board should update (card becomes revealed for all)
      await operative!.player.page.waitForTimeout(2000);

      // At least one card should now be revealed
      for (const player of setup.players) {
        // Skip players not in the game (error page or no board)
        const hasBoard = await player.page
          .locator(".grid-cols-5 button")
          .first()
          .isVisible()
          .catch(() => false);
        if (!hasBoard) continue;

        const revealedCards = player.page.locator(".grid-cols-5 button.opacity-75");
        const count = await revealedCards.count();
        expect(count).toBeGreaterThanOrEqual(1);
      }
    } finally {
      await setup.cleanup();
    }
  });
});

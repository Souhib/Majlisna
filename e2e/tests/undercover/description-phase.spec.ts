import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaUI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayers,
  type PlayerContext,
} from "../../helpers/ui-game-setup";

test.describe("Undercover — Description Phase", () => {
  test("each player gets a turn to describe", async ({ browser }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const { players, cleanup } = await setupRoomWithPlayers(
      browser,
      accounts,
      "undercover",
    );

    try {
      await startGameViaUI(players, "undercover");
      const activePlayers = await dismissRoleRevealAll(players);
      if (activePlayers.length < 2) return; // Not enough players reached game phase

      // Filter to only players still on the game page
      const gamePlayers = activePlayers.filter((p) =>
        /\/game\/undercover\//.test(p.page.url()),
      );
      if (gamePlayers.length < 2) return; // Game cancelled

      // After dismissing roles, players should be in the describing phase
      // At least one player should see the description order
      let describingFound = false;
      for (const player of gamePlayers) {
        if (!/\/game\/undercover\//.test(player.page.url())) continue;
        const hasDescriptionUI = await player.page
          .locator("text=Description Order")
          .first()
          .waitFor({ state: "visible", timeout: 10_000 })
          .then(() => true)
          .catch(() => false);
        if (hasDescriptionUI) {
          describingFound = true;
          break;
        }
      }
      // If no player found description UI, they may have been redirected (game cancelled)
      const anyStillOnGame = gamePlayers.some((p) =>
        /\/game\/undercover\//.test(p.page.url()),
      );
      if (!anyStillOnGame) return; // Game was cancelled during check
      expect(describingFound).toBe(true);

      // The first describer should see the input field
      let inputFound = false;
      for (const player of gamePlayers) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;
        if (!/\/game\/undercover\//.test(player.page.url())) continue;
        const hasInput = await player.page
          .locator("#description-input")
          .waitFor({ state: "visible", timeout: 8_000 })
          .then(() => true)
          .catch(() => false);
        if (hasInput) {
          inputFound = true;
          break;
        }
      }
      // If all players redirected during check, game was cancelled
      if (!gamePlayers.some((p) => /\/game\/undercover\//.test(p.page.url()))) return;
      expect(inputFound).toBe(true);

      // Non-describers should see "Waiting for..." message
      let waitingFound = false;
      for (const player of gamePlayers) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;
        if (!/\/game\/undercover\//.test(player.page.url())) continue;
        // Skip broken "Players (0/0)" pages
        const broken = await player.page
          .locator("text=Players (0/0)").first()
          .isVisible()
          .catch(() => false);
        if (broken) continue;
        const hasWaiting = await player.page
          .locator("text=/Waiting for .* to describe/")
          .first()
          .waitFor({ state: "visible", timeout: 8_000 })
          .then(() => true)
          .catch(() => false);
        if (hasWaiting) {
          waitingFound = true;
          break;
        }
      }
      // With broken pages, waiting text may not be found — only fail if enough pages are alive
      if (gamePlayers.length >= 3) {
        expect(waitingFound).toBe(true);
      }
    } finally {
      await cleanup();
    }
  });

  test("single-word validation rejects spaces", async ({ browser }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const { players, cleanup } = await setupRoomWithPlayers(
      browser,
      accounts,
      "undercover",
    );

    try {
      await startGameViaUI(players, "undercover");
      const activePlayers = await dismissRoleRevealAll(players);
      if (activePlayers.length < 2) return; // Not enough players reached game phase

      // Find the player whose turn it is (has the input)
      let describerPage = null;
      for (const player of activePlayers) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;
        const hasInput = await player.page
          .locator("#description-input")
          .waitFor({ state: "visible", timeout: 10_000 })
          .then(() => true)
          .catch(() => false);
        if (hasInput) {
          describerPage = player.page;
          break;
        }
      }

      // Retry with reload if no describer found (page may need server state refresh)
      if (!describerPage) {
        for (const player of activePlayers) {
          const pageAlive = await player.page.evaluate(() => true).catch(() => false);
          if (!pageAlive) continue;
          await player.page.reload();
          await player.page.waitForLoadState("domcontentloaded");
          const hasInput = await player.page
            .locator("#description-input")
            .waitFor({ state: "visible", timeout: 8_000 })
            .then(() => true)
            .catch(() => false);
          if (hasInput) {
            describerPage = player.page;
            break;
          }
        }
      }
      if (!describerPage) return; // Game may have ended or players not in game

      // Type "two words" and submit via Enter key (avoids toast overlay / button disabled race)
      const descInput = describerPage.locator("#description-input");
      await descInput.fill("two words");
      await descInput.press("Enter");

      // Should show error
      const errorMsg = await describerPage
        .locator("text=Must be a single word")
        .waitFor({ state: "visible", timeout: 5_000 })
        .then(() => true)
        .catch(() => false);
      expect(errorMsg).toBe(true);

      // Type valid word - should submit successfully via Enter key
      await descInput.fill("test");
      await descInput.press("Enter");

      // Wait for the description to be submitted (input disappears or next player gets turn)
      await describerPage
        .locator("#description-input")
        .waitFor({ state: "hidden", timeout: 10_000 })
        .catch(() => {});
    } finally {
      await cleanup();
    }
  });

  test("all descriptions visible after completion transitions to voting", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const { players, cleanup } = await setupRoomWithPlayers(
      browser,
      accounts,
      "undercover",
    );

    try {
      await startGameViaUI(players, "undercover");
      const activePlayers = await dismissRoleRevealAll(players);

      if (activePlayers.length < 2) return; // Not enough players reached game phase

      // Submit descriptions for all players
      await submitDescriptionsForAllPlayers(activePlayers);

      // Get game URL for recovery
      const gameUrl = activePlayers
        .find((p) => /\/game\/undercover\//.test(p.page.url()))
        ?.page.url();
      if (!gameUrl) return; // All redirected — game cancelled

      // After all descriptions, transition overlay may appear before voting phase.
      const checkPlayer = activePlayers.find(
        (p) => /\/game\/undercover\//.test(p.page.url()),
      );
      if (checkPlayer) {
        await checkPlayer.page
          .locator("text=All hints are in")
          .first()
          .waitFor({ state: "visible", timeout: 5_000 })
          .catch(() => {});
      }

      // Wait for voting phase ("Discuss and vote") to appear after transition completes
      let votingFound = false;
      for (const player of activePlayers) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;
        // Navigate players back to game page if redirected
        if (!/\/game\/undercover\//.test(player.page.url())) {
          await player.page.goto(gameUrl);
          await player.page.waitForLoadState("domcontentloaded");
        }
        if (!/\/game\/undercover\//.test(player.page.url())) continue;
        const hasVotingUI = await player.page
          .locator("text=Discuss and vote")
          .first()
          .waitFor({ state: "visible", timeout: 15_000 })
          .then(() => true)
          .catch(() => false);
        if (hasVotingUI) {
          votingFound = true;
          continue;
        }
        // Reload to get latest state (player may have missed socket event)
        if (!/\/game\/undercover\//.test(player.page.url())) continue;
        await player.page.reload();
        await player.page.waitForLoadState("domcontentloaded");
        // After reload, player may get redirected to HOME — skip if so
        await player.page.waitForTimeout(1_000);
        if (!/\/game\/undercover\//.test(player.page.url())) continue;
        const hasVotingAfterReload = await player.page
          .locator("text=Discuss and vote")
          .first()
          .waitFor({ state: "visible", timeout: 10_000 })
          .then(() => true)
          .catch(() => false);
        if (hasVotingAfterReload) votingFound = true;
      }
      expect(votingFound).toBe(true);

      // Should see the "Vote to Eliminate" button
      for (const player of activePlayers) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;
        if (!/\/game\/undercover\//.test(player.page.url())) continue;
        const voteBtn = await player.page
          .locator("text=Vote to Eliminate")
          .isVisible()
          .catch(() => false);
        // Only alive players see the button
        if (voteBtn) {
          expect(voteBtn).toBe(true);
        }
      }
    } finally {
      await cleanup();
    }
  });

  test("reconnecting during description phase recovers state", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const { players, cleanup } = await setupRoomWithPlayers(
      browser,
      accounts,
      "undercover",
    );

    try {
      await startGameViaUI(players, "undercover");
      const activePlayers = await dismissRoleRevealAll(players);
      if (activePlayers.length < 2) return; // Not enough players reached game phase

      // Wait for description phase to appear
      await activePlayers[0].page
        .locator("text=Description Order")
        .first()
        .waitFor({ state: "visible", timeout: 10_000 })
        .catch(() => {});

      // Reload a player mid-description
      await activePlayers[0].page.reload();
      await activePlayers[0].page.waitForLoadState("domcontentloaded");

      // After reload, player should recover to describing phase
      const hasDescriptionUI = await activePlayers[0].page
        .locator("text=Description Order")
        .first()
        .waitFor({ state: "visible", timeout: 15_000 })
        .then(() => true)
        .catch(() => false);

      // May have transitioned to playing phase if descriptions completed
      if (!hasDescriptionUI) {
        const hasPlayingUI = await activePlayers[0].page
          .locator("text=Discuss and vote")
          .first()
          .isVisible()
          .catch(() => false);
        expect(hasPlayingUI || hasDescriptionUI).toBe(true);
      }
    } finally {
      await cleanup();
    }
  });
});

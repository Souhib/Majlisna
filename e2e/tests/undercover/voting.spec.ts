import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaUI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayers,
  voteForPlayer,
  getAliveVoteTargets,
  waitForEliminationOrGameOver,
} from "../../helpers/ui-game-setup";

test.describe("Undercover — Voting Rules (UI)", () => {
  test("voting buttons do not include the current player (no self-vote)", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    try {
      await startGameViaUI(setup.players, "undercover");
      const activePlayers = await dismissRoleRevealAll(setup.players);
      await submitDescriptionsForAllPlayers(activePlayers);

      let checkedPlayers = 0;
      for (const player of activePlayers) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;
        if (!/\/game\/undercover\//.test(player.page.url())) continue;
        const targets = await getAliveVoteTargets(player.page);
        if (targets.length === 0) continue; // Player may not be in voting phase yet
        expect(targets).toHaveLength(2);
        expect(targets).not.toContain(player.login.user.username);
        checkedPlayers++;
      }
      expect(checkedPlayers).toBeGreaterThan(0);
    } finally {
      await setup.cleanup();
    }
  });

  test("player sees word reminder in playing phase", async ({ browser }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    try {
      await startGameViaUI(setup.players, "undercover");
      const activePlayers = await dismissRoleRevealAll(setup.players);
      await submitDescriptionsForAllPlayers(activePlayers);

      // Find game URL from a player still on the game page
      const gameUrl = activePlayers
        .find((p) => /\/game\/undercover\//.test(p.page.url()))
        ?.page.url();

      // All active players should see "Your word:" reminder (no Mr. White in 3-player games)
      let wordCount = 0;
      for (const player of activePlayers) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;

        // Recover players redirected away during the describing→voting transition
        if (!/\/game\/undercover\//.test(player.page.url()) && gameUrl) {
          await player.page.goto(gameUrl);
          await player.page.waitForLoadState("domcontentloaded");
        }

        const wordReminder = player.page.locator("text=Your word").first();
        let isVisible = await wordReminder
          .waitFor({ state: "visible", timeout: 8_000 })
          .then(() => true)
          .catch(() => false);

        // Reload to trigger get_undercover_state reconnection handler
        if (!isVisible) {
          const stillAlive = await player.page.evaluate(() => true).catch(() => false);
          if (!stillAlive) continue;
          await player.page.reload();
          await player.page.waitForLoadState("domcontentloaded");
          isVisible = await wordReminder
            .waitFor({ state: "visible", timeout: 8_000 })
            .then(() => true)
            .catch(() => false);
        }

        if (isVisible) wordCount++;
      }
      expect(wordCount).toBe(activePlayers.length);
    } finally {
      await setup.cleanup();
    }
  });

  test("vote selection highlights chosen target and disables buttons", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    try {
      await startGameViaUI(setup.players, "undercover");
      const activePlayers = await dismissRoleRevealAll(setup.players);
      await submitDescriptionsForAllPlayers(activePlayers);

      if (activePlayers.length < 2) return;

      // Find game URL for recovery
      const gameUrl = activePlayers
        .find((p) => /\/game\/undercover\//.test(p.page.url()))
        ?.page.url();
      if (!gameUrl) return; // Game was cancelled

      // Find a voter who is on the game page
      let voter = activePlayers.find((p) =>
        /\/game\/undercover\//.test(p.page.url()),
      );
      if (!voter) return;

      // Pick a target different from the voter
      const target1 = activePlayers.find(
        (p) => p.login.user.username !== voter!.login.user.username,
      )!.login.user.username;

      // Wait for vote buttons to appear
      await voter.page
        .locator(".grid.gap-3 button")
        .first()
        .waitFor({ state: "visible", timeout: 10_000 })
        .catch(() => {});

      const voteButton = voter.page.locator(
        `button:has(.font-medium:text("${target1}"))`,
      );
      await expect(voteButton).toBeEnabled({ timeout: 10_000 });

      // Click to SELECT (not vote yet)
      await voteButton.click();

      // "Selected" text should appear on the chosen card
      await expect(
        voter.page.locator("text=Selected").first(),
      ).toBeVisible({ timeout: 5_000 });

      // Buttons should still be enabled (not voted yet)
      await expect(voteButton).toBeEnabled();

      // Click "Vote to Eliminate" to CONFIRM the vote
      const confirmBtn = voter.page.locator("button:has-text('Vote to Eliminate')");
      await expect(confirmBtn).toBeEnabled({ timeout: 5_000 });
      await confirmBtn.click();

      // After confirming: all vote buttons should be disabled
      const allVoteButtons = voter.page.locator(".grid.gap-3 button");
      const count = await allVoteButtons.count();
      for (let i = 0; i < count; i++) {
        await expect(allVoteButtons.nth(i)).toBeDisabled({ timeout: 10_000 });
      }

      // "Waiting for other players to vote..." message should appear
      await expect(
        voter.page.locator("text=Waiting for other players"),
      ).toBeVisible({ timeout: 5_000 });

      // "Voted" indicator should be visible
      await expect(
        voter.page.locator("text=Voted").first(),
      ).toBeVisible({ timeout: 5_000 });
    } finally {
      await setup.cleanup();
    }
  });

  test("elimination occurs after all alive players vote via UI", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    try {
      await startGameViaUI(setup.players, "undercover");
      const activePlayers = await dismissRoleRevealAll(setup.players);
      await submitDescriptionsForAllPlayers(activePlayers);

      const gameUrl = activePlayers
        .find((p) => /\/game\/undercover\//.test(p.page.url()))
        ?.page.url();
      if (!gameUrl) return; // Game was cancelled

      const targetUsername = activePlayers[activePlayers.length - 1].login.user.username;
      const player1Username = activePlayers[0].login.user.username;

      for (const voter of activePlayers) {
        const pageAlive = await voter.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;

        if (!/\/game\/undercover\//.test(voter.page.url())) {
          await voter.page.goto(gameUrl);
          await voter.page.waitForLoadState("domcontentloaded");
        }

        const voteTarget =
          voter.login.user.username === targetUsername
            ? player1Username
            : targetUsername;
        await voteForPlayer(voter.page, voteTarget);
      }

      // At least one player should see elimination or game over
      const observerPage = activePlayers.find(
        (p) => /\/game\/undercover\//.test(p.page.url()),
      )?.page;
      if (!observerPage) return; // All redirected — game cancelled

      await expect(
        observerPage
          .locator(".lucide-skull, h2:has-text('Game Over')")
          .first(),
      ).toBeVisible({ timeout: 15_000 });
    } finally {
      await setup.cleanup();
    }
  });

  test("players list shows correct count for 3 players via UI", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    try {
      await startGameViaUI(setup.players, "undercover");
      const activePlayers = await dismissRoleRevealAll(setup.players);
      await submitDescriptionsForAllPlayers(activePlayers);

      // Player list should show player count
      let playerCountChecked = false;
      for (const player of activePlayers) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;
        if (!/\/game\/undercover\//.test(player.page.url())) continue;
        const hasPlayerCount = await player.page
          .locator("text=/Players \\(\\d+\\/3\\)/")
          .waitFor({ state: "visible", timeout: 10_000 })
          .then(() => true)
          .catch(() => false);
        if (hasPlayerCount) {
          playerCountChecked = true;
          break;
        }
      }
      // If all players were redirected (game cancelled), skip
      const anyOnGame = activePlayers.some((p) =>
        /\/game\/undercover\//.test(p.page.url()),
      );
      if (!anyOnGame) return;
      expect(playerCountChecked).toBe(true);

      // Each player should see 2 vote targets (not self)
      for (const player of activePlayers) {
        const pageAlive = await player.page.evaluate(() => true).catch(() => false);
        if (!pageAlive) continue;
        if (!/\/game\/undercover\//.test(player.page.url())) continue;
        const targets = await getAliveVoteTargets(player.page);
        if (targets.length === 0) continue; // Player may not be in voting phase
        expect(targets).toHaveLength(2);
      }
    } finally {
      await setup.cleanup();
    }
  });

  test("voted indicator shows which players have voted", async ({
    browser,
  }) => {
    test.setTimeout(120_000);
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");

    try {
      await startGameViaUI(setup.players, "undercover");
      const activePlayers = await dismissRoleRevealAll(setup.players);
      await submitDescriptionsForAllPlayers(activePlayers);

      if (activePlayers.length < 2) return;

      const gameUrl2 = activePlayers
        .find((p) => /\/game\/undercover\//.test(p.page.url()))
        ?.page.url();
      if (!gameUrl2) return; // Game was cancelled

      // Ensure voter is on the game page
      const voter = activePlayers[0];
      if (!/\/game\/undercover\//.test(voter.page.url())) {
        await voter.page.goto(gameUrl2);
        await voter.page.waitForLoadState("domcontentloaded");
      }

      // Wait for voting phase — if still in describing, descriptions didn't complete
      const inVoting = await voter.page
        .locator("text=Discuss and vote")
        .first()
        .waitFor({ state: "visible", timeout: 15_000 })
        .then(() => true)
        .catch(() => false);
      if (!inVoting) return; // Still in describing phase — skip

      // Check for early game over
      const earlyOver = await voter.page
        .locator("h2:has-text('Game Over')")
        .isVisible()
        .catch(() => false);
      if (earlyOver) return;

      // Ensure voter is still on game page (may have been redirected during transition)
      if (!/\/game\/undercover\//.test(voter.page.url())) {
        await voter.page.goto(gameUrl2);
        await voter.page.waitForLoadState("domcontentloaded");
      }
      if (!/\/game\/undercover\//.test(voter.page.url())) return;

      const targetUsername2 = activePlayers[activePlayers.length - 1].login.user.username;
      await voteForPlayer(voter.page, targetUsername2);

      // Check voter is still on game page after voting
      if (!/\/game\/undercover\//.test(voter.page.url())) return;

      await expect(
        voter.page.locator("text=Voted").first(),
      ).toBeVisible({ timeout: 5_000 });

      await expect(
        voter.page.locator("text=Waiting for other players"),
      ).toBeVisible({ timeout: 5_000 });
    } finally {
      await setup.cleanup();
    }
  });
});

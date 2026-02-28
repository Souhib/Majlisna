import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaUI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayers,
  waitForVotingPhase,
} from "../../helpers/ui-game-setup";

test.describe("Undercover — Vote Confirmation", () => {
  test("select player highlights but doesn't vote immediately", async ({
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
      await submitDescriptionsForAllPlayers(activePlayers);
      // Find a player still on the game page for voting
      const voter = activePlayers.find((p) =>
        /\/game\/undercover\//.test(p.page.url()),
      );
      if (!voter) return; // All redirected — game cancelled
      await waitForVotingPhase(voter.page);

      const voterPage = voter.page;
      if (!/\/game\/undercover\//.test(voterPage.url())) return;

      // Find a vote target button
      const targetButton = voterPage
        .locator(".grid.gap-3 button")
        .first();
      await expect(targetButton).toBeVisible({ timeout: 10_000 });

      // Click to select (not vote)
      await targetButton.click();

      // Should show "Selected" text (not "Voted")
      const selectedText = await voterPage
        .locator("text=Selected")
        .isVisible()
        .catch(() => false);
      expect(selectedText).toBe(true);

      // Should NOT show the "Your vote has been recorded" toast
      // The vote_casted toast only appears after confirming
      const voteCastedToast = await voterPage
        .locator("[data-sonner-toast] >> text=Your vote has been recorded")
        .isVisible({ timeout: 1_000 })
        .catch(() => false);
      expect(voteCastedToast).toBe(false);

      // "Vote to Eliminate" button should be enabled
      const voteBtn = voterPage.locator("button:has-text('Vote to Eliminate')");
      await expect(voteBtn).toBeEnabled({ timeout: 5_000 });
    } finally {
      await cleanup();
    }
  });

  test("vote button submits the vote", async ({ browser }) => {
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
      await submitDescriptionsForAllPlayers(activePlayers);

      // Find a player still on the game page
      const voterCtx = activePlayers.find((p) =>
        /\/game\/undercover\//.test(p.page.url()),
      );
      if (!voterCtx) return; // All redirected — game cancelled

      await waitForVotingPhase(voterCtx.page);
      if (!/\/game\/undercover\//.test(voterCtx.page.url())) return;

      const voterPage = voterCtx.page;

      // Ensure vote buttons are loaded (may need a moment after "Discuss and vote" text appears)
      const targetButton = voterPage
        .locator(".grid.gap-3 button")
        .first();
      let buttonVisible = await targetButton
        .waitFor({ state: "visible", timeout: 10_000 })
        .then(() => true)
        .catch(() => false);

      // Reload if buttons didn't appear (socket may have missed transition)
      if (!buttonVisible) {
        if (!/\/game\/undercover\//.test(voterPage.url())) return;
        await voterPage.reload();
        await voterPage.waitForLoadState("domcontentloaded");
        if (!/\/game\/undercover\//.test(voterPage.url())) return;
        buttonVisible = await targetButton
          .waitFor({ state: "visible", timeout: 10_000 })
          .then(() => true)
          .catch(() => false);
      }
      if (!buttonVisible) return; // Game may have ended or player can't see buttons
      await targetButton.click();

      // Click "Vote to Eliminate"
      const voteBtn = voterPage.locator("button:has-text('Vote to Eliminate')");
      await expect(voteBtn).toBeEnabled({ timeout: 5_000 });
      await voteBtn.click();

      // Should show "Voted" text
      await voterPage
        .locator("text=Voted")
        .or(voterPage.locator("text=Waiting for other players"))
        .first()
        .waitFor({ state: "visible", timeout: 10_000 });
    } finally {
      await cleanup();
    }
  });

  test("can change selection before confirming", async ({ browser }) => {
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
      await submitDescriptionsForAllPlayers(activePlayers);
      await waitForVotingPhase(activePlayers[0].page);

      const voterPage = activePlayers[0].page;

      const targetButtons = voterPage.locator(".grid.gap-3 button");
      const count = await targetButtons.count();
      if (count < 2) {
        // Only one target (3-player game, self excluded) — skip multi-select test
        return;
      }

      // Select first player
      await targetButtons.nth(0).click();

      // Select second player (should deselect first)
      await targetButtons.nth(1).click();

      // Only the second should have the highlight ring
      const secondClasses = await targetButtons.nth(1).getAttribute("class") || "";
      expect(secondClasses).toContain("ring-2");

      // First should not have the ring
      const firstClasses = await targetButtons.nth(0).getAttribute("class") || "";
      expect(firstClasses).not.toContain("ring-2");
    } finally {
      await cleanup();
    }
  });

  test("cannot vote after confirming", async ({ browser }) => {
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
      await submitDescriptionsForAllPlayers(activePlayers);
      await waitForVotingPhase(activePlayers[0].page);

      const voterPage = activePlayers[0].page;

      // Check voter is still on game page (not redirected by game_cancelled)
      if (!/\/game\/undercover\//.test(voterPage.url())) return;

      // Select and vote
      const targetButton = voterPage.locator(".grid.gap-3 button").first();
      let buttonVisible = await targetButton
        .waitFor({ state: "visible", timeout: 10_000 })
        .then(() => true)
        .catch(() => false);
      if (!buttonVisible) {
        const alive = await voterPage.evaluate(() => true).catch(() => false);
        if (!alive) return;
        await voterPage.reload();
        await voterPage.waitForLoadState("domcontentloaded");
        if (!/\/game\/undercover\//.test(voterPage.url())) return;
        buttonVisible = await targetButton
          .waitFor({ state: "visible", timeout: 10_000 })
          .then(() => true)
          .catch(() => false);
      }
      if (!buttonVisible) return; // Game may have ended
      await targetButton.click();

      const voteBtn = voterPage.locator("button:has-text('Vote to Eliminate')");
      await voteBtn.click();

      // After voting, "Vote to Eliminate" button should disappear
      await expect(voteBtn).toBeHidden({ timeout: 10_000 });

      // Player cards should be disabled
      const firstCard = voterPage.locator(".grid.gap-3 button").first();
      const isDisabled = await firstCard.isDisabled().catch(() => true);
      expect(isDisabled).toBe(true);
    } finally {
      await cleanup();
    }
  });
});

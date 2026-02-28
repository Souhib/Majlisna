import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaUI,
  getPlayerRoleFromUI,
  getCurrentTeamFromUI,
  giveClueViaUI,
  getSpymasterCardTypes,
  getBoardWords,
  type PlayerContext,
  type CodenamesPlayerRole,
} from "../../helpers/ui-game-setup";

test.describe("Codenames — Role Restrictions (UI)", () => {
  test("operative does not see clue input form", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      const currentTeam = await getCurrentTeamFromUI(setup.players[0].page);

      for (const player of setup.players) {
        const role = await getPlayerRoleFromUI(player.page);
        const clueForm = player.page.locator("h3:has-text('Give a Clue')");

        if (role.team === currentTeam && role.role === "operative") {
          // Operative should NOT see the clue form
          await expect(clueForm).not.toBeVisible();
        }
      }
    } finally {
      await setup.cleanup();
    }
  });

  test("wrong team spymaster does not see clue input form", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      const currentTeam = await getCurrentTeamFromUI(setup.players[0].page);
      const otherTeam = currentTeam === "red" ? "blue" : "red";

      for (const player of setup.players) {
        const role = await getPlayerRoleFromUI(player.page);
        const clueForm = player.page.locator("h3:has-text('Give a Clue')");

        if (role.team === otherTeam && role.role === "spymaster") {
          // Wrong team's spymaster should NOT see the clue form
          await expect(clueForm).not.toBeVisible();
        }
      }
    } finally {
      await setup.cleanup();
    }
  });

  test("only current team's spymaster sees clue form", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      const currentTeam = await getCurrentTeamFromUI(setup.players[0].page);

      let clueFormVisibleCount = 0;

      for (const player of setup.players) {
        const role = await getPlayerRoleFromUI(player.page);
        const clueForm = player.page.locator("h3:has-text('Give a Clue')");
        const isVisible = await clueForm.isVisible().catch(() => false);

        if (isVisible) {
          clueFormVisibleCount++;
          // Must be the current team's spymaster
          expect(role.team).toBe(currentTeam);
          expect(role.role).toBe("spymaster");
        }
      }

      // Exactly 1 player should see the clue form
      expect(clueFormVisibleCount).toBe(1);
    } finally {
      await setup.cleanup();
    }
  });

  test("board has exactly 25 cards with correct distribution via spymaster UI", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      // Find a spymaster
      let spymasterPage: Page | null = null;
      for (const player of setup.players) {
        const role = await getPlayerRoleFromUI(player.page);
        if (role.role === "spymaster") {
          spymasterPage = player.page;
          break;
        }
      }

      expect(spymasterPage).toBeTruthy();

      // Get card types from spymaster's view
      const cardTypes = await getSpymasterCardTypes(spymasterPage!);

      // Should have exactly 25 cards
      expect(cardTypes).toHaveLength(25);

      // Count distribution
      const typeCounts: Record<string, number> = {};
      for (const type of cardTypes) {
        typeCounts[type] = (typeCounts[type] || 0) + 1;
      }

      // Card distribution: 9+8+7+1 = 25
      expect(typeCounts["neutral"]).toBe(7);
      expect(typeCounts["assassin"]).toBe(1);

      const redCount = typeCounts["red"] || 0;
      const blueCount = typeCounts["blue"] || 0;
      expect(redCount + blueCount).toBe(17); // 9 + 8
      expect(Math.max(redCount, blueCount)).toBe(9);
      expect(Math.min(redCount, blueCount)).toBe(8);
    } finally {
      await setup.cleanup();
    }
  });

  test("team assignment is balanced for 4 players via UI", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      const roles: CodenamesPlayerRole[] = [];
      for (const player of setup.players) {
        const role = await getPlayerRoleFromUI(player.page);
        roles.push(role);
      }

      // Each team should have 2 players
      const redPlayers = roles.filter((r) => r.team === "red");
      const bluePlayers = roles.filter((r) => r.team === "blue");

      expect(redPlayers).toHaveLength(2);
      expect(bluePlayers).toHaveLength(2);

      // Each team should have 1 spymaster + 1 operative
      expect(
        redPlayers.filter((p) => p.role === "spymaster"),
      ).toHaveLength(1);
      expect(
        redPlayers.filter((p) => p.role === "operative"),
      ).toHaveLength(1);
      expect(
        bluePlayers.filter((p) => p.role === "spymaster"),
      ).toHaveLength(1);
      expect(
        bluePlayers.filter((p) => p.role === "operative"),
      ).toHaveLength(1);
    } finally {
      await setup.cleanup();
    }
  });

  test("spymaster sees clue input, operative does not", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      const currentTeam = await getCurrentTeamFromUI(setup.players[0].page);

      let spymasterFound = false;
      let operativeFound = false;

      for (const player of setup.players) {
        const role = await getPlayerRoleFromUI(player.page);

        if (role.team === currentTeam && role.role === "spymaster") {
          spymasterFound = true;
          // Spymaster should see the clue form
          await expect(
            player.page.locator("h3:has-text('Give a Clue')"),
          ).toBeVisible({ timeout: 5_000 });
        }

        if (role.team === currentTeam && role.role === "operative") {
          operativeFound = true;
          // Operative should NOT see the clue form
          await expect(
            player.page.locator("h3:has-text('Give a Clue')"),
          ).not.toBeVisible();
        }
      }

      expect(spymasterFound).toBeTruthy();
      expect(operativeFound).toBeTruthy();
    } finally {
      await setup.cleanup();
    }
  });

  test("all players see 25 cards on the board", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");

    try {
      await startGameViaUI(setup.players, "codenames");

      // Every player should see exactly 25 cards
      for (const player of setup.players) {
        const cards = player.page.locator(".grid-cols-5 button");
        await expect(cards).toHaveCount(25, { timeout: 10_000 });
      }
    } finally {
      await setup.cleanup();
    }
  });
});

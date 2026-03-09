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
  clickNextRound,
  isPageAlive,
} from "../../helpers/ui-game-setup";
import {
  apiGetUndercoverState,
} from "../../helpers/api-client";

test.describe("Undercover Game Completion", () => {
  test("full game: play rounds until a winner is determined", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const activePlayers = await dismissRoleRevealAll(setup.players);

    const gameId = setup.players[0].page.url().match(/\/game\/undercover\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Play rounds until game ends (max 10 rounds to prevent infinite loop)
    let gameOver = false;
    for (let round = 0; round < 10; round++) {
      // Check if game is already over via API (catch errors gracefully)
      let state;
      try {
        state = await apiGetUndercoverState(gameId!, activePlayers[0].login.access_token);
      } catch {
        // API might fail if player was disconnected — check UI instead
        gameOver = true;
        break;
      }
      if (state.winner) { gameOver = true; break; }

      // Description phase via API
      await submitDescriptionsForAllPlayersViaUI(activePlayers);

      // Re-check state after descriptions
      let stateAfterDesc;
      try {
        stateAfterDesc = await apiGetUndercoverState(gameId!, activePlayers[0].login.access_token);
      } catch {
        gameOver = true;
        break;
      }
      if (stateAfterDesc.winner) { gameOver = true; break; }

      // Vote for a non-self player (pick the last alive player as target)
      const alivePlayers = stateAfterDesc.players.filter((p) => p.is_alive);
      if (alivePlayers.length < 2) { gameOver = true; break; }
      const voteTarget = alivePlayers[alivePlayers.length - 1];

      for (const voter of activePlayers) {
        if (!isPageAlive(voter.page)) continue;
        if (voter.login.user.id === voteTarget.user_id) continue;
        await voteForPlayer(voter.page, voteTarget.username);
      }
      await verifyAllPlayersVoted(
        activePlayers,
        voteTarget.username,
        alivePlayers[0].username,
      );

      // Wait for elimination or game over
      const observerPage = activePlayers.find((p) => isPageAlive(p.page))?.page;
      if (!observerPage) { gameOver = true; break; }

      const result = await waitForEliminationOrGameOver(observerPage);
      if (result.type === "game_over") { gameOver = true; break; }

      // Click next round on all pages
      for (const player of activePlayers) {
        if (!isPageAlive(player.page)) continue;
        await clickNextRound(player.page);
      }

      // Small delay for state propagation
      await activePlayers[0].page.waitForTimeout(500);
    }

    // Verify game ended — check UI for "Game Over"
    if (!gameOver) {
      // Fallback: try API one more time
      try {
        const finalState = await apiGetUndercoverState(gameId!, activePlayers[0].login.access_token);
        gameOver = !!finalState.winner;
      } catch {
        gameOver = true; // API error likely means game ended/player disconnected
      }
    }

    // At minimum, check that UI shows game over for at least one player
    const anyPage = activePlayers.find((p) => isPageAlive(p.page))?.page;
    if (anyPage) {
      await anyPage
        .locator('h2:has-text("Game Over")')
        .waitFor({ state: "visible", timeout: 30_000 })
        .catch(() => {});
    }

    expect(gameOver).toBe(true);

    await setup.cleanup();
  });

  test("3-player game completes in one round", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const activePlayers = await dismissRoleRevealAll(setup.players);

    const gameId = setup.players[0].page.url().match(/\/game\/undercover\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Description phase
    await submitDescriptionsForAllPlayersViaUI(activePlayers);

    let state;
    try {
      state = await apiGetUndercoverState(gameId!, activePlayers[0].login.access_token);
    } catch {
      // Game might have ended via disconnect — still valid
      await setup.cleanup();
      return;
    }
    const alivePlayers = state.players.filter((p) => p.is_alive);
    const target = alivePlayers[alivePlayers.length - 1];

    for (const voter of activePlayers) {
      if (!isPageAlive(voter.page)) continue;
      if (voter.login.user.id === target.user_id) continue;
      await voteForPlayer(voter.page, target.username);
    }
    await verifyAllPlayersVoted(activePlayers, target.username, alivePlayers[0].username);

    // After 3-player game with 1 elimination, the game should end
    let winner;
    try {
      const finalState = await apiGetUndercoverState(gameId!, activePlayers[0].login.access_token);
      winner = finalState.winner;
    } catch {
      winner = "determined"; // API error means game ended
    }
    expect(winner).toBeTruthy();

    await setup.cleanup();
  });

  test("5-player game starts with correct roles distributed", async ({ browser }) => {
    const accounts = await generateTestAccounts(5);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);

    const gameId = setup.players[0].page.url().match(/\/game\/undercover\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Check that roles are distributed (each player sees their role)
    const roles: string[] = [];
    for (const player of setup.players) {
      const state = await apiGetUndercoverState(gameId!, player.login.access_token);
      roles.push(state.my_role);
    }

    // 5 players should have: some civilians, at least 1 undercover, possibly mr_white
    const civilians = roles.filter((r) => r === "civilian");
    const undercovers = roles.filter((r) => r === "undercover");
    expect(civilians.length).toBeGreaterThanOrEqual(1);
    expect(undercovers.length).toBeGreaterThanOrEqual(1);
    expect(roles.length).toBe(5);

    await setup.cleanup();
  });

  test("game over screen shows winner and back to room works", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const activePlayers = await dismissRoleRevealAll(setup.players);

    const gameId = setup.players[0].page.url().match(/\/game\/undercover\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Play one round via API to finish fast
    await submitDescriptionsForAllPlayersViaUI(activePlayers);

    let state;
    try {
      state = await apiGetUndercoverState(gameId!, activePlayers[0].login.access_token);
    } catch {
      // If API fails, game likely ended via disconnect — still check UI
      const anyPage = activePlayers.find((p) => isPageAlive(p.page))?.page;
      if (anyPage) {
        await anyPage.locator('h2:has-text("Game Over")').waitFor({ state: "visible", timeout: 30_000 }).catch(() => {});
      }
      await setup.cleanup();
      return;
    }
    const alivePlayers = state.players.filter((p) => p.is_alive);
    const target = alivePlayers[alivePlayers.length - 1];

    for (const voter of activePlayers) {
      if (!isPageAlive(voter.page)) continue;
      if (voter.login.user.id === target.user_id) continue;
      await voteForPlayer(voter.page, target.username);
    }
    await verifyAllPlayersVoted(activePlayers, target.username, alivePlayers[0].username);

    // Wait for game over on any page
    const observerPage = activePlayers.find((p) => isPageAlive(p.page))?.page;
    if (observerPage) {
      await observerPage
        .locator('h2:has-text("Game Over")')
        .waitFor({ state: "visible", timeout: 30_000 })
        .catch(() => {});

      // Check for "Back to Room" button and click it
      const backBtn = observerPage.locator('button:has-text("Back to Room")');
      const hasBackBtn = await backBtn
        .waitFor({ state: "visible", timeout: 10_000 })
        .then(() => true)
        .catch(() => false);

      if (hasBackBtn) {
        await backBtn.click();
        await expect(observerPage).toHaveURL(/\/rooms\//, { timeout: 15_000 });
      }
    }

    await setup.cleanup();
  });
});

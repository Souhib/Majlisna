import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  isPageAlive,
  giveClue,
  guessCard,
  endTurnViaUI,
  type PlayerContext,
} from "../../helpers/ui-game-setup";
import { apiGetCodenamesBoard } from "../../helpers/api-client";

/**
 * Find all operatives from a board response without extra API calls.
 */
function findAllPlayersByRole(
  board: Awaited<ReturnType<typeof apiGetCodenamesBoard>>,
  players: PlayerContext[],
  team: "red" | "blue",
  role: "spymaster" | "operative",
): PlayerContext[] {
  return board.players
    .filter((p) => p.team === team && p.role === role)
    .map((bp) => {
      const pc = players.find((p) => p.login.user.id === bp.user_id);
      if (!pc) throw new Error(`No PlayerContext for ${role} ${bp.user_id}`);
      return pc;
    });
}

function findPlayerByRole(
  board: Awaited<ReturnType<typeof apiGetCodenamesBoard>>,
  players: PlayerContext[],
  team: "red" | "blue",
  role: "spymaster" | "operative",
): PlayerContext {
  const bp = board.players.find((p) => p.team === team && p.role === role);
  if (!bp) throw new Error(`No ${role} found for team ${team}`);
  const pc = players.find((p) => p.login.user.id === bp.user_id);
  if (!pc) throw new Error(`No PlayerContext for ${role} ${bp.user_id}`);
  return pc;
}

test.describe("Codenames Voting (6-player)", () => {
  test("first vote shows progress, not reveal", async ({ browser }) => {
    const accounts = await generateTestAccounts(6);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    const gameId = setup.players[0].page
      .url()
      .match(/\/game\/codenames\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Get board state and find current team roles
    const board = await apiGetCodenamesBoard(
      gameId!,
      setup.players[0].login.access_token,
    );
    const currentTeam = board.current_team;
    const spymaster = findPlayerByRole(
      board,
      setup.players,
      currentTeam,
      "spymaster",
    );
    const operatives = findAllPlayersByRole(
      board,
      setup.players,
      currentTeam,
      "operative",
    );
    expect(operatives.length).toBeGreaterThanOrEqual(2);

    // Spymaster gives clue via UI
    await giveClue(spymaster.page, "testvote", 1);

    // Read spymaster board to find a team card word
    const spymasterBoard = await apiGetCodenamesBoard(
      gameId!,
      spymaster.login.access_token,
    );
    const teamCard = spymasterBoard.board.find(
      (c) => c.card_type === currentTeam && !c.revealed,
    );
    expect(teamCard).toBeTruthy();
    const teamCardWord = teamCard!.word;
    const teamCardIndex = spymasterBoard.board.indexOf(teamCard!);

    // Wait for operative to see the clue
    await operatives[0].page.waitForTimeout(3000);

    // First operative votes via UI (clicks the card)
    await guessCard(operatives[0].page, teamCardWord);

    // Wait for polling to process
    await operatives[0].page.waitForTimeout(3000);

    // Verify the card is NOT revealed yet (partial vote)
    const boardAfterVote = await apiGetCodenamesBoard(
      gameId!,
      setup.players[0].login.access_token,
    );
    expect(boardAfterVote.board[teamCardIndex].revealed).toBe(false);

    await setup.cleanup();
  });

  test("both operatives vote, card reveals", async ({ browser }) => {
    const accounts = await generateTestAccounts(6);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    const gameId = setup.players[0].page
      .url()
      .match(/\/game\/codenames\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    const board = await apiGetCodenamesBoard(
      gameId!,
      setup.players[0].login.access_token,
    );
    const currentTeam = board.current_team;
    const spymaster = findPlayerByRole(
      board,
      setup.players,
      currentTeam,
      "spymaster",
    );
    const operatives = findAllPlayersByRole(
      board,
      setup.players,
      currentTeam,
      "operative",
    );
    expect(operatives.length).toBeGreaterThanOrEqual(2);

    // Give clue via UI
    await giveClue(spymaster.page, "teamwork", 1);

    // Find a team card word
    const spymasterBoard = await apiGetCodenamesBoard(
      gameId!,
      spymaster.login.access_token,
    );
    const teamCard = spymasterBoard.board.find(
      (c) => c.card_type === currentTeam && !c.revealed,
    );
    expect(teamCard).toBeTruthy();
    const teamCardWord = teamCard!.word;
    const teamCardIndex = spymasterBoard.board.indexOf(teamCard!);

    // Wait for operatives to see the clue
    await operatives[0].page.waitForTimeout(3000);

    // First operative votes via UI
    await guessCard(operatives[0].page, teamCardWord);

    // Wait briefly for vote to register
    await operatives[0].page.waitForTimeout(2000);

    // Second operative votes same card via UI
    await guessCard(operatives[1].page, teamCardWord);

    // Wait for polling to update
    await operatives[1].page.waitForTimeout(3000);

    // Verify card is now revealed via API
    const updatedBoard = await apiGetCodenamesBoard(
      gameId!,
      setup.players[0].login.access_token,
    );
    expect(updatedBoard.board[teamCardIndex].revealed).toBe(true);

    await setup.cleanup();
  });

  test("vote badges visible on board after partial vote", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(6);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    const gameId = setup.players[0].page
      .url()
      .match(/\/game\/codenames\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    const board = await apiGetCodenamesBoard(
      gameId!,
      setup.players[0].login.access_token,
    );
    const currentTeam = board.current_team;
    const spymaster = findPlayerByRole(
      board,
      setup.players,
      currentTeam,
      "spymaster",
    );
    const operatives = findAllPlayersByRole(
      board,
      setup.players,
      currentTeam,
      "operative",
    );
    expect(operatives.length).toBeGreaterThanOrEqual(2);

    // Give clue via UI
    await giveClue(spymaster.page, "badge", 1);

    // Find a team card word
    const spymasterBoard = await apiGetCodenamesBoard(
      gameId!,
      spymaster.login.access_token,
    );
    const teamCard = spymasterBoard.board.find(
      (c) => c.card_type === currentTeam && !c.revealed,
    );
    expect(teamCard).toBeTruthy();
    const teamCardWord = teamCard!.word;
    const teamCardIndex = spymasterBoard.board.indexOf(teamCard!);

    // Wait for operative to see the clue
    await operatives[0].page.waitForTimeout(3000);

    // First operative votes via UI
    await guessCard(operatives[0].page, teamCardWord);

    // Wait for polling to update the UI
    await setup.players[0].page.waitForTimeout(3000);

    // On an operative's page, check for vote badge visibility
    const operativePage = operatives[0].page;
    if (isPageAlive(operativePage)) {
      const cardButtons = operativePage.locator(".grid-cols-5 button");
      const targetCard = cardButtons.nth(teamCardIndex);
      const badge = targetCard.locator("span");
      await expect(badge.first()).toBeVisible({ timeout: 10_000 });
    }

    await setup.cleanup();
  });

  test("full game to completion with voting", async ({ browser }) => {
    test.setTimeout(300_000);
    const accounts = await generateTestAccounts(6);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    const gameId = setup.players[0].page
      .url()
      .match(/\/game\/codenames\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Play turns until game ends
    for (let turn = 0; turn < 30; turn++) {
      const board = await apiGetCodenamesBoard(
        gameId!,
        setup.players[0].login.access_token,
      );
      if (board.status === "finished") break;

      const currentTeam = board.current_team;

      let spymaster: PlayerContext;
      let operatives: PlayerContext[];
      try {
        spymaster = findPlayerByRole(
          board,
          setup.players,
          currentTeam,
          "spymaster",
        );
        operatives = findAllPlayersByRole(
          board,
          setup.players,
          currentTeam,
          "operative",
        );
      } catch {
        break;
      }

      // Give clue via UI
      await giveClue(spymaster.page, `clue${turn}`, 1);

      // Get spymaster board to find team card word
      const smBoard = await apiGetCodenamesBoard(
        gameId!,
        spymaster.login.access_token,
      );
      if (smBoard.status === "finished") break;

      const teamCard = smBoard.board.find(
        (c) => c.card_type === currentTeam && !c.revealed,
      );

      if (teamCard) {
        // All operatives vote for the same team card via UI
        // guessCard() waits for the card to be enabled (polling delivers clue)
        for (const op of operatives) {
          await guessCard(op.page, teamCard.word);
        }
      }

      // Wait for votes to process
      await operatives[0].page.waitForTimeout(1000);

      // Check if game ended or turn already switched after guess
      const afterGuess = await apiGetCodenamesBoard(
        gameId!,
        setup.players[0].login.access_token,
      );
      if (afterGuess.status === "finished") break;

      // Only end turn if the current team hasn't changed (guess didn't auto-end turn)
      if (afterGuess.current_team === currentTeam) {
        await endTurnViaUI(operatives[0].page).catch(() => {});
        await operatives[0].page.waitForTimeout(1000);
      }
    }

    // Verify game finished
    const finalBoard = await apiGetCodenamesBoard(
      gameId!,
      setup.players[0].login.access_token,
    );
    expect(finalBoard.status).toBe("finished");
    expect(finalBoard.winner).toBeTruthy();

    // Verify UI shows game over
    const anyPage = setup.players.find((p) => isPageAlive(p.page))?.page;
    if (anyPage) {
      await expect(
        anyPage
          .locator('h2:has-text("Game Over")')
          .or(anyPage.locator("text=Game Over")),
      ).toBeVisible({ timeout: 15_000 });
    }

    await setup.cleanup();
  });

  test("assassin via vote ends game", async ({ browser }) => {
    const accounts = await generateTestAccounts(6);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    const gameId = setup.players[0].page
      .url()
      .match(/\/game\/codenames\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    const board = await apiGetCodenamesBoard(
      gameId!,
      setup.players[0].login.access_token,
    );
    const currentTeam = board.current_team;
    const opponentTeam = currentTeam === "red" ? "blue" : "red";
    const spymaster = findPlayerByRole(
      board,
      setup.players,
      currentTeam,
      "spymaster",
    );
    const operatives = findAllPlayersByRole(
      board,
      setup.players,
      currentTeam,
      "operative",
    );
    expect(operatives.length).toBeGreaterThanOrEqual(2);

    // Give clue via UI
    await giveClue(spymaster.page, "danger", 1);

    // Find assassin card word from spymaster board view
    const spymasterBoard = await apiGetCodenamesBoard(
      gameId!,
      spymaster.login.access_token,
    );
    const assassinCard = spymasterBoard.board.find(
      (c) => c.card_type === "assassin",
    );
    expect(assassinCard).toBeTruthy();
    const assassinWord = assassinCard!.word;

    // Wait for operatives to see the clue
    await operatives[0].page.waitForTimeout(3000);

    // Both operatives vote for assassin via UI
    for (const op of operatives) {
      await guessCard(op.page, assassinWord);
      await op.page.waitForTimeout(1000);
    }

    // Wait for UI to update
    await setup.players[0].page.waitForTimeout(3000);

    // Verify UI shows game over
    const anyPage = setup.players.find((p) => isPageAlive(p.page))?.page;
    if (anyPage) {
      await expect(
        anyPage
          .locator('h2:has-text("Game Over")')
          .or(anyPage.locator("text=Game Over")),
      ).toBeVisible({ timeout: 15_000 });
    }

    // Verify via API that opponent won
    const finalBoard = await apiGetCodenamesBoard(
      gameId!,
      setup.players[0].login.access_token,
    );
    expect(finalBoard.status).toBe("finished");
    expect(finalBoard.winner).toBe(opponentTeam);

    await setup.cleanup();
  });
});

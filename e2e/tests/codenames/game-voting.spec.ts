import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
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

    // First operative votes via UI (clicks the card)
    // guessCard() waits up to 30s for the card to be enabled (clue delivered via Socket.IO)
    await guessCard(operatives[0].page, teamCardWord);

    // Verify the card is NOT revealed yet (partial vote) — poll API for consistency
    await expect.poll(async () => {
      const b = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
      return b.board[teamCardIndex].revealed;
    }, { timeout: 15_000 }).toBe(false);

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

    // Both operatives vote via UI
    // guessCard() waits up to 30s for the card to be enabled (clue delivered via Socket.IO)
    await guessCard(operatives[0].page, teamCardWord);
    await guessCard(operatives[1].page, teamCardWord);

    // Verify card is now revealed via API (poll until server processes votes)
    await expect.poll(async () => {
      const b = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
      return b.board[teamCardIndex].revealed;
    }, { timeout: 15_000 }).toBe(true);

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

    // First operative votes via UI
    // guessCard() waits up to 30s for the card to be enabled (clue delivered via Socket.IO)
    await guessCard(operatives[0].page, teamCardWord);

    // The voter's own page marks the card as their choice...
    const voterCard = operatives[0].page.locator('[data-testid="codenames-card"]').nth(teamCardIndex);
    await expect(voterCard).toHaveAttribute("data-mine", "true", { timeout: 10_000 });
    // ...and the other operative's page shows it pointed at, with the voter's badge
    const otherCard = operatives[1].page.locator('[data-testid="codenames-card"]').nth(teamCardIndex);
    await expect(otherCard).toHaveAttribute("data-pointed", "true", { timeout: 10_000 });
    await expect(otherCard.locator(".cn-ptr")).toBeVisible();

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

    // Play turns until the game ends: every operative of the team votes for one of its
    // cards (the card turns once they all have), then the turn passes if it is still
    // theirs. Every step must work: none is excused by "the game probably ended" (TQ-07).
    for (let turn = 0; turn < 30; turn++) {
      const board = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
      if (board.status === "finished") break;
      const currentTeam = board.current_team;
      const spymaster = findPlayerByRole(board, setup.players, currentTeam, "spymaster");
      const operatives = findAllPlayersByRole(board, setup.players, currentTeam, "operative");

      await giveClue(spymaster.page, `clue${turn}`, 1);
      const smBoard = await apiGetCodenamesBoard(gameId!, spymaster.login.access_token);
      const teamCard = smBoard.board.find((c) => c.card_type === currentTeam && !c.revealed);
      expect(teamCard, "a team with cards left to find").toBeTruthy();
      const cardIndex = smBoard.board.indexOf(teamCard!);
      for (const op of operatives) await guessCard(op.page, teamCard!.word);
      await expect
        .poll(async () => (await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token)).board[cardIndex].revealed)
        .toBe(true);

      const afterGuess = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
      if (afterGuess.status === "finished") break;
      expect(afterGuess.current_team).toBe(currentTeam);
      await endTurnViaUI(operatives[0].page);
      await expect
        .poll(async () => (await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token)).current_team)
        .not.toBe(currentTeam);
    }

    // Verify game finished
    const finalBoard = await apiGetCodenamesBoard(
      gameId!,
      setup.players[0].login.access_token,
    );
    expect(finalBoard.status).toBe("finished");
    expect(finalBoard.winner).toBeTruthy();

    // Every page shows the end
    for (const player of setup.players) {
      await expect(player.page.locator('h2:has-text("Game Over")').first()).toBeVisible({ timeout: 30_000 });
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

    // Both operatives vote for assassin via UI
    // guessCard() waits up to 30s for the card to be enabled (clue delivered via Socket.IO)
    for (const op of operatives) {
      await guessCard(op.page, assassinWord);
    }

    // Every page shows the end
    for (const player of setup.players) {
      await expect(player.page.locator('h2:has-text("Game Over")').first()).toBeVisible({ timeout: 30_000 });
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

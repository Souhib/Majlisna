import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  giveClue,
  guessCard,
  endTurnViaUI,
  findSpymaster,
  findOperative,
} from "../../helpers/ui-game-setup";
import { apiGetCodenamesBoard, expectApiError, rawPost } from "../../helpers/api-client";

test.describe("Codenames Game Gameplay", () => {
  test("spymaster gives clue and operatives see it", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    const gameId = setup.players[0].page.url().match(/\/game\/codenames\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Read board via API to determine current team + find spymaster/operative pages
    const board = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
    const currentTeam = board.current_team;
    const spymaster = await findSpymaster(setup.players, gameId!, currentTeam);
    const operative = await findOperative(setup.players, gameId!, currentTeam);

    // Give clue via UI
    await giveClue(spymaster.page, "testclue", 1);

    // The operative sees the clue on their page
    await expect(
      operative.page.locator("text=testclue").first().or(operative.page.locator("text=TESTCLUE").first()),
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });

  test("an operative cannot pass the team's turn before the clue", async ({ browser }) => {
    // Prepare — the first team's operative, before their spymaster has spoken
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    const gameId = await startGameViaAPI(setup.players, "codenames", setup.roomId);
    const board = await apiGetCodenamesBoard(gameId, setup.players[0].login.access_token);
    const team = board.current_team;
    const spymaster = await findSpymaster(setup.players, gameId, team);
    const operative = await findOperative(setup.players, gameId, team);
    await expect(operative.page.locator('[data-testid="codenames-board"]')).toBeVisible({ timeout: 15_000 });

    // Assert — the page offers no End Turn, and the server refuses the call by name: one
    // operative used to pass the team's whole turn before the clue (BR-15)
    await expect(operative.page.getByRole("button", { name: "End Turn" })).toHaveCount(0);
    await expectApiError(await rawPost(`/api/v1/codenames/games/${gameId}/end-turn`, {}, operative.login.access_token), 400, "errors.api.noClueGiven");
    const after = await apiGetCodenamesBoard(gameId, operative.login.access_token);
    expect(after.current_team).toBe(team);

    // ...once the clue is given, End Turn is there and passes the turn
    await giveClue(spymaster.page, "patience", 1);
    await endTurnViaUI(operative.page);
    await expect.poll(async () => (await apiGetCodenamesBoard(gameId, operative.login.access_token)).current_team).not.toBe(team);

    await setup.cleanup();
  });

  test("a clue of two words is refused, in the field and by the server", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    const gameId = await startGameViaAPI(setup.players, "codenames", setup.roomId);
    const board = await apiGetCodenamesBoard(gameId, setup.players[0].login.access_token);
    const spymaster = await findSpymaster(setup.players, gameId, board.current_team);
    const clues: string[] = [];
    spymaster.page.on("request", (r) => r.url().endsWith("/clue") && clues.push(r.url()));

    // Act — two words in the field
    const field = spymaster.page.locator('input[placeholder="One word clue"]');
    await field.fill("the sunnah");
    await spymaster.page.getByRole("button", { name: "Give clue" }).click();

    // Assert — said under the field, nothing sent; the server refuses it by name too
    await expect(spymaster.page.getByText("Give a one-word clue.")).toBeVisible({ timeout: 10_000 });
    expect(clues).toEqual([]);
    await expectApiError(
      await rawPost(`/api/v1/codenames/games/${gameId}/clue`, { clue_word: "the sunnah", clue_number: 1 }, spymaster.login.access_token),
      400,
      "errors.api.clueMustBeOneWord",
    );
    // ...and a card's own word is refused as well
    const oneWordCard = board.board.find((c) => !/\s/.test(c.word))!;
    await expectApiError(
      await rawPost(`/api/v1/codenames/games/${gameId}/clue`, { clue_word: oneWordCard.word, clue_number: 1 }, spymaster.login.access_token),
      400,
      "errors.api.clueWordIsOnBoard",
    );
    expect((await apiGetCodenamesBoard(gameId, spymaster.login.access_token)).current_turn.clue_word).toBeNull();

    await setup.cleanup();
  });

  test("operative guesses correct card and it reveals", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    const gameId = setup.players[0].page.url().match(/\/game\/codenames\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Read board via API for roles
    const board = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
    const currentTeam = board.current_team;
    const spymaster = await findSpymaster(setup.players, gameId!, currentTeam);
    const operative = await findOperative(setup.players, gameId!, currentTeam);

    // Spymaster gives clue via UI
    await giveClue(spymaster.page, "hint", 1);

    // Read spymaster's board to find a team card word (spymaster can see card_type)
    const spymasterBoard = await apiGetCodenamesBoard(gameId!, spymaster.login.access_token);
    const teamCard = spymasterBoard.board.find(
      (c) => c.card_type === currentTeam && !c.revealed,
    );
    expect(teamCard).toBeTruthy();
    const teamCardWord = teamCard!.word;
    const teamCardIndex = spymasterBoard.board.indexOf(teamCard!);

    // Operative guesses via UI
    // guessCard() waits up to 30s for the card to be enabled (clue delivered via Socket.IO)
    await guessCard(operative.page, teamCardWord);

    // Verify the card is now revealed via API (poll until server processes)
    await expect.poll(async () => {
      const b = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
      return b.board[teamCardIndex].revealed;
    }, { timeout: 15_000 }).toBe(true);

    // Remaining count should have decreased
    const updatedBoard = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
    if (currentTeam === "red") {
      expect(updatedBoard.red_remaining).toBe(board.red_remaining - 1);
    } else {
      expect(updatedBoard.blue_remaining).toBe(board.blue_remaining - 1);
    }

    await setup.cleanup();
  });

  test("guessing assassin card ends game with opponent winning", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    const gameId = setup.players[0].page.url().match(/\/game\/codenames\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Read board via API for roles
    const board = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
    const currentTeam = board.current_team;
    const spymaster = await findSpymaster(setup.players, gameId!, currentTeam);
    const operative = await findOperative(setup.players, gameId!, currentTeam);

    // Give clue via UI
    await giveClue(spymaster.page, "danger", 1);

    // Find assassin card word from spymaster's board view
    const spymasterBoard = await apiGetCodenamesBoard(gameId!, spymaster.login.access_token);
    const assassinCard = spymasterBoard.board.find((c) => c.card_type === "assassin");
    expect(assassinCard).toBeTruthy();
    const assassinWord = assassinCard!.word;

    // Operative guesses the assassin via UI
    // guessCard() waits up to 30s for the card to be enabled (clue delivered via Socket.IO)
    await guessCard(operative.page, assassinWord);

    // Every player sees the end
    for (const player of setup.players) {
      await expect(player.page.locator('h2:has-text("Game Over")').first()).toBeVisible({ timeout: 15_000 });
    }

    // Verify via API that opponent won
    const finalBoard = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
    expect(finalBoard.status).toBe("finished");
    const opponentTeam = currentTeam === "red" ? "blue" : "red";
    expect(finalBoard.winner).toBe(opponentTeam);

    await setup.cleanup();
  });

  test("end turn switches team", async ({ browser }) => {
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    const gameId = setup.players[0].page.url().match(/\/game\/codenames\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Read board via API to get current team AND player roles
    const board = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
    const initialTeam = board.current_team;
    const otherTeam = initialTeam === "red" ? "blue" : "red";
    const spymaster = await findSpymaster(setup.players, gameId!, initialTeam);
    const operative = await findOperative(setup.players, gameId!, initialTeam);

    // Spymaster gives clue via UI
    await giveClue(spymaster.page, "pass", 1);

    // Operative ends turn via UI
    // endTurnViaUI() waits for the End Turn button to be visible (clue delivered via Socket.IO)
    await endTurnViaUI(operative.page);

    // Verify team switched via API (poll until server processes)
    await expect.poll(async () => {
      const b = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
      return b.current_team;
    }, { timeout: 15_000 }).toBe(otherTeam);

    await setup.cleanup();
  });

  test("full game played to completion via UI", async ({ browser }) => {
    // Full game can take 15+ turns — increase timeout
    test.setTimeout(180_000);
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    await startGameViaAPI(setup.players, "codenames", setup.roomId);

    const gameId = setup.players[0].page.url().match(/\/game\/codenames\/([a-f0-9-]+)/)?.[1];
    expect(gameId).toBeTruthy();

    // Play the game: each turn, the spymaster gives a clue and the operative turns one of
    // the team's cards, then ends the turn if it is still theirs. Every step must work:
    // no step is excused by "the game probably ended" (TQ-07).
    for (let turn = 0; turn < 30; turn++) {
      const board = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
      if (board.status === "finished") break;
      const currentTeam = board.current_team;
      const spymaster = await findSpymaster(setup.players, gameId!, currentTeam);
      const operative = await findOperative(setup.players, gameId!, currentTeam);

      await giveClue(spymaster.page, `clue${turn}`, 1);
      const smBoard = await apiGetCodenamesBoard(gameId!, spymaster.login.access_token);
      const teamCard = smBoard.board.find((c) => c.card_type === currentTeam && !c.revealed);
      expect(teamCard, "a team with cards left to find").toBeTruthy();
      const cardIndex = smBoard.board.indexOf(teamCard!);
      await guessCard(operative.page, teamCard!.word);
      await expect
        .poll(async () => (await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token)).board[cardIndex].revealed)
        .toBe(true);

      const afterGuess = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
      if (afterGuess.status === "finished") break;
      // A clue of 1 allows one more guess: the turn is still the team's, so it passes it
      expect(afterGuess.current_team).toBe(currentTeam);
      await endTurnViaUI(operative.page);
      await expect
        .poll(async () => (await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token)).current_team)
        .not.toBe(currentTeam);
    }

    // Verify game finished
    const finalBoard = await apiGetCodenamesBoard(gameId!, setup.players[0].login.access_token);
    expect(finalBoard.status).toBe("finished");
    expect(finalBoard.winner).toBeTruthy();

    // Every page shows the end
    for (const player of setup.players) {
      await expect(player.page.locator('h2:has-text("Game Over")').first()).toBeVisible({ timeout: 15_000 });
    }

    await setup.cleanup();
  });
});

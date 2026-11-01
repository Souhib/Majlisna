import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI, giveClue, guessCard, findSpymaster, findOperative } from "../../helpers/ui-game-setup";
import { apiGetCodenamesBoard, apiUnlockedAchievements } from "../../helpers/api-client";

/**
 * The end of a Codenames game (WP-09 + WP-13): the card that decided it is turned on
 * screen first, then the veil ("Game Over", who won) comes over the board, then lifts
 * into the colophon. The veil used to cover the board 80 ms after the click, so nobody
 * saw the card that ended the game (F3).
 */

interface EndingTimeline {
  /** When the decisive card's face changed (it was turned). */
  cardTurnedAt: number | null;
  /** When the veil appeared, and when it went. */
  veilAt: number | null;
  veilGoneAt: number | null;
  /** What the veil said. */
  veilText: string;
}

/** Watch one card's face and the veil, from now on, on the page's own clock. */
async function watchTheEnding(page: Page, cardIndex: number): Promise<void> {
  await page.evaluate((index) => {
    const w = window as unknown as { __ending: EndingTimeline };
    w.__ending = { cardTurnedAt: null, veilAt: null, veilGoneAt: null, veilText: "" };
    const card = () => document.querySelectorAll('[data-testid="codenames-card"]')[index];
    const startFace = card()?.getAttribute("data-face");
    const check = () => {
      const now = performance.now();
      if (w.__ending.cardTurnedAt === null && card() && card()!.getAttribute("data-face") !== startFace) w.__ending.cardTurnedAt = now;
      const veil = document.querySelector(".cn-veil");
      if (veil && w.__ending.veilAt === null) w.__ending.veilAt = now;
      if (veil) w.__ending.veilText = veil.textContent ?? "";
      if (!veil && w.__ending.veilAt !== null && w.__ending.veilGoneAt === null) w.__ending.veilGoneAt = now;
    };
    new MutationObserver(check).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["data-face"] });
  }, cardIndex);
}

const timeline = (page: Page) => page.evaluate(() => (window as unknown as { __ending: EndingTimeline }).__ending);

test.describe("Codenames — the end of the game", () => {
  test("the decisive card is turned on screen before the veil comes, then the colophon", async ({ browser }) => {
    // Prepare — a 4-player game, the first team's clue given
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    const gameId = await startGameViaAPI(setup.players, "codenames", setup.roomId);
    const board = await apiGetCodenamesBoard(gameId, setup.players[0].login.access_token);
    const team = board.current_team;
    const spymaster = await findSpymaster(setup.players, gameId, team);
    const operative = await findOperative(setup.players, gameId, team);
    const watcher = setup.players.find((p) => p !== spymaster && p !== operative)!;
    await giveClue(spymaster.page, "danger", 1);
    const spyBoard = await apiGetCodenamesBoard(gameId, spymaster.login.access_token);
    const assassin = spyBoard.board.findIndex((c) => c.card_type === "assassin");
    expect(assassin).toBeGreaterThanOrEqual(0);
    for (const page of [operative.page, watcher.page]) await watchTheEnding(page, assassin);

    // Act — the operative turns the assassin: the game ends
    await guessCard(operative.page, spyBoard.board[assassin].word);

    // Assert — on the operative's page and on another player's, in that order: the card,
    // then (a beat later) the veil with who won, then the colophon once it has lifted
    const opponent = team === "red" ? "Blue" : "Red";
    await expect(operative.page.locator(".cn-veil")).toBeVisible({ timeout: 15_000 });
    for (const page of [operative.page, watcher.page]) {
      await expect(page.locator(".cn-veil")).toHaveCount(0, { timeout: 15_000 });
      await expect(page.locator("[data-colophon-title]")).toBeVisible({ timeout: 10_000 });

      const seen = await timeline(page);
      expect(seen.cardTurnedAt, "the decisive card was turned on screen").not.toBeNull();
      expect(seen.veilAt, "the veil came").not.toBeNull();
      expect(seen.veilText).toContain("Game Over");
      expect(seen.veilText).toContain(opponent);
      expect(seen.veilAt! - seen.cardTurnedAt!, "the veil waits for the card's weave").toBeGreaterThanOrEqual(400);
      expect(seen.veilGoneAt! - seen.veilAt!, "the veil holds the ceremony, then lifts").toBeGreaterThanOrEqual(800);
    }
    const final = await apiGetCodenamesBoard(gameId, setup.players[0].login.access_token);
    expect(final.status).toBe("finished");
    expect(final.winner).toBe(team === "red" ? "blue" : "red");

    // The operative who turned the assassin is sealed Assassin Finder, though their team
    // lost (owner rule (f): the badge had no logic and never unlocked); nobody else is
    expect(await apiUnlockedAchievements(operative.login.user.id)).toContain("assassin_finder");
    for (const player of setup.players.filter((p) => p !== operative)) {
      expect(await apiUnlockedAchievements(player.login.user.id)).not.toContain("assassin_finder");
    }
    const sealOn = (page: Page) => page.locator('[data-slot="colophon"]').getByText("Assassin Finder");
    await expect(sealOn(operative.page)).toContainText("you");
    await expect(sealOn(watcher.page)).toContainText(operative.login.user.username);

    await setup.cleanup();
  });
});

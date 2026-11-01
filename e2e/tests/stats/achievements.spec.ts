import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaUI,
  undercoverRoles,
  voteForPlayer,
  verifyAllPlayersVoted,
  giveClue,
  guessCard,
  endTurnViaUI,
  findSpymaster,
  findOperative,
  type PlayerContext,
} from "../../helpers/ui-game-setup";
import {
  apiEndTurn,
  apiGetCodenamesBoard,
  apiGetUndercoverState,
  apiGetUserStats,
  apiGiveClue,
  apiUnlockedAchievements,
} from "../../helpers/api-client";

/**
 * The special achievements are earned in play (owner rule (f)): they had no logic at all
 * (`stat_field: None`, "checked via custom logic" that did not exist), so five of the
 * badges could never unlock. The server now reads them off the game's final state, and
 * every seat's game-over colophon seals what was earned, under the earner's name.
 *
 * Each test plays a game whose ending makes the rule certain, never likely: the votes and
 * the guesses are chosen from the roles the server dealt.
 */

/** The game-over colophon of a page. */
const colophon = (page: Page) => page.locator('[data-slot="colophon"]');

/** One seal of the colophon, by its title: its label and caption ("Clean Sweep · you and Maryam · Gold"). */
const seal = (page: Page, title: string) => colophon(page).getByText(title);

/** A row of the /stats "By game" panel's list ("Games hosted", "Rooms created"). */
const statRow = (page: Page, label: string) => page.locator("dl > div").filter({ hasText: label }).locator("dd");

/**
 * Turn one card as the lone operative, through the board. The page drops a second tap
 * while its first guess is in flight (FR-4), so the next tap waits for this one's answer
 * to be read and for the operative's own board to show the card turned — as a player
 * would. The last card of the game is not looked for on the board: the veil comes over it.
 */
async function turnCard(
  operative: PlayerContext,
  gameId: string,
  card: { word: string; index: number },
  { last = false }: { last?: boolean } = {},
): Promise<void> {
  const page = operative.page;
  const answered = page.waitForEvent("requestfinished", {
    predicate: (r) => r.method() === "POST" && new URL(r.url()).pathname === `/api/v1/codenames/games/${gameId}/guess`,
    timeout: 20_000,
  });
  await guessCard(page, card.word);
  expect((await (await answered).response())?.status()).toBe(200);
  expect((await apiGetCodenamesBoard(gameId, operative.login.access_token)).board[card.index].revealed).toBe(true);
  if (!last) {
    await expect(page.locator('[data-testid="codenames-card"]').nth(card.index)).toHaveAttribute("data-face", "wool", { timeout: 15_000 });
  }
}

test.describe("Special achievements", () => {
  test("the undercover who outlasts the table, never named by a vote, is sealed Perfect Infiltrator and Last One Standing", async ({
    browser,
  }) => {
    // Prepare — three fresh players: one undercover, two civilians, no Mr. White
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const host = setup.players[0];
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const players = await dismissRoleRevealAll(setup.players);
    const roles = await undercoverRoles(players, gameId);
    const undercover = players.find((p) => roles.get(p.login.user.id) === "undercover")!;
    const [named, other] = players.filter((p) => p !== undercover);
    expect(roles.get(named.login.user.id)).toBe("civilian");
    expect(roles.get(other.login.user.id)).toBe("civilian");
    await submitDescriptionsForAllPlayersViaUI(players);

    // Act — nobody names the undercover: two votes send a civilian out, who names the other
    await voteForPlayer(undercover.page, named.login.user.username);
    await voteForPlayer(other.page, named.login.user.username);
    await voteForPlayer(named.page, other.login.user.username);
    await verifyAllPlayersVoted(players);

    // Assert — one civilian against one undercover: parity, the undercover wins alone
    for (const player of players) {
      await expect(player.page.locator('h2:has-text("Game Over")')).toBeVisible({ timeout: 30_000 });
    }
    const final = await apiGetUndercoverState(gameId, host.login.access_token);
    expect(final.winner).toBe("undercovers");

    // ...the server unlocked both for the undercover, and neither for a civilian
    expect(await apiUnlockedAchievements(undercover.login.user.id)).toEqual(
      expect.arrayContaining(["perfect_undercover", "last_survivor"]),
    );
    for (const civilian of [named, other]) {
      const unlocked = await apiUnlockedAchievements(civilian.login.user.id);
      expect(unlocked).not.toContain("perfect_undercover");
      expect(unlocked).not.toContain("last_survivor");
    }

    // ...and every seat's colophon seals both, under the undercover's name
    for (const player of players) {
      for (const title of ["Perfect Infiltrator", "Last One Standing"]) {
        await expect(seal(player.page, title)).toBeVisible({ timeout: 15_000 });
        await expect(seal(player.page, title)).toContainText(undercover.login.user.username);
      }
    }

    // The host's stats count the game they hosted and the room they opened; a guest's do not.
    // games_hosted had no writer at all (PD-05), rooms_created none either (WP-07).
    const guest = players.find((p) => p !== host)!;
    expect((await apiGetUserStats(host.login.user.id)).games_hosted).toBe(1);
    expect((await apiGetUserStats(host.login.user.id)).rooms_created).toBe(1);
    expect((await apiGetUserStats(guest.login.user.id)).games_hosted).toBe(0);
    await host.page.goto("/stats");
    await expect(statRow(host.page, "Games hosted")).toHaveText("1", { timeout: 15_000 });
    await expect(statRow(host.page, "Rooms created")).toHaveText("1");
    await guest.page.goto("/stats");
    await expect(statRow(guest.page, "Games hosted")).toHaveText("0", { timeout: 15_000 });

    await setup.cleanup();
  });

  test("a team that turns only its own cards, one clue exactly, is sealed Clean Sweep and Flawless Round", async ({ browser }) => {
    // Prepare — four players: a spymaster and an operative on each side
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts, "codenames");
    const gameId = await startGameViaAPI(setup.players, "codenames", setup.roomId);
    const opening = await apiGetCodenamesBoard(gameId, setup.players[0].login.access_token);
    const team = opening.current_team;
    const otherTeam = team === "red" ? "blue" : "red";
    const spymaster = await findSpymaster(setup.players, gameId, team);
    const operative = await findOperative(setup.players, gameId, team);
    const otherSpymaster = await findSpymaster(setup.players, gameId, otherTeam);
    const otherOperative = await findOperative(setup.players, gameId, otherTeam);
    const spyBoard = await apiGetCodenamesBoard(gameId, spymaster.login.access_token);
    const own = spyBoard.board.map((card, index) => ({ ...card, index })).filter((card) => card.card_type === team);
    expect(own.length).toBeGreaterThan(3);

    // Act — a clue for three, three of the team's cards, and the operative stops there:
    // a perfect round (exactly the number given, all the team's own)
    await giveClue(spymaster.page, "sweepone", 3);
    for (const card of own.slice(0, 3)) await turnCard(operative, gameId, card);
    await endTurnViaUI(operative.page);
    await expect.poll(async () => (await apiGetCodenamesBoard(gameId, operative.login.access_token)).current_team).toBe(otherTeam);

    // ...the other side gives its clue and passes, turning nothing (setup: it is not the side under test)
    await apiGiveClue(gameId, "patience", 1, otherSpymaster.login.access_token);
    await apiEndTurn(gameId, otherOperative.login.access_token);
    await expect.poll(async () => (await apiGetCodenamesBoard(gameId, operative.login.access_token)).current_team).toBe(team);

    // ...then a clue with no limit, and the rest of the team's cards: the team wins
    await giveClue(spymaster.page, "sweeptwo", 0);
    const rest = own.slice(3);
    for (const [i, card] of rest.entries()) await turnCard(operative, gameId, card, { last: i === rest.length - 1 });

    // Assert — the team won without one wrong card
    const final = await apiGetCodenamesBoard(gameId, operative.login.access_token);
    expect(final.winner).toBe(team);
    for (const player of [spymaster, operative]) {
      expect(await apiUnlockedAchievements(player.login.user.id)).toEqual(expect.arrayContaining(["sweep_victory", "perfect_round_1"]));
    }
    for (const player of [otherSpymaster, otherOperative]) {
      const unlocked = await apiUnlockedAchievements(player.login.user.id);
      expect(unlocked).not.toContain("sweep_victory");
      expect(unlocked).not.toContain("perfect_round_1");
    }

    // ...and the colophon seals both: "you and <teammate>" on the team's pages, the two
    // names on the other side's
    const names = [spymaster.login.user.username, operative.login.user.username];
    for (const title of ["Clean Sweep", "Flawless Round"]) {
      for (const [player, mate] of [
        [spymaster, operative],
        [operative, spymaster],
      ] as const) {
        await expect(seal(player.page, title)).toBeVisible({ timeout: 20_000 });
        await expect(seal(player.page, title)).toContainText("you");
        await expect(seal(player.page, title)).toContainText(mate.login.user.username);
      }
      for (const player of [otherSpymaster, otherOperative]) {
        await expect(seal(player.page, title)).toBeVisible({ timeout: 20_000 });
        for (const name of names) await expect(seal(player.page, title)).toContainText(name);
      }
    }

    await setup.cleanup();
  });
});

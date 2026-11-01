import { expect, type Browser, type Page } from "@playwright/test";
import {
  apiLogin,
  apiCreateRoom,
  apiGetRoom,
  apiJoinRoom,
  apiStartGame,
  apiGetUndercoverState,
  apiGetCodenamesBoard,
  apiSubmitDescription,
  apiSubmitVote,
  apiUpdateRoomSettings,
  type LoginResponse,
  type RoomResponse,
  type CodenamesBoardState,
  type UndercoverGameState,
} from "./api-client";
import { createPlayerPage } from "../fixtures/auth.fixture";
import { ROUTES, FRONTEND_URL } from "./constants";

// ─── Types ──────────────────────────────────────────────────

export interface PlayerContext {
  page: Page;
  login: LoginResponse;
  account: { email: string; password: string };
}

export interface UIGameSetup {
  players: PlayerContext[];
  roomDetails: RoomResponse;
  roomId: string;
  cleanup: () => Promise<void>;
}

export interface CodenamesPlayerRole {
  team: "red" | "blue";
  role: "spymaster" | "operative";
}

// ─── Utilities ──────────────────────────────────────────────

/**
 * Whether a player's page is still open. The old helper called `page.url()` in a
 * try/catch, which never throws, so it answered true for a page whose context had been
 * closed (TQ-15). Only the specs that close a player's browser on purpose meet a closed
 * page; everywhere else a closed page is a failure the next locator reports.
 */
export function isPageAlive(page: Page): boolean {
  return !page.isClosed();
}

/** The game id in a game page's address (`/game/<game>/<id>`). */
export function gameIdFromUrl(page: Page, game: "undercover" | "codenames" | "wordquiz" | "mcqquiz"): string {
  const id = page.url().match(new RegExp(`/game/${game}/([a-f0-9-]+)`))?.[1];
  if (!id) throw new Error(`not on a ${game} game page: ${page.url()}`);
  return id;
}

/** Open every player's browser on the room lobby and wait until each one sees the whole table. */
async function openLobbies(
  browser: Browser,
  accounts: { email: string; password: string }[],
  logins: LoginResponse[],
  roomId: string,
): Promise<PlayerContext[]> {
  const players: PlayerContext[] = [];
  for (let i = 0; i < accounts.length; i++) {
    const page = await createPlayerPage(browser, accounts[i].email, accounts[i].password);
    await page.goto(ROUTES.room(roomId));
    await page.waitForLoadState("domcontentloaded");
    players.push({ page, login: logins[i], account: accounts[i] });
  }
  await Promise.all(
    players.map((player) =>
      expect(player.page.locator(`text=Players (${accounts.length})`)).toBeVisible({ timeout: 30_000 }),
    ),
  );
  return players;
}

/** Close every player's browser (a context closed before, by the spec itself, is fine). */
function closeAll(players: PlayerContext[]): () => Promise<void> {
  return async () => {
    for (const p of players) await p.page.context().close();
  };
}

// ─── Room Setup via Pure API ────────────────────────────────

/**
 * Create a room and join all players via API, then open browser pages
 * pointed at the room lobby. No UI interaction for setup — game tests
 * should use this to focus on testing game logic, not room joining.
 */
export async function setupRoomWithPlayers(
  browser: Browser,
  accounts: { email: string; password: string }[],
  gameType: "undercover" | "codenames" | "word_quiz" | "mcq_quiz" = "undercover",
): Promise<UIGameSetup> {
  const logins = await Promise.all(accounts.map((a) => apiLogin(a.email, a.password)));

  const room = await apiCreateRoom(logins[0].access_token, gameType);
  const roomDetails = await apiGetRoom(room.id, logins[0].access_token);

  // Long timers, so no clock runs out during a test that does not ask for it
  await apiUpdateRoomSettings(
    room.id,
    { description_timer: 600, voting_timer: 600, codenames_clue_timer: 600, codenames_guess_timer: 600 },
    logins[0].access_token,
  );

  for (let i = 1; i < logins.length; i++) {
    await apiJoinRoom(roomDetails.public_id, logins[i].user.id, roomDetails.password, logins[i].access_token);
  }

  const players = await openLobbies(browser, accounts, logins, room.id);
  return { players, roomDetails, roomId: room.id, cleanup: closeAll(players) };
}

// ─── Room Setup via UI (for room management tests) ──────────

/**
 * Create a room via API, then have non-host players join through the UI
 * (fill room code + PIN, click join). Use this ONLY in room tests that
 * need to verify the UI join flow works.
 */
export async function setupRoomWithPlayersViaUI(
  browser: Browser,
  accounts: { email: string; password: string }[],
  gameType: "undercover" | "codenames" | "word_quiz" = "undercover",
): Promise<UIGameSetup> {
  const logins = await Promise.all(accounts.map((a) => apiLogin(a.email, a.password)));

  const room = await apiCreateRoom(logins[0].access_token, gameType);
  const roomDetails = await apiGetRoom(room.id, logins[0].access_token);
  await apiUpdateRoomSettings(
    room.id,
    { description_timer: 600, voting_timer: 600, codenames_clue_timer: 600, codenames_guess_timer: 600 },
    logins[0].access_token,
  );

  const hostPage = await createPlayerPage(browser, accounts[0].email, accounts[0].password);
  await hostPage.goto(ROUTES.room(room.id));
  await expect(hostPage.locator("text=/Players \\(\\d+/")).toBeVisible({ timeout: 10_000 });
  const players: PlayerContext[] = [{ page: hostPage, login: logins[0], account: accounts[0] }];

  // Other players join via UI
  for (let i = 1; i < accounts.length; i++) {
    const page = await createPlayerPage(browser, accounts[i].email, accounts[i].password);
    await page.goto(ROUTES.rooms);
    await joinWithCodeAndPin(page, roomDetails.public_id, roomDetails.password);
    await expect(page).toHaveURL(/\/rooms\/[a-f0-9-]+/, { timeout: 15_000 });
    players.push({ page, login: logins[i], account: accounts[i] });
  }

  await Promise.all(
    players.map((player) => expect(player.page.locator(`text=Players (${accounts.length})`)).toBeVisible({ timeout: 30_000 })),
  );
  return { players, roomDetails, roomId: room.id, cleanup: closeAll(players) };
}

/** On /rooms: type the code and the PIN, then Join. */
export async function joinWithCodeAndPin(page: Page, code: string, pin: string): Promise<void> {
  await page.locator('input[id="room-code"]').fill(code);
  const digits = pin.split("");
  for (let j = 0; j < 4; j++) {
    await page.locator(`input[aria-label="Password digit ${j + 1}"]`).fill(digits[j]);
  }
  const joinBtn = page.locator('button[type="submit"]');
  await expect(joinBtn).toBeEnabled({ timeout: 10_000 });
  await joinBtn.click();
}

// ─── Game Start via API ─────────────────────────────────────

const GAME_URL_PATH: Record<string, string> = {
  undercover: "undercover",
  codenames: "codenames",
  word_quiz: "wordquiz",
  mcq_quiz: "mcqquiz",
};

const GAME_URL_PATTERN: Record<string, RegExp> = {
  undercover: /\/game\/undercover\//,
  codenames: /\/game\/codenames\//,
  word_quiz: /\/game\/wordquiz\//,
  mcq_quiz: /\/game\/mcqquiz\//,
};

/**
 * Start a game via API and navigate all players to the game page.
 * Use this in game tests to skip testing the start button UI.
 */
export async function startGameViaAPI(
  players: PlayerContext[],
  gameType: "undercover" | "codenames" | "word_quiz" | "mcq_quiz",
  roomId: string,
): Promise<string> {
  const result = await apiStartGame(roomId, gameType, players[0].login.access_token);
  const gameUrl = `/game/${GAME_URL_PATH[gameType]}/${result.game_id}`;

  await Promise.all(
    players.map(async (player) => {
      await player.page.goto(`${FRONTEND_URL}${gameUrl}`);
      await player.page.waitForLoadState("domcontentloaded");
    }),
  );

  for (const player of players) {
    await expect(player.page).toHaveURL(GAME_URL_PATTERN[gameType], { timeout: 15_000 });
    if (gameType === "codenames") {
      await expect(player.page.locator('[data-testid="codenames-card"]').first()).toBeVisible({ timeout: 15_000 });
    } else if (gameType === "word_quiz") {
      await expect(player.page.locator("h1:has-text('Kalimat')").or(player.page.locator("h1:has-text('كلمات')"))).toBeVisible({
        timeout: 15_000,
      });
    } else if (gameType === "mcq_quiz") {
      await expect(
        player.page
          .locator("h1:has-text('The Quiz')")
          .or(player.page.locator("h1:has-text('Le Quiz')"))
          .or(player.page.locator("h1:has-text('مسائل')")),
      ).toBeVisible({ timeout: 15_000 });
    } else {
      await expect(player.page.locator("h1:has-text('Undercover')")).toBeVisible({ timeout: 15_000 });
    }
  }
  return result.game_id;
}

// ─── Game Start via UI ──────────────────────────────────────

/**
 * Host clicks the start button (after picking the game in the lobby's picker), and every
 * player is taken to the game page by the room's push (or its 2 s poll).
 */
export async function startGameViaUI(
  players: PlayerContext[],
  gameType: "undercover" | "codenames" | "word_quiz" | "mcq_quiz",
): Promise<void> {
  const hostPage = players[0].page;
  await expect(hostPage.locator(`text=Players (${players.length})`)).toBeVisible({ timeout: 30_000 });

  // The lobby's game picker (a tab list; undercover is default). Picking a tab also saves
  // the room's game type on the server (PATCH settings).
  const tabNames: Record<string, string> = {
    undercover: "Undercover",
    codenames: "Codenames",
    word_quiz: "Kalimat",
    mcq_quiz: "The Quiz",
  };
  const gameTab = hostPage.getByRole("tab", { name: tabNames[gameType], exact: true });
  if ((await gameTab.getAttribute("aria-selected")) !== "true") {
    await gameTab.click();
  }
  await expect(gameTab).toHaveAttribute("aria-selected", "true");

  const startButton = hostPage.locator('button:has-text("Start")');
  await expect(startButton).toBeEnabled({ timeout: 10_000 });
  await startButton.click();

  // Every player follows the table; one who does not is a failure, never forced along
  await Promise.all(players.map((player) => expect(player.page).toHaveURL(GAME_URL_PATTERN[gameType], { timeout: 20_000 })));
}

// ─── Undercover: Role Reveal ────────────────────────────────

/** The describing phase's heading, or a later phase's (the table may have moved on). */
function atTheTable(page: Page) {
  return page
    .locator('h2:has-text("turn to describe")')
    .or(page.locator('h2:has-text("is describing")'))
    .or(page.locator('h2:has-text("Discuss and vote")'))
    .or(page.locator('h2:has-text("Game Over")'))
    .first();
}

/**
 * Wait for role reveal screen and dismiss it for all players.
 * Returns only players confirmed on the game page (active players).
 */
export async function dismissRoleRevealAll(players: PlayerContext[]): Promise<PlayerContext[]> {
  for (const player of players) {
    // The first reading ("Your role is in your word.") ends with "I understand".
    const dismissBtn = player.page.getByRole("button", { name: "I understand" });
    await expect(dismissBtn).toBeVisible({ timeout: 15_000 });
    await dismissBtn.click();
    await expect(atTheTable(player.page)).toBeVisible({ timeout: 15_000 });
  }
  return players;
}

/** Each player's own role, read from their own state (a role is secret: nobody else's payload has it). */
export async function undercoverRoles(players: PlayerContext[], gameId: string): Promise<Map<string, string>> {
  const roles = new Map<string, string>();
  for (const player of players) {
    const state = await apiGetUndercoverState(gameId, player.login.access_token);
    roles.set(player.login.user.id, state.my_role);
  }
  return roles;
}

// ─── Undercover: Description Phase ──────────────────────────

/**
 * Submit a description via the UI for the current describer.
 * Fills the #description-input and presses Submit.
 */
export async function submitDescriptionViaUI(page: Page, word: string): Promise<void> {
  const input = page.locator("#description-input");
  await input.fill(word);
  const submitBtn = page.locator('button:has-text("Submit")').first();
  await expect(submitBtn).toBeEnabled({ timeout: 5_000 });
  await submitBtn.click();
}

/** A one-off description: never anyone's word (the server refuses a describer's own word). */
const description = () => `desc${Math.random().toString(36).slice(2, 6)}`;

/** The player whose turn it is to describe, from the server's state. */
function describerOf(state: UndercoverGameState, players: PlayerContext[]): PlayerContext {
  const entry = state.description_order?.[state.current_describer_index ?? 0];
  const describer = players.find((p) => p.login.user.id === entry?.user_id);
  if (!describer) throw new Error(`the describer ${entry?.username} is not among the players given`);
  return describer;
}

/** Wait until the server has moved past this describer (the next one, or the vote). */
async function waitForTurnToMove(gameId: string, token: string, index: number): Promise<void> {
  await expect
    .poll(
      async () => {
        const state = await apiGetUndercoverState(gameId, token);
        return state.turn_phase !== "describing" || state.current_describer_index !== index;
      },
      { timeout: 15_000, intervals: [250] },
    )
    .toBe(true);
}

/** Every player's page shows the vote (or the end of the game). */
async function waitForVotingEverywhere(players: PlayerContext[]): Promise<void> {
  for (const player of players) {
    if (!isPageAlive(player.page)) continue;
    await expect(
      player.page.locator("text=Discuss and vote").or(player.page.locator('h2:has-text("Game Over")')),
    ).toBeVisible({ timeout: 30_000 });
  }
}

/**
 * Every living player describes through the UI, in the server's order: the describer is
 * read from the state, and their page must show the field (no hunting from page to page
 * with snapshots). Returns once every page shows the vote.
 */
export async function submitDescriptionsForAllPlayersViaUI(activePlayers: PlayerContext[]): Promise<void> {
  const gameId = gameIdFromUrl(activePlayers[0].page, "undercover");
  const token = activePlayers[0].login.access_token;

  for (let turn = 0; turn <= activePlayers.length; turn++) {
    const state = await apiGetUndercoverState(gameId, token);
    if (state.turn_phase !== "describing") break;
    if (turn === activePlayers.length) throw new Error("still describing after every player has described");
    const index = state.current_describer_index ?? 0;
    const describer = describerOf(state, activePlayers);
    const input = describer.page.locator("#description-input");
    await expect(input).toBeVisible({ timeout: 20_000 });
    await submitDescriptionViaUI(describer.page, description());
    await expect(input).toBeHidden({ timeout: 10_000 });
    await waitForTurnToMove(gameId, token, index);
  }

  await waitForVotingEverywhere(activePlayers);
}

/**
 * Submit descriptions for all alive players via the API.
 * This bypasses UI interaction entirely for reliability, then waits
 * for the voting phase to appear on all players' UIs.
 * Use this only for setup in error/boundary tests, not for gameplay E2E.
 */
export async function submitDescriptionsForAllPlayersViaAPI(activePlayers: PlayerContext[]): Promise<void> {
  const gameId = gameIdFromUrl(activePlayers[0].page, "undercover");
  const token = activePlayers[0].login.access_token;

  for (let turn = 0; turn <= activePlayers.length; turn++) {
    const state = await apiGetUndercoverState(gameId, token);
    if (state.turn_phase !== "describing") break;
    if (turn === activePlayers.length) throw new Error("still describing after every player has described");
    const index = state.current_describer_index ?? 0;
    const describer = describerOf(state, activePlayers);
    await apiSubmitDescription(gameId, description(), describer.login.access_token);
    await waitForTurnToMove(gameId, token, index);
  }

  await waitForVotingEverywhere(activePlayers);
}

// ─── Undercover: Voting ─────────────────────────────────────

/** What a page shows once its player's ballot is in: their vote, the round counted, or the end. */
function votedOrResolved(page: Page) {
  return page
    .getByRole("status")
    .filter({ hasText: "Waiting for the others to vote." })
    .or(page.locator('[data-testid="elimination-overlay"]'))
    .or(page.locator('[data-testid="you-are-eliminated"]'))
    .or(page.locator('h2:has-text("Game Over")'));
}

/** Vote for a player through the UI: pick their seat, then "Vote to eliminate". */
export async function voteForPlayer(page: Page, targetUsername: string): Promise<void> {
  const candidate = page.getByRole("button", { name: `Vote for ${targetUsername}`, exact: true });
  await expect(candidate).toBeVisible({ timeout: 10_000 });
  await candidate.click();
  await expect(candidate).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "Vote to eliminate" }).click();
  await expect(votedOrResolved(page)).toBeVisible({ timeout: 10_000 });
}

/**
 * Every living player votes through the UI: for `target`, or, for the target, for
 * `fallback` (nobody may vote for themselves). Then asserts every ballot is in.
 */
export async function voteOut(
  voters: PlayerContext[],
  alive: { user_id: string; username: string }[],
  target: { user_id: string; username: string },
  fallback: { user_id: string; username: string },
): Promise<void> {
  const living = new Set(alive.map((p) => p.user_id));
  const ballots = voters.filter((voter) => living.has(voter.login.user.id));
  for (const voter of ballots) {
    await voteForPlayer(voter.page, voter.login.user.id === target.user_id ? fallback.username : target.username);
  }
  await verifyAllPlayersVoted(ballots);
}

/**
 * Assert that every given voter's ballot is in: their page shows their vote, the round
 * counted, or the end. It used to cast a missing ballot itself, which turned a lost
 * click into a pass (TQ-16); a ballot that should exist is checked, never re-cast.
 */
export async function verifyAllPlayersVoted(voters: PlayerContext[]): Promise<void> {
  for (const voter of voters) {
    if (!isPageAlive(voter.page)) continue;
    await expect(votedOrResolved(voter.page), `${voter.login.user.username} has not voted`).toBeVisible({ timeout: 15_000 });
  }
}

/** Every alive player votes through the API (setup only; gameplay specs vote in the UI). */
export async function voteOutViaAPI(
  gameId: string,
  voters: PlayerContext[],
  state: UndercoverGameState,
  targetId: string,
): Promise<void> {
  const alive = state.players.filter((p) => p.is_alive);
  const fallback = alive.find((p) => p.user_id !== targetId);
  if (!fallback) throw new Error("nobody else alive to vote for");
  for (const p of alive) {
    const voter = voters.find((v) => v.login.user.id === p.user_id);
    if (!voter) throw new Error(`no player context for ${p.username}`);
    await apiSubmitVote(gameId, p.user_id === targetId ? fallback.user_id : targetId, voter.login.access_token);
  }
}

// ─── Undercover: Elimination / Game Over ────────────────────

/** Wait for either the round-over screen or the end of the game. */
export async function waitForEliminationOrGameOver(page: Page): Promise<{ type: "elimination" | "game_over" }> {
  const gameOver = page.locator('h2:has-text("Game Over")');
  await page.locator('[data-testid="elimination-overlay"]').or(gameOver).first().waitFor({ state: "visible", timeout: 30_000 });
  return { type: (await gameOver.count()) > 0 ? "game_over" : "elimination" };
}

/**
 * Start the next round from the round-over screen as the host: "Next round" forces it
 * (every other player has "I’m ready", owner rule (d)). Waits until every player is back
 * at the describing table.
 */
export async function startNextRoundAsHost(hostPage: Page, players: PlayerContext[]): Promise<void> {
  const nextRound = hostPage.getByRole("button", { name: "Next round" });
  await expect(nextRound).toBeEnabled({ timeout: 15_000 });
  await nextRound.click();
  await waitForDescribingEverywhere(players);
}

/** Every player is back at the describing table (a new round has opened). */
export async function waitForDescribingEverywhere(players: PlayerContext[]): Promise<void> {
  for (const player of players) {
    if (!isPageAlive(player.page)) continue;
    await expect(player.page.locator('[data-testid="elimination-overlay"]')).toBeHidden({ timeout: 15_000 });
    await expect(
      player.page.locator('h2:has-text("turn to describe")').or(player.page.locator('h2:has-text("is describing")')).first(),
    ).toBeVisible({ timeout: 15_000 });
  }
}

// ─── Codenames Helpers ──────────────────────────────────────

/** Give a clue as spymaster (one word: the server refuses anything else). */
export async function giveClue(spymasterPage: Page, clue: string, count: number, { timeout = 30_000 }: { timeout?: number } = {}): Promise<void> {
  const clueInput = spymasterPage.locator('input[placeholder="One word clue"]');
  await clueInput.waitFor({ state: "visible", timeout });
  await clueInput.fill(clue);

  // The count is a group of toggles: 1-4, or "No limit" for 0 (1 is pressed by default).
  const countButton = spymasterPage
    .getByRole("group", { name: "How many cards it points to" })
    .getByRole("button", { name: count === 0 ? "No limit" : String(count), exact: true });
  await countButton.click();
  await expect(countButton).toHaveAttribute("aria-pressed", "true");

  const submitBtn = spymasterPage.getByRole("button", { name: "Give clue" });
  await expect(submitBtn).toBeEnabled({ timeout: 5_000 });
  await submitBtn.click();
}

/**
 * The board's button for a card, by its word. CardCell names a card "Word" or "Word,
 * <its state>" (the team, the votes, "meaning"), so the word is matched whole: up to the
 * end of the name or its first ", ". A `^Word\b` match also took "Umar ibn Abdul Aziz"
 * for "Umar" (and "Ilm al-Rijal" for "Ilm"), and `.first()` then clicked whichever came
 * first on the board.
 */
export function cardButton(page: Page, cardWord: string) {
  const escaped = cardWord.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return page.locator('[data-testid="codenames-board"]').getByRole("button", { name: new RegExp(`^${escaped}(?:, |$)`) });
}

/** Guess a card as operative by clicking on a card word. */
export async function guessCard(operativePage: Page, cardWord: string): Promise<void> {
  const card = cardButton(operativePage, cardWord).first();
  await expect(card).toBeEnabled({ timeout: 30_000 });
  await card.click({ timeout: 15_000 });
}

/** Click "End Turn" as an operative (offered once the clue is on the board). */
export async function endTurnViaUI(operativePage: Page): Promise<void> {
  const endTurnBtn = operativePage.locator('button:has-text("End Turn")');
  await expect(endTurnBtn).toBeVisible({ timeout: 10_000 });
  await endTurnBtn.click();
}

// ─── Codenames: Role Discovery ──────────────────────────────

/** Every player's team and role, from the board (public: who plays what is no secret). */
export async function getCodenamesRoles(players: PlayerContext[], gameId?: string): Promise<Map<string, CodenamesPlayerRole>> {
  const gid = gameId || gameIdFromUrl(players[0].page, "codenames");
  const board = await apiGetCodenamesBoard(gid, players[0].login.access_token);
  const roles = new Map<string, CodenamesPlayerRole>();
  for (const p of board.players) {
    roles.set(p.user_id, { team: p.team, role: p.role });
  }
  return roles;
}

/** Find the spymaster PlayerContext for a given team. */
export async function findSpymaster(players: PlayerContext[], gameId?: string, team?: "red" | "blue"): Promise<PlayerContext> {
  const roles = await getCodenamesRoles(players, gameId);
  const found = players.find((p) => {
    const r = roles.get(p.login.user.id);
    return r && r.role === "spymaster" && (team ? r.team === team : true);
  });
  if (!found) throw new Error(`No spymaster found for team=${team}`);
  return found;
}

/** Find an operative PlayerContext for a given team. */
export async function findOperative(players: PlayerContext[], gameId?: string, team?: "red" | "blue"): Promise<PlayerContext> {
  const roles = await getCodenamesRoles(players, gameId);
  const found = players.find((p) => {
    const r = roles.get(p.login.user.id);
    return r && r.role === "operative" && (team ? r.team === team : true);
  });
  if (!found) throw new Error(`No operative found for team=${team}`);
  return found;
}

/** Find ALL operative PlayerContexts for a given team. */
export async function findAllOperatives(players: PlayerContext[], gameId?: string, team?: "red" | "blue"): Promise<PlayerContext[]> {
  const roles = await getCodenamesRoles(players, gameId);
  return players.filter((p) => {
    const r = roles.get(p.login.user.id);
    return r && r.role === "operative" && (team ? r.team === team : true);
  });
}

export type { CodenamesBoardState };

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
  apiUpdateRoomSettings,
  type LoginResponse,
  type RoomResponse,
  type CodenamesBoardState,
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
 * Check if a Playwright page is still alive (browser context not closed).
 */
export function isPageAlive(page: Page): boolean {
  try {
    page.url();
    return true;
  } catch {
    return false;
  }
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
  // Login all players via API (parallel)
  const logins = await Promise.all(
    accounts.map((a) => apiLogin(a.email, a.password)),
  );

  // Host creates room via API
  const room = await apiCreateRoom(logins[0].access_token, gameType);
  const roomDetails = await apiGetRoom(room.id, logins[0].access_token);

  // Set very long timers so they never expire during tests
  await apiUpdateRoomSettings(
    room.id,
    {
      description_timer: 600,
      voting_timer: 600,
      codenames_clue_timer: 600,
      codenames_guess_timer: 600,
    },
    logins[0].access_token,
  );

  // All other players join via API
  for (let i = 1; i < logins.length; i++) {
    await apiJoinRoom(
      roomDetails.public_id,
      logins[i].user.id,
      roomDetails.password,
      logins[i].access_token,
    );
  }

  // Create browser pages and navigate to room lobby
  const players: PlayerContext[] = [];
  for (let i = 0; i < accounts.length; i++) {
    const page = await createPlayerPage(
      browser,
      accounts[i].email,
      accounts[i].password,
    );
    await page.goto(ROUTES.room(room.id));
    await page.waitForLoadState("domcontentloaded");
    players.push({ page, login: logins[i], account: accounts[i] });
  }

  // Wait for all players to see the full player count
  const expectedCount = accounts.length;
  await Promise.all(
    players.map((player) =>
      expect(player.page.locator(`text=Players (${expectedCount})`))
        .toBeVisible({ timeout: 30_000 })
    ),
  );

  return {
    players,
    roomDetails,
    roomId: room.id,
    cleanup: async () => {
      for (const p of players) {
        await p.page.context().close().catch(() => {});
      }
    },
  };
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
  const logins = await Promise.all(
    accounts.map((a) => apiLogin(a.email, a.password)),
  );

  // Host creates room via API
  const room = await apiCreateRoom(logins[0].access_token, gameType);
  const roomDetails = await apiGetRoom(room.id, logins[0].access_token);

  // Set very long timers so they never expire during tests
  await apiUpdateRoomSettings(
    room.id,
    {
      description_timer: 600,
      voting_timer: 600,
      codenames_clue_timer: 600,
      codenames_guess_timer: 600,
    },
    logins[0].access_token,
  );

  // Host navigates directly to room lobby
  const hostPage = await createPlayerPage(
    browser,
    accounts[0].email,
    accounts[0].password,
  );
  hostPage.on('pageerror', err => console.error(`[E2E] Host pageerror: ${err.message}\n${err.stack}`));
  hostPage.on('console', msg => {
    if (msg.type() === 'error' && msg.text().includes('ErrorBoundary')) {
      console.error(`[E2E] Host ErrorBoundary: ${msg.text()}`);
    }
  });
  await hostPage.goto(ROUTES.room(room.id));
  await hostPage.waitForLoadState("domcontentloaded");
  await expect(
    hostPage.locator('text=/Players \\(\\d+/')
  ).toBeVisible({ timeout: 10_000 });

  const players: PlayerContext[] = [
    { page: hostPage, login: logins[0], account: accounts[0] },
  ];

  // Other players join via UI
  for (let i = 1; i < accounts.length; i++) {
    const page = await createPlayerPage(
      browser,
      accounts[i].email,
      accounts[i].password,
    );
    page.on('pageerror', err => console.error(`[E2E] Player ${i} pageerror: ${err.message}\n${err.stack}`));
    page.on('console', msg => {
      if (msg.type() === 'error' && msg.text().includes('ErrorBoundary')) {
        console.error(`[E2E] Player ${i} ErrorBoundary: ${msg.text()}`);
      }
    });

    await page.goto(ROUTES.rooms);
    await page.waitForLoadState("domcontentloaded");

    // Fill room code + PIN and click join
    await page.locator('input[id="room-code"]').fill(roomDetails.public_id);
    const pinDigits = roomDetails.password.split("");
    for (let j = 0; j < 4; j++) {
      await page
        .locator(`input[aria-label="Password digit ${j + 1}"]`)
        .fill(pinDigits[j]);
    }
    const joinBtn = page.locator('button[type="submit"]');
    await expect(joinBtn).toBeEnabled({ timeout: 10_000 });
    await joinBtn.click();

    // Wait for navigation to room page
    await expect(page).toHaveURL(/\/rooms\/[a-f0-9-]+/, { timeout: 15_000 });
    players.push({ page, login: logins[i], account: accounts[i] });
  }

  // Verify all players see full count
  const expectedCount = accounts.length;
  await Promise.all(
    players.map((player) =>
      expect(player.page.locator(`text=Players (${expectedCount})`))
        .toBeVisible({ timeout: 30_000 })
    ),
  );

  return {
    players,
    roomDetails,
    roomId: room.id,
    cleanup: async () => {
      for (const p of players) {
        await p.page.context().close().catch(() => {});
      }
    },
  };
}

// ─── Game Start via API ─────────────────────────────────────

/**
 * Start a game via API and navigate all players to the game page.
 * Use this in game tests to skip testing the start button UI.
 */
export async function startGameViaAPI(
  players: PlayerContext[],
  gameType: "undercover" | "codenames" | "word_quiz" | "mcq_quiz",
  roomId: string,
): Promise<void> {
  const hostToken = players[0].login.access_token;
  const result = await apiStartGame(roomId, gameType, hostToken);
  const gameUrlPathMap: Record<string, string> = {
    undercover: "undercover",
    codenames: "codenames",
    word_quiz: "wordquiz",
    mcq_quiz: "mcqquiz",
  };
  const gameUrlPath = gameUrlPathMap[gameType] || gameType;
  const gameUrl = `/game/${gameUrlPath}/${result.game_id}`;

  // Navigate all players to the game page
  await Promise.all(
    players.map(async (player) => {
      await player.page.goto(`${FRONTEND_URL}${gameUrl}`);
      await player.page.waitForLoadState("domcontentloaded");
    }),
  );

  // Wait for game UI to load on all pages
  const urlPatterns: Record<string, RegExp> = {
    undercover: /\/game\/undercover\//,
    codenames: /\/game\/codenames\//,
    word_quiz: /\/game\/wordquiz\//,
    mcq_quiz: /\/game\/mcqquiz\//,
  };
  const urlPattern = urlPatterns[gameType];

  for (const player of players) {
    await expect(player.page).toHaveURL(urlPattern, { timeout: 15_000 });
    if (gameType === "codenames") {
      await expect(
        player.page.locator('[data-testid="codenames-card"]').first(),
      ).toBeVisible({ timeout: 15_000 });
    } else if (gameType === "word_quiz") {
      await expect(
        player.page.locator("h1:has-text('Kalimat')").or(player.page.locator("h1:has-text('كلمات')")),
      ).toBeVisible({ timeout: 15_000 });
    } else if (gameType === "mcq_quiz") {
      await expect(
        player.page.locator("h1:has-text('The Quiz')").or(player.page.locator("h1:has-text('Le Quiz')")).or(player.page.locator("h1:has-text('مسائل')")),
      ).toBeVisible({ timeout: 15_000 });
    } else {
      await expect(
        player.page.locator("h1:has-text('Undercover')"),
      ).toBeVisible({ timeout: 15_000 });
    }
  }
}

// ─── Game Start via UI ──────────────────────────────────────

/**
 * Host clicks the start button. For codenames, first selects the game type.
 * Returns after all players have navigated to the game page.
 *
 * With REST polling, players auto-navigate when active_game_id appears
 * in the room state response.
 */
export async function startGameViaUI(
  players: PlayerContext[],
  gameType: "undercover" | "codenames" | "word_quiz" | "mcq_quiz",
): Promise<void> {
  const hostPage = players[0].page;

  // Wait for all players to appear in the lobby before starting
  const playerCountText = `Players (${players.length})`;
  await expect(
    hostPage.locator(`text=${playerCountText}`),
  ).toBeVisible({ timeout: 30_000 });

  // Select game type in the lobby's game picker (a tab list; undercover is default).
  // Picking a tab also saves the room's game type on the server (PATCH settings).
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

  // Click start game
  const startButton = hostPage.locator('button:has-text("Start")');
  await expect(startButton).toBeEnabled({ timeout: 10_000 });
  await startButton.click();

  // Wait for all players to navigate to game page
  // With polling, the room page auto-navigates when active_game_id appears
  const urlPatternMap: Record<string, RegExp> = {
    undercover: /\/game\/undercover\//,
    codenames: /\/game\/codenames\//,
    word_quiz: /\/game\/wordquiz\//,
    mcq_quiz: /\/game\/mcqquiz\//,
  };
  const urlPattern = urlPatternMap[gameType];

  // Wait for all players to auto-navigate via polling/Socket.IO
  await Promise.all(
    players.map((player) =>
      expect(player.page).toHaveURL(urlPattern, { timeout: 20_000 })
    ),
  );

  // Fallback: force-navigate any stuck players (log as warning)
  let gameUrl = "";
  for (const player of players) {
    if (urlPattern.test(player.page.url())) {
      gameUrl = player.page.url();
      break;
    }
  }

  for (const player of players) {
    if (!urlPattern.test(player.page.url()) && gameUrl) {
      console.warn(`[E2E] Player did not auto-navigate; forcing to ${gameUrl}`);
      await player.page.goto(gameUrl);
      await expect(player.page).toHaveURL(urlPattern, { timeout: 15_000 });
    }
  }
}

// ─── Undercover: Role Reveal ────────────────────────────────

/**
 * Wait for role reveal screen and dismiss it for all players.
 * Returns only players confirmed on the game page (active players).
 */
export async function dismissRoleRevealAll(
  players: PlayerContext[],
): Promise<PlayerContext[]> {
  const activePlayers: PlayerContext[] = [];

  for (const player of players) {
    if (!isPageAlive(player.page)) continue;

    // The first reading ("Your role is in your word.") ends with "I understand".
    const dismissBtn = player.page.getByRole("button", { name: "I understand" });
    await expect(dismissBtn).toBeVisible({ timeout: 15_000 });
    await dismissBtn.click();

    // The player is now at the table: the describing phase's heading ("Your turn to
    // describe" / "<name> is describing"), or a later phase if the table moved on.
    await expect(
      player.page
        .locator('h2:has-text("turn to describe")')
        .or(player.page.locator('h2:has-text("is describing")'))
        .or(player.page.locator('h2:has-text("Discuss and vote")'))
        .or(player.page.locator('h2:has-text("Game Over")'))
        .first(),
    ).toBeVisible({ timeout: 15_000 });

    activePlayers.push(player);
  }

  return activePlayers;
}

// ─── Undercover: Description Phase ──────────────────────────

/**
 * Extract the game ID from a player's page URL.
 * URL format: /game/undercover/{gameId}
 */
function extractGameId(page: Page): string | null {
  const url = page.url();
  const match = url.match(/\/game\/undercover\/([a-f0-9-]+)/);
  return match ? match[1] : null;
}

/**
 * Submit a description via the UI for the current describer.
 * Fills the #description-input and presses Enter.
 */
export async function submitDescriptionViaUI(
  page: Page,
  word: string,
): Promise<void> {
  const input = page.locator("#description-input");
  await input.fill(word);
  // Wait for React to process the input and enable the Submit button
  const submitBtn = page.locator('button:has-text("Submit")').first();
  await expect(submitBtn).toBeEnabled({ timeout: 5_000 });
  await submitBtn.click();
}

/**
 * Submit descriptions for all alive players via the UI.
 * Finds which player's page has the description input visible (only the
 * current describer sees it), fills and submits, then waits for the next
 * describer or phase transition.
 */
export async function submitDescriptionsForAllPlayersViaUI(
  activePlayers: PlayerContext[],
): Promise<void> {
  const alivePlayers = activePlayers.filter((p) => isPageAlive(p.page));
  if (alivePlayers.length === 0) return;

  const maxIterations = alivePlayers.length + 2;

  for (let i = 0; i < maxIterations; i++) {
    // Check if phase already transitioned past describing
    const anyPage = alivePlayers.find((p) => isPageAlive(p.page))?.page;
    if (!anyPage) break;

    const phaseTransitioned = await anyPage
      .locator('text=Discuss and vote')
      .or(anyPage.locator('h2:has-text("Game Over")'))
      .isVisible()
      .catch(() => false);
    if (phaseTransitioned) break;

    // Find which player's page has the description input visible.
    // Poll with 500ms intervals for up to 20s (polling fallback is 2s).
    let describer: PlayerContext | undefined;
    const deadline = Date.now() + 20_000;
    while (Date.now() < deadline) {
      for (const player of alivePlayers) {
        if (!isPageAlive(player.page)) continue;
        const inputVisible = await player.page
          .locator("#description-input")
          .isVisible()
          .catch(() => false);
        if (inputVisible) {
          describer = player;
          break;
        }
      }
      if (describer) break;

      // Check for phase transition while waiting
      const transitioned = await anyPage
        .locator('text=Discuss and vote')
        .or(anyPage.locator('h2:has-text("Game Over")'))
        .isVisible()
        .catch(() => false);
      if (transitioned) break;

      await anyPage.waitForTimeout(500);
    }

    if (!describer) break;

    // Submit description via UI
    const word = `desc${Math.random().toString(36).slice(2, 6)}`;
    await submitDescriptionViaUI(describer.page, word);

    // Wait for the input to disappear (server processed the description)
    await expect(
      describer.page.locator("#description-input")
    ).toBeHidden({ timeout: 10_000 });
  }

  // Wait for all players to see the voting phase or game over
  for (const player of activePlayers) {
    if (!isPageAlive(player.page)) continue;
    await expect(
      player.page
        .locator("text=Discuss and vote")
        .or(player.page.locator('h2:has-text("Game Over")'))
    ).toBeVisible({ timeout: 30_000 });
  }
}

/**
 * Submit descriptions for all alive players via the API.
 * This bypasses UI interaction entirely for reliability, then waits
 * for the voting phase to appear on all players' UIs.
 * Use this only for setup in error/boundary tests, not for gameplay E2E.
 */
export async function submitDescriptionsForAllPlayersViaAPI(
  activePlayers: PlayerContext[],
): Promise<void> {
  const alivePlayers = activePlayers.filter((p) => isPageAlive(p.page));
  if (alivePlayers.length === 0) return;

  // Get game ID from any player's URL
  const gameId = extractGameId(alivePlayers[0].page);
  if (!gameId) throw new Error("Could not extract game ID from player URL");

  // Submit descriptions one by one, re-fetching state each time
  for (let submitted = 0; submitted < alivePlayers.length; submitted++) {
    // Re-fetch state to get current describer
    const currentState = await apiGetUndercoverState(
      gameId,
      alivePlayers[0].login.access_token,
    );

    // Check if descriptions are done
    if (currentState.turn_phase !== "describing") break;
    if (
      !currentState.description_order ||
      currentState.description_order.length === 0
    ) {
      break;
    }

    const idx = currentState.current_describer_index ?? 0;
    if (idx >= currentState.description_order.length) break;

    const describerId = currentState.description_order[idx].user_id;
    const describer = alivePlayers.find(
      (p) => p.login.user.id === describerId,
    );
    if (!describer) break;

    const word = `desc${Math.random().toString(36).slice(2, 6)}`;
    await apiSubmitDescription(gameId, word, describer.login.access_token);

    // Small delay for server processing
    const sleepFn = (ms: number) => new Promise(r => setTimeout(r, ms));
    await sleepFn(300);
  }

  // Wait for all players to see the voting phase (polling updates the UI)
  for (const player of activePlayers) {
    if (!isPageAlive(player.page)) continue;
    await expect(
      player.page
        .locator("text=Discuss and vote")
        .or(player.page.locator('h2:has-text("Game Over")'))
    ).toBeVisible({ timeout: 30_000 });
  }
}

// ─── Undercover: Voting ─────────────────────────────────────

/**
 * Vote for a specific player by username.
 * Retries once if the click doesn't register.
 */
export async function voteForPlayer(
  page: Page,
  targetUsername: string,
): Promise<void> {
  // Check if already voted
  const alreadyVoted = await page
    .locator("text=Waiting for")
    .isVisible()
    .catch(() => false);
  if (alreadyVoted) return;

  // Check for game over
  const gameOver = await page
    .locator('h2:has-text("Game Over")')
    .isVisible()
    .catch(() => false);
  if (gameOver) return;

  // Find the player card and click it
  const playerCard = page.locator(`button:has-text("${targetUsername}")`).first();
  await playerCard.waitFor({ state: "visible", timeout: 10_000 });
  await playerCard.click();

  // Click the vote/eliminate button
  const voteBtn = page.locator('button:has-text("Vote to Eliminate")').first();
  await voteBtn.waitFor({ state: "visible", timeout: 5_000 });
  await voteBtn.click();

  // Verify vote was submitted (UI shows waiting message or vote status)
  await expect(
    page
      .locator("text=Waiting for")
      .or(page.locator('h2:has-text("Game Over")'))
      .or(page.locator('[data-testid="elimination-overlay"], [data-testid="you-are-eliminated"]'))
  ).toBeVisible({ timeout: 10_000 });
}

/**
 * Verify all players have voted. If any haven't, retry with target or fallback.
 * fallbackUsername is needed because the vote target can't vote for themselves.
 */
export async function verifyAllPlayersVoted(
  activePlayers: PlayerContext[],
  targetUsername: string,
  fallbackUsername?: string,
): Promise<void> {
  for (const player of activePlayers) {
    if (!isPageAlive(player.page)) continue;

    const done = await player.page
      .locator("text=Waiting for")
      .or(player.page.locator('h2:has-text("Game Over")'))
      .or(player.page.locator('[data-testid="elimination-overlay"], [data-testid="you-are-eliminated"]'))
      .isVisible()
      .catch(() => false);

    if (done) continue;

    // Player hasn't voted — retry with target, fall back if they ARE the target
    try {
      await voteForPlayer(player.page, targetUsername);
    } catch {
      if (fallbackUsername) {
        await voteForPlayer(player.page, fallbackUsername);
      } else {
        throw new Error(
          `Player ${player.login.user.username} hasn't voted for ${targetUsername} and no fallback provided`,
        );
      }
    }
  }
}

// ─── Undercover: Elimination / Game Over ────────────────────

/**
 * Wait for either elimination screen or game over.
 */
export async function waitForEliminationOrGameOver(
  page: Page,
): Promise<{ type: "elimination" | "game_over"; playerName?: string }> {
  await page
    .locator('[data-testid="elimination-overlay"]')
    .or(page.locator('h2:has-text("Game Over")'))
    .waitFor({ state: "visible", timeout: 30_000 });

  const gameOver = await page
    .locator('h2:has-text("Game Over")')
    .isVisible()
    .catch(() => false);

  if (gameOver) {
    return { type: "game_over" };
  }

  return { type: "elimination" };
}

/**
 * Start the next round from the round-over screen. Only the host has "Next round"
 * (the others read "The host starts the next round"), so this clicks it on the host's
 * page and waits until every player is back at the describing table.
 */
export async function startNextRoundAsHost(
  hostPage: Page,
  players: PlayerContext[],
): Promise<void> {
  const nextRound = hostPage.getByRole("button", { name: "Next round" });
  await expect(nextRound).toBeEnabled({ timeout: 15_000 });
  await nextRound.click();

  for (const player of players) {
    if (!isPageAlive(player.page)) continue;
    await expect(player.page.locator('[data-testid="elimination-overlay"]')).toBeHidden({ timeout: 15_000 });
    await expect(
      player.page
        .locator('h2:has-text("turn to describe")')
        .or(player.page.locator('h2:has-text("is describing")'))
        .first(),
    ).toBeVisible({ timeout: 15_000 });
  }
}

// ─── Codenames Helpers ──────────────────────────────────────

/**
 * Give a clue as spymaster.
 */
export async function giveClue(
  spymasterPage: Page,
  clue: string,
  count: number,
  { timeout = 30_000 }: { timeout?: number } = {},
): Promise<void> {
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
 * Guess a card as operative by clicking on a card word.
 */
export async function guessCard(
  operativePage: Page,
  cardWord: string,
): Promise<void> {
  // Match card by accessible name (starts with the word).
  // The button name includes vote badge/hint text, so use regex for word boundary.
  // Escape special regex chars in the word to prevent matching issues.
  const escaped = cardWord.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const card = operativePage.locator('[data-testid="codenames-board"]').getByRole("button", { name: new RegExp(`^${escaped}\\b`), disabled: false }).first();
  await expect(card).toBeEnabled({ timeout: 30_000 });
  await card.click({ timeout: 15_000 });
}

/**
 * Click the "End Turn" button as an operative.
 * The button is only visible when canGuess is true (operative's turn with a clue given).
 */
export async function endTurnViaUI(
  operativePage: Page,
): Promise<void> {
  const endTurnBtn = operativePage.locator('button:has-text("End Turn")');
  await endTurnBtn.waitFor({ state: "visible", timeout: 10_000 });
  await endTurnBtn.click();
}

// ─── Codenames: Role Discovery ──────────────────────────────

/**
 * Extract the game ID from a codenames page URL.
 * URL format: /game/codenames/{gameId}
 */
function extractCodenamesGameId(page: Page): string | null {
  const url = page.url();
  const match = url.match(/\/game\/codenames\/([a-f0-9-]+)/);
  return match ? match[1] : null;
}

/**
 * Get codenames roles for all players by querying the board API.
 * Returns a Map from user_id to { team, role }.
 */
export async function getCodenamesRoles(
  players: PlayerContext[],
  gameId?: string,
): Promise<Map<string, CodenamesPlayerRole>> {
  const gid =
    gameId || extractCodenamesGameId(players[0].page);
  if (!gid) throw new Error("Could not determine codenames game ID");

  const board = await apiGetCodenamesBoard(gid, players[0].login.access_token);
  const roles = new Map<string, CodenamesPlayerRole>();
  for (const p of board.players) {
    roles.set(p.user_id, { team: p.team, role: p.role });
  }
  return roles;
}

/**
 * Find the spymaster PlayerContext for a given team.
 */
export async function findSpymaster(
  players: PlayerContext[],
  gameId?: string,
  team?: "red" | "blue",
): Promise<PlayerContext> {
  const roles = await getCodenamesRoles(players, gameId);
  const found = players.find((p) => {
    const r = roles.get(p.login.user.id);
    return r && r.role === "spymaster" && (team ? r.team === team : true);
  });
  if (!found) throw new Error(`No spymaster found for team=${team}`);
  return found;
}

/**
 * Find an operative PlayerContext for a given team.
 */
export async function findOperative(
  players: PlayerContext[],
  gameId?: string,
  team?: "red" | "blue",
): Promise<PlayerContext> {
  const roles = await getCodenamesRoles(players, gameId);
  const found = players.find((p) => {
    const r = roles.get(p.login.user.id);
    return r && r.role === "operative" && (team ? r.team === team : true);
  });
  if (!found) throw new Error(`No operative found for team=${team}`);
  return found;
}

/**
 * Find ALL operative PlayerContexts for a given team.
 */
export async function findAllOperatives(
  players: PlayerContext[],
  gameId?: string,
  team?: "red" | "blue",
): Promise<PlayerContext[]> {
  const roles = await getCodenamesRoles(players, gameId);
  return players.filter((p) => {
    const r = roles.get(p.login.user.id);
    return r && r.role === "operative" && (team ? r.team === team : true);
  });
}

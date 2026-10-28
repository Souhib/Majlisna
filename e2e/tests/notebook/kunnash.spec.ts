import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaAPI,
  isPageAlive,
  type PlayerContext,
} from "../../helpers/ui-game-setup";
import {
  apiGetUndercoverState,
  apiSubmitVote,
  apiGetNotebookGameWords,
  apiListNotebook,
  apiGetWordQuizState,
  apiWordQuizTimerExpired,
  apiWordQuizNextRound,
  apiUpdateRoomSettings,
  type NotebookEntry,
} from "../../helpers/api-client";
import { FRONTEND_URL } from "../../helpers/constants";

/**
 * The Kunnash (كُنّاش): the words a player keeps from a finished game.
 *
 * From the game-over colophon a player keeps the game's words ("Keep the words",
 * which then becomes the link "Kept in your kunnash"), or one at a time with the
 * bookmark toggle on each word row. /notebook lists them newest first, in the
 * player's language (the Arabic leads in the Arabic UI, with no transliteration),
 * and removes one with a short undo window.
 */

const gameIdOf = (page: Page, game: "undercover" | "wordquiz"): string => {
  const id = page.url().match(new RegExp(`/game/${game}/([a-f0-9-]+)`))?.[1];
  if (!id) throw new Error(`not on a ${game} game page: ${page.url()}`);
  return id;
};

const arabicOf = (e: { word_ar: string | null; word_ar_vocalized: string | null }) =>
  e.word_ar_vocalized?.trim() || e.word_ar?.trim() || null;

/** Play a 3-player Undercover game to its end: everyone describes, then the table votes one player out. */
async function finishThreePlayerUndercover(players: PlayerContext[]): Promise<string> {
  const active = await dismissRoleRevealAll(players);
  expect(active).toHaveLength(3);
  const gameId = gameIdOf(active[0].page, "undercover");

  await submitDescriptionsForAllPlayersViaAPI(active);
  const state = await apiGetUndercoverState(gameId, active[0].login.access_token);
  const target = state.players[state.players.length - 1];
  const fallback = state.players[0];
  for (const voter of active) {
    const votedFor = voter.login.user.id === target.user_id ? fallback.user_id : target.user_id;
    await apiSubmitVote(gameId, votedFor, voter.login.access_token);
  }

  // Three players, one vote: the game is over for everyone
  for (const player of active) {
    if (!isPageAlive(player.page)) continue;
    await expect(player.page.locator('h2:has-text("Game Over")')).toBeVisible({ timeout: 30_000 });
  }
  return gameId;
}

test.describe("Kunnash — keeping a game's words", () => {
  test("Undercover: keep the words from the colophon, read them in the kunnash, remove one", async ({ browser }) => {
    // Prepare
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    const gameId = await finishThreePlayerUndercover(setup.players);

    const keeper = setup.players[1];
    const page = keeper.page;
    const token = keeper.login.access_token;
    const before = await apiGetNotebookGameWords(gameId, token);
    expect(before.game_type).toBe("undercover");
    expect(before.words).toHaveLength(2); // the table's word and the other word
    expect(before.words.every((w) => !w.kept)).toBe(true);

    // The colophon offers to keep them: one action, and a toggle per word
    const keepAll = page.getByRole("button", { name: "Keep the words" });
    await expect(keepAll).toBeVisible({ timeout: 15_000 });
    const toggles = page.getByTestId("notebook-keep-word");
    await expect(toggles).toHaveCount(2);
    for (const word of before.words) {
      await expect(page.getByRole("button", { name: `Keep ${word.word} in your kunnash` })).toHaveAttribute("aria-pressed", "false");
    }

    // Act — keep both
    await keepAll.click();

    // Assert — the action turns into its kept state (a link, and focus follows it)
    const keptLink = page.getByRole("link", { name: "Kept in your kunnash" });
    await expect(keptLink).toBeVisible({ timeout: 10_000 });
    await expect(keptLink).toBeFocused();
    await expect(keepAll).toHaveCount(0);
    for (const word of before.words) {
      await expect(page.getByRole("button", { name: `Keep ${word.word} in your kunnash` })).toHaveAttribute("aria-pressed", "true");
    }
    const after = await apiGetNotebookGameWords(gameId, token);
    expect(after.words.every((w) => w.kept && !!w.entry_id)).toBe(true);

    // Another player of the same game has kept nothing
    const other = await apiGetNotebookGameWords(gameId, setup.players[2].login.access_token);
    expect(other.words.every((w) => !w.kept)).toBe(true);

    // The kunnash lists both words, under the game's heading
    await keptLink.click();
    await expect(page).toHaveURL(/\/notebook$/, { timeout: 10_000 });
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Kunnash");
    const entries = page.locator("[data-notebook-entry]");
    await expect(entries).toHaveCount(2, { timeout: 10_000 });
    await expect(page.getByRole("heading", { level: 2 }).filter({ hasText: "Undercover" })).toBeVisible();
    await expect(page.getByText("2 words", { exact: true })).toBeVisible();

    const listed = await apiListNotebook(token);
    expect(listed.total).toBe(2);
    for (const entry of listed.entries) {
      const row = page.locator(`[data-notebook-entry="${entry.id}"]`);
      await expect(row).toContainText(entry.word_display);
      const arabic = arabicOf(entry);
      if (arabic) await expect(row.locator('[lang="ar"]')).toHaveText(arabic);
      if (entry.hint) await expect(row).toContainText(entry.hint);
    }

    // Remove one: the row offers Undo for a few seconds, then the word is gone
    const removed: NotebookEntry = listed.entries[0];
    const kept: NotebookEntry = listed.entries[1];
    await page.getByRole("button", { name: `Remove ${removed.word_display} from your kunnash` }).click();
    const removedRow = page.locator(`[data-notebook-entry="${removed.id}"]`);
    await expect(removedRow).toContainText(`${removed.word_display} was taken out of your kunnash.`);
    await expect(removedRow.getByRole("button", { name: `Undo: put ${removed.word_display} back` })).toBeFocused();
    await expect(removedRow).toHaveCount(0, { timeout: 15_000 });
    await expect(entries).toHaveCount(1);

    await expect
      .poll(async () => (await apiListNotebook(token)).entries.map((e) => e.id), { timeout: 10_000 })
      .toEqual([kept.id]);
    const afterRemoval = await apiGetNotebookGameWords(gameId, token);
    expect(afterRemoval.words.find((w) => w.word === removed.word)?.kept).toBe(false);
    expect(afterRemoval.words.find((w) => w.word === kept.word)?.kept).toBe(true);

    // In Arabic: the page and the word read in Arabic, with no transliteration
    await page.evaluate(() => localStorage.setItem("majlisna-language", "ar"));
    await page.goto(`${FRONTEND_URL}/notebook`);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("الكُنّاش");
    const [arEntry] = (await apiListNotebook(token, "ar")).entries;
    expect(arEntry.id).toBe(kept.id);
    const arRow = page.locator(`[data-notebook-entry="${kept.id}"]`);
    await expect(arRow).toBeVisible({ timeout: 10_000 });
    const arabic = arabicOf(arEntry);
    if (arabic) {
      // the headword line: the Arabic alone (its meaning, below, may fall back to English)
      const headword = arRow.locator("p").first();
      await expect(headword.locator('[lang="ar"]')).toHaveText(arabic);
      await expect(headword).not.toContainText(arEntry.word_display);
      await expect(arRow.getByRole("button", { name: `أزِل كلمة «${arabic}» من كُنّاشك` })).toBeVisible();
    }

    await setup.cleanup();
  });

  test("Kalimat: the colophon lists the game's words; keep them all, then put one back", async ({ browser }) => {
    // Prepare — a solo Kalimat game played to its end (each round runs out)
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    const player = setup.players[0];
    const token = player.login.access_token;
    await apiUpdateRoomSettings(setup.roomId, { word_quiz_turn_duration: 1 }, token);
    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    const gameId = gameIdOf(player.page, "wordquiz");

    const totalRounds = (await apiGetWordQuizState(gameId, token)).total_rounds;
    for (let round = 1; round <= totalRounds; round++) {
      let state = await apiGetWordQuizState(gameId, token);
      if (state.round_phase === "game_over") break;
      if (state.round_phase === "playing") {
        // the 1 s round must really be over on the server before it is called
        await expect
          .poll(async () => (await apiWordQuizTimerExpired(gameId, token)).action, { timeout: 10_000, intervals: [500] })
          .not.toBe("timer_not_expired");
      }
      await expect
        .poll(async () => (await apiGetWordQuizState(gameId, token)).round_phase, { timeout: 10_000, intervals: [500] })
        .not.toBe("playing");
      state = await apiGetWordQuizState(gameId, token);
      if (state.round_phase === "results") await apiWordQuizNextRound(gameId, token);
    }
    expect((await apiGetWordQuizState(gameId, token)).game_over).toBe(true);

    const words = (await apiGetNotebookGameWords(gameId, token)).words;
    expect(words).toHaveLength(totalRounds);

    // The page picks up the end of the game (the API calls above were made outside it)
    const page = player.page;
    await page.reload();
    await expect(page.locator('h2:has-text("Game Over")')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "The words", level: 3 })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("notebook-keep-word")).toHaveCount(totalRounds);

    // Act — keep them all
    await page.getByRole("button", { name: "Keep the words" }).click();
    await expect(page.getByRole("link", { name: "Kept in your kunnash" })).toBeVisible({ timeout: 10_000 });
    for (const toggle of await page.getByTestId("notebook-keep-word").all()) {
      await expect(toggle).toHaveAttribute("aria-pressed", "true");
    }

    // ...then put the first one back: "Keep the words" is offered again
    const first = words[0];
    const firstToggle = page.getByRole("button", { name: `Keep ${first.word_display} in your kunnash` });
    await firstToggle.click();
    await expect(firstToggle).toHaveAttribute("aria-pressed", "false");
    await expect(page.getByRole("button", { name: "Keep the words" })).toBeVisible();

    // Assert — the server agrees, and the kunnash lists the others under Kalimat
    await expect
      .poll(async () => (await apiGetNotebookGameWords(gameId, token)).words.filter((w) => w.kept).map((w) => w.word), {
        timeout: 10_000,
      })
      .toEqual(words.slice(1).map((w) => w.word));

    await page.goto(`${FRONTEND_URL}/notebook`);
    await expect(page.locator("[data-notebook-entry]")).toHaveCount(totalRounds - 1, { timeout: 10_000 });
    await expect(page.getByRole("heading", { level: 2 }).filter({ hasText: "Kalimat" })).toBeVisible();
    await expect(page.getByRole("button", { name: `Remove ${first.word_display} from your kunnash` })).toHaveCount(0);

    await setup.cleanup();
  });
});

import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaUI, gameIdFromUrl } from "../../helpers/ui-game-setup";
import { apiGetMCQQuizState, apiMCQQuizNextRound, apiSubmitMCQQuizAnswer, apiUpdateRoomSettings } from "../../helpers/api-client";
import { dbRiddleWord, type RiddleWordRow } from "../../helpers/db";

/**
 * Samar riddles (السَّمَر) while a table waits: each member is asked rung 1 of a Kalimat
 * word ("While you wait: who is it?"), whose answer comes on a tap 30 s after the riddle
 * was first shown, or "when the game starts". The lobby follows the table into the game at
 * once, so that answer is read at the room's next wait: "The last riddle, “…”, was X."
 *
 * The riddle is the word's own content: the spec checks the line and the answer against
 * the word in the E2E database (the riddle's id is the word's). The tab keeps the riddle
 * (sessionStorage `majlisna-riddle:<room>:lobby`), so a reload shows it again and asks the
 * server nothing.
 */

const RIDDLE = "A riddle while you wait";
const RIDDLE_REQUEST = /\/api\/v1\/rooms\/[^/]+\/riddle\?/;

interface StoredRiddle {
  current: { riddle: { id: string; hint: string }; shownAt: number; revealed: boolean } | null;
  last: { riddle: { id: string; hint: string } } | null;
}

const riddleKey = (roomId: string) => `majlisna-riddle:${roomId}:lobby`;

async function storedRiddle(page: Page, roomId: string): Promise<StoredRiddle | null> {
  return page.evaluate((key) => JSON.parse(sessionStorage.getItem(key) ?? "null"), riddleKey(roomId));
}

/** The riddle the page shows now (once it has one), and the word it was drawn from. */
async function shownRiddle(page: Page, roomId: string): Promise<{ id: string; hint: string; word: RiddleWordRow }> {
  await expect.poll(async () => (await storedRiddle(page, roomId))?.current?.riddle.id ?? null, { timeout: 15_000 }).not.toBeNull();
  const { riddle } = (await storedRiddle(page, roomId))!.current!;
  return { id: riddle.id, hint: riddle.hint, word: dbRiddleWord(riddle.id) };
}

/** Kalimat's own question for the word's theme. */
function askFor(category: string): string {
  if (category === "Prophets" || category === "Companions") return "While you wait: who is it?";
  if (category === "Places") return "While you wait: where is it?";
  return "While you wait: what is it?";
}

function countRiddleRequests(page: Page): string[] {
  const asked: string[] = [];
  page.on("request", (request) => {
    if (RIDDLE_REQUEST.test(request.url())) asked.push(request.url());
  });
  return asked;
}

test.describe("Lobby — the samar riddle", () => {
  test("a waiting guest is asked rung 1 of a Kalimat word; a reload keeps it and asks nothing", async ({ browser }) => {
    // Prepare — a Quiz table of two: ready to start (The Quiz needs one), so the host has
    // the next move and no riddle, while the guest waits for the host
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const [host, guest] = setup.players;

    // Assert — the guest's riddle is the word's first rung, asked as Kalimat asks it
    const riddle = guest.page.getByRole("region", { name: RIDDLE });
    const { hint, word } = await shownRiddle(guest.page, setup.roomId);
    expect(hint).toBe(word.hint1_en);
    await expect(riddle).toContainText(askFor(word.category));
    await expect(riddle).toContainText(word.hint1_en);
    await expect(riddle).toContainText("The answer in a moment, or after the game.");
    // the answer is kept back: neither shown nor offered before 30 s
    await expect(riddle.getByText(/^It was /)).toHaveCount(0);
    await expect(riddle.getByRole("button", { name: "Show the answer" })).toHaveCount(0);

    // The host of a ready table has the next move, and no riddle (the start is theirs)
    // (the button's accessible name is the game's: "Start The Quiz")
    await expect(host.page.getByRole("button", { name: "Start The Quiz" })).toBeEnabled({ timeout: 15_000 });
    await expect(host.page.getByRole("region", { name: RIDDLE })).toHaveCount(0);

    // Act — the guest reloads
    const asked = countRiddleRequests(guest.page);
    await guest.page.reload();

    // Assert — the same riddle, from the tab, without a request
    await expect(riddle).toContainText(word.hint1_en, { timeout: 15_000 });
    await expect(guest.page.locator(`text=Players (2)`)).toBeVisible();
    expect(asked, "a reload asked for another riddle").toEqual([]);

    await setup.cleanup();
  });

  test("the riddle on screen when the game starts is answered at the room's next wait", async ({ browser }) => {
    test.setTimeout(120_000);
    // Prepare — a one-question Quiz table; the guest is asked a riddle while the host is about to start
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
    const [host, guest] = setup.players;
    await apiUpdateRoomSettings(setup.roomId, { mcq_quiz_rounds: 1, mcq_quiz_turn_duration: 600 }, host.login.access_token);
    const first = await shownRiddle(guest.page, setup.roomId);
    const { word } = first;

    // Act — the game starts (the guest follows the table), is played and ends
    await startGameViaUI(setup.players, "mcq_quiz");
    const gameId = gameIdFromUrl(guest.page, "mcqquiz");
    for (const player of setup.players) await apiSubmitMCQQuizAnswer(gameId, 0, player.login.access_token);
    await expect
      .poll(async () => (await apiGetMCQQuizState(gameId, host.login.access_token)).round_phase, { timeout: 15_000 })
      .toBe("results");
    await apiMCQQuizNextRound(gameId, host.login.access_token);
    const back = guest.page.getByRole("button", { name: "Back to the room" });
    await expect(back).toBeVisible({ timeout: 15_000 });
    await back.click();
    await expect(guest.page).toHaveURL(new RegExp(`/rooms/${setup.roomId}`), { timeout: 15_000 });

    // Assert — the lobby answers the riddle the game interrupted, and asks a new one
    const riddle = guest.page.getByRole("region", { name: RIDDLE });
    await expect(riddle).toContainText(`The last riddle, “${word.hint1_en}”, was ${word.word_en}.`, { timeout: 15_000 });
    await expect(riddle).toContainText("The answer in a moment, or after the game.");
    const next = await storedRiddle(guest.page, setup.roomId);
    expect(next?.last?.riddle.id).toBe(first.id);

    await setup.cleanup();
  });

  test("the answer is offered 30 s after the riddle was shown (never in a Kalimat lobby), and another riddle follows", async ({ browser }) => {
    // Prepare — an Undercover table of two, short of its three: everyone waits
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts, "undercover");
    const [host, guest] = setup.players;
    const riddle = guest.page.getByRole("region", { name: RIDDLE });
    const { word } = await shownRiddle(guest.page, setup.roomId);

    // the tab first showed it 31 s ago: the offer is due as the page opens
    await guest.page.evaluate((key) => {
      const record = JSON.parse(sessionStorage.getItem(key)!);
      record.current.shownAt = Date.now() - 31_000;
      sessionStorage.setItem(key, JSON.stringify(record));
    }, riddleKey(setup.roomId));
    await guest.page.reload();
    const show = riddle.getByRole("button", { name: "Show the answer" });
    await expect(show).toBeVisible({ timeout: 15_000 });

    // A Kalimat lobby offers no answer: the word could come up in the game
    await apiUpdateRoomSettings(setup.roomId, { game_type: "word_quiz" }, host.login.access_token);
    await expect(riddle).toContainText("The answer after the game: it could come up in Kalimat.", { timeout: 15_000 });
    await expect(show).toHaveCount(0);
    await apiUpdateRoomSettings(setup.roomId, { game_type: "undercover" }, host.login.access_token);
    await expect(show).toBeVisible({ timeout: 15_000 });

    // Act — the guest asks for the answer
    await show.click();

    // Assert — the word, and the focus on it (the button is gone)
    const answer = riddle.getByText(`It was ${word.word_en}`);
    await expect(answer).toBeVisible();
    await expect(riddle.locator("p:focus")).toContainText(`It was ${word.word_en}`);
    expect((await storedRiddle(guest.page, setup.roomId))?.current?.revealed).toBe(true);

    // Act — another riddle
    const asked = countRiddleRequests(guest.page);
    await riddle.getByRole("button", { name: "Another riddle" }).click();

    // Assert — one request, and a riddle whose answer is kept back again
    await expect(riddle).toContainText("The answer in a moment, or after the game.", { timeout: 15_000 });
    await expect(riddle.getByText(/^It was /)).toHaveCount(0);
    expect(asked).toHaveLength(1);
    const next = await shownRiddle(guest.page, setup.roomId);
    expect((await storedRiddle(guest.page, setup.roomId))?.current?.revealed).toBe(false);
    await expect(riddle).toContainText(next.word.hint1_en);

    await setup.cleanup();
  });
});

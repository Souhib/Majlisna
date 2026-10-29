import { test, expect, type Browser, type Page } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { apiListNotebook, apiLogin } from "../../helpers/api-client";
import { generateTestAccounts } from "../../helpers/test-setup";
import { dbDailyWord, dbDailyWordPlay, dbNotebookEntries, type DailyWordRow } from "../../helpers/db";

/**
 * The word of the day (كلمة اليوم, /today): one Kalimat word a day, the same for
 * everyone, found from its six hints. A signed-out visitor sees the number, the theme
 * and hint 1; a player reveals hints ("Another hint: 5 points instead of 6"), guesses
 * (a wrong try opens the next hint), finds the word or gives up, and keeps it in the
 * kunnash. The home page carries a card that leads to it.
 *
 * Today's answer is read from the E2E database (helpers/db.ts), never from the API:
 * the API keeps the word until the caller has finished, and a spec that solved it from
 * an API answer would only prove the API leaks it. Every test registers its own
 * players, so each starts the day fresh while the word is the same for all of them.
 */

const LADDER = "Hints, from the vaguest to the most specific";
const WRONG_GUESS = "Zzzqxj";

/** The theme as the page words it (game.quiz.kalimat.category), from QuizWord's stored label. */
const CATEGORY_TEXT: Record<string, string> = {
  Prophets: "a prophet",
  Companions: "a Companion",
  Places: "a place",
  Quran: "from the Qur’an",
  "Islamic History": "from Islamic history",
  "Islamic Concepts": "a concept of the faith",
  "Daily Life": "from daily life",
};

/** The panel's question, as Kalimat asks it for that theme. */
function promptFor(category: string): string {
  if (category === "Prophets" || category === "Companions") return "Who is it?";
  if (category === "Places") return "Where is it?";
  return "What is it?";
}

/** The Makkah day the page shows (`<time dateTime>` in the day's line). */
async function shownDay(page: Page): Promise<string> {
  const time = page.locator(".daily-meta time");
  await expect(time).toHaveAttribute("datetime", /^\d{4}-\d{2}-\d{2}$/, { timeout: 15_000 });
  return (await time.getAttribute("datetime"))!;
}

/** The day's word, from the database, for the day the page shows. */
async function todaysWord(page: Page): Promise<{ day: string; word: DailyWordRow }> {
  const day = await shownDay(page);
  const word = dbDailyWord(day);
  expect(word, `no daily_word row for ${day}: the page read must have drawn one`).not.toBeNull();
  return { day, word: word! };
}

/** A fresh, signed-in player in a context of their own. */
async function newPlayer(browser: Browser) {
  const [account] = await generateTestAccounts(1);
  const page = await createPlayerPage(browser, account.email, account.password);
  const login = await apiLogin(account.email, account.password);
  return { page, userId: login.user.id, token: login.access_token, close: () => page.context().close() };
}

async function openToday(page: Page): Promise<void> {
  await page.goto("/today");
  await expect(page.getByRole("heading", { level: 1, name: "Word of the day" })).toBeVisible({ timeout: 15_000 });
}

/**
 * The day turns at midnight in Makkah (21:00 UTC). A test that straddled it would read
 * one day's word and play the next one's (409 dailyWordNotToday), so a test that starts
 * this close to the turn waits for the new day first. Each test takes well under a minute.
 */
const DAY_TURN_MARGIN_MS = 3 * 60_000;

function msToMakkahMidnight(now = Date.now()): number {
  const next = new Date(now);
  next.setUTCHours(21, 0, 0, 0);
  if (next.getTime() <= now) next.setUTCDate(next.getUTCDate() + 1);
  return next.getTime() - now;
}

test.describe("Word of the day", () => {
  test.beforeEach(async ({}, testInfo) => {
    const ms = msToMakkahMidnight();
    if (ms > DAY_TURN_MARGIN_MS) return;
    console.warn(`[daily-word] ${Math.ceil(ms / 1000)} s to Makkah midnight: waiting for the new day before "${testInfo.title}"`);
    testInfo.setTimeout(testInfo.timeout + ms + 10_000);
    await new Promise((resolve) => setTimeout(resolve, ms + 5_000));
  });

  test("a signed-out visitor sees the number, the theme and hint 1, and is asked to sign in", async ({ page }) => {
    // Act
    await openToday(page);

    // Assert — the day's line: "#N · <Makkah date> · <theme>"
    const { word } = await todaysWord(page);
    const meta = page.locator(".daily-meta");
    await expect(meta).toContainText(/#\d+/);
    const number = Number((await meta.textContent())!.match(/#(\d+)/)![1]);
    expect(number).toBeGreaterThanOrEqual(1);
    await expect(meta).toContainText(CATEGORY_TEXT[word.category]);
    await expect(page.locator("#daily-play-title")).toHaveText(promptFor(word.category));

    // Hint 1 only: the rung in play, the five others hidden, and nothing to reveal them with
    const ladder = page.getByRole("list", { name: LADDER });
    await expect(ladder.getByRole("listitem")).toHaveCount(6);
    const first = ladder.locator('[data-rung="1"]');
    await expect(first).toHaveAttribute("data-state", "now");
    await expect(first).toContainText(word.hints_en["1"]);
    for (let rung = 2; rung <= 6; rung++) {
      const hidden = ladder.locator(`[data-rung="${rung}"]`);
      await expect(hidden).toHaveAttribute("data-state", "hidden");
      await expect(hidden).not.toContainText(word.hints_en[String(rung)]);
    }
    await expect(page.getByRole("button", { name: /^Another hint/ })).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "Your answer" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Give up" })).toHaveCount(0);

    // "Sign in to play" stands where the field would be, and brings the visitor back
    const signIn = page.getByRole("link", { name: "Sign in to play" });
    await expect(signIn).toHaveAttribute("href", "/auth/login?redirect=%2Ftoday");
    const [account] = await generateTestAccounts(1);
    await signIn.click();
    await expect(page).toHaveURL(/\/auth\/login\?redirect=%2Ftoday$/);
    await page.locator('input[id="email"]').fill(account.email);
    await page.locator('input[id="password"]').fill(account.password);
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL(/\/today$/, { timeout: 15_000 });
    await expect(page.getByRole("textbox", { name: "Your answer" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("link", { name: "Sign in to play" })).toHaveCount(0);

    // Viewing writes no play: the first move does
    const { user } = await apiLogin(account.email, account.password);
    expect(dbDailyWordPlay(user.id, await shownDay(page))).toBeNull();
  });

  test("a player reveals a hint, makes a wrong guess, then finds the word", async ({ browser }) => {
    // Prepare
    const player = await newPlayer(browser);
    const { page } = player;
    await openToday(page);
    const { day, word } = await todaysWord(page);
    const ladder = page.getByRole("list", { name: LADDER });
    const field = page.getByRole("textbox", { name: "Your answer" });
    await expect(field).toBeVisible();
    await expect(page.getByText("Worth 6 points now")).toBeVisible();

    // Act — ask for hint 2
    await page.getByRole("button", { name: "Another hint: 5 points instead of 6" }).click();

    // Assert — hint 2 is in play and takes focus; the next offer is one point lower
    const second = ladder.locator('[data-rung="2"]');
    await expect(second).toHaveAttribute("data-state", "now");
    await expect(second).toContainText(word.hints_en["2"]);
    await expect(second).toBeFocused();
    await expect(ladder.locator('[data-rung="1"]')).toHaveAttribute("data-state", "past");
    await expect(page.getByRole("button", { name: "Another hint: 4 points instead of 5" })).toBeVisible();
    await expect(page.getByText("Worth 5 points now")).toBeVisible();

    // Act — a wrong guess
    await field.fill(WRONG_GUESS);
    await page.getByRole("button", { name: "Answer", exact: true }).click();

    // Assert — it opens hint 3, says so, stays in the field and is listed in the tries
    await expect(page.getByText(`“${WRONG_GUESS}” is not it. Hint 3 is open now.`)).toBeVisible();
    await expect(field).toBeFocused();
    await expect(field).toHaveValue("");
    const third = ladder.locator('[data-rung="3"]');
    await expect(third).toHaveAttribute("data-state", "now");
    await expect(third).toContainText(word.hints_en["3"]);
    await expect(page.getByRole("button", { name: "Another hint: 3 points instead of 4" })).toBeVisible();
    const tries = page.getByRole("region", { name: "Your try" });
    await expect(tries).toContainText(WRONG_GUESS);
    expect(dbDailyWordPlay(player.userId, day)).toMatchObject({
      hints_revealed: 3,
      attempts: 1,
      guesses: [WRONG_GUESS],
      solved: false,
      gave_up: false,
      score: null,
    });

    // Act — the right answer, as the database holds it
    await field.fill(word.word_en);
    await page.getByRole("button", { name: "Answer", exact: true }).click();

    // Assert — the reveal takes focus: found at hint 3, worth 4, streak 1
    const title = page.getByRole("heading", { name: "You found it", level: 2 });
    await expect(title).toBeVisible({ timeout: 15_000 });
    await expect(title).toBeFocused();
    const colophon = page.locator('[data-slot="colophon"]');
    await expect(colophon).toContainText("found at hint 3 · 4 points");
    await expect(colophon).toContainText(word.word_en);
    if (word.word_ar) await expect(colophon.locator('p[lang="ar"]')).toBeVisible();
    await expect(colophon.locator("dl")).toContainText("Your streak");
    await expect(colophon.locator("dl dd").first()).toHaveText("1");
    await expect(page.getByRole("textbox", { name: "Your answer" })).toHaveCount(0);
    // the ladder as played: rung 3 found, the rest still hidden
    await expect(ladder.locator('[data-rung="3"]')).toContainText("found");
    await expect(ladder.locator('[data-rung="4"]')).toHaveAttribute("data-state", "hidden");
    await expect(page.getByRole("region", { name: "Your 2 tries" })).toContainText(word.word_en);

    expect(dbDailyWordPlay(player.userId, day)).toMatchObject({
      hints_revealed: 3,
      attempts: 2,
      guesses: [WRONG_GUESS, word.word_en],
      solved: true,
      gave_up: false,
      score: 4,
    });

    // A reload keeps the day as it ended, and moves no focus
    await page.reload();
    await expect(page.getByRole("heading", { name: "You found it", level: 2 })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "You found it", level: 2 })).not.toBeFocused();

    await player.close();
  });

  test("a player who gives up sees the word revealed", async ({ browser }) => {
    // Prepare
    const player = await newPlayer(browser);
    const { page } = player;
    await openToday(page);
    const { day, word } = await todaysWord(page);
    await expect(page.getByRole("textbox", { name: "Your answer" })).toBeVisible();

    // Act — give up, and confirm it in the dialog
    await page.getByRole("button", { name: "Give up" }).click();
    const dialog = page.getByRole("alertdialog", { name: "Give up today’s word?" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Keep looking" })).toBeFocused();
    await dialog.getByRole("button", { name: "Show me the word" }).click();

    // Assert — the reveal takes focus: the word, its Arabic, "given up", streak 0
    await expect(dialog).toHaveCount(0);
    const title = page.getByRole("heading", { name: "The word was", level: 2 });
    await expect(title).toBeVisible({ timeout: 15_000 });
    await expect(title).toBeFocused();
    const colophon = page.locator('[data-slot="colophon"]');
    await expect(colophon).toContainText("given up");
    await expect(colophon).toContainText(word.word_en);
    if (word.word_ar) await expect(colophon.locator('p[lang="ar"]')).toBeVisible();
    await expect(colophon.locator("dl dd").first()).toHaveText("0");
    await expect(colophon.getByRole("button", { name: "Keep in your kunnash" })).toBeVisible();
    // nothing is in play any more: hint 1 reads as passed, the others stay hidden
    const ladder = page.getByRole("list", { name: LADDER });
    await expect(ladder.locator('[data-rung="1"]')).toHaveAttribute("data-state", "past");
    await expect(ladder.locator('[data-rung="2"]')).toHaveAttribute("data-state", "hidden");

    expect(dbDailyWordPlay(player.userId, day)).toMatchObject({
      hints_revealed: 1,
      attempts: 0,
      solved: false,
      gave_up: true,
      score: 0,
    });

    await player.close();
  });

  test("keeping the word puts it in the kunnash", async ({ browser }) => {
    // Prepare — a player finds the word at hint 1, typed in Arabic script when it has one
    const player = await newPlayer(browser);
    const { page } = player;
    await openToday(page);
    const { day, word } = await todaysWord(page);
    const field = page.getByRole("textbox", { name: "Your answer" });
    await field.fill(word.word_ar ?? word.word_en);
    await page.getByRole("button", { name: "Answer", exact: true }).click();
    await expect(page.getByRole("heading", { name: "You found it", level: 2 })).toBeFocused({ timeout: 15_000 });
    await expect(page.locator('[data-slot="colophon"]')).toContainText("found at hint 1 · 6 points");
    expect(dbDailyWordPlay(player.userId, day)).toMatchObject({ solved: true, score: 6, hints_revealed: 1 });
    expect((await apiListNotebook(player.token)).total).toBe(0);

    // Act — keep it
    await page.getByRole("button", { name: "Keep in your kunnash" }).click();

    // Assert — the action becomes its kept link, focus follows, and the server agrees
    const kept = page.getByRole("link", { name: "Kept in your kunnash" });
    await expect(kept).toBeVisible({ timeout: 10_000 });
    await expect(kept).toBeFocused();
    await expect(page.getByRole("button", { name: "Keep in your kunnash" })).toHaveCount(0);
    const listed = await apiListNotebook(player.token);
    expect(listed.total).toBe(1);
    const [entry] = listed.entries;
    expect(entry).toMatchObject({ word: word.word_en, game_type: "daily_word", source_game_id: null });
    expect(dbNotebookEntries(player.userId)).toEqual([{ term: word.word_en, game_type: "DAILY_WORD", source_game_id: null }]);

    // The kunnash lists it under its own heading
    await kept.click();
    await expect(page).toHaveURL(/\/notebook$/, { timeout: 10_000 });
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Kunnash");
    await expect(page.locator("[data-notebook-entry]")).toHaveCount(1, { timeout: 10_000 });
    await expect(page.getByRole("heading", { level: 2 }).filter({ hasText: "Word of the day" })).toBeVisible();
    await expect(page.locator(`[data-notebook-entry="${entry.id}"]`)).toContainText(entry.word_display);

    // Back on /today the word reads as kept, after a reload too
    await page.goto("/today");
    await expect(page.getByRole("link", { name: "Kept in your kunnash" })).toBeVisible({ timeout: 15_000 });

    await player.close();
  });

  test("the home card leads to today’s word, and follows the player's day", async ({ page, browser }) => {
    // Prepare — the day's word, read once so it is drawn
    await openToday(page);
    const { word } = await todaysWord(page);

    // Act — a signed-out visitor on the home page
    await page.goto("/");

    // Assert — the card: its name, hint 1, and the way to /today
    const card = page.locator(".home-daily");
    await expect(card.getByRole("heading", { level: 2, name: "Word of the day" })).toBeVisible({ timeout: 15_000 });
    await expect(card).toContainText(/#\d+/);
    await expect(card).toContainText(CATEGORY_TEXT[word.category]);
    await expect(card).toContainText(word.hints_en["1"]);
    const find = card.getByRole("link", { name: "Find today’s word" });
    await expect(find).toHaveAttribute("href", "/today");
    await find.click();
    await expect(page).toHaveURL(/\/today$/);
    await expect(page.getByRole("heading", { level: 1, name: "Word of the day" })).toBeVisible();

    // A player under way: the card shows the hint they reached and offers to continue
    const player = await newPlayer(browser);
    await openToday(player.page);
    await player.page.getByRole("button", { name: "Another hint: 5 points instead of 6" }).click();
    await expect(player.page.getByRole("list", { name: LADDER }).locator('[data-rung="2"]')).toHaveAttribute("data-state", "now");
    await player.page.goto("/");
    const playerCard = player.page.locator(".home-daily");
    await expect(playerCard).toContainText(word.hints_en["2"], { timeout: 15_000 });
    await expect(playerCard).toContainText("hint 2");
    await playerCard.getByRole("link", { name: "Continue today’s word" }).click();
    await expect(player.page).toHaveURL(/\/today$/);

    // ...and, once they have given up, says so and offers to see the word
    await player.page.getByRole("button", { name: "Give up" }).click();
    await player.page.getByRole("alertdialog").getByRole("button", { name: "Show me the word" }).click();
    await expect(player.page.getByRole("heading", { name: "The word was", level: 2 })).toBeVisible({ timeout: 15_000 });
    await player.page.goto("/");
    await expect(playerCard).toContainText("You gave up today’s word", { timeout: 15_000 });
    await expect(playerCard.getByRole("link", { name: "See today’s word" })).toHaveAttribute("href", "/today");

    await player.close();
  });
});

import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI, gameIdFromUrl, type UIGameSetup } from "../../helpers/ui-game-setup";
import { apiGetMCQQuizState, apiMCQQuizNextRound, apiSubmitMCQQuizAnswer, apiUpdateRoomSettings } from "../../helpers/api-client";

/**
 * "Share" on a game's colophon (every game; here The Quiz, the quickest to finish). Where
 * the browser can hand a file to the system's share sheet, the tap draws the colophon card
 * (a PNG, on the device) and shares it with the line; where it cannot (Firefox desktop,
 * Linux Chromium: no Web Share), the tap copies the line, "Majlisna · The Quiz · Yusuf’s
 * majlis · 1 question · … · majlisna.app", and says so.
 *
 * The browser's own share sheet and clipboard are replaced by recorders (an init script),
 * so each spec decides what the browser can do and reads exactly what the page handed it.
 */

interface Handed {
  copied: string[];
  shared: { title?: string; text?: string; files: { name: string; type: string; size: number }[] }[];
}

/** No Web Share at all; the clipboard records what is written to it. */
function withoutWebShare() {
  const nav = Navigator.prototype as unknown as Record<string, unknown>;
  delete nav.share;
  delete nav.canShare;
  const handed = { copied: [] as string[], shared: [] as unknown[] };
  (window as unknown as { __handed: unknown }).__handed = handed;
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: async (text: string) => void handed.copied.push(text) },
  });
}

/** A share sheet that takes PNG files, recording what it was handed; the clipboard records too. */
function withFileSharing() {
  const handed = { copied: [] as string[], shared: [] as unknown[] };
  (window as unknown as { __handed: unknown }).__handed = handed;
  Object.defineProperty(navigator, "canShare", {
    configurable: true,
    value: (data: { files?: File[] }) => !!data.files && data.files.every((f) => f.type === "image/png"),
  });
  Object.defineProperty(navigator, "share", {
    configurable: true,
    value: async (data: { title?: string; text?: string; files?: File[] }) =>
      void handed.shared.push({
        title: data.title,
        text: data.text,
        files: (data.files ?? []).map((f) => ({ name: f.name, type: f.type, size: f.size })),
      }),
  });
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: async (text: string) => void handed.copied.push(text) },
  });
}

const handed = (page: Page) => page.evaluate(() => (window as unknown as { __handed: Handed }).__handed);

/** A one-question Quiz played to its colophon by its only player. */
async function quizToColophon(browser: Parameters<typeof setupRoomWithPlayers>[0], browserCan: () => void): Promise<UIGameSetup> {
  const accounts = await generateTestAccounts(1);
  const setup = await setupRoomWithPlayers(browser, accounts, "mcq_quiz");
  const player = setup.players[0];
  const token = player.login.access_token;
  await apiUpdateRoomSettings(setup.roomId, { mcq_quiz_rounds: 1, mcq_quiz_turn_duration: 600 }, token);
  await player.page.addInitScript(browserCan);
  await startGameViaAPI(setup.players, "mcq_quiz", setup.roomId);
  const gameId = gameIdFromUrl(player.page, "mcqquiz");
  await apiSubmitMCQQuizAnswer(gameId, 0, token);
  await expect.poll(async () => (await apiGetMCQQuizState(gameId, token)).round_phase, { timeout: 15_000 }).toBe("results");
  await apiMCQQuizNextRound(gameId, token);
  await expect(player.page.getByText("Final Scores")).toBeVisible({ timeout: 15_000 });
  return setup;
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The colophon's line: the game, whose majlis (a name isolated in U+2068/U+2069), its count, how long it lasted. */
const shareLine = (host: string) => new RegExp(`^Majlisna · The Quiz · ⁨${escape(host)}⁩’s majlis · 1 question( · [^·]+)? · majlisna\\.app$`);

test.describe("The Quiz — Share on the colophon", () => {
  test("without Web Share, Share copies the colophon's line and says so", async ({ browser }) => {
    // Prepare
    const setup = await quizToColophon(browser, withoutWebShare);
    const { page, login } = setup.players[0];
    const share = page.getByRole("button", { name: "Share", exact: true });
    // the way on, in order: … Play again, Share, Leave the room
    await expect(share).toBeVisible();
    await expect(page.getByRole("button", { name: "Play again" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Leave the room" })).toBeVisible();

    // Act
    await share.click();

    // Assert — the line is copied, the button and the live region say so, nothing was shared
    await expect(page.getByRole("button", { name: "Copied", exact: true })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "The line is copied: paste it to share it." })).toBeAttached();
    const { copied, shared } = await handed(page);
    expect(copied).toHaveLength(1);
    expect(copied[0]).toMatch(shareLine(login.user.username));
    expect(shared).toEqual([]);

    await setup.cleanup();
  });

  test("where files can be shared, Share hands the share sheet the colophon card as a PNG", async ({ browser }) => {
    // Prepare
    const setup = await quizToColophon(browser, withFileSharing);
    const { page, login } = setup.players[0];

    // Act
    await page.getByRole("button", { name: "Share", exact: true }).click();

    // Assert — one share: the card (a PNG drawn on the device), the game's name, the line
    await expect.poll(async () => (await handed(page)).shared.length, { timeout: 15_000 }).toBe(1);
    const { copied, shared } = await handed(page);
    expect(shared[0].title).toBe("The Quiz");
    expect(shared[0].text).toMatch(shareLine(login.user.username));
    expect(shared[0].files).toHaveLength(1);
    expect(shared[0].files[0].type).toBe("image/png");
    expect(shared[0].files[0].name).toMatch(/\.png$/);
    expect(shared[0].files[0].size).toBeGreaterThan(10_000);
    expect(copied).toEqual([]);
    // the button is itself again, not busy
    await expect(page.getByRole("button", { name: "Share", exact: true })).toBeEnabled();

    await setup.cleanup();
  });
});

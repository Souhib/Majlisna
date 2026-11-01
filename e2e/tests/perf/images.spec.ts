import { test, expect, type Page, type Response } from "@playwright/test";
import { FIRST_VISIT_STORAGE, signInPage } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";

/**
 * The images a screen downloads are the size it draws (WP-23).
 *
 * - The home sky: a 768 × 1024 tablet at DPR 1 draws its 2:1 crop about 960 px wide (the
 *   cover box is wider than the viewport in portrait), so it takes tab1200 (≤ 110 kB),
 *   not the 215 kB tab1600 the preload and the <picture> used to ask for. One sky only:
 *   the preload in index.html and the <picture> agree.
 * - The arch of a colophon (the Jabreen photograph): a 390 px phone at DPR 3 draws it
 *   1170 px wide, so it takes the 1200w file, not the 1600w one (there was no 1200w).
 */

const SKY_MAX_BYTES = 110_000;

/** The word of the day turns at midnight in Makkah (21:00 UTC); a give-up must not straddle it. */
function msToMakkahMidnight(now = Date.now()): number {
  const next = new Date(now);
  next.setUTCHours(21, 0, 0, 0);
  if (next.getTime() <= now) next.setUTCDate(next.getUTCDate() + 1);
  return next.getTime() - now;
}

/** Every response whose path matches, with its body length. */
function collect(page: Page, pattern: RegExp): { url: string; bytes: Promise<number> }[] {
  const seen: { url: string; bytes: Promise<number> }[] = [];
  page.on("response", (response: Response) => {
    if (pattern.test(new URL(response.url()).pathname)) {
      seen.push({ url: response.url(), bytes: response.body().then((b) => b.length) });
    }
  });
  return seen;
}

test.describe("Perf — image sizes", () => {
  for (const colorScheme of ["dark", "light"] as const) {
    test(`a 768 × 1024 tablet at DPR 1 downloads one sky of ${SKY_MAX_BYTES / 1000} kB or less (${colorScheme})`, async ({ browser }) => {
      const context = await browser.newContext({
        storageState: FIRST_VISIT_STORAGE,
        viewport: { width: 768, height: 1024 },
        deviceScaleFactor: 1,
        colorScheme,
      });
      const page = await context.newPage();
      const skies = collect(page, /^\/sky\//);

      await page.goto("/");
      await page.waitForLoadState("networkidle");

      expect(skies.map((s) => new URL(s.url).pathname)).toEqual([
        `/sky/${colorScheme === "dark" ? "sky-maghrib" : "sky-asr"}.tab1200.webp`,
      ]);
      expect(await skies[0].bytes).toBeLessThanOrEqual(SKY_MAX_BYTES);
      // ...and it is the one the <picture> draws
      const drawn = await page.locator(".home-hero picture img, picture img").first().evaluate((img) => (img as HTMLImageElement).currentSrc);
      expect(new URL(drawn).pathname).toBe(new URL(skies[0].url).pathname);

      await context.close();
    });
  }

  test("a colophon on a 390 px phone at DPR 3 loads the 1200w arch photograph", async ({ browser }, testInfo) => {
    // Close to the turn of the day, wait for the new one (the give-up names its day)
    const ms = msToMakkahMidnight();
    if (ms < 2 * 60_000) {
      testInfo.setTimeout(testInfo.timeout + ms + 10_000);
      await new Promise((resolve) => setTimeout(resolve, ms + 5_000));
    }

    // Prepare — a phone, signed in, on the word of the day (its reveal is a colophon in the arch)
    const [account] = await generateTestAccounts(1);
    const context = await browser.newContext({
      storageState: FIRST_VISIT_STORAGE,
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 3,
      isMobile: true,
      hasTouch: true,
    });
    const page = await context.newPage();
    await signInPage(page, account.email, account.password);
    const arches = collect(page, /jabreen-niches\.duo\.\d+-[^/]*\.webp$/);
    await page.goto("/today");
    await expect(page.getByRole("textbox", { name: "Your answer" })).toBeVisible({ timeout: 15_000 });

    // Act — give up: the reveal opens in the arch
    await page.getByRole("button", { name: "Give up" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Show me the word" }).click();
    const photo = page.locator(".arch-photo img");
    await expect(photo).toBeVisible({ timeout: 15_000 });
    await photo.scrollIntoViewIfNeeded();
    await expect.poll(() => photo.evaluate((img) => (img as HTMLImageElement).currentSrc), { timeout: 15_000 }).toContain(".1200");

    // Assert — the 1200w file, and only it
    await expect.poll(() => arches.length, { timeout: 15_000 }).toBeGreaterThan(0);
    const names = arches.map((a) => new URL(a.url).pathname);
    expect(names.every((n) => n.includes("jabreen-niches.duo.1200")), names.join(", ")).toBe(true);

    await context.close();
  });
});

import { test, expect, type Page } from "@playwright/test";
import { FRONTEND_URL } from "../../helpers/constants";
import { dbDailyWordHints } from "../../helpers/db";

/**
 * A phone says its language with its region (ar-SA, fr-FR). That raw tag used to become
 * the page's language: Arabic laid out left to right, cached in localStorage for good,
 * and sent to the API as `?lang=ar-SA`, which answered English. Now the page's language
 * is the bare code, so an ar-SA phone reads the page right to left and the word of the
 * day's hint in Arabic (WP-05).
 *
 * Also WP-05: Google's sign-in script loads on the sign-in pages only, not on every page.
 */

const GSI = /accounts\.google\.com\/gsi\/client/;

/** The Makkah day /today shows (`<time dateTime>` in its line). */
async function shownDay(page: Page): Promise<string> {
  const time = page.locator(".daily-meta time");
  await expect(time).toHaveAttribute("datetime", /^\d{4}-\d{2}-\d{2}$/, { timeout: 15_000 });
  return (await time.getAttribute("datetime"))!;
}

test.describe("i18n — a regional browser language", () => {
  test("an ar-SA phone gets the page in Arabic, right to left, and today's hint in Arabic", async ({ browser }) => {
    // Prepare — a first visit (no stored language, no welcome done) from an ar-SA browser
    const context = await browser.newContext({ locale: "ar-SA", storageState: { cookies: [], origins: [] } });
    const page = await context.newPage();
    const asked: string[] = [];
    page.on("request", (r) => {
      const lang = new URL(r.url()).searchParams.get("lang");
      if (lang) asked.push(lang);
    });

    // Act — the welcome dialog offers the three languages; Escape keeps the detected one
    await page.goto(FRONTEND_URL);
    const welcome = page.getByRole("dialog");
    await expect(welcome).toBeVisible({ timeout: 15_000 });
    await expect(welcome).toContainText("اختر لغتك");
    await page.keyboard.press("Escape");
    await expect(welcome).toHaveCount(0);

    // Assert — the bare language: Arabic, right to left, and stored as "ar", never "ar-SA"
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.locator("html")).toHaveAttribute("lang", "ar");
    expect(await page.evaluate(() => localStorage.getItem("majlisna-language"))).toBe("ar");

    // ...and the word of the day reads in Arabic: its first hint is the Arabic one
    await page.goto(`${FRONTEND_URL}/today`);
    const day = await shownDay(page);
    const rung = page.locator('[data-rung="1"]');
    await expect(rung).toContainText(dbDailyWordHints(day, "ar")["1"], { timeout: 15_000 });
    expect(asked.length).toBeGreaterThan(0);
    expect(asked.every((lang) => lang === "ar")).toBe(true);

    await context.close();
  });
});

test.describe("Google's sign-in script", () => {
  test("loads on the sign-in page only, never on the home or about page", async ({ page }) => {
    // Google's script is answered locally (the stack's client id is a placeholder)
    const scripts: string[] = [];
    await page.route(GSI, (route) => route.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
    page.on("request", (r) => {
      if (GSI.test(r.url())) scripts.push(new URL(page.url()).pathname);
    });

    for (const path of ["/", "/about"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await expect(page.locator('script[src*="accounts.google.com/gsi/client"]')).toHaveCount(0);
    }
    expect(scripts).toEqual([]);

    await page.goto("/auth/login");
    await expect(page.locator('script[src*="accounts.google.com/gsi/client"]')).toHaveCount(1, { timeout: 15_000 });
    await expect.poll(() => scripts.length).toBe(1);

    // ...and it goes when the sign-in page does
    await page.getByRole("link", { name: "About", exact: true }).first().click();
    await expect(page).toHaveURL(/\/about$/);
    await expect(page.locator('script[src*="accounts.google.com/gsi/client"]')).toHaveCount(0);
  });
});

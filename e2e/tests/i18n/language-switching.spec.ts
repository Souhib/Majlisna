import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { FRONTEND_URL, ROUTES } from "../../helpers/constants";

/**
 * The nav's language switch (a group of EN / FR / ع buttons). Its own label is
 * translated ("Switch language", « Changer de langue », «تغيير اللغة»), so it is found
 * by the French button it holds, whatever the current language.
 */
function languageSwitch(page: Page) {
  return page.getByRole("banner").locator('[role="group"]:has(button[lang="fr"])');
}

test.describe("i18n Language Switching", () => {
  test("switching to French updates UI text", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const page = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );

    // Reset language to English first
    await page.evaluate(() => localStorage.setItem("majlisna-language", "en"));
    await page.goto(FRONTEND_URL);
    await page.waitForLoadState("domcontentloaded");

    // The nav's language switch: three always-visible buttons, one tap each
    const frenchOption = languageSwitch(page).getByRole("button", { name: "Français" });
    await expect(frenchOption).toBeVisible({ timeout: 10_000 });
    await expect(frenchOption).toHaveAttribute("aria-pressed", "false");
    await frenchOption.click();
    await expect(frenchOption).toHaveAttribute("aria-pressed", "true");

    // Verify French text appears — "Salons" is French for "Rooms"
    await expect(
      page.locator("text=Salons").first(),
    ).toBeVisible({ timeout: 10_000 });

    await page.context().close();
  });

  test("switching to Arabic enables RTL layout", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const page = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );

    // Reset language to English first
    await page.evaluate(() => localStorage.setItem("majlisna-language", "en"));
    await page.goto(FRONTEND_URL);
    await page.waitForLoadState("domcontentloaded");

    // The nav's language switch: three always-visible buttons, one tap each
    const arabicOption = languageSwitch(page).getByRole("button", { name: "العربية" });
    await expect(arabicOption).toBeVisible({ timeout: 10_000 });
    await arabicOption.click();
    await expect(arabicOption).toHaveAttribute("aria-pressed", "true");

    // Verify the HTML element has dir="rtl"
    await expect.poll(
      async () => page.locator("html").getAttribute("dir"),
      { timeout: 10_000 },
    ).toBe("rtl");

    await page.context().close();
  });

  test("language persists across page navigation", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const page = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );

    // Reset language to English first
    await page.evaluate(() => localStorage.setItem("majlisna-language", "en"));
    await page.goto(FRONTEND_URL);
    await page.waitForLoadState("domcontentloaded");

    // Switch to French
    const frenchOption = languageSwitch(page).getByRole("button", { name: "Français" });
    await expect(frenchOption).toBeVisible({ timeout: 10_000 });
    await frenchOption.click();
    await expect(frenchOption).toHaveAttribute("aria-pressed", "true");

    // Verify French is active
    await expect(
      page.locator("text=Salons").first(),
    ).toBeVisible({ timeout: 10_000 });

    // Navigate to the leaderboard page
    await page.goto(`${FRONTEND_URL}${ROUTES.leaderboard}`);
    await page.waitForLoadState("domcontentloaded");

    // Verify French text is still shown — nav should show "Salons" not "Rooms"
    await expect(
      page.locator("text=Salons").first(),
    ).toBeVisible({ timeout: 10_000 });

    await page.context().close();
  });
});

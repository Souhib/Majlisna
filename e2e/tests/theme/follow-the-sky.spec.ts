import { test, expect, type Browser, type Page, type Request } from "@playwright/test";
import { FIRST_VISIT_STORAGE } from "../../fixtures/auth.fixture";
import { FRONTEND_URL } from "../../helpers/constants";

/**
 * "Follow the sky" (the theme menu): the afternoon light from sunrise to Maghrib, the
 * night from Maghrib to sunrise, computed on the device from the stored prayer-times
 * city. Nothing is asked of the network. The choice is stored (`majlisna-theme` = "sky",
 * and the week of turns in `majlisna-sky-light`), and index.html's inline script applies
 * the sky's light before the first paint, with no app script at all.
 *
 * The places are on the equator, where the sun rises near 06:00 and sets near 18:00 solar
 * time all year: one at solar midnight (night, six hours from either turn) and one at
 * solar noon (day). The device's light is set to the other light each time, so the page
 * can only show the sky's light if the sky decided it.
 */

type Light = "light" | "dark";

/** The longitude where the mean solar time is `hour` right now. */
function longitudeAtSolarHour(hour: number, now = new Date()): number {
  const utcHours = now.getUTCHours() + now.getUTCMinutes() / 60;
  let lng = (hour - utcHours) * 15;
  while (lng < -180) lng += 360;
  while (lng >= 180) lng -= 360;
  return Math.round(lng * 1000) / 1000;
}

const PLACES: { city: string; solarHour: number; sky: Light; note: RegExp }[] = [
  { city: "Midnight Meridian", solarHour: 0, sky: "dark", note: /^Day comes back at sunrise, \d{2}:\d{2} in Midnight Meridian\.$/ },
  { city: "Noon Meridian", solarHour: 12, sky: "light", note: /^Night comes at Maghrib, \d{2}:\d{2} in Noon Meridian\.$/ },
];

const other = (light: Light): Light => (light === "dark" ? "light" : "dark");

/** A visitor whose device is in `device` light, with a prayer-times city stored. */
async function visitorWithCity(browser: Browser, device: Light, city: string, lng: number): Promise<Page> {
  const context = await browser.newContext({
    colorScheme: device,
    serviceWorkers: "block",
    storageState: {
      cookies: [],
      origins: [
        {
          origin: FRONTEND_URL,
          localStorage: [
            ...FIRST_VISIT_STORAGE.origins[0].localStorage,
            { name: "majlisna-city", value: city },
            { name: "majlisna-coordinates", value: JSON.stringify({ lat: 0, lng }) },
          ],
        },
      ],
    },
  });
  return context.newPage();
}

test.describe("Theme — Follow the sky", () => {
  for (const place of PLACES) {
    test(`at solar ${place.solarHour === 0 ? "midnight" : "noon"} the sky gives the ${place.sky === "dark" ? "night" : "afternoon"}, stored, before paint, with no request`, async ({
      browser,
    }) => {
      // Prepare — a device in the other light, a city on the equator at that solar hour
      const device = other(place.sky);
      const lng = longitudeAtSolarHour(place.solarHour);
      const page = await visitorWithCity(browser, device, place.city, lng);
      await page.goto("/privacy");
      const html = page.locator("html");
      await expect(html).toHaveAttribute("data-theme", device);

      const trigger = page.getByRole("button", { name: "Theme: Your device’s light" });
      await trigger.click();
      const menu = page.getByRole("menu");
      await expect(menu).toBeVisible();
      await expect(menu).toContainText("Theme");
      const sky = menu.getByRole("menuitemradio", { name: "Follow the sky" });
      // the choice says what it will do, as its description
      await expect(sky).toHaveAccessibleDescription(place.note);

      // Act — choose it, watching every request the page makes from now on
      const requests: Request[] = [];
      page.on("request", (request) => requests.push(request));
      await sky.click();

      // Assert — the sky's light, at once
      await expect(html).toHaveAttribute("data-theme", place.sky);
      expect(await page.evaluate(() => document.documentElement.classList.contains("dark"))).toBe(place.sky === "dark");
      await expect(page.getByRole("button", { name: "Theme: Follow the sky" })).toBeVisible();
      expect(
        requests.map((r) => r.url()),
        "choosing the sky asked the network",
      ).toEqual([]);

      // ...stored: the choice, and the light with the week of turns the pre-paint script walks
      const stored = await page.evaluate(() => ({
        theme: localStorage.getItem("majlisna-theme"),
        sky: JSON.parse(localStorage.getItem("majlisna-sky-light") ?? "null") as { light: string; turns: [number, string][] } | null,
      }));
      expect(stored.theme).toBe("sky");
      expect(stored.sky?.light).toBe(place.sky);
      expect(stored.sky?.turns.length, "fewer than a week of turns").toBeGreaterThanOrEqual(12);
      expect(stored.sky!.turns[0][0]).toBeGreaterThan(Date.now());
      expect(stored.sky!.turns[0][1]).toBe(other(place.sky));

      // Act — a new visit of the same device, with every script but the inline one refused
      const storage = await page.context().storageState();
      await page.context().close();
      const context = await browser.newContext({ colorScheme: device, serviceWorkers: "block", storageState: storage });
      const bare = await context.newPage();
      const refused: string[] = [];
      await bare.route(/\.(m?js)(\?|$)/, (route) => {
        refused.push(route.request().url());
        return route.abort();
      });
      await bare.goto("/privacy");

      // Assert — the inline script alone put the page in the sky's light, against the device's
      expect(refused.length, "no app script was refused: the check proves nothing").toBeGreaterThan(0);
      await expect(bare.locator("#root")).toBeEmpty();
      expect(await bare.evaluate(() => document.documentElement.dataset.theme)).toBe(place.sky);
      expect(await bare.evaluate(() => document.documentElement.classList.contains("dark"))).toBe(place.sky === "dark");

      await context.close();
    });
  }
});

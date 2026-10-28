import { test, expect, type Page } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI } from "../../helpers/ui-game-setup";

/**
 * Deterministic contrast guard for text on a translucent tint.
 *
 * The axe scan next door caught a tinted label once and then couldn't reproduce it: it
 * runs right after `domcontentloaded`, while content is still mid entrance-animation,
 * and axe skips a node that is momentarily `opacity: 0`. Whether the label got measured
 * at all came down to how fast the machine was.
 *
 * This measures the settled state instead, and composites every translucent background
 * between the text and the first opaque one the way a browser does, so the number it
 * asserts is the number a player actually sees. Its subject is Kalimat's hint ladder:
 * the rung in play is a 9 % brass wash over the panel (`color-mix(... transparent)`),
 * carrying the hint itself and the small "now" tag, in both lights (the wash composites
 * over opposite grounds, so one light passing says nothing about the other).
 */

interface Measured {
  text: string;
  fontSize: string;
  ratio: number;
  tinted: boolean;
}

async function measureTintedText(page: Page, rootSelector: string): Promise<Measured[]> {
  return page.evaluate((selector) => {
    // Resolve ANY css colour (oklch, oklab, color-mix, rgba, …) to sRGB by painting it:
    // the theme is authored in oklch, which cannot be parsed with a regex.
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    type RGBA = [number, number, number, number];
    const toRgba = (css: string): RGBA => {
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = "#000";
      ctx.fillStyle = css;
      ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      return [d[0], d[1], d[2], d[3] / 255];
    };
    const over = (fg: RGBA, bg: RGBA): RGBA => [
      fg[0] * fg[3] + bg[0] * (1 - fg[3]),
      fg[1] * fg[3] + bg[1] * (1 - fg[3]),
      fg[2] * fg[3] + bg[2] * (1 - fg[3]),
      1,
    ];
    const luminance = ([r, g, b]: RGBA) => {
      const [R, G, B] = [r, g, b].map((c) => {
        const s = c / 255;
        return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * R + 0.7152 * G + 0.0722 * B;
    };

    /** Every background from the element up to the first opaque one, composited. */
    const groundOf = (el: Element): { ground: RGBA; tinted: boolean } => {
      const layers: RGBA[] = [];
      let node: Element | null = el;
      let base: RGBA = toRgba(getComputedStyle(document.body).backgroundColor);
      while (node) {
        const colour = toRgba(getComputedStyle(node).backgroundColor);
        if (colour[3] >= 1) {
          base = colour;
          break;
        }
        if (colour[3] > 0) layers.push(colour);
        node = node.parentElement;
      }
      let ground = base;
      for (const layer of layers.reverse()) ground = over(layer, ground);
      return { ground, tinted: layers.length > 0 };
    };

    const root = document.querySelector(selector);
    if (!root) return [];
    const out: { text: string; fontSize: string; ratio: number; tinted: boolean }[] = [];
    for (const el of [root, ...root.querySelectorAll("*")]) {
      // only elements that draw text themselves, and only what a sighted player sees
      const own = [...el.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE).map((n) => n.textContent ?? "").join("").trim();
      if (!own) continue;
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (box.width <= 1 || box.height <= 1 || style.visibility === "hidden" || el.closest("[aria-hidden='true']")) continue;
      const { ground, tinted } = groundOf(el);
      const fg = over(toRgba(style.color), ground);
      const [hi, lo] = [luminance(fg), luminance(ground)].sort((a, b) => b - a);
      out.push({ text: own, fontSize: style.fontSize, ratio: Number(((hi + 0.05) / (lo + 0.05)).toFixed(2)), tinted });
    }
    return out;
  }, rootSelector);
}

/** Wait until every finite animation on the page has finished (the thread clock loops). */
async function settle(page: Page): Promise<void> {
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
        .map((a) => a.finished.catch(() => undefined)),
    ),
  );
}

test.describe("Accessibility — Contrast", () => {
  test("Kalimat's hint in play meets WCAG AA on its brass wash, in both lights", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const setup = await setupRoomWithPlayers(browser, accounts, "word_quiz");
    await startGameViaAPI(setup.players, "word_quiz", setup.roomId);
    const page = setup.players[0].page;
    const gameUrl = page.url();

    for (const theme of ["dark", "light"] as const) {
      await page.evaluate((t) => localStorage.setItem("majlisna-theme", t), theme);
      await page.goto(gameUrl);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

      const rung = page
        .getByRole("list", { name: "Hints, from the vaguest to the most specific" })
        .locator('li[aria-current="step"]');
      await expect(rung).toBeVisible({ timeout: 15_000 });
      await settle(page);

      const measured = await measureTintedText(page, '.hint-ladder li[aria-current="step"]');
      const tinted = measured.filter((m) => m.tinted);
      expect(
        tinted.length,
        `${theme}: no text found on the rung's tint — has the hint ladder markup changed? ${JSON.stringify(measured)}`,
      ).toBeGreaterThanOrEqual(2);
      const failing = tinted.filter((m) => m.ratio < 4.5);
      expect(failing, `${theme}: text below the 4.5:1 AA floor for small text: ${JSON.stringify(failing)}`).toEqual([]);
    }

    await setup.cleanup();
  });
});

import { test, expect } from "@playwright/test";
import { ROUTES } from "../../helpers/constants";

/**
 * Deterministic contrast guard for the home page role chips.
 *
 * The axe scan next door caught these once and then couldn't reproduce it: it runs
 * right after `domcontentloaded`, while the cards are still mid entrance-animation,
 * and axe skips a node that is momentarily `opacity: 0`. Whether the chips got
 * measured at all came down to how fast the machine was — the violation showed up in
 * CI after three clean local runs.
 *
 * This measures the settled state instead, and composites the translucent chip tint
 * over its background the way a browser does, so the number it asserts is the number
 * a user actually sees.
 */
test.describe("Accessibility — Contrast", () => {
  test("home page chips meet WCAG AA for small text", async ({ page }) => {
    await page.goto(ROUTES.home);
    await page.waitForLoadState("networkidle");
    // The chips animate in; measure once they have stopped moving.
    await page.waitForTimeout(1500);

    const chips = await page.evaluate(() => {
      // Resolve ANY css colour (oklch, oklab, rgba, …) to sRGB by painting it — the
      // theme is authored in oklch, which cannot be parsed with a regex.
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 1;
      const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
      const toRgba = (css: string): [number, number, number, number] => {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = css;
        ctx.fillRect(0, 0, 1, 1);
        const d = ctx.getImageData(0, 0, 1, 1).data;
        return [d[0], d[1], d[2], d[3] / 255];
      };
      const over = (fg: [number, number, number, number], bg: [number, number, number, number]) =>
        [0, 1, 2].map((i) => fg[i] * fg[3] + bg[i] * (1 - fg[3])) as [number, number, number];
      const luminance = ([r, g, b]: number[]) => {
        const [R, G, B] = [r, g, b].map((c) => {
          const s = c / 255;
          return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
        });
        return 0.2126 * R + 0.7152 * G + 0.0722 * B;
      };

      return [...document.querySelectorAll("span.rounded-full.text-xs")].map((el) => {
        let node: HTMLElement | null = el.parentElement;
        let base: [number, number, number, number] = [255, 255, 255, 1];
        while (node) {
          const colour = toRgba(getComputedStyle(node).backgroundColor);
          if (colour[3] > 0) {
            base = colour;
            break;
          }
          node = node.parentElement;
        }
        const bg = over(toRgba(getComputedStyle(el).backgroundColor), base);
        const fg = over(toRgba(getComputedStyle(el).color), [...bg, 1] as [number, number, number, number]);
        const [hi, lo] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
        return {
          text: (el.textContent ?? "").trim(),
          fontSize: getComputedStyle(el).fontSize,
          ratio: Number(((hi + 0.05) / (lo + 0.05)).toFixed(2)),
        };
      });
    });

    expect(chips.length, "no chips found — has the home page markup changed?").toBeGreaterThan(0);
    const failing = chips.filter((c) => c.ratio < 4.5);
    expect(failing, `chips below the 4.5:1 AA floor for small text: ${JSON.stringify(failing)}`).toEqual([]);
  });
});

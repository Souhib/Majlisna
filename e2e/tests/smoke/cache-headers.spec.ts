import { test, expect } from "@playwright/test";
import { FRONTEND_URL } from "../../helpers/constants";

/**
 * What the frontend's nginx lets a browser (and Cloudflare) keep (WP-16, FP-06). Only
 * Vite's content-hashed output under /assets/ may be cached for good. Every file from
 * public/ keeps its name across releases, so it must be able to change: the service
 * worker is revalidated on every update check, the skies kept a week, the rest a day.
 * The old extension rule made all of them immutable for a year, the service worker
 * included, which Cloudflare would have kept at its edge.
 */

function maxAge(cacheControl: string): number {
  const match = cacheControl.match(/max-age=(\d+)/);
  return match ? Number(match[1]) : 0;
}

test.describe("Smoke — cache headers", () => {
  test("the service worker is revalidated every time", async ({ request }) => {
    const response = await request.head(`${FRONTEND_URL}/sw.js`);
    expect(response.status()).toBe(200);
    const cacheControl = response.headers()["cache-control"] ?? "";
    expect(cacheControl).toContain("no-cache");
    expect(cacheControl).not.toContain("immutable");
  });

  test("the public files keep their names, so none is immutable", async ({ request }) => {
    for (const [path, longest] of [
      ["/favicon.svg", 86_400],
      ["/favicon.ico", 86_400],
      ["/manifest.json", 86_400],
      ["/sky/sky-maghrib.800.webp", 604_800],
    ] as const) {
      const response = await request.get(`${FRONTEND_URL}${path}`);
      expect(response.status(), path).toBe(200);
      const cacheControl = response.headers()["cache-control"] ?? "";
      expect(cacheControl, path).not.toContain("immutable");
      expect(maxAge(cacheControl), `${path}: ${cacheControl}`).toBeLessThanOrEqual(longest);
    }
  });

  test("the hashed build output is immutable, and the page itself is not", async ({ page, request }) => {
    const shell = await page.goto("/");
    expect(shell!.headers()["cache-control"] ?? "").toContain("no-cache");

    const asset = await page.evaluate(() => (document.querySelector('script[type="module"][src*="/assets/"]') as HTMLScriptElement | null)?.src);
    expect(asset, "a hashed module on the page").toBeTruthy();
    const response = await request.get(asset!);
    expect(response.status()).toBe(200);
    const cacheControl = response.headers()["cache-control"] ?? "";
    expect(cacheControl).toContain("immutable");
    expect(maxAge(cacheControl)).toBe(31_536_000);
  });
});

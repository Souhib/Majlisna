import { expect, type Page } from "@playwright/test";

/**
 * The motion rule the specs hold every animated screen to (DESIGN.md §7): the final state
 * is in the DOM from the first frame, and the animation only moves what is already there.
 * A screen reader and a selector must find the same text with or without motion, and
 * nothing may stay at opacity 0 once the animation is over.
 *
 * `watchFrames` records, from inside the page, every animation frame from the first one in
 * which `selector` matches: the element's text and the animations then running in it. It is
 * started BEFORE the action that brings the screen (another player's move, a push), so the
 * first frame it records is the first frame the screen is drawn in.
 */

export interface WatchedFrame {
  /** ms since the first frame the selector matched */
  t: number;
  text: string;
  /** the animations alive in that frame, inside the element: CSS name, or id, or "anonymous" */
  animations: string[];
}

export interface FrameWatch {
  /** Every recorded frame, once the watch is over (`durationMs` after the first match). */
  frames: () => Promise<WatchedFrame[]>;
}

let watchCount = 0;

export async function watchFrames(page: Page, selector: string, { durationMs = 1_500, timeout = 30_000 } = {}): Promise<FrameWatch> {
  const key = `__frameWatch${++watchCount}`;
  await page.evaluate(
    ({ selector, key, durationMs }) => {
      const out: { t: number; text: string; animations: string[] }[] = [];
      const box = { out, done: false };
      (window as unknown as Record<string, unknown>)[key] = box;
      let start: number | null = null;
      const tick = (now: number) => {
        const el = document.querySelector(selector);
        if (el) {
          if (start === null) start = now;
          const animations = document
            .getAnimations()
            .filter((a) => {
              const target = (a.effect as KeyframeEffect | null)?.target;
              return !!target && (target === el || el.contains(target)) && a.playState !== "finished" && a.playState !== "idle";
            })
            .map((a) => (a as CSSAnimation).animationName || a.id || "anonymous");
          out.push({ t: Math.round(now - start), text: el.textContent ?? "", animations });
          if (now - start >= durationMs) {
            box.done = true;
            return;
          }
        }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    },
    { selector, key, durationMs },
  );
  return {
    frames: async () => {
      await page.waitForFunction((k) => (window as unknown as Record<string, { done: boolean }>)[k]?.done, key, { timeout });
      return page.evaluate((k) => (window as unknown as Record<string, { out: WatchedFrame[] }>)[k].out, key);
    },
  };
}

/** Every animation name seen in the watch. */
export function animationsSeen(frames: WatchedFrame[]): string[] {
  return [...new Set(frames.flatMap((f) => f.animations))];
}

/**
 * The watch's verdict: from its very first frame, and in every frame after it, the element
 * already says each of `texts`; and something was animating in it meanwhile (else the spec
 * would prove nothing about motion).
 */
export function expectTextFromFirstFrame(frames: WatchedFrame[], texts: (string | RegExp)[], what: string): void {
  expect(frames.length, `${what}: no frame recorded`).toBeGreaterThan(0);
  for (const frame of frames) {
    for (const text of texts) {
      const found = typeof text === "string" ? frame.text.includes(text) : text.test(frame.text);
      expect(found, `${what}: at +${frame.t} ms the text lacks ${String(text)}: "${frame.text}"`).toBe(true);
    }
  }
}

/** Wait until every finite animation on the page has finished (the thread clock runs for a whole phase). */
export async function settleAnimations(page: Page): Promise<void> {
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((a) => a.id !== "thread-clock" && a.effect?.getComputedTiming().iterations !== Infinity)
        .map((a) => a.finished.catch(() => undefined)),
    ),
  );
}

/**
 * The opacity each element matching `selector` (inside `root`) is drawn at, multiplied up its
 * ancestors: what the eye gets once the motion is over. A part left at 0 is a part that stayed hidden.
 */
export async function drawnOpacities(page: Page, selector: string): Promise<{ text: string; opacity: number }[]> {
  return page.evaluate((sel) => {
    return [...document.querySelectorAll(sel)].map((el) => {
      let opacity = 1;
      for (let node: Element | null = el; node; node = node.parentElement) opacity *= Number(getComputedStyle(node).opacity);
      return { text: (el.textContent ?? "").trim(), opacity: Math.round(opacity * 100) / 100 };
    });
  }, selector);
}

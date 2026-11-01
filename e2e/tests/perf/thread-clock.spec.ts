import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers, startGameViaAPI, dismissRoleRevealAll } from "../../helpers/ui-game-setup";

/**
 * The thread clock runs on the compositor (WP-18). It used to animate `width`: a 500 ms
 * width transition on a one-second tick, so the thread moved half of each second and
 * stood still the other half, and every frame it moved laid the page out (308 layouts in
 * 5 s on a phone). Now it is ONE `transform` animation per timer window (id
 * "thread-clock"), and the 500 ms tick only changes the figures.
 *
 * Measured like the animations audit's p3-clock probe: a Chrome trace of 5 s of a timed
 * phase with nothing else moving, and the page's animations sampled all along.
 */

interface TraceEvent {
  name: string;
  ph: string;
}

test.describe("Perf — the thread clock", () => {
  test("five seconds of a timed phase: one transform animation, no width, few layouts", async ({ browser }) => {
    // Prepare — an Undercover table at its (600 s) describing phase
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    await startGameViaAPI(setup.players, "undercover", setup.roomId);
    await dismissRoleRevealAll(setup.players);
    const page = setup.players[0].page;
    await expect(page.locator('[role="timer"][aria-label^="Time left: "]')).toBeVisible({ timeout: 15_000 });
    // the entrance animations finish; the clock's own runs for the whole phase
    await page.evaluate(() =>
      Promise.all(
        document
          .getAnimations()
          .filter((a) => a.id !== "thread-clock" && a.effect?.getComputedTiming().iterations !== Infinity)
          .map((a) => a.finished.catch(() => undefined)),
      ),
    );

    // The clock is one animation, of transform
    const clock = await page.evaluate(() => {
      const thread = document.getAnimations().filter((a) => a.id === "thread-clock");
      const keyframes = thread.flatMap((a) => (a.effect as KeyframeEffect).getKeyframes());
      return { count: thread.length, properties: [...new Set(keyframes.flatMap((k) => Object.keys(k)))] };
    });
    expect(clock.count).toBe(1);
    expect(clock.properties).toContain("transform");
    expect(clock.properties).not.toContain("width");

    // Act — trace 5 s, sampling every animation on the page every 100 ms meanwhile
    const cdp = await page.context().newCDPSession(page);
    const events: TraceEvent[] = [];
    cdp.on("Tracing.dataCollected", (e) => {
      for (const event of e.value) events.push({ name: String(event.name), ph: String(event.ph) });
    });
    const done = new Promise<void>((resolve) => cdp.once("Tracing.tracingComplete", () => resolve()));
    await cdp.send("Tracing.start", {
      categories: "devtools.timeline,disabled-by-default-devtools.timeline",
      transferMode: "ReportEvents",
    });
    const animated = await page.evaluate(
      () =>
        new Promise<string[]>((resolve) => {
          const seen = new Set<string>();
          const sample = () => {
            for (const a of document.getAnimations()) {
              if (a instanceof CSSTransition) seen.add(a.transitionProperty);
              const effect = a.effect as KeyframeEffect | null;
              for (const k of effect?.getKeyframes() ?? []) for (const p of Object.keys(k)) seen.add(p);
            }
          };
          const timer = setInterval(sample, 100);
          setTimeout(() => {
            clearInterval(timer);
            resolve([...seen]);
          }, 5_000);
        }),
    );
    await cdp.send("Tracing.end");
    await done;

    // Assert — nothing animated `width`, and the page was laid out only a handful of times
    expect(animated).not.toContain("width");
    const layouts = events.filter((e) => e.name === "Layout" && e.ph !== "E").length;
    expect(layouts, `${layouts} layouts in 5 s`).toBeLessThan(20);

    await setup.cleanup();
  });
});

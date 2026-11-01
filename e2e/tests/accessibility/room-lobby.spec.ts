import { test, expect } from "../../fixtures/auth.fixture";
import AxeBuilder from "@axe-core/playwright";
import { ROUTES } from "../../helpers/constants";

test.describe("Accessibility — Room Lobby", () => {
  test("rooms page has no critical or serious violations", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.rooms);
    await authenticatedPage.waitForLoadState("domcontentloaded");
    // Wait for actual content to render
    await expect(
      authenticatedPage.getByRole('heading', { name: 'Rooms', level: 1 }),
    ).toBeVisible({ timeout: 10_000 });
    // Wait for the entrance animations to finish (opacity 0→1), so axe measures the
    // colours a player sees: every finite animation on the page, not a guessed second
    await authenticatedPage.evaluate(() =>
      Promise.all(
        document
          .getAnimations()
          .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
          .map((a) => a.finished.catch(() => undefined)),
      ),
    );

    const results = await new AxeBuilder({ page: authenticatedPage })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const criticalViolations = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );

    expect(criticalViolations).toEqual([]);
  });
});

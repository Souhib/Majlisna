import { expect, test } from "../../fixtures/auth.fixture";
import { ROUTES } from "../../helpers/constants";

/**
 * The Content-Security-Policy is ENFORCED, not report-only. This is what makes that
 * safe to do: a missed source no longer fails silently in production, it fails here.
 *
 * The policy was report-only because the telemetry hosts are baked into the bundle at
 * build time and were not knowable to nginx. They are now substituted from the same
 * build args (see front/Dockerfile) — as is the API origin, which `'self'` does NOT
 * cover when the backend is served from a different port or subdomain. That last one
 * was found by this very test.
 *
 * Violations are collected through `console`, never `page.evaluate`. Playwright
 * evaluates in the page's main world, which Chromium subjects to CSP, so reading the
 * result with `evaluate` reports an `eval` violation of the harness's own making —
 * indistinguishable, in the assertion, from one belonging to the app.
 */

const MARKER = "__CSP_VIOLATION__";

/** Reports violations over console so no page evaluation is needed to read them. */
const REPORT_VIOLATIONS_OVER_CONSOLE = (marker: string) => {
  document.addEventListener("securitypolicyviolation", (event) => {
    // Only `enforce` breaks anything; a future report-only probe must not fail a test.
    if (event.disposition !== "enforce") return;
    console.warn(
      `${marker}${JSON.stringify({
        directive: event.effectiveDirective || event.violatedDirective,
        blockedURI: event.blockedURI,
        // Reported so a failure names the culprit instead of leaving you to guess
        // whether it is app code or the test harness.
        sourceFile: event.sourceFile,
        line: event.lineNumber,
        sample: event.sample,
      })}`,
    );
  });
};

type Violation = {
  directive: string;
  blockedURI: string;
  sourceFile?: string;
  line?: number;
  sample?: string;
};

/** Attaches the console listener and returns the growing list of violations. */
async function watchViolations(page: import("@playwright/test").Page): Promise<Violation[]> {
  const violations: Violation[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (text.startsWith(MARKER)) violations.push(JSON.parse(text.slice(MARKER.length)));
  });
  await page.addInitScript(REPORT_VIOLATIONS_OVER_CONSOLE, MARKER);
  return violations;
}

test.describe("Smoke — Content-Security-Policy", () => {
  test("the policy is enforced, not merely reported", async ({ page }) => {
    const response = await page.goto(ROUTES.home);
    const headers = response!.headers();

    expect(headers["content-security-policy"], "CSP header missing on the app shell").toBeTruthy();
    expect(
      headers["content-security-policy-report-only"],
      "a report-only header alongside the enforced one means the enforced one is probably a copy",
    ).toBeUndefined();
    // The build-time substitution must not leak its own placeholders.
    expect(headers["content-security-policy"]).not.toMatch(/__(API_CONNECT|TELEMETRY_\w+)_SRC__/);
  });

  test("public pages load with no CSP violations", async ({ page }) => {
    const violations = await watchViolations(page);

    for (const route of [ROUTES.home, ROUTES.login, ROUTES.register, ROUTES.leaderboard]) {
      await page.goto(route);
      await page.waitForLoadState("networkidle");
    }

    expect(violations, `CSP violations on the public pages: ${JSON.stringify(violations)}`).toEqual([]);
  });

  test("an authenticated page loads with no CSP violations", async ({ authenticatedPage }) => {
    // Covers what the public pages cannot: the API calls and the Socket.IO
    // connection, i.e. the `connect-src` half of the policy.
    const violations = await watchViolations(authenticatedPage);

    await authenticatedPage.goto(ROUTES.rooms);
    await authenticatedPage.waitForLoadState("networkidle");
    await expect(authenticatedPage.getByRole("heading", { name: "Rooms", level: 1 })).toBeVisible({
      timeout: 10_000,
    });

    expect(violations, `CSP violations on the rooms page: ${JSON.stringify(violations)}`).toEqual([]);
  });

  test("the security headers survive on a static asset and on /health", async ({ page }) => {
    // nginx drops inherited add_header in any location that declares its own, which
    // is why security-headers.conf is included per-location. These two locations set
    // their own Cache-Control / Content-Type and are the ones that regressed before.
    const shell = await page.goto(ROUTES.home);
    const assetUrl = await page.evaluate(() => {
      const script = [...document.querySelectorAll("script[src]")].find((s) =>
        (s as HTMLScriptElement).src.includes("/assets/"),
      );
      return (script as HTMLScriptElement | undefined)?.src;
    });
    expect(assetUrl, "no hashed asset found on the page").toBeTruthy();

    const asset = await page.request.get(assetUrl!);
    const health = await page.request.get("/health");

    for (const [name, response] of [
      ["app shell", shell!],
      ["static asset", asset],
      ["/health", health],
    ] as const) {
      const headers = response.headers();
      expect(headers["x-content-type-options"], `nosniff missing on ${name}`).toBe("nosniff");
      expect(headers["x-frame-options"], `X-Frame-Options missing on ${name}`).toBeTruthy();
      expect(headers["content-security-policy"], `CSP missing on ${name}`).toBeTruthy();
    }
  });
});

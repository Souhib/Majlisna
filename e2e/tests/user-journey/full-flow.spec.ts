import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "crypto";
import { FRONTEND_URL, TEST_USER, TEST_ADMIN } from "../../helpers/constants";

/**
 * Full user journey test: register → login → create room → join → start game.
 * This validates the complete flow through the UI so all other tests
 * can safely use API shortcuts for setup.
 */
test.describe("Full User Journey", () => {
  test("register, login, create room, join, and start game through UI", async ({
    browser,
  }) => {
    // ─── Step 1: Register player 1 via UI ─────────────────────
    const id = randomUUID().slice(0, 8);
    const player1Email = `journey-${id}@test.com`;
    const player1Password = "testpass1";
    const player1Username = `journey-${id}`;

    const ctx1 = await browser.newContext({
      storageState: {
        cookies: [],
        origins: [
          {
            origin: FRONTEND_URL,
            localStorage: [
              { name: "ipg-first-visit-complete", value: "true" },
            ],
          },
        ],
      },
    });
    const page1 = await ctx1.newPage();

    await page1.goto(`${FRONTEND_URL}/auth/register`);
    await page1.waitForLoadState("domcontentloaded");

    await page1.locator("#username").fill(player1Username);
    await page1.locator("#email").fill(player1Email);
    await page1.locator("#password").fill(player1Password);

    // Wait for the register API call to complete before navigating to login
    const [registerResponse] = await Promise.all([
      page1.waitForResponse((r) => r.url().includes("/register") && r.request().method() === "POST"),
      page1.locator('button[type="submit"]').click(),
    ]);
    expect(registerResponse.ok()).toBe(true);

    // Registration creates user, now login to get auth tokens
    // (backend register endpoint returns user data only, not tokens)
    await page1.goto(`${FRONTEND_URL}/auth/login`);
    await page1.waitForLoadState("domcontentloaded");

    await page1.locator("#email").fill(player1Email);
    await page1.locator("#password").fill(player1Password);
    await page1.locator('button[type="submit"]').click();

    // Should redirect to home after login
    await expect(page1).toHaveURL(/\/$/, { timeout: 15_000 });

    // Wait for auth tokens to be stored
    await page1.waitForFunction(
      (key) => !!localStorage.getItem(key),
      "ipg-token",
      { timeout: 10_000 },
    );

    // ─── Step 2: Create room via UI ───────────────────────────
    await page1.goto(`${FRONTEND_URL}/rooms/create`);
    // Retry if auth redirect happens (async auth init on page load)
    const onCreatePage = await page1
      .waitForURL(/\/rooms\/create/, { timeout: 5_000 })
      .then(() => true)
      .catch(() => false);
    if (!onCreatePage) {
      await page1.goto(`${FRONTEND_URL}/rooms/create`);
      await expect(page1).toHaveURL(/\/rooms\/create/, { timeout: 15_000 });
    }

    // Select "Undercover" game type (it may be default, click to be sure)
    await page1.locator('button:has-text("Undercover")').click();

    // Wait for submit button to be enabled (it shows "Loading..." while form initializes)
    const createSubmit = page1.locator('button[type="submit"]');
    await expect(createSubmit).toBeEnabled({ timeout: 15_000 });
    await createSubmit.click();

    // Should redirect to room lobby
    await expect(page1).toHaveURL(/\/rooms\/[a-f0-9-]+/, { timeout: 15_000 });

    // ─── Step 3: Extract room code + PIN from lobby ───────────
    // Wait for lobby to fully load with room data
    await page1.waitForLoadState("domcontentloaded");
    await page1.locator('text=Room Code').waitFor({ state: "visible", timeout: 15_000 });

    // Extract room code and password from the lobby page
    // The room code is displayed near "Room Code" label and the password near "Password" label
    const roomCode = await page1.evaluate(() => {
      // Find the Room Code section and get the code text
      const body = document.body.innerText;
      // Room code is a 5-char alphanumeric string shown after "Room Code"
      const codeMatch = body.match(/Room Code[\s\S]*?([A-Z0-9]{5})/);
      return codeMatch ? codeMatch[1] : null;
    });
    expect(roomCode).toBeTruthy();

    const roomPassword = await page1.evaluate(() => {
      const body = document.body.innerText;
      // Password is a 4-digit PIN shown after "Password"
      const pinMatch = body.match(/Password[\s\S]*?(\d{4})/);
      return pinMatch ? pinMatch[1] : null;
    });
    expect(roomPassword).toBeTruthy();

    // ─── Step 4: Login players 2-3 via UI ─────────────────────
    // Use pre-seeded test accounts
    const otherAccounts = [
      { email: TEST_USER.email, password: TEST_USER.password },
      { email: TEST_ADMIN.email, password: TEST_ADMIN.password },
    ];

    const otherPages: Page[] = [];
    for (const account of otherAccounts) {
      const ctx = await browser.newContext({
        storageState: {
          cookies: [],
          origins: [
            {
              origin: FRONTEND_URL,
              localStorage: [
                { name: "ipg-first-visit-complete", value: "true" },
              ],
            },
          ],
        },
      });
      const page = await ctx.newPage();

      await page.goto(`${FRONTEND_URL}/auth/login`);
      await page.waitForLoadState("domcontentloaded");

      await page.locator("#email").fill(account.email);
      await page.locator("#password").fill(account.password);
      await page.locator('button[type="submit"]').click();

      // Should redirect to home after login
      await expect(page).toHaveURL(/\/$/, { timeout: 15_000 });

      // Wait for auth tokens
      await page.waitForFunction(
        (key) => !!localStorage.getItem(key),
        "ipg-token",
        { timeout: 10_000 },
      );

      otherPages.push(page);
    }

    // ─── Step 5: Players 2-3 join room via UI ─────────────────
    for (const page of otherPages) {
      await page.goto(`${FRONTEND_URL}/rooms`);
      // Retry if auth redirect happens
      const onRooms = await page
        .waitForURL(/\/rooms/, { timeout: 5_000 })
        .then(() => true)
        .catch(() => false);
      if (!onRooms) {
        await page.goto(`${FRONTEND_URL}/rooms`);
      }
      await page.waitForLoadState("domcontentloaded");

      // Fill room code
      await page.locator('#room-code').fill(roomCode!);

      // Fill 4-digit PIN
      const pinDigits = roomPassword!.split("");
      for (let j = 0; j < 4; j++) {
        await page
          .locator(`input[aria-label="Password digit ${j + 1}"]`)
          .fill(pinDigits[j]);
      }

      // Click join
      const joinBtn = page.locator('button[type="submit"]');
      await expect(joinBtn).toBeEnabled({ timeout: 10_000 });
      await joinBtn.click();

      // Should redirect to room lobby
      await expect(page).toHaveURL(/\/rooms\/[a-f0-9-]+/, { timeout: 15_000 });
    }

    // ─── Step 6: Verify all 3 players see each other ──────────
    const allPages = [page1, ...otherPages];
    for (const page of allPages) {
      await page.waitForFunction(
        () => {
          const m = document.body.innerText.match(/Players \((\d+)/);
          return m && parseInt(m[1]) >= 3;
        },
        { timeout: 15_000 },
      );
    }

    // ─── Step 7: Host clicks Start ────────────────────────────
    const startButton = page1.locator('button:has-text("Start")');
    await expect(startButton).toBeEnabled({ timeout: 10_000 });
    await startButton.click();

    // All players should navigate to the game page
    for (const page of allPages) {
      await expect(page).toHaveURL(/\/game\/undercover\//, { timeout: 15_000 });
    }

    // ─── Step 8: Verify game UI visible ───────────────────────
    // All players should see the role reveal screen
    for (const page of allPages) {
      await expect(
        page.locator("text=Your Role"),
      ).toBeVisible({ timeout: 15_000 });
    }

    // Cleanup
    for (const page of allPages) {
      await page.context().close().catch(() => {});
    }
  });
});

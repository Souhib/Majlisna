import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import {
  apiLogin,
  apiCreateRoom,
  apiGetRoom,
  apiGetShareLink,
} from "../../helpers/api-client";
import { ROUTES, FRONTEND_URL } from "../../helpers/constants";

test.describe("Room Share Link", () => {
  test("share link contains room code and password", async ({ browser }) => {
    // Prepare
    const accounts = await generateTestAccounts(1);
    const login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(login.access_token);
    const roomDetails = await apiGetRoom(room.id, login.access_token);

    const page = await createPlayerPage(browser, accounts[0].email, accounts[0].password);
    await page.goto(ROUTES.room(room.id));
    await page.waitForLoadState("domcontentloaded");

    // Wait for room lobby to load
    await expect(page.locator(`text=${roomDetails.public_id}`)).toBeVisible({ timeout: 10_000 });

    // Act — intercept clipboard write to capture the copied URL
    let copiedText = "";
    await page.evaluate(() => {
      (window as unknown as { __clipboardText: string }).__clipboardText = "";
      Object.defineProperty(navigator, "clipboard", {
        value: {
          writeText: (text: string) => {
            (window as unknown as { __clipboardText: string }).__clipboardText = text;
            return Promise.resolve();
          },
          readText: () =>
            Promise.resolve(
              (window as unknown as { __clipboardText: string }).__clipboardText,
            ),
        },
        writable: true,
        configurable: true,
      });
    });

    // Click the share link button
    const shareButton = page.locator('button:has-text("Share Link")')
      .or(page.locator('button:has-text("Link Copied")'));
    await expect(shareButton).toBeVisible({ timeout: 10_000 });
    await shareButton.first().click();

    // Read the captured clipboard text
    copiedText = await page.evaluate(
      () => (window as unknown as { __clipboardText: string }).__clipboardText,
    );

    // Assert — URL contains code and pin parameters
    expect(copiedText).toContain("code=");
    expect(copiedText).toContain("pin=");
    expect(copiedText).toContain("/rooms/join");
    expect(copiedText).toContain(roomDetails.public_id);
    expect(copiedText).toContain(roomDetails.password);

    await page.context().close();
  });

  test("navigating to share link auto-joins room", async ({ browser }) => {
    // Prepare
    const accounts = await generateTestAccounts(2);
    const hostLogin = await apiLogin(accounts[0].email, accounts[0].password);
    const joinerLogin = await apiLogin(accounts[1].email, accounts[1].password);

    const room = await apiCreateRoom(hostLogin.access_token);

    // Get share link data via API
    const shareData = await apiGetShareLink(room.id, hostLogin.access_token);

    // Act — player 2 navigates to the share link URL
    const joinerPage = await createPlayerPage(browser, accounts[1].email, accounts[1].password);
    const shareUrl = `${FRONTEND_URL}/rooms/join?code=${shareData.public_id}&pin=${shareData.password}`;
    await joinerPage.goto(shareUrl);

    // Assert — player 2 is auto-joined and sees the room lobby
    await expect(joinerPage).toHaveURL(/\/rooms\/[a-f0-9-]+/, { timeout: 15_000 });

    // Verify player count shows 2 (host + joiner)
    await expect(joinerPage.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });

    await joinerPage.context().close();
  });

  test("invalid share link shows error", async ({ browser }) => {
    // Prepare
    const accounts = await generateTestAccounts(1);

    const page = await createPlayerPage(browser, accounts[0].email, accounts[0].password);

    // Act — navigate to an invalid share link
    await page.goto(`${FRONTEND_URL}/rooms/join?code=ZZZZZ&pin=9999`);

    // Assert — the page says the link failed, once and in place (no toast)
    const joinError = page.getByTestId("join-error");
    await expect(joinError).toBeVisible({ timeout: 15_000 });
    await expect(joinError).toHaveAttribute("role", "alert");
    await expect(page.locator('[data-sonner-toast][data-type="error"]')).toHaveCount(0);
    await expect(page).toHaveURL(/\/rooms\/join/);

    await page.context().close();
  });
});

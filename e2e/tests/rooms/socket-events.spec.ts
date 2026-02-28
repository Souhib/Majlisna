import { test, expect } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { apiLogin, apiCreateRoom, apiGetRoom } from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";
import { generateTestAccounts } from "../../helpers/test-setup";

test.describe("Rooms — Socket Events", () => {
  test("player 1 sees join notification when player 2 joins", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(2);
    // Player 1 creates room via API and navigates to lobby
    const p1Login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(p1Login.access_token, "undercover");

    const player1 = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await player1.goto(ROUTES.room(room.id));
    await player1.waitForLoadState("domcontentloaded");

    // Wait for socket connection and room page to render
    await player1.waitForFunction(
      () => /Players \(\d+/.test(document.body.innerText),
      { timeout: 10_000 },
    ).catch(() => {});

    // Player 2 joins via UI
    const player2 = await createPlayerPage(
      browser,
      accounts[1].email,
      accounts[1].password,
    );
    await player2.goto(ROUTES.rooms);
    await player2.waitForLoadState("domcontentloaded");

    // Get room details for code and password
    const roomDetails = await apiGetRoom(room.id, p1Login.access_token);

    await player2.locator('input[id="room-code"]').fill(roomDetails.public_id);
    const pinDigits = roomDetails.password.split("");
    for (let i = 0; i < 4; i++) {
      await player2
        .locator(`input[aria-label="Password digit ${i + 1}"]`)
        .fill(pinDigits[i]);
    }
    await player2.locator('button[type="submit"]').click();

    // Player 2 should land in the lobby
    await expect(player2).toHaveURL(/\/rooms\//, { timeout: 15_000 });

    // Player 1 should see a toast about player joining
    await expect(
      player1.locator('[data-sonner-toast]').first(),
    ).toBeVisible({ timeout: 10_000 });

    // Both players should see each other in the player list
    await player1.waitForTimeout(1000);
    const p1PlayerNames = await player1
      .locator(".bg-muted\\/50 .text-sm.font-medium, [class*='bg-muted'] .text-sm.font-medium")
      .allTextContents();
    expect(p1PlayerNames.length).toBeGreaterThanOrEqual(2);

    await player1.context().close();
    await player2.context().close();
  });

  test("player 1 sees leave notification when player 2 leaves", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(2);
    // Setup: create room and have both players join
    const p1Login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(p1Login.access_token, "undercover");
    const roomDetails = await apiGetRoom(room.id, p1Login.access_token);

    const player1 = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await player1.goto(ROUTES.room(room.id));
    await player1.waitForLoadState("domcontentloaded");
    await player1.waitForTimeout(2000);

    const player2 = await createPlayerPage(
      browser,
      accounts[1].email,
      accounts[1].password,
    );
    await player2.goto(ROUTES.rooms);
    await player2.waitForLoadState("domcontentloaded");
    await player2.locator('input[id="room-code"]').fill(roomDetails.public_id);
    const pinDigits = roomDetails.password.split("");
    for (let i = 0; i < 4; i++) {
      await player2
        .locator(`input[aria-label="Password digit ${i + 1}"]`)
        .fill(pinDigits[i]);
    }
    await player2.locator('button[type="submit"]').click();
    await expect(player2).toHaveURL(/\/rooms\//, { timeout: 15_000 });
    await player2.waitForTimeout(2000);

    // Player 2 disconnects by closing their page
    await player2.context().close();

    // Player 1 should eventually see a disconnected or left notification
    // Wait for the disconnect grace period event or permanent leave
    await expect(
      player1.locator('[data-sonner-toast]').last(),
    ).toBeVisible({ timeout: 15_000 });

    await player1.context().close();
  });

  test("ownership transfers when host leaves", async ({ browser }) => {
    test.setTimeout(90_000);
    const accounts = await generateTestAccounts(2);
    // Player 1 (host) creates room
    const p1Login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(p1Login.access_token, "undercover");
    const roomDetails = await apiGetRoom(room.id, p1Login.access_token);

    const player1 = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await player1.goto(ROUTES.room(room.id));
    await player1.waitForLoadState("domcontentloaded");
    await player1.waitForTimeout(2000);

    // Player 2 joins
    const player2 = await createPlayerPage(
      browser,
      accounts[1].email,
      accounts[1].password,
    );
    await player2.goto(ROUTES.rooms);
    await player2.waitForLoadState("domcontentloaded");
    await player2.locator('input[id="room-code"]').fill(roomDetails.public_id);
    const pinDigits = roomDetails.password.split("");
    for (let i = 0; i < 4; i++) {
      await player2
        .locator(`input[aria-label="Password digit ${i + 1}"]`)
        .fill(pinDigits[i]);
    }
    await player2.locator('button[type="submit"]').click();
    await expect(player2).toHaveURL(/\/rooms\//, { timeout: 15_000 });

    // Wait for player2 to appear in the player list (confirms socket join_room processed)
    await expect(player1.locator("text=Players (2)")).toBeVisible({ timeout: 10_000 });

    // Also ensure player2's socket is connected
    await player2.waitForFunction(
      () => (window as any).__SOCKET__?.connected === true,
      { timeout: 10_000 },
    ).catch(() => {});

    // Host (player 1) disconnects
    await player1.context().close();

    // After grace period (30s in e2e), ownership should transfer via socket event
    await player2.waitForTimeout(35_000);

    // Player 2 should now see the host controls (game type selector + start button)
    await expect(
      player2.locator('text=Game Type'),
    ).toBeVisible({ timeout: 10_000 });

    await player2.context().close();
  });
});

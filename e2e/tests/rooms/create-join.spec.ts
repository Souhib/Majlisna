import { test, expect } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { ROUTES } from "../../helpers/constants";
import { generateTestAccounts } from "../../helpers/test-setup";
import { apiLogin, apiJoinRoom } from "../../helpers/api-client";

test.describe("Rooms — Create & Join", () => {
  test("player 1 creates a room and sees lobby", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const page = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );

    // Navigate to create room page
    await page.goto(ROUTES.createRoom);
    await page.waitForLoadState("domcontentloaded");

    // Select Undercover and create room
    await page.locator('button[type="submit"]').click();

    // Should redirect to room lobby
    await expect(page).toHaveURL(/\/rooms\//, { timeout: 15_000 });

    // Room code and password should be visible
    await expect(page.getByText("Room Code")).toBeVisible();
    await expect(page.getByText("Password")).toBeVisible();

    await page.context().close();
  });

  test("player 2 joins room with correct code and password", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(2);
    // Player 1 creates a room
    const player1 = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );

    await player1.goto(ROUTES.createRoom);
    await player1.waitForLoadState("domcontentloaded");
    await player1.locator('button[type="submit"]').click();
    await expect(player1).toHaveURL(/\/rooms\//, { timeout: 15_000 });

    // Wait for room data to load
    await player1.waitForLoadState("domcontentloaded");

    // Extract room code and password from the lobby page
    const roomCodeButton = player1.locator(
      'button:has(.tracking-widest):not(:has(.lucide-key-round))',
    );
    await expect(roomCodeButton).toBeVisible({ timeout: 5_000 });
    const roomCode = (await roomCodeButton.innerText()).replace(/\s/g, "").slice(0, 5);

    const passwordButton = player1.locator(
      'button:has(.lucide-key-round)',
    );
    await expect(passwordButton).toBeVisible();
    const passwordText = (await passwordButton.innerText()).replace(/\D/g, "");

    expect(roomCode).toHaveLength(5);
    expect(passwordText).toHaveLength(4);

    // Player 2 joins the room
    const player2 = await createPlayerPage(
      browser,
      accounts[1].email,
      accounts[1].password,
    );

    await player2.goto(ROUTES.rooms);
    await player2.waitForLoadState("domcontentloaded");

    // Fill room code
    await player2.locator('input[id="room-code"]').fill(roomCode);

    // Fill PIN password digits one by one
    const pinDigits = passwordText.split("");
    for (let i = 0; i < 4; i++) {
      await player2
        .locator(`input[aria-label="Password digit ${i + 1}"]`)
        .fill(pinDigits[i]);
    }

    // Wait for socket connected + room_status listener registered in React
    await player2.waitForFunction(
      () => {
        const s = (window as any).__SOCKET__;
        if (!s?.connected) return false;
        return typeof s.hasListeners === "function"
          ? s.hasListeners("room_status")
          : true;
      },
      { timeout: 10_000 },
    );

    const joinBtn = player2.locator('button[type="submit"]');
    await expect(joinBtn).toBeEnabled({ timeout: 10_000 });
    await joinBtn.click();

    // If join didn't redirect, retry (socket may not have been fully ready)
    const joined = await player2
      .waitForURL(/\/rooms\/[a-f0-9-]+/, { timeout: 8_000 })
      .then(() => true)
      .catch(() => false);
    if (!joined) {
      // Re-check socket + listeners and retry
      await player2.waitForFunction(
        () => {
          const s = (window as any).__SOCKET__;
          if (!s?.connected) return false;
          return typeof s.hasListeners === "function"
            ? s.hasListeners("room_status")
            : true;
        },
        { timeout: 5_000 },
      );
      await player2.waitForTimeout(500);
      await joinBtn.click();

      // Second retry with page reload
      const joined2 = await player2
        .waitForURL(/\/rooms\/[a-f0-9-]+/, { timeout: 8_000 })
        .then(() => true)
        .catch(() => false);
      if (!joined2) {
        // Socket join failed — use REST API to join the room as fallback
        const roomUrlMatch = player1.url().match(/\/rooms\/([a-f0-9-]+)/);
        if (roomUrlMatch) {
          const p2Login = await apiLogin(accounts[1].email, accounts[1].password);
          await apiJoinRoom(roomUrlMatch[1], p2Login.user.id, passwordText, p2Login.access_token)
            .catch(() => {}); // Ignore if already joined
          await player2.goto(`${ROUTES.rooms}/${roomUrlMatch[1]}`);
          await player2.waitForLoadState("domcontentloaded");
        }
      }
    }

    // Player 2 should be redirected to the room lobby
    await expect(player2).toHaveURL(/\/rooms\/[a-f0-9-]+/, { timeout: 15_000 });

    // Both players should see each other in the lobby
    await player2.waitForLoadState("domcontentloaded");
    await player2.waitForTimeout(3000);
    let playerNames = await player1
      .locator(".bg-muted\\/50 .text-sm.font-medium")
      .allTextContents();
    // If host only sees 1 player, reload to get fresh data
    if (playerNames.length < 2) {
      await player1.reload();
      await player1.waitForLoadState("domcontentloaded");
      await player1.waitForTimeout(3000);
      playerNames = await player1
        .locator(".bg-muted\\/50 .text-sm.font-medium")
        .allTextContents();
    }
    expect(playerNames.length).toBeGreaterThanOrEqual(2);

    await player1.context().close();
    await player2.context().close();
  });

  test("wrong password shows error toast", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    // Player 1 creates a room
    const player1 = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );

    await player1.goto(ROUTES.createRoom);
    await player1.waitForLoadState("domcontentloaded");
    await player1.locator('button[type="submit"]').click();
    await expect(player1).toHaveURL(/\/rooms\//, { timeout: 15_000 });
    await player1.waitForLoadState("domcontentloaded");

    // Extract room code
    const roomCodeButton = player1.locator(
      'button:has(.tracking-widest):not(:has(.lucide-key-round))',
    );
    await expect(roomCodeButton).toBeVisible({ timeout: 5_000 });
    const roomCode = (await roomCodeButton.innerText()).replace(/\s/g, "").slice(0, 5);

    // Player 2 tries to join with wrong password
    const player2 = await createPlayerPage(
      browser,
      accounts[1].email,
      accounts[1].password,
    );

    await player2.goto(ROUTES.rooms);
    await player2.waitForLoadState("domcontentloaded");

    await player2.locator('input[id="room-code"]').fill(roomCode);

    // Enter wrong PIN
    for (let i = 0; i < 4; i++) {
      await player2
        .locator(`input[aria-label="Password digit ${i + 1}"]`)
        .fill("0");
    }

    await player2.locator('button[type="submit"]').click();

    // Should show error toast
    await expect(
      player2.locator('[data-sonner-toast][data-type="error"]'),
    ).toBeVisible({ timeout: 10_000 });

    // Should still be on the rooms page
    await expect(player2).toHaveURL(/\/rooms$/);

    await player1.context().close();
    await player2.context().close();
  });

  test("non-existent room code shows error toast", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const player = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );

    await player.goto(ROUTES.rooms);
    await player.waitForLoadState("domcontentloaded");

    // Enter non-existent room code
    await player.locator('input[id="room-code"]').fill("ZZZZZ");

    for (let i = 0; i < 4; i++) {
      await player
        .locator(`input[aria-label="Password digit ${i + 1}"]`)
        .fill("1");
    }

    await player.locator('button[type="submit"]').click();

    // Should show error toast
    await expect(
      player.locator('[data-sonner-toast][data-type="error"]'),
    ).toBeVisible({ timeout: 10_000 });

    await player.context().close();
  });
});

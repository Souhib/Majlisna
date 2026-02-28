import { test, expect } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { apiLogin, apiCreateRoom, apiGetRoom } from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";
import { generateTestAccounts } from "../../helpers/test-setup";

test.describe("Rooms — Host Permissions", () => {
  test("only host sees game type selector and start button", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(2);
    const p1Login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(p1Login.access_token, "undercover");
    const roomDetails = await apiGetRoom(room.id, p1Login.access_token);

    // Host joins
    const host = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await host.goto(ROUTES.room(room.id));
    await host.waitForLoadState("domcontentloaded");
    await host.waitForFunction(
      () => /Players \(\d+/.test(document.body.innerText),
      { timeout: 10_000 },
    ).catch(() => {});

    // Non-host joins
    const nonHost = await createPlayerPage(
      browser,
      accounts[1].email,
      accounts[1].password,
    );
    await nonHost.goto(ROUTES.rooms);
    await nonHost.waitForLoadState("domcontentloaded");
    await nonHost.locator('input[id="room-code"]').fill(roomDetails.public_id);
    const pinDigits = roomDetails.password.split("");
    for (let i = 0; i < 4; i++) {
      await nonHost
        .locator(`input[aria-label="Password digit ${i + 1}"]`)
        .fill(pinDigits[i]);
    }
    await nonHost.locator('button[type="submit"]').click();
    await expect(nonHost).toHaveURL(/\/rooms\//, { timeout: 15_000 });
    await nonHost.waitForTimeout(2000);

    // Host should see game type and start
    await expect(host.locator('text=Game Type')).toBeVisible();
    await expect(host.locator('button:has-text("Start")')).toBeVisible();

    // Non-host should NOT see game type selector or start button
    await expect(nonHost.locator('text=Game Type')).not.toBeVisible();
    await expect(
      nonHost.locator('button:has-text("Start")'),
    ).not.toBeVisible();

    await host.context().close();
    await nonHost.context().close();
  });

  test("start button is disabled with insufficient players for undercover", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(1);
    // Undercover requires minimum 3 players
    const p1Login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(p1Login.access_token, "undercover");

    const host = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await host.goto(ROUTES.room(room.id));
    await host.waitForLoadState("domcontentloaded");
    await host.waitForFunction(
      () => /Players \(\d+/.test(document.body.innerText),
      { timeout: 10_000 },
    ).catch(() => {});

    // Only 1 player (host), start button should be disabled
    const startButton = host.locator('button:has-text("Start")');
    await expect(startButton).toBeDisabled();

    // Should show minimum players message
    await expect(host.getByText(/[Mm]inimum.*3/)).toBeVisible();

    await host.context().close();
  });

  test("start button is disabled with insufficient players for codenames", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(1);
    // Codenames requires minimum 4 players
    const p1Login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(p1Login.access_token, "codenames");

    const host = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await host.goto(ROUTES.room(room.id));
    await host.waitForLoadState("domcontentloaded");
    await host.waitForFunction(
      () => /Players \(\d+/.test(document.body.innerText),
      { timeout: 10_000 },
    ).catch(() => {});

    // Select Codenames
    await host.locator('button:has-text("Codenames")').click();

    // Start should be disabled with < 4 players
    const startButton = host.locator('button:has-text("Start")');
    await expect(startButton).toBeDisabled();

    // Should show minimum players message
    await expect(host.getByText(/[Mm]inimum.*4/)).toBeVisible();

    await host.context().close();
  });

  test("start becomes enabled when enough players join for undercover", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(3);
    const p1Login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(p1Login.access_token, "undercover");
    const roomDetails = await apiGetRoom(room.id, p1Login.access_token);

    const host = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await host.goto(ROUTES.room(room.id));
    await host.waitForLoadState("domcontentloaded");
    await host.waitForFunction(
      () => /Players \(\d+/.test(document.body.innerText),
      { timeout: 10_000 },
    ).catch(() => {});

    // Start should be disabled with 1 player
    await expect(host.locator('button:has-text("Start")')).toBeDisabled();

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
    await player2.waitForTimeout(1500);

    // Player 3 joins
    const player3 = await createPlayerPage(
      browser,
      accounts[2].email,
      accounts[2].password,
    );
    await player3.goto(ROUTES.rooms);
    await player3.waitForLoadState("domcontentloaded");
    await player3.locator('input[id="room-code"]').fill(roomDetails.public_id);
    for (let i = 0; i < 4; i++) {
      await player3
        .locator(`input[aria-label="Password digit ${i + 1}"]`)
        .fill(pinDigits[i]);
    }
    await player3.locator('button[type="submit"]').click();
    await expect(player3).toHaveURL(/\/rooms\//, { timeout: 15_000 });
    await player3.waitForTimeout(1500);

    // Now with 3 players, start should be enabled
    await expect(host.locator('button:has-text("Start")')).toBeEnabled({
      timeout: 10_000,
    });

    await host.context().close();
    await player2.context().close();
    await player3.context().close();
  });

  test("host can switch between game types", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const p1Login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(p1Login.access_token, "undercover");

    const host = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await host.goto(ROUTES.room(room.id));
    await host.waitForLoadState("domcontentloaded");
    await host.waitForFunction(
      () => /Players \(\d+/.test(document.body.innerText),
      { timeout: 10_000 },
    ).catch(() => {});

    // Switch to Codenames
    const codenamesButton = host.locator('button:has-text("Codenames")');
    await expect(codenamesButton).toBeVisible();
    await codenamesButton.click();

    // Codenames should now be selected (has primary styling)
    await expect(codenamesButton).toHaveClass(/bg-primary/);

    // Switch back to Undercover
    const undercoverButton = host.locator('button:has-text("Undercover")');
    await undercoverButton.click();
    await expect(undercoverButton).toHaveClass(/bg-primary/);

    await host.context().close();
  });
});

test.describe("Rooms — Join Edge Cases", () => {
  test("room code input accepts only 5 characters", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const player = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await player.goto(ROUTES.rooms);
    await player.waitForLoadState("domcontentloaded");

    const roomCodeInput = player.locator('input[id="room-code"]');
    await roomCodeInput.fill("ABCDEFGH"); // Try 8 chars

    const value = await roomCodeInput.inputValue();
    expect(value.length).toBeLessThanOrEqual(5);

    await player.context().close();
  });

  test("PIN input auto-advances to next digit", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const player = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await player.goto(ROUTES.rooms);
    await player.waitForLoadState("domcontentloaded");

    // Type first digit
    const pin1 = player.locator('input[aria-label="Password digit 1"]');
    await pin1.fill("1");

    // Focus should move to next input
    const pin2 = player.locator('input[aria-label="Password digit 2"]');
    await expect(pin2).toBeFocused({ timeout: 2000 });

    await player.context().close();
  });

  test("PIN input only accepts digits", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const player = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await player.goto(ROUTES.rooms);
    await player.waitForLoadState("domcontentloaded");

    const pin1 = player.locator('input[aria-label="Password digit 1"]');
    await pin1.fill("a");

    const value = await pin1.inputValue();
    // Should be empty or only contain digit
    expect(value).toMatch(/^[0-9]?$/);

    await player.context().close();
  });

  test("join button is disabled when form is incomplete", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(1);
    const player = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await player.goto(ROUTES.rooms);
    await player.waitForLoadState("domcontentloaded");

    // Only fill room code, no password
    await player.locator('input[id="room-code"]').fill("ABCDE");

    const joinButton = player.locator('button[type="submit"]');
    await expect(joinButton).toBeDisabled();

    await player.context().close();
  });

  test("room code and password are copyable in lobby", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const p1Login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(p1Login.access_token, "undercover");

    const host = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await host.goto(ROUTES.room(room.id));
    await host.waitForLoadState("domcontentloaded");
    await host.waitForFunction(
      () => /Players \(\d+/.test(document.body.innerText),
      { timeout: 10_000 },
    ).catch(() => {});

    // Room code button should be visible and clickable
    const roomCodeButton = host.locator(
      'button:has(.tracking-widest):not(:has(.lucide-key-round))',
    );
    await expect(roomCodeButton).toBeVisible();

    // Password button should be visible
    const passwordButton = host.locator('button:has(.lucide-key-round)');
    await expect(passwordButton).toBeVisible();

    // Click to copy room code — should show "Copied!" feedback
    await roomCodeButton.click();
    await expect(host.getByText("Copied!")).toBeVisible({ timeout: 3000 });

    await host.context().close();
  });
});

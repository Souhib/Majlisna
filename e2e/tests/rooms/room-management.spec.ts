import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayersViaUI } from "../../helpers/ui-game-setup";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { apiLogin, apiCreateRoom, apiGetRoom } from "../../helpers/api-client";
import { ROUTES, FRONTEND_URL } from "../../helpers/constants";

test.describe("Room Management", () => {
  test("create room and see lobby with room code", async ({ browser }) => {
    const accounts = await generateTestAccounts(1);
    const login = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(login.access_token);

    const page = await createPlayerPage(browser, accounts[0].email, accounts[0].password);
    await page.goto(ROUTES.room(room.id));
    await page.waitForLoadState("domcontentloaded");

    // Verify room code is displayed
    await expect(page.locator(`text=${room.public_id}`)).toBeVisible({ timeout: 10_000 });
    // Verify player count
    await expect(page.locator("text=Players (1)")).toBeVisible({ timeout: 10_000 });

    await page.context().close();
  });

  test("join room with correct code and PIN", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayersViaUI(browser, accounts);

    // Both players should see Players (2)
    await expect(setup.players[0].page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    await expect(setup.players[1].page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });

  test("wrong PIN shows error toast", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const login1 = await apiLogin(accounts[0].email, accounts[0].password);
    const room = await apiCreateRoom(login1.access_token);
    const roomDetails = await apiGetRoom(room.id, login1.access_token);

    const page = await createPlayerPage(browser, accounts[1].email, accounts[1].password);
    await page.goto(ROUTES.rooms);
    await page.waitForLoadState("domcontentloaded");

    // Fill room code
    await page.locator('input[id="room-code"]').fill(roomDetails.public_id);
    // Fill wrong PIN
    for (let j = 0; j < 4; j++) {
      await page.locator(`input[aria-label="Password digit ${j + 1}"]`).fill("0");
    }
    const joinBtn = page.locator('button[type="submit"]');
    await expect(joinBtn).toBeEnabled({ timeout: 10_000 });
    await joinBtn.click();

    // The wrong PIN is said in the line under the tiles (no toast), and nobody moves
    await expect(page.getByTestId("join-error")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-sonner-toast][data-type="error"]')).toHaveCount(0);
    await expect(page).toHaveURL(/\/rooms$/);

    await page.context().close();
  });

  test("leave room returns to rooms list", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayersViaUI(browser, accounts);

    const player2 = setup.players[1].page;

    // Wait for player 2 to see the room fully loaded (player count >= 2) before leaving
    await player2.waitForFunction(
      () => {
        const m = document.body.innerText.match(/Players \((\d+)/);
        return m && parseInt(m[1]) >= 2;
      },
      { timeout: 20_000 },
    );

    // Player 2 clicks leave
    const leaveBtn = player2.locator('button:has-text("Leave")');
    await expect(leaveBtn).toBeVisible({ timeout: 10_000 });
    await leaveBtn.click();

    // Player 2 navigated to rooms
    await expect(player2).toHaveURL(/\/rooms$/, { timeout: 15_000 });

    // Host should see player count decrease (via polling)
    await setup.players[0].page.waitForFunction(
      () => {
        const m = document.body.innerText.match(/Players \((\d+)/);
        return m && parseInt(m[1]) <= 1;
      },
      { timeout: 25_000 },
    );

    await setup.cleanup();
  });

  test("host starts game and all players navigate to game page", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);

    const setup = await setupRoomWithPlayersViaUI(browser, accounts);
    const hostPage = setup.players[0].page;

    // All 3 players should be visible (verified by setupRoomWithPlayersViaUI)
    await expect(hostPage.locator("text=Players (3)")).toBeVisible({ timeout: 15_000 });

    // Wait for "player joined" toasts to auto-dismiss so they don't cause layout shifts
    await expect(hostPage.locator('[data-sonner-toast]')).toHaveCount(0, { timeout: 10_000 });

    const startButton = hostPage.locator('button:has-text("Start Game")');
    await expect(startButton).toBeEnabled({ timeout: 10_000 });
    await startButton.click();

    // All players should navigate to game page
    for (const player of setup.players) {
      await expect(player.page).toHaveURL(/\/game\/undercover\//, { timeout: 15_000 });
    }

    await setup.cleanup();
  });
});

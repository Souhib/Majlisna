import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  isPageAlive,
  type PlayerContext,
} from "../../helpers/ui-game-setup";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import {
  apiLogin,
  apiCreateRoom,
  apiGetRoom,
  apiJoinRoom,
  apiJoinRoomAsSpectator,
  apiUpdateRoomSettings,
} from "../../helpers/api-client";
import { ROUTES, FRONTEND_URL } from "../../helpers/constants";

test.describe("Spectator Mode", () => {
  test("spectator joins room and appears in player list", async ({ browser }) => {
    // Prepare
    const accounts = await generateTestAccounts(2);
    const playerLogin = await apiLogin(accounts[0].email, accounts[0].password);
    const spectatorLogin = await apiLogin(accounts[1].email, accounts[1].password);

    const room = await apiCreateRoom(playerLogin.access_token);
    const roomDetails = await apiGetRoom(room.id, playerLogin.access_token);

    // Spectator joins via API. The PIN comes from the host (as a real spectator
    // would get it from a share link) — join-spectator requires it.
    await apiJoinRoomAsSpectator(
      room.id,
      spectatorLogin.access_token,
      roomDetails.password,
    );

    // Open browser pages for both
    const playerPage = await createPlayerPage(browser, accounts[0].email, accounts[0].password);
    const spectatorPage = await createPlayerPage(browser, accounts[1].email, accounts[1].password);

    await playerPage.goto(ROUTES.room(room.id));
    await playerPage.waitForLoadState("domcontentloaded");
    await spectatorPage.goto(ROUTES.room(room.id));
    await spectatorPage.waitForLoadState("domcontentloaded");

    // Assert — spectator sees the room lobby
    await expect(spectatorPage.locator(`text=${roomDetails.public_id}`)).toBeVisible({ timeout: 10_000 });

    // Assert — spectator section is visible with Eye icon indicator
    await expect(playerPage.locator("text=Spectators (1)")).toBeVisible({ timeout: 15_000 });
    await expect(spectatorPage.locator("text=Spectators (1)")).toBeVisible({ timeout: 15_000 });

    // Assert — spectator username appears under the spectator section
    await expect(
      playerPage.locator(`text=${spectatorLogin.user.username}`),
    ).toBeVisible({ timeout: 10_000 });

    await playerPage.context().close();
    await spectatorPage.context().close();
  });

  test("spectator cannot start a game", async ({ browser }) => {
    // Prepare
    const accounts = await generateTestAccounts(2);
    const playerLogin = await apiLogin(accounts[0].email, accounts[0].password);
    const spectatorLogin = await apiLogin(accounts[1].email, accounts[1].password);

    const room = await apiCreateRoom(playerLogin.access_token);
    const roomDetails = await apiGetRoom(room.id, playerLogin.access_token);

    // Spectator joins via API (join-spectator requires the room PIN)
    await apiJoinRoomAsSpectator(
      room.id,
      spectatorLogin.access_token,
      roomDetails.password,
    );

    // Open spectator browser page
    const spectatorPage = await createPlayerPage(browser, accounts[1].email, accounts[1].password);
    await spectatorPage.goto(ROUTES.room(room.id));
    await spectatorPage.waitForLoadState("domcontentloaded");

    // Assert — spectator does NOT see the "Start Game" button
    await expect(spectatorPage.locator("text=Spectators (1)")).toBeVisible({ timeout: 15_000 });
    await expect(spectatorPage.locator('button:has-text("Start Game")')).toBeHidden();

    await spectatorPage.context().close();
  });

  test("spectator sees game state but cannot interact", async ({ browser }) => {
    // Prepare — 3 players + 1 spectator
    const accounts = await generateTestAccounts(4);
    const playerLogins = await Promise.all(
      accounts.slice(0, 3).map((a) => apiLogin(a.email, a.password)),
    );
    const spectatorLogin = await apiLogin(accounts[3].email, accounts[3].password);

    // Create room and join players via API
    const room = await apiCreateRoom(playerLogins[0].access_token);
    const roomDetails = await apiGetRoom(room.id, playerLogins[0].access_token);

    // Set long timers
    await apiUpdateRoomSettings(
      room.id,
      { description_timer: 600, voting_timer: 600 },
      playerLogins[0].access_token,
    );

    // Join other players
    for (let i = 1; i < 3; i++) {
      await apiJoinRoom(
        roomDetails.public_id,
        playerLogins[i].user.id,
        roomDetails.password,
        playerLogins[i].access_token,
      );
    }

    // Spectator joins (join-spectator requires the room PIN)
    await apiJoinRoomAsSpectator(
      room.id,
      spectatorLogin.access_token,
      roomDetails.password,
    );

    // Start undercover game via API
    const gameResult = await (
      await import("../../helpers/api-client")
    ).apiStartGame(room.id, "undercover", playerLogins[0].access_token);

    // Open spectator browser page and navigate to game
    const spectatorPage = await createPlayerPage(browser, accounts[3].email, accounts[3].password);
    const gameUrl = `/game/undercover/${gameResult.game_id}`;
    await spectatorPage.goto(`${FRONTEND_URL}${gameUrl}`);
    await spectatorPage.waitForLoadState("domcontentloaded");

    // Assert — spectator sees the game page
    await expect(
      spectatorPage.locator("h1:has-text('Undercover')"),
    ).toBeVisible({ timeout: 15_000 });

    // Assert — spectator sees "Spectating" badge/text
    await expect(
      spectatorPage.locator("text=Spectating"),
    ).toBeVisible({ timeout: 10_000 });

    // Assert — spectator does NOT see the role reveal (no "I understand" button)
    await expect(
      spectatorPage.locator('button:has-text("I understand")'),
    ).toBeHidden();

    // Assert — spectator does NOT see description input
    await expect(spectatorPage.locator("#description-input")).toBeHidden();

    // Assert — spectator does NOT see "Vote to Eliminate" button
    await expect(
      spectatorPage.locator('button:has-text("Vote to Eliminate")'),
    ).toBeHidden();

    await spectatorPage.context().close();
  });
});

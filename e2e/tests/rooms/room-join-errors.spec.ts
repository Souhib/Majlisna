import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import {
  apiLogin,
  apiCreateRoom,
  apiGetRoom,
  rawPatch,
} from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";
import { setupRoomWithPlayers } from "../../helpers/ui-game-setup";

test.describe("Room Join Errors", () => {
  test("join room with wrong PIN via API returns error", async () => {
    const accounts = await generateTestAccounts(2);
    const login1 = await apiLogin(accounts[0].email, accounts[0].password);
    const login2 = await apiLogin(accounts[1].email, accounts[1].password);
    const room = await apiCreateRoom(login1.access_token);
    const roomDetails = await apiGetRoom(room.id, login1.access_token);

    const res = await rawPatch(
      "/api/v1/rooms/join",
      {
        // No user_id: the joining identity comes from the JWT, and RoomJoin is
        // declared with extra="forbid", so sending it is a 422 instead of the
        // wrong-PIN 403 this test is about.
        public_room_id: roomDetails.public_id,
        password: "0000",
      },
      login2.access_token,
    );

    expect(res.status).toBe(403);
  });

  test("join room with non-existent code via API returns error", async () => {
    const accounts = await generateTestAccounts(1);
    const login = await apiLogin(accounts[0].email, accounts[0].password);

    const res = await rawPatch(
      "/api/v1/rooms/join",
      {
        public_room_id: "ZZZZZ",
        password: "1234",
      },
      login.access_token,
    );

    expect(res.status).toBe(404);
  });

  test("join room via UI with non-existent room code shows error", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(1);
    const page = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );

    await page.goto(ROUTES.rooms);
    await page.waitForLoadState("domcontentloaded");

    // Fill non-existent room code
    await page.locator('input[id="room-code"]').fill("ZZZZZ");
    for (let j = 0; j < 4; j++) {
      await page
        .locator(`input[aria-label="Password digit ${j + 1}"]`)
        .fill("1");
    }
    const joinBtn = page.locator('button[type="submit"]');
    await expect(joinBtn).toBeEnabled({ timeout: 10_000 });
    await joinBtn.click();

    // The refusal is said once, in the line under the tiles (no toast on top of it)
    const joinError = page.getByTestId("join-error");
    await expect(joinError).toBeVisible({ timeout: 10_000 });
    await expect(joinError).toHaveAttribute("role", "alert");
    await expect(page.locator('[data-sonner-toast][data-type="error"]')).toHaveCount(0);
    await expect(page).toHaveURL(/\/rooms$/);

    await page.context().close();
  });

  test("a visitor who opens a room's address without a seat is told so at once, and joins with its code and PIN", async ({ browser }) => {
    // Prepare — a host in their lobby, and someone who has the room's address only
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts.slice(0, 1));
    const [host] = setup.players;
    const visitor = await createPlayerPage(browser, accounts[1].email, accounts[1].password);
    const roomStates: number[] = [];
    visitor.on("response", (r) => new URL(r.url()).pathname === `/api/v1/rooms/${setup.roomId}/state` && roomStates.push(r.status()));

    // Act
    await visitor.goto(`/rooms/${setup.roomId}`);

    // Assert — said once, with no retries behind it (it used to retry for ~3 s, then say
    // the room "did not open" with nothing to do but go back), and a way in right there
    await expect(visitor.getByRole("heading", { name: "This room did not open" })).toBeVisible({ timeout: 15_000 });
    const join = visitor.getByRole("button", { name: "Join this room" });
    await expect(join).toBeDisabled();
    expect(roomStates).toEqual([404]);

    // Act — the code and the PIN, typed in the page
    await visitor.locator("#lobby-join-code").fill(setup.roomDetails.public_id);
    await visitor.locator("#lobby-join-pin").fill(setup.roomDetails.password);
    await expect(join).toBeEnabled();
    // ...the refused read was not asked again meanwhile: a refusal is not polled
    expect(roomStates).toEqual([404]);
    await join.click();

    // Assert — seated: both lobbies count two
    await expect(visitor).toHaveURL(new RegExp(`/rooms/${setup.roomId}$`));
    await expect(visitor.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    await expect(host.page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });

    await visitor.context().close();
    await setup.cleanup();
  });
});

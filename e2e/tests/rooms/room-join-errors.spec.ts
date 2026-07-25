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

    // Should show error toast
    await expect(
      page.locator('[data-sonner-toast][data-type="error"]'),
    ).toBeVisible({ timeout: 10_000 });

    await page.context().close();
  });
});

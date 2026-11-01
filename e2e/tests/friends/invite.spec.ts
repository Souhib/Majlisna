import { test, expect } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  apiAcceptFriendRequest,
  apiCreateRoom,
  apiGetRoomState,
  apiLogin,
  apiSendFriendRequest,
} from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";

/**
 * A room invitation reaches the friend wherever they are in the app: every signed-in
 * page keeps a personal socket (no room), the invite arrives on it as a quiet strip
 * under the nav, and "Join" seats the friend in the room. Every invite used to be
 * answered "Invite sent" and never arrive: the personal socket was refused (TQ-13).
 */
test.describe("Friends — a room invitation", () => {
  test("the host invites a friend from the lobby, and the friend joins from the strip", async ({ browser }) => {
    // Prepare — two friends; the host in a new room's lobby, the friend on the home page
    const [hostAccount, friendAccount] = await generateTestAccounts(2);
    const host = await apiLogin(hostAccount.email, hostAccount.password);
    const friend = await apiLogin(friendAccount.email, friendAccount.password);
    const request = await apiSendFriendRequest(friend.user.id, host.access_token);
    await apiAcceptFriendRequest(request.friendship_id, friend.access_token);
    const room = await apiCreateRoom(host.access_token);

    const hostPage = await createPlayerPage(browser, hostAccount.email, hostAccount.password);
    await hostPage.goto(ROUTES.room(room.id));
    await expect(hostPage.locator("text=Players (1)")).toBeVisible({ timeout: 15_000 });
    const friendPage = await createPlayerPage(browser, friendAccount.email, friendAccount.password);
    await friendPage.goto(ROUTES.friends);
    await expect(friendPage.getByRole("heading", { name: "Friends", level: 1 })).toBeVisible({ timeout: 15_000 });
    await expect(friendPage.getByTestId("room-invite")).toHaveCount(0);

    // Act — "Invite a friend", then the friend's Invite
    await hostPage.getByRole("button", { name: "Invite a friend" }).click();
    const dialog = hostPage.getByRole("dialog", { name: "Invite a friend" });
    const invite = dialog.getByRole("button", { name: `Invite ${friend.user.username}` });
    await expect(invite).toBeVisible({ timeout: 10_000 });
    await invite.click();
    await expect(dialog.getByText("Invited")).toBeVisible({ timeout: 10_000 });

    // Assert — the strip reaches the friend's page, naming the host, with no reload
    const strip = friendPage.getByTestId("room-invite");
    await expect(strip).toBeVisible({ timeout: 15_000 });
    await expect(strip).toContainText(`${host.user.username} invites you to their majlis.`);

    // Act — the friend joins from it
    await strip.getByRole("button", { name: "Join" }).click();

    // Assert — seated in the room, on both screens
    await expect(friendPage).toHaveURL(new RegExp(`/rooms/${room.id}$`), { timeout: 15_000 });
    for (const page of [hostPage, friendPage]) {
      await expect(page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    }
    const state = await apiGetRoomState(room.id, host.access_token);
    expect(state.players.map((p) => p.user_id).sort()).toEqual([host.user.id, friend.user.id].sort());

    await hostPage.context().close();
    await friendPage.context().close();
  });
});

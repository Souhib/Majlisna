import { test, expect } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  apiCreateRoom,
  apiGetRoom,
  apiGetRoomState,
  apiJoinRoom,
  apiLogin,
  expectApiError,
  rawJoinRoom,
} from "../../helpers/api-client";
import { FRONTEND_URL, ROUTES } from "../../helpers/constants";

/**
 * One live room at a time (WP-07, WP-08): a player seated (and connected) in room A who
 * opens room B's share link is told so, and offered "Leave A and join". Confirming
 * leaves A through the normal leave, then joins B; A's roster no longer lists them. The
 * share link used to seat them in B while A's host could still deal them into a game
 * they never saw (BR-21).
 */
test.describe("Joining while seated elsewhere", () => {
  test("a player seated in A who opens B's link is offered to leave A, and A's roster lets them go", async ({ browser }) => {
    // Prepare — room A (its host and the player) and room B (another host)
    const [hostA, player, hostB] = await generateTestAccounts(3);
    const loginA = await apiLogin(hostA.email, hostA.password);
    const loginPlayer = await apiLogin(player.email, player.password);
    const loginB = await apiLogin(hostB.email, hostB.password);
    const roomA = await apiGetRoom((await apiCreateRoom(loginA.access_token)).id, loginA.access_token);
    const roomB = await apiGetRoom((await apiCreateRoom(loginB.access_token)).id, loginB.access_token);
    await apiJoinRoom(roomA.public_id, loginPlayer.user.id, roomA.password, loginPlayer.access_token);

    // A's host watches A's lobby; the player sits in A, their lobby open in one tab
    const hostPage = await createPlayerPage(browser, hostA.email, hostA.password);
    await hostPage.goto(ROUTES.room(roomA.id));
    const playerPage = await createPlayerPage(browser, player.email, player.password);
    await playerPage.goto(ROUTES.room(roomA.id));
    for (const page of [hostPage, playerPage]) {
      await expect(page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    }

    // The server's rule first: a join elsewhere is refused by name, and names the room
    const refused = await expectApiError(
      await rawJoinRoom(roomB.public_id, roomB.password, loginPlayer.access_token),
      409,
      "errors.api.userAlreadyInRoom",
    );
    expect(refused.details?.room_id).toBe(roomA.id);

    // Act — in a second tab, the player opens B's share link
    const linkTab = await playerPage.context().newPage();
    await linkTab.goto(`${FRONTEND_URL}/rooms/join?code=${roomB.public_id}&pin=${roomB.password}`);

    // Assert — the page says so and offers to leave A (named by its code), never a toast
    await expect(linkTab.getByTestId("join-error")).toHaveText(
      "You already have a seat in another room. Leave it to sit here.",
      { timeout: 15_000 },
    );
    const leaveAndJoin = linkTab.getByRole("button", { name: `Leave ${roomA.public_id} and join` });
    await expect(leaveAndJoin).toBeVisible({ timeout: 10_000 });
    await expect(linkTab.locator('[data-sonner-toast][data-type="error"]')).toHaveCount(0);
    expect((await apiGetRoomState(roomA.id, loginA.access_token)).players.map((p) => p.user_id)).toContain(loginPlayer.user.id);

    // Act — confirm
    await leaveAndJoin.click();

    // Assert — the player is in B's lobby; A's roster no longer lists them, on its host's screen too
    await expect(linkTab).toHaveURL(new RegExp(`/rooms/${roomB.id}$`), { timeout: 15_000 });
    await expect(linkTab.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    await expect(hostPage.locator("text=Players (1)")).toBeVisible({ timeout: 15_000 });
    const stateA = await apiGetRoomState(roomA.id, loginA.access_token);
    expect(stateA.players.map((p) => p.user_id)).not.toContain(loginPlayer.user.id);
    const stateB = await apiGetRoomState(roomB.id, loginB.access_token);
    expect(stateB.players.map((p) => p.user_id).sort()).toEqual([loginB.user.id, loginPlayer.user.id].sort());

    await hostPage.context().close();
    await playerPage.context().close();
  });
});

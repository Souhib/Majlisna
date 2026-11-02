import { test, expect, type Browser, type Page } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  apiAcceptFriendRequest,
  apiBanPlayer,
  apiCreateRoom,
  apiGetRoomState,
  apiGetShareLink,
  apiJoinRoom,
  apiKickPlayer,
  apiLogin,
  apiSendFriendRequest,
  expectApiError,
  rawGet,
  rawJoinRoom,
  rawPatch,
  rawPost,
  rawRequest,
} from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";

/**
 * A room invitation reaches the friend wherever they are in the app: every signed-in
 * page keeps a personal socket (no room), the invite arrives on it as a quiet strip
 * under the nav, and "Join" seats the friend in the room. Every invite used to be
 * answered "Invite sent" and never arrive: the personal socket was refused (TQ-13).
 *
 * The invite is stored on the server and accepted by its id, without the PIN: it used to
 * carry the PIN, and the PIN rotates (now on a ban), so an invite sent before it opened a
 * join that was refused.
 *
 * Kick and ban (owner decision, 2 November 2026): a kicked player keeps the invites sent
 * to them and their own, and may be invited back; a ban deletes both kinds for that room,
 * no member may invite the banned player (the inviter is told why), and only the lift
 * opens the door again.
 */

/** The host's invite, sent through the API (the lobby's dialog is the first test's). */
async function apiInvite(roomId: string, friendId: string, token: string): Promise<{ invite: { id: string } }> {
  const res = await rawPost(`/api/v1/rooms/${roomId}/invite`, { friend_user_id: friendId }, token);
  expect(res.status, await res.clone().text()).toBe(200);
  return res.json();
}

/** The ids of the caller's live invites (`GET /rooms/invites`). */
async function listedInvites(token: string): Promise<string[]> {
  const res = await rawGet("/api/v1/rooms/invites", token);
  expect(res.status, await res.clone().text()).toBe(200);
  return (await res.json()).map((i: { id: string }) => i.id);
}

/** A page opened on /friends once its stored invites have been read (the strip's source). */
async function openFriendsPage(browser: Browser, email: string, password: string): Promise<Page> {
  const page = await createPlayerPage(browser, email, password);
  const read = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/v1/rooms/invites" && response.request().method() === "GET",
  );
  await page.goto(ROUTES.friends);
  await read;
  await expect(page.getByRole("heading", { name: "Friends", level: 1 })).toBeVisible({ timeout: 15_000 });
  return page;
}

/**
 * Two friends, the host in a new room's lobby, and the friend seated in it who then closed
 * the app (an away seat: only an away member can be invited to their own room). The host's
 * page stays open; the friend's is closed.
 */
async function friendAwayFromTheHostsRoom(browser: Browser) {
  const [hostAccount, friendAccount] = await generateTestAccounts(2);
  const host = await apiLogin(hostAccount.email, hostAccount.password);
  const friend = await apiLogin(friendAccount.email, friendAccount.password);
  const request = await apiSendFriendRequest(friend.user.id, host.access_token);
  await apiAcceptFriendRequest(request.friendship_id, friend.access_token);
  const room = await apiCreateRoom(host.access_token);
  const hostPage = await createPlayerPage(browser, hostAccount.email, hostAccount.password);
  await hostPage.goto(ROUTES.room(room.id));
  const { public_id: code, password: pin } = await apiGetShareLink(room.id, host.access_token);
  const friendPage = await createPlayerPage(browser, friendAccount.email, friendAccount.password);
  await apiJoinRoom(code, friend.user.id, pin, friend.access_token);
  const friendInTheRoom = watchRoomState(friendPage);
  await friendPage.goto(ROUTES.room(room.id));
  await expect(hostPage.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
  // Closed only once its room socket is in: the API seat already reads connected, so
  // closing a page that had not connected yet left nothing to notice until the seat went
  // stale (20 s), and the away check below failed under load
  await expect(friendPage.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
  await expect.poll(friendInTheRoom, { timeout: 15_000 }).toBe(true);
  await friendPage.context().close();
  await expect
    .poll(async () => (await apiGetRoomState(room.id, host.access_token)).players.find((p) => p.user_id === friend.user.id)?.is_connected, {
      timeout: 15_000,
    })
    .toBe(false);
  return { hostAccount, friendAccount, host, friend, room, hostPage, code, pin };
}

/**
 * Whether the page's room socket has been sent its first room state, from now on. The
 * server sends it at the end of its connect handler, once it has recorded the seat as
 * connected (ws/handlers.py `connect`), so from then on closing the page marks the seat
 * away. Only the room socket hears `room_state`: the app shell's personal one never does.
 * Its polling fallback's answers are read too.
 */
function watchRoomState(page: Page): () => boolean {
  let heard = false;
  const hear = (payload: string) => {
    if (payload.includes('"room_state"')) heard = true;
  };
  page.on("websocket", (ws) => ws.on("framereceived", ({ payload }) => hear(String(payload))));
  page.on("response", (response) => {
    if (!new URL(response.url()).pathname.startsWith("/socket.io/") || response.request().method() !== "GET") return;
    // a poll still open when the page closes has no body to read: nothing was heard
    response.text().then(hear, () => undefined);
  });
  return () => heard;
}

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

  test("an invite sent before a ban still opens the room: it needs no PIN", async ({ browser }) => {
    // Prepare — a host in the lobby with a guest; a friend on the friends page
    const [hostAccount, guestAccount, friendAccount] = await generateTestAccounts(3);
    const host = await apiLogin(hostAccount.email, hostAccount.password);
    const guest = await apiLogin(guestAccount.email, guestAccount.password);
    const friend = await apiLogin(friendAccount.email, friendAccount.password);
    const request = await apiSendFriendRequest(friend.user.id, host.access_token);
    await apiAcceptFriendRequest(request.friendship_id, friend.access_token);
    const room = await apiCreateRoom(host.access_token);
    const { public_id: code, password: oldPin } = await apiGetShareLink(room.id, host.access_token);
    await apiJoinRoom(code, guest.user.id, oldPin, guest.access_token);

    const hostPage = await createPlayerPage(browser, hostAccount.email, hostAccount.password);
    await hostPage.goto(ROUTES.room(room.id));
    await expect(hostPage.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    const friendPage = await createPlayerPage(browser, friendAccount.email, friendAccount.password);
    await friendPage.goto(ROUTES.friends);
    await expect(friendPage.getByRole("heading", { name: "Friends", level: 1 })).toBeVisible({ timeout: 15_000 });

    // Act — the host invites the friend, then bans the guest (the PIN rotates)
    await apiInvite(room.id, friend.user.id, host.access_token);
    const strip = friendPage.getByTestId("room-invite");
    await expect(strip).toContainText(`${host.user.username} invites you to their majlis.`, { timeout: 15_000 });
    await apiBanPlayer(room.id, guest.user.id, host.access_token);
    const { password: newPin } = await apiGetShareLink(room.id, host.access_token);
    expect(newPin).not.toBe(oldPin);
    await strip.getByRole("button", { name: "Join" }).click();

    // Assert — seated, with no code or PIN in any address on the way
    await expect(friendPage).toHaveURL(new RegExp(`/rooms/${room.id}$`), { timeout: 15_000 });
    expect(friendPage.url()).not.toContain(oldPin);
    for (const page of [hostPage, friendPage]) {
      await expect(page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    }
    const state = await apiGetRoomState(room.id, host.access_token);
    expect(state.players.map((p) => p.user_id).sort()).toEqual([host.user.id, friend.user.id].sort());

    await hostPage.context().close();
    await friendPage.context().close();
  });

  test("an invite waiting while the page was closed shows on the next page, and a removed player sits down with it", async ({ browser }) => {
    // Prepare — the friend sits in the room, then closes the app (an away seat)
    const { friendAccount, host, friend, room, hostPage } = await friendAwayFromTheHostsRoom(browser);

    // Act — invited while away, then removed by the host (a kick: no ban); the friend opens the app again
    const sent = await apiInvite(room.id, friend.user.id, host.access_token);
    await apiKickPlayer(room.id, friend.user.id, host.access_token);
    await expect(hostPage.locator("text=Players (1)")).toBeVisible({ timeout: 15_000 });
    expect(await listedInvites(friend.access_token)).toEqual([sent.invite.id]);
    const again = await openFriendsPage(browser, friendAccount.email, friendAccount.password);

    // Assert — the stored invite shows, and Join seats the removed friend again
    const strip = again.getByTestId("room-invite");
    await expect(strip).toContainText(`${host.user.username} invites you to their majlis.`, { timeout: 15_000 });
    await strip.getByRole("button", { name: "Join" }).click();
    await expect(again).toHaveURL(new RegExp(`/rooms/${room.id}$`), { timeout: 15_000 });
    for (const page of [hostPage, again]) {
      await expect(page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    }
    const state = await apiGetRoomState(room.id, host.access_token);
    expect(state.players.map((p) => p.user_id).sort()).toEqual([host.user.id, friend.user.id].sort());

    await hostPage.context().close();
    await again.context().close();
  });

  test("a removed friend can be invited back from the lobby, and joins from the strip", async ({ browser }) => {
    // Prepare — two friends seated together; the host removes the friend (a kick)
    const [hostAccount, friendAccount] = await generateTestAccounts(2);
    const host = await apiLogin(hostAccount.email, hostAccount.password);
    const friend = await apiLogin(friendAccount.email, friendAccount.password);
    const request = await apiSendFriendRequest(friend.user.id, host.access_token);
    await apiAcceptFriendRequest(request.friendship_id, friend.access_token);
    const room = await apiCreateRoom(host.access_token);
    const { public_id: code, password: pin } = await apiGetShareLink(room.id, host.access_token);
    await apiJoinRoom(code, friend.user.id, pin, friend.access_token);
    const hostPage = await createPlayerPage(browser, hostAccount.email, hostAccount.password);
    await hostPage.goto(ROUTES.room(room.id));
    await expect(hostPage.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    await apiKickPlayer(room.id, friend.user.id, host.access_token);
    await expect(hostPage.locator("text=Players (1)")).toBeVisible({ timeout: 15_000 });
    const friendPage = await openFriendsPage(browser, friendAccount.email, friendAccount.password);

    // Act — "Invite a friend", then the friend's Invite
    await hostPage.getByRole("button", { name: "Invite a friend" }).click();
    const dialog = hostPage.getByRole("dialog", { name: "Invite a friend" });
    await dialog.getByRole("button", { name: `Invite ${friend.user.username}` }).click();
    await expect(dialog.getByText("Invited")).toBeVisible({ timeout: 10_000 });

    // Assert — the strip reaches the friend, and Join seats them with the same room's PIN unchanged
    const strip = friendPage.getByTestId("room-invite");
    await expect(strip).toContainText(`${host.user.username} invites you to their majlis.`, { timeout: 15_000 });
    await strip.getByRole("button", { name: "Join" }).click();
    await expect(friendPage).toHaveURL(new RegExp(`/rooms/${room.id}$`), { timeout: 15_000 });
    await expect(hostPage.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    expect((await apiGetShareLink(room.id, host.access_token)).password).toBe(pin);

    await hostPage.context().close();
    await friendPage.context().close();
  });

  test("a banned friend never sees the room's invites, cannot be invited or come in, until the host lifts the ban", async ({ browser }) => {
    // Prepare — the friend sits in the room, closes the app, is invited while away, then banned
    const { friendAccount, host, friend, room, hostPage, code, pin: oldPin } = await friendAwayFromTheHostsRoom(browser);
    const sent = await apiInvite(room.id, friend.user.id, host.access_token);
    await apiBanPlayer(room.id, friend.user.id, host.access_token);
    await expect(hostPage.locator("text=Players (1)")).toBeVisible({ timeout: 15_000 });
    const { password: newPin } = await apiGetShareLink(room.id, host.access_token);
    expect(newPin).not.toBe(oldPin);

    // Assert — the ban deleted the invite: never listed, and spent (404). An invite that
    // raced the ban would answer 403 roomBanned (backend test_room_invites.py).
    expect(await listedInvites(friend.access_token)).toEqual([]);
    await expectApiError(await rawPost(`/api/v1/rooms/invites/${sent.invite.id}/accept`, {}, friend.access_token), 404, "errors.api.roomInviteNotFound");
    // ...no other door: the code with either PIN, or watching
    await expectApiError(await rawJoinRoom(code, newPin, friend.access_token), 403, "errors.api.roomBanned");
    await expectApiError(await rawJoinRoom(code, oldPin, friend.access_token), 403, "errors.api.roomBanned");
    await expectApiError(
      await rawPatch("/api/v1/rooms/join-spectator", { room_id: room.id, password: newPin }, friend.access_token),
      403,
      "errors.api.roomBanned",
    );

    // ...the friend opening the app sees no invite to the room
    const again = await openFriendsPage(browser, friendAccount.email, friendAccount.password);
    await expect(again.getByTestId("room-invite")).toHaveCount(0);

    // Act — the host tries to invite them again from the lobby
    await hostPage.getByRole("button", { name: "Invite a friend" }).click();
    const dialog = hostPage.getByRole("dialog", { name: "Invite a friend" });
    await dialog.getByRole("button", { name: `Invite ${friend.user.username}` }).click();

    // Assert — the friend's row says why, and the server refused it by name; nothing reached the friend
    await expect(dialog.getByRole("status")).toHaveText("Banned from this room", { timeout: 10_000 });
    await expect(dialog.getByRole("button", { name: `Invite ${friend.user.username}` })).toHaveCount(0);
    await expectApiError(
      await rawPost(`/api/v1/rooms/${room.id}/invite`, { friend_user_id: friend.user.id }, host.access_token),
      403,
      "errors.api.inviteeBanned",
    );
    expect(await listedInvites(friend.access_token)).toEqual([]);
    await expect(again.getByTestId("room-invite")).toHaveCount(0);
    await hostPage.keyboard.press("Escape");

    // Act — the host lifts the ban, then invites the friend again
    const lifted = await rawRequest("DELETE", `/api/v1/rooms/${room.id}/bans/${friend.user.id}`, undefined, host.access_token);
    expect(lifted.status, await lifted.clone().text()).toBe(200);
    const reinvited = await apiInvite(room.id, friend.user.id, host.access_token);

    // Assert — the invite reaches the open page, and Join seats the friend
    expect(await listedInvites(friend.access_token)).toEqual([reinvited.invite.id]);
    const strip = again.getByTestId("room-invite");
    await expect(strip).toContainText(`${host.user.username} invites you to their majlis.`, { timeout: 15_000 });
    await strip.getByRole("button", { name: "Join" }).click();
    await expect(again).toHaveURL(new RegExp(`/rooms/${room.id}$`), { timeout: 15_000 });
    for (const page of [hostPage, again]) {
      await expect(page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    }

    await hostPage.context().close();
    await again.context().close();
  });

  test("the invites a banned member sent die with the ban: their friend is not let in", async ({ browser }) => {
    // The ban rotates the PIN to cut off what the banned player handed out; an invite
    // needs no PIN, so theirs must go too (review F1), or their friend sat down and read
    // the new PIN in the room state.
    // Prepare — a member seated with the host invites a friend of their own at once (an
    // API seat counts as connected until it goes stale)
    const [hostAccount, memberAccount, cronyAccount] = await generateTestAccounts(3);
    const host = await apiLogin(hostAccount.email, hostAccount.password);
    const member = await apiLogin(memberAccount.email, memberAccount.password);
    const crony = await apiLogin(cronyAccount.email, cronyAccount.password);
    const request = await apiSendFriendRequest(crony.user.id, member.access_token);
    await apiAcceptFriendRequest(request.friendship_id, crony.access_token);
    const room = await apiCreateRoom(host.access_token);
    const { public_id: code, password: pin } = await apiGetShareLink(room.id, host.access_token);
    await apiJoinRoom(code, member.user.id, pin, member.access_token);
    const sent = await apiInvite(room.id, crony.user.id, member.access_token);

    const hostPage = await createPlayerPage(browser, hostAccount.email, hostAccount.password);
    await hostPage.goto(ROUTES.room(room.id));
    await expect(hostPage.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    const cronyPage = await createPlayerPage(browser, cronyAccount.email, cronyAccount.password);
    await cronyPage.goto(ROUTES.friends);
    const strip = cronyPage.getByTestId("room-invite");
    await expect(strip).toContainText(`${member.user.username} invites you to their majlis.`, { timeout: 15_000 });

    // Act — the host bans the member, then the friend presses Join on the strip still shown
    await apiBanPlayer(room.id, member.user.id, host.access_token);
    await expect(hostPage.locator("text=Players (1)")).toBeVisible({ timeout: 15_000 });
    const listed = await rawGet("/api/v1/rooms/invites", crony.access_token);
    expect((await listed.json()).map((i: { id: string }) => i.id)).not.toContain(sent.invite.id);
    await strip.getByRole("button", { name: "Join" }).click();

    // Assert — refused in the server's words, then only Close; nobody new at the table
    await expect(cronyPage.getByTestId("room-invite-error")).toHaveText("This invitation is no longer valid.", { timeout: 15_000 });
    await expect(strip.getByRole("button", { name: "Join" })).toHaveCount(0);
    await strip.getByRole("button", { name: "Close" }).click();
    await expect(strip).toHaveCount(0);
    expect(cronyPage.url()).not.toContain(`/rooms/${room.id}`);
    const state = await apiGetRoomState(room.id, host.access_token);
    expect(state.players.map((p) => p.user_id)).toEqual([host.user.id]);

    await hostPage.context().close();
    await cronyPage.context().close();
  });

  test("the invites a removed member sent stay: their friend sits down with one", async ({ browser }) => {
    // A kick is for someone who left without quitting: what they handed out still stands
    // Prepare — a member seated with the host invites a friend of their own
    const [hostAccount, memberAccount, cronyAccount] = await generateTestAccounts(3);
    const host = await apiLogin(hostAccount.email, hostAccount.password);
    const member = await apiLogin(memberAccount.email, memberAccount.password);
    const crony = await apiLogin(cronyAccount.email, cronyAccount.password);
    const request = await apiSendFriendRequest(crony.user.id, member.access_token);
    await apiAcceptFriendRequest(request.friendship_id, crony.access_token);
    const room = await apiCreateRoom(host.access_token);
    const { public_id: code, password: pin } = await apiGetShareLink(room.id, host.access_token);
    await apiJoinRoom(code, member.user.id, pin, member.access_token);
    const sent = await apiInvite(room.id, crony.user.id, member.access_token);

    const hostPage = await createPlayerPage(browser, hostAccount.email, hostAccount.password);
    await hostPage.goto(ROUTES.room(room.id));
    await expect(hostPage.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    const cronyPage = await createPlayerPage(browser, cronyAccount.email, cronyAccount.password);
    await cronyPage.goto(ROUTES.friends);
    const strip = cronyPage.getByTestId("room-invite");
    await expect(strip).toContainText(`${member.user.username} invites you to their majlis.`, { timeout: 15_000 });

    // Act — the host removes the member, then the friend presses Join on the strip
    await apiKickPlayer(room.id, member.user.id, host.access_token);
    await expect(hostPage.locator("text=Players (1)")).toBeVisible({ timeout: 15_000 });
    expect(await listedInvites(crony.access_token)).toEqual([sent.invite.id]);
    await strip.getByRole("button", { name: "Join" }).click();

    // Assert — seated, with the room's PIN unchanged
    await expect(cronyPage).toHaveURL(new RegExp(`/rooms/${room.id}$`), { timeout: 15_000 });
    await expect(hostPage.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    const state = await apiGetRoomState(room.id, host.access_token);
    expect(state.players.map((p) => p.user_id).sort()).toEqual([host.user.id, crony.user.id].sort());
    expect(state.password).toBe(pin);

    await hostPage.context().close();
    await cronyPage.context().close();
  });
});

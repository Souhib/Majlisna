import { test, expect, type Page } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers } from "../../helpers/ui-game-setup";
import {
  apiBanPlayer,
  apiGetRoomState,
  apiGetShareLink,
  apiListBans,
  apiUpdateRoomSettings,
  expectApiError,
  rawJoinRoom,
  rawPatch,
  rawPost,
} from "../../helpers/api-client";
import { FRONTEND_URL } from "../../helpers/constants";

/**
 * Kick and ban are two host actions (owner decision, 2 November 2026; it replaced owner
 * rule (c), under which every kick banned and rotated the PIN).
 *
 * - Remove (a kick) is for someone who left without quitting: the seat goes, and that is
 *   all. No ban, the same PIN: the player sits down again with the same link.
 * - Ban is for someone the table does not want back: the seat goes, the player cannot come
 *   back (not with the old link, not with the new PIN, not as a spectator), the PIN
 *   changes, and the host's lobby lists them under "Banned players" with a way to let
 *   them back; once that is done they join again with the NEW PIN.
 *
 * The invite side of both (a kicked player invited back, a banned one who cannot be) is
 * `tests/friends/invite.spec.ts`.
 */

/** The four PIN tiles of the lobby header, read as a string. */
async function pinOnScreen(page: Page): Promise<string> {
  const tiles = page.getByRole("group", { name: "PIN" }).locator(".code-tile");
  await expect(tiles).toHaveCount(4, { timeout: 15_000 });
  return (await tiles.allTextContents()).join("");
}

/** A player's row in the host's roster (the E2E row shape PlayerRoster keeps). */
function rosterRow(page: Page, username: string) {
  return page.locator(`div.flex.items-center.justify-between:has(span:text-is("${username}"))`);
}

/**
 * Everything the page's Socket.IO connections receive, from now on: the WebSocket frames
 * and the bodies of any polling answer (the lobby's socket may fall back to polling).
 */
function socketTraffic(page: Page): string[] {
  const seen: string[] = [];
  page.on("websocket", (ws) => ws.on("framereceived", ({ payload }) => seen.push(String(payload))));
  page.on("response", (response) => {
    if (!new URL(response.url()).pathname.startsWith("/socket.io/") || response.request().method() !== "GET") return;
    response.text().then((body) => seen.push(body), () => undefined);
  });
  return seen;
}

/** A room state carrying this PIN, as the server sends it (RoomState.password). */
const carriesPin = (traffic: string[], pin: string) => {
  const field = new RegExp(`"password"\\s*:\\s*"${pin.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`);
  return traffic.some((frame) => field.test(frame));
};

test.describe("Remove, ban and lift", () => {
  test("a removed player is told they may come back, and sits down again with the same code and PIN", async ({ browser }) => {
    // Prepare — three players in the lobby
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const [host, kicked, other] = setup.players;
    const code = setup.roomDetails.public_id;
    const pin = setup.roomDetails.password;
    const kickedName = kicked.login.user.username;
    expect(await pinOnScreen(host.page)).toBe(pin);

    // Act — the host removes the player: the row's Remove, then the dialog's
    await rosterRow(host.page, kickedName).getByRole("button", { name: `Remove ${kickedName} from the room` }).click();
    const confirm = host.page.getByRole("alertdialog", { name: `Remove ${kickedName}?` });
    await expect(confirm).toContainText("can come back with its code and PIN, or through an invite");
    await confirm.getByRole("button", { name: "Remove", exact: true }).click();

    // Assert — the table is two, and every line says who was removed (the room is told
    // which removal it was: the other member's line does not read "left")
    for (const player of [host, other]) {
      await expect(player.page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
      await expect(player.page.getByTestId("lobby-activity")).toContainText(`${kickedName} was removed from the majlis`, { timeout: 10_000 });
    }

    // ...the removed player is on /rooms and told they may join again
    await expect(kicked.page).toHaveURL(/\/rooms$/, { timeout: 15_000 });
    await expect(kicked.page.getByTestId("room-notice")).toContainText("the host removed you. You may join again with its code and PIN");

    // ...nothing else changed: the same PIN on screen and on the server, and nobody banned
    expect((await apiGetShareLink(setup.roomId, host.login.access_token)).password).toBe(pin);
    expect(await pinOnScreen(host.page)).toBe(pin);
    expect(await apiListBans(setup.roomId, host.login.access_token)).toEqual([]);
    await expect(host.page.getByRole("heading", { name: /^Banned players/ })).toHaveCount(0);

    // Act — the removed player opens the same share link again
    await kicked.page.goto(`${FRONTEND_URL}/rooms/join?code=${code}&pin=${pin}`);

    // Assert — seated again, on every screen
    await expect(kicked.page).toHaveURL(new RegExp(`/rooms/${setup.roomId}$`), { timeout: 15_000 });
    for (const player of setup.players) {
      await expect(player.page.locator("text=Players (3)")).toBeVisible({ timeout: 15_000 });
    }
    const state = await apiGetRoomState(setup.roomId, host.login.access_token);
    expect(state.players.map((p) => p.user_id)).toContain(kicked.login.user.id);
    expect(state.password).toBe(pin);

    await setup.cleanup();
  });

  test("a banned player cannot rejoin until the host lifts the ban, then joins with the new PIN", async ({ browser }) => {
    // Prepare — three players in the lobby
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const [host, banned, other] = setup.players;
    const code = setup.roomDetails.public_id;
    const oldPin = setup.roomDetails.password;
    const bannedName = banned.login.user.username;
    expect(await pinOnScreen(host.page)).toBe(oldPin);
    // The banned player's page is watched from a fresh load, so its sockets are seen from
    // their handshake; a settings change pushes a room state, which proves the watch hears it
    const bannedTraffic = socketTraffic(banned.page);
    await banned.page.reload();
    await expect(banned.page.locator("text=Players (3)")).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => pinOnScreen(banned.page)).toBe(oldPin);
    await apiUpdateRoomSettings(setup.roomId, { description_timer: 590 }, host.login.access_token);
    await expect.poll(() => carriesPin(bannedTraffic, oldPin), { timeout: 15_000 }).toBe(true);

    // Act — the host bans the player: the row's Ban, then the dialog's
    await rosterRow(host.page, bannedName).getByRole("button", { name: `Ban ${bannedName} from the room` }).click();
    const confirm = host.page.getByRole("alertdialog", { name: `Ban ${bannedName}?` });
    await expect(confirm).toContainText("cannot come back, not even through an invite, until you lift the ban");
    await expect(confirm).toContainText("The PIN changes too");
    await confirm.getByRole("button", { name: "Ban", exact: true }).click();

    // Assert — the table is two, and every line says who was banned
    for (const player of [host, other]) {
      await expect(player.page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
      await expect(player.page.getByTestId("lobby-activity")).toContainText(`${bannedName} was banned from the majlis`, { timeout: 10_000 });
    }

    // ...the banned player is on /rooms and told they are banned
    await expect(banned.page).toHaveURL(/\/rooms$/, { timeout: 15_000 });
    await expect(banned.page.getByTestId("room-notice")).toContainText("the host banned you from it");

    // ...the PIN has changed, on the host's screen and on the server
    const { password: newPin } = await apiGetShareLink(setup.roomId, host.login.access_token);
    expect(newPin).not.toBe(oldPin);
    await expect.poll(() => pinOnScreen(host.page), { timeout: 15_000 }).toBe(newPin);

    // ...the host's lobby lists the banned player
    await expect(host.page.getByRole("heading", { name: "Banned players (1)" })).toBeVisible({ timeout: 15_000 });
    const lift = host.page.getByRole("button", { name: `Let ${bannedName} come back` });
    await expect(lift).toBeVisible();
    expect((await apiListBans(setup.roomId, host.login.access_token)).map((b) => b.user_id)).toEqual([banned.login.user.id]);
    // a guest sees no such list
    await expect(other.page.getByRole("heading", { name: /^Banned players/ })).toHaveCount(0);

    // The banned player cannot come back: not with the old link (its PIN is gone), not
    // with the new PIN, not as a spectator; and the page says why, once
    await banned.page.goto(`${FRONTEND_URL}/rooms/join?code=${code}&pin=${newPin}`);
    const refusal = banned.page.getByTestId("join-error");
    await expect(refusal).toHaveText("The host banned you from this room.", { timeout: 15_000 });
    await expect(banned.page.getByRole("button", { name: /Leave .* and join/ })).toHaveCount(0);
    // ...and offers no repair: a ban holds whatever the code and PIN, so neither "type the
    // code yourself" nor "ask for a fresh link" (review F2); the way home stays
    await expect(banned.page.getByRole("link", { name: "Type the code yourself" })).toHaveCount(0);
    await expect(banned.page.getByText(/fresh link|new link or invite/)).toHaveCount(0);
    await expect(banned.page.getByRole("link", { name: "Back to the majlis" })).toBeVisible();
    await expectApiError(await rawJoinRoom(code, newPin, banned.login.access_token), 403, "errors.api.roomBanned");
    await expectApiError(await rawJoinRoom(code, oldPin, banned.login.access_token), 403, "errors.api.roomBanned");
    await expectApiError(
      await rawPatch("/api/v1/rooms/join-spectator", { room_id: setup.roomId, password: newPin }, banned.login.access_token),
      403,
      "errors.api.roomBanned",
    );

    // Not one room state carrying the new PIN reached the banned player's sockets, on any
    // of them: the push that announced it is addressed to the members still seated (review
    // R2; it went to the whole room channel, where a cut socket held by another worker
    // stayed until that worker's next audit tick)
    expect(carriesPin(bannedTraffic, newPin), "the banned page heard the new PIN").toBe(false);

    // Act — the host lets them back
    await lift.click();

    // Assert — the list says nobody is banned; the PIN stays the new one
    await expect(host.page.getByRole("heading", { name: "Banned players (0)" })).toBeVisible({ timeout: 10_000 });
    await expect(host.page.getByText("No one is banned from this room.")).toBeVisible();
    expect(await apiListBans(setup.roomId, host.login.access_token)).toEqual([]);

    // The old PIN does not come back with the lift: it is simply wrong now
    await expectApiError(await rawJoinRoom(code, oldPin, banned.login.access_token), 403, "errors.api.wrongRoomPassword");

    // ...and the player joins again with the new PIN, through the share link
    await banned.page.goto(`${FRONTEND_URL}/rooms/join?code=${code}&pin=${newPin}`);
    await expect(banned.page).toHaveURL(new RegExp(`/rooms/${setup.roomId}$`), { timeout: 15_000 });
    for (const player of setup.players) {
      await expect(player.page.locator("text=Players (3)")).toBeVisible({ timeout: 15_000 });
    }
    const state = await apiGetRoomState(setup.roomId, host.login.access_token);
    expect(state.players.map((p) => p.user_id)).toContain(banned.login.user.id);

    await setup.cleanup();
  });

  test("a link made before a ban says the PIN may have changed, and the new link opens the room", async ({ browser }) => {
    // Prepare — a host and a guest; a friend holds the room's link with today's PIN
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts.slice(0, 2));
    const [host, guest] = setup.players;
    const friend = await createPlayerPage(browser, accounts[2].email, accounts[2].password);
    const code = setup.roomDetails.public_id;
    const oldPin = setup.roomDetails.password;

    // Act — the host bans the guest (the PIN rotates), then the friend opens the old link
    await apiBanPlayer(setup.roomId, guest.login.user.id, host.login.access_token);
    const { password: newPin } = await apiGetShareLink(setup.roomId, host.login.access_token);
    expect(newPin).not.toBe(oldPin);
    await friend.goto(`${FRONTEND_URL}/rooms/join?code=${code}&pin=${oldPin}`);

    // Assert — refused for the PIN, and told why it may have changed and what to do: a link
    // keeps the PIN it was made with (review F1; a friend's invite needs no PIN)
    await expect(friend.getByTestId("join-error")).toHaveText("Incorrect room password.", { timeout: 15_000 });
    await expect(friend.getByText("The room’s PIN may have changed since this link was made")).toBeVisible();
    await expect(friend.getByRole("link", { name: "Type the code yourself" })).toBeVisible();

    // ...and the host's new link opens it
    await friend.goto(`${FRONTEND_URL}/rooms/join?code=${code}&pin=${newPin}`);
    await expect(friend).toHaveURL(new RegExp(`/rooms/${setup.roomId}$`), { timeout: 15_000 });
    await expect(host.page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });

    await friend.context().close();
    await setup.cleanup();
  });

  test("a guest can neither remove nor ban", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const [, guest, target] = setup.players;

    // No Remove nor Ban on a guest's roster, and the server refuses both calls by name
    const row = rosterRow(guest.page, target.login.user.username);
    await expect(row).toBeVisible({ timeout: 10_000 });
    await expect(row.getByRole("button")).toHaveCount(0);
    await expectApiError(
      await rawPatch(`/api/v1/rooms/${setup.roomId}/kick`, { user_id: target.login.user.id }, guest.login.access_token),
      403,
      "errors.api.notRoomHost",
    );
    await expectApiError(
      await rawPost(`/api/v1/rooms/${setup.roomId}/bans`, { user_id: target.login.user.id }, guest.login.access_token),
      403,
      "errors.api.notRoomHost",
    );
    expect((await apiGetRoomState(setup.roomId, guest.login.access_token)).players).toHaveLength(3);
    expect(await apiListBans(setup.roomId, setup.players[0].login.access_token)).toEqual([]);

    await setup.cleanup();
  });
});

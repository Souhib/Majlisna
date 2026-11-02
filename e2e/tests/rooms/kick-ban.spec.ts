import { test, expect, type Page } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers } from "../../helpers/ui-game-setup";
import {
  apiGetRoomState,
  apiGetShareLink,
  apiKickPlayer,
  apiListBans,
  apiUpdateRoomSettings,
  expectApiError,
  rawJoinRoom,
  rawPatch,
} from "../../helpers/api-client";
import { FRONTEND_URL } from "../../helpers/constants";

/**
 * A kick is a ban for the room's lifetime, and it rotates the PIN (owner rule (c)): the
 * host confirms it, the kicked player cannot come back (not with the old link, not with
 * the new PIN either), the host's lobby lists them under "Removed players" with a way to
 * let them back, and once that is done they join again with the NEW PIN. The kicked
 * player used to be back a second later with the same code and PIN (BR-20, SEC F04).
 */

/** The four PIN tiles of the lobby header, read as a string. */
async function pinOnScreen(page: Page): Promise<string> {
  const tiles = page.getByRole("group", { name: "PIN" }).locator(".code-tile");
  await expect(tiles).toHaveCount(4, { timeout: 15_000 });
  return (await tiles.allTextContents()).join("");
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

test.describe("Kick, ban and lift", () => {
  test("a kicked player cannot rejoin until the host lifts the ban, then joins with the new PIN", async ({ browser }) => {
    // Prepare — three players in the lobby
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const [host, kicked, other] = setup.players;
    const code = setup.roomDetails.public_id;
    const oldPin = setup.roomDetails.password;
    const kickedName = kicked.login.user.username;
    expect(await pinOnScreen(host.page)).toBe(oldPin);
    // The kicked player's page is watched from a fresh load, so its sockets are seen from
    // their handshake; a settings change pushes a room state, which proves the watch hears it
    const kickedTraffic = socketTraffic(kicked.page);
    await kicked.page.reload();
    await expect(kicked.page.locator("text=Players (3)")).toBeVisible({ timeout: 15_000 });
    await expect.poll(() => pinOnScreen(kicked.page)).toBe(oldPin);
    await apiUpdateRoomSettings(setup.roomId, { description_timer: 590 }, host.login.access_token);
    await expect.poll(() => carriesPin(kickedTraffic, oldPin), { timeout: 15_000 }).toBe(true);

    // Act — the host removes the player: the row's Remove, then the dialog's
    const row = host.page.locator(`div.flex.items-center.justify-between:has(span:text-is("${kickedName}"))`);
    await row.locator("button").last().click();
    const confirm = host.page.getByRole("alertdialog", { name: `Remove ${kickedName}?` });
    await expect(confirm).toContainText("cannot come back to it");
    await confirm.getByRole("button", { name: "Remove", exact: true }).click();

    // Assert — the table is two, the kicked player is on /rooms and told why
    for (const player of [host, other]) {
      await expect(player.page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    }
    await expect(kicked.page).toHaveURL(/\/rooms$/, { timeout: 15_000 });
    await expect(kicked.page.getByTestId("room-notice")).toContainText("the host removed you");

    // ...the PIN has changed, on the host's screen and on the server
    const { password: newPin } = await apiGetShareLink(setup.roomId, host.login.access_token);
    expect(newPin).not.toBe(oldPin);
    await expect.poll(() => pinOnScreen(host.page), { timeout: 15_000 }).toBe(newPin);

    // ...the host's lobby lists the removed player
    await expect(host.page.getByRole("heading", { name: "Removed players (1)" })).toBeVisible({ timeout: 15_000 });
    const lift = host.page.getByRole("button", { name: `Let ${kickedName} come back` });
    await expect(lift).toBeVisible();
    expect((await apiListBans(setup.roomId, host.login.access_token)).map((b) => b.user_id)).toEqual([kicked.login.user.id]);
    // a guest sees no such list
    await expect(other.page.getByRole("heading", { name: /^Removed players/ })).toHaveCount(0);

    // The kicked player cannot come back: not with the old link (its PIN is gone), not
    // with the new PIN, not as a spectator; and the page says why, once
    await kicked.page.goto(`${FRONTEND_URL}/rooms/join?code=${code}&pin=${newPin}`);
    const refusal = kicked.page.getByTestId("join-error");
    await expect(refusal).toHaveText("The host removed you from this room.", { timeout: 15_000 });
    await expect(kicked.page.getByRole("button", { name: /Leave .* and join/ })).toHaveCount(0);
    // ...and offers no repair: a ban holds whatever the code and PIN, so neither "type the
    // code yourself" nor "ask for a fresh link" (review F2); the way home stays
    await expect(kicked.page.getByRole("link", { name: "Type the code yourself" })).toHaveCount(0);
    await expect(kicked.page.getByText(/fresh link|new link or invite/)).toHaveCount(0);
    await expect(kicked.page.getByRole("link", { name: "Back to the majlis" })).toBeVisible();
    await expectApiError(await rawJoinRoom(code, newPin, kicked.login.access_token), 403, "errors.api.roomBanned");
    await expectApiError(await rawJoinRoom(code, oldPin, kicked.login.access_token), 403, "errors.api.roomBanned");
    await expectApiError(
      await rawPatch("/api/v1/rooms/join-spectator", { room_id: setup.roomId, password: newPin }, kicked.login.access_token),
      403,
      "errors.api.roomBanned",
    );

    // Not one room state carrying the new PIN reached the kicked player's sockets, on any
    // of them: the push that announced it is addressed to the members still seated (review
    // R2; it went to the whole room channel, where a kicked socket held by another worker
    // stayed until that worker's next audit tick)
    expect(carriesPin(kickedTraffic, newPin), "the kicked page heard the new PIN").toBe(false);

    // Act — the host lets them back
    await lift.click();

    // Assert — the list says nobody is removed; the PIN stays the new one
    await expect(host.page.getByRole("heading", { name: "Removed players (0)" })).toBeVisible({ timeout: 10_000 });
    await expect(host.page.getByText("No one has been removed from this room.")).toBeVisible();
    expect(await apiListBans(setup.roomId, host.login.access_token)).toEqual([]);

    // The old PIN does not come back with the lift: it is simply wrong now
    await expectApiError(await rawJoinRoom(code, oldPin, kicked.login.access_token), 403, "errors.api.wrongRoomPassword");

    // ...and the player joins again with the new PIN, through the share link
    await kicked.page.goto(`${FRONTEND_URL}/rooms/join?code=${code}&pin=${newPin}`);
    await expect(kicked.page).toHaveURL(new RegExp(`/rooms/${setup.roomId}$`), { timeout: 15_000 });
    for (const player of setup.players) {
      await expect(player.page.locator("text=Players (3)")).toBeVisible({ timeout: 15_000 });
    }
    const state = await apiGetRoomState(setup.roomId, host.login.access_token);
    expect(state.players.map((p) => p.user_id)).toContain(kicked.login.user.id);

    await setup.cleanup();
  });

  test("a link made before a kick says the PIN may have changed, and the new link opens the room", async ({ browser }) => {
    // Prepare — a host and a guest; a friend holds the room's link with today's PIN
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts.slice(0, 2));
    const [host, guest] = setup.players;
    const friend = await createPlayerPage(browser, accounts[2].email, accounts[2].password);
    const code = setup.roomDetails.public_id;
    const oldPin = setup.roomDetails.password;

    // Act — the host removes the guest (the PIN rotates), then the friend opens the old link
    await apiKickPlayer(setup.roomId, guest.login.user.id, host.login.access_token);
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

  test("a guest cannot kick", async ({ browser }) => {
    const accounts = await generateTestAccounts(3);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const [, guest, target] = setup.players;

    // No Remove on a guest's roster, and the server refuses the call by name
    const row = guest.page.locator(`div.flex.items-center.justify-between:has(span:text-is("${target.login.user.username}"))`);
    await expect(row).toBeVisible({ timeout: 10_000 });
    await expect(row.getByRole("button")).toHaveCount(0);
    await expectApiError(
      await rawPatch(`/api/v1/rooms/${setup.roomId}/kick`, { user_id: target.login.user.id }, guest.login.access_token),
      403,
      "errors.api.notRoomHost",
    );
    expect((await apiGetRoomState(setup.roomId, guest.login.access_token)).players).toHaveLength(3);

    await setup.cleanup();
  });
});

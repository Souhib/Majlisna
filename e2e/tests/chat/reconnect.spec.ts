import { test, expect, type WebSocketRoute } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import { apiCreateRoom, apiGetRoom, apiJoinRoom, apiLogin, apiSendChatMessage } from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";

const CHAT_INPUT = 'input[placeholder="Type a message…"]';

/**
 * The host's link drops for about ten seconds in the lobby (its sockets cut and refused,
 * its REST calls failing), and meanwhile a chat line and a new player arrive. Once the
 * link is back, the lobby shows both without a reload: a reconnect re-reads the room and
 * the chat history (python-socketio replays nothing it sent while the socket was down).
 * Before WP-08 the line sent during the outage only appeared after a reload.
 */
test.describe("Chat — a reconnect catches up", () => {
  test("a chat line sent during a socket outage appears once the link is back", async ({ browser }) => {
    // Prepare — a room of two (the guest only talks through the API), and a third player
    const [hostAccount, guestAccount, lateAccount] = await generateTestAccounts(3);
    const host = await apiLogin(hostAccount.email, hostAccount.password);
    const guest = await apiLogin(guestAccount.email, guestAccount.password);
    const late = await apiLogin(lateAccount.email, lateAccount.password);
    const room = await apiCreateRoom(host.access_token);
    const details = await apiGetRoom(room.id, host.access_token);
    await apiJoinRoom(details.public_id, guest.user.id, details.password, guest.access_token);

    // The host's browser, with a switch on its network: down, every socket is cut and
    // refused, and every API call or polling request fails as if offline
    const page = await createPlayerPage(browser, hostAccount.email, hostAccount.password);
    const context = page.context();
    let down = false;
    const live = new Set<WebSocketRoute>();
    await context.routeWebSocket(/\/socket\.io\//, (ws) => {
      if (down) {
        void ws.close({ code: 1001, reason: "offline" });
        return;
      }
      ws.connectToServer();
      live.add(ws);
      ws.onClose(() => live.delete(ws));
    });
    await context.route(/\/(api\/v1|socket\.io)\//, (route) => (down ? route.abort("internetdisconnected") : route.continue()));

    await page.goto(ROUTES.room(room.id));
    await expect(page.locator("text=Players (2)")).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(CHAT_INPUT)).toBeVisible();
    await apiSendChatMessage(room.id, "before-drop", guest.access_token);
    await expect(page.getByText("before-drop")).toBeVisible({ timeout: 10_000 });

    // Act — the link goes down: the sockets close, and the page says it is reconnecting
    down = true;
    for (const ws of [...live]) await ws.close({ code: 1001, reason: "offline" });
    await expect(page.getByText("Reconnecting…")).toBeVisible({ timeout: 15_000 });

    // ...meanwhile a line is sent and a player sits down; the outage lasts ten seconds
    await apiSendChatMessage(room.id, "while-down-hello", guest.access_token);
    await apiJoinRoom(details.public_id, late.user.id, details.password, late.access_token);
    await page.waitForTimeout(10_000); // the length of the outage, not a wait for anything
    await expect(page.getByText("while-down-hello")).toHaveCount(0);

    // ...then it comes back
    down = false;

    // Assert — reconnected, and both the line and the new player are there, with no reload
    await expect(page.getByText("Connected again")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("while-down-hello")).toHaveCount(1, { timeout: 15_000 });
    await expect(page.locator("text=Players (3)")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("before-drop")).toHaveCount(1);

    await context.close();
  });
});

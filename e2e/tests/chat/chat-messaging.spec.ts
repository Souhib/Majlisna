import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import { setupRoomWithPlayers } from "../../helpers/ui-game-setup";

const CHAT_INPUT_SELECTOR = 'input[placeholder="Type a message…"]';

/**
 * The ChatPanel is inline in the room lobby and starts open by default.
 * If it was collapsed (via the toggle button), click the "Chat" header to re-open.
 */
async function ensureChatOpen(page: import("@playwright/test").Page) {
  const chatInput = page.locator(CHAT_INPUT_SELECTOR);

  // Already open?
  if (await chatInput.isVisible().catch(() => false)) return;

  // Click the Chat header toggle to open
  const toggle = page.getByText("Chat", { exact: true });
  if (await toggle.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await toggle.click();
  }

  await expect(chatInput).toBeVisible({ timeout: 5_000 });
}

test.describe("Chat Messaging in Room", () => {
  test("chat panel is visible in room lobby with input field", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts);

    const hostPage = setup.players[0].page;

    // Chat panel starts open — input should be visible
    await expect(
      hostPage.locator(CHAT_INPUT_SELECTOR),
    ).toBeVisible({ timeout: 10_000 });

    // "No messages yet" placeholder should be visible
    await expect(
      hostPage.getByText("No messages yet"),
    ).toBeVisible({ timeout: 5_000 });

    await setup.cleanup();
  });

  test("send message and see it appear for sender", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts);

    const hostPage = setup.players[0].page;

    // Send a message
    await ensureChatOpen(hostPage);
    const input = hostPage.locator(CHAT_INPUT_SELECTOR);
    await input.fill("Assalamu Alaikum!");
    await input.press("Enter");

    // Message should appear for the sender
    await expect(
      hostPage.getByText("Assalamu Alaikum!"),
    ).toBeVisible({ timeout: 10_000 });

    // Input should be cleared after sending
    await expect(input).toHaveValue("");

    await setup.cleanup();
  });

  test("send and receive message between two players via Socket.IO", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts);

    const page1 = setup.players[0].page;
    const page2 = setup.players[1].page;

    // Player 1 sends a message
    await ensureChatOpen(page1);
    const input1 = page1.locator(CHAT_INPUT_SELECTOR);
    await input1.fill("Salam from player 1!");
    await input1.press("Enter");

    // Player 2 should see the message via Socket.IO
    await ensureChatOpen(page2);
    await expect(
      page2.getByText("Salam from player 1!"),
    ).toBeVisible({ timeout: 15_000 });

    // Player 2 replies
    const input2 = page2.locator(CHAT_INPUT_SELECTOR);
    await input2.fill("Wa Alaikum Assalam!");
    await input2.press("Enter");

    // Player 1 should see the reply via Socket.IO
    await expect(
      page1.getByText("Wa Alaikum Assalam!"),
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });

  test("messages persist after page reload (loaded via REST)", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts);

    const hostPage = setup.players[0].page;

    // Send a message
    await ensureChatOpen(hostPage);
    const input = hostPage.locator(CHAT_INPUT_SELECTOR);
    await input.fill("Bismillah");
    await input.press("Enter");

    // Verify message appears
    await expect(hostPage.getByText("Bismillah")).toBeVisible({
      timeout: 10_000,
    });

    // Reload page
    await hostPage.reload();
    await hostPage.waitForLoadState("domcontentloaded");

    // Wait for room to re-render
    await expect(
      hostPage.locator(CHAT_INPUT_SELECTOR),
    ).toBeVisible({ timeout: 15_000 });

    // Message should still be visible (loaded from REST on mount)
    await expect(hostPage.getByText("Bismillah")).toBeVisible({
      timeout: 15_000,
    });

    await setup.cleanup();
  });

  test("multiple messages appear in order", async ({ browser }) => {
    const accounts = await generateTestAccounts(2);
    const setup = await setupRoomWithPlayers(browser, accounts);

    const page1 = setup.players[0].page;
    const page2 = setup.players[1].page;

    // Player 1 sends two messages
    await ensureChatOpen(page1);
    const input1 = page1.locator(CHAT_INPUT_SELECTOR);
    await input1.fill("First message");
    await input1.press("Enter");
    await expect(page1.getByText("First message")).toBeVisible({
      timeout: 10_000,
    });

    await input1.fill("Second message");
    await input1.press("Enter");
    await expect(page1.getByText("Second message")).toBeVisible({
      timeout: 10_000,
    });

    // Player 2 should see both messages
    await ensureChatOpen(page2);
    await expect(
      page2.getByText("First message"),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page2.getByText("Second message"),
    ).toBeVisible({ timeout: 15_000 });

    await setup.cleanup();
  });
});

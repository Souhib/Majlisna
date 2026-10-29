import { test, expect } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import {
  apiLogin,
  apiSendFriendRequest,
  apiAcceptFriendRequest,
  apiGetFriends,
  apiGetPendingRequests,
} from "../../helpers/api-client";
import { ROUTES } from "../../helpers/constants";

test.describe("Friends Page", () => {
  test("friends page loads for authenticated user", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.friends);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Should see the friends page heading
    await expect(
      authenticatedPage.getByRole("heading", { name: "Friends", level: 1 }),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("friends page shows empty state when no friends", async ({
    browser,
  }) => {
    // Create a fresh user with no friends
    const accounts = await generateTestAccounts(1);
    const page = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );

    await page.goto(ROUTES.friends);
    await page.waitForLoadState("domcontentloaded");

    // The empty state itself. The old union (/no friends/ | /add friend/ | main) matched
    // <main> at once and, once the page had rendered, three elements: a strict-mode
    // violation that only failed when the check ran after the render.
    await expect(page.getByRole("heading", { name: "No friends yet" })).toBeVisible({ timeout: 10_000 });

    await page.context().close();
  });

  test("accepted friend appears in friends list", async ({ browser }) => {
    // Create two fresh users
    const accounts = await generateTestAccounts(2);
    const login1 = await apiLogin(accounts[0].email, accounts[0].password);
    const login2 = await apiLogin(accounts[1].email, accounts[1].password);

    // Send friend request from user1 to user2
    const friendship = await apiSendFriendRequest(
      login2.user.id,
      login1.access_token,
    );

    // Accept from user2
    await apiAcceptFriendRequest(friendship.friendship_id, login2.access_token);

    // Verify via API
    const friends1 = await apiGetFriends(login1.access_token);
    expect(friends1.length).toBe(1);

    // Verify on UI for user1
    const page = await createPlayerPage(
      browser,
      accounts[0].email,
      accounts[0].password,
    );
    await page.goto(ROUTES.friends);
    await page.waitForLoadState("domcontentloaded");

    // Should see user2's username in the friends list
    await expect(
      page.getByText(login2.user.username).first(),
    ).toBeVisible({ timeout: 15_000 });

    await page.context().close();
  });

  test("pending friend request is visible to addressee", async ({
    browser,
  }) => {
    const accounts = await generateTestAccounts(2);
    const login1 = await apiLogin(accounts[0].email, accounts[0].password);
    const login2 = await apiLogin(accounts[1].email, accounts[1].password);

    // Send friend request from user1 to user2
    await apiSendFriendRequest(login2.user.id, login1.access_token);

    // Verify pending request via API for user2
    const pending = await apiGetPendingRequests(login2.access_token);
    expect(pending.length).toBe(1);

    // Verify on UI for user2
    const page = await createPlayerPage(
      browser,
      accounts[1].email,
      accounts[1].password,
    );
    await page.goto(ROUTES.friends);
    await page.waitForLoadState("domcontentloaded");

    // Click on "Pending" tab to see pending requests
    const pendingTab = page.getByRole("button", { name: /Pending/i });
    await expect(pendingTab).toBeVisible({ timeout: 10_000 });
    await pendingTab.click();

    // Should see pending request from user1 (username visible)
    await expect(
      page.getByText(login1.user.username).first(),
    ).toBeVisible({ timeout: 15_000 });

    await page.context().close();
  });

  test("unauthenticated user is redirected from friends page", async ({
    page,
  }) => {
    await page.goto(ROUTES.friends);
    await page.waitForLoadState("domcontentloaded");

    // Should redirect to login
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 10_000 });
  });

  test("friends nav link navigates to friends page", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.home);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Friends link is inside the user dropdown menu
    // Open the user menu (avatar button with username)
    const userMenuBtn = authenticatedPage.locator('[data-testid="user-menu-trigger"]');
    await expect(userMenuBtn).toBeVisible({ timeout: 10_000 });
    await userMenuBtn.click();

    // Click the friends link in the dropdown
    const friendsLink = authenticatedPage.locator('a[href="/friends"]').first();
    await expect(friendsLink).toBeVisible({ timeout: 5_000 });
    await friendsLink.click();

    await expect(authenticatedPage).toHaveURL(/\/friends/, {
      timeout: 10_000,
    });
  });
});

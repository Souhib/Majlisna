import { test, expect, type Page } from "@playwright/test";
import { createPlayerPage } from "../../fixtures/auth.fixture";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  setupRoomWithPlayers,
  startGameViaAPI,
  dismissRoleRevealAll,
  submitDescriptionsForAllPlayersViaUI,
  undercoverRoles,
  voteOut,
} from "../../helpers/ui-game-setup";
import { apiGetUndercoverState, expectApiError, rawGetMe, rawPost } from "../../helpers/api-client";
import { ROUTES, STORAGE_KEYS } from "../../helpers/constants";
import { dbUserExists } from "../../helpers/db";

/**
 * Deleting an account from the profile: the password confirms it, the account is gone
 * (its tokens and its password with it), and a player who deletes mid-game leaves that
 * game like any departure, so the others play on (SEC F05: the purge used to delete the
 * seat behind the game's back, and the ghost blocked the describing turn forever).
 */

/** Profile → "Delete my account" → the password → "Delete permanently". */
async function deleteAccountFromProfile(page: Page, password: string): Promise<void> {
  await page.goto(ROUTES.profile);
  await page.getByRole("button", { name: "Delete my account" }).click();
  const dialog = page.getByRole("alertdialog", { name: "Delete your account?" });
  await expect(dialog).toBeVisible();
  await dialog.getByPlaceholder("Enter your password").fill(password);
  const deleted = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/v1/users/me/account");
  await dialog.getByRole("button", { name: "Delete permanently" }).click();
  expect((await deleted).status()).toBe(204);
  await expect(page.getByText("Your account has been deleted")).toBeVisible({ timeout: 10_000 });
}

test.describe("Account deletion", () => {
  test("delete the account, then it can no longer log in", async ({ browser }) => {
    // Prepare
    const [account] = await generateTestAccounts(1);
    const page = await createPlayerPage(browser, account.email, account.password);
    const token = await page.evaluate((key) => localStorage.getItem(key), STORAGE_KEYS.token);
    const me = (await (await rawGetMe(token!)).json()) as { id: string };

    // A wrong password is refused in the dialog, and the account stays
    await page.goto(ROUTES.profile);
    await page.getByRole("button", { name: "Delete my account" }).click();
    const dialog = page.getByRole("alertdialog", { name: "Delete your account?" });
    await dialog.getByPlaceholder("Enter your password").fill("not-my-password");
    await dialog.getByRole("button", { name: "Delete permanently" }).click();
    // ...said as a wrong password: the dialog has no email field (review F6)
    await expect(dialog.getByRole("alert")).toContainText("That password is not right.");
    await expect(dialog.getByText("Please check your email and password.")).toHaveCount(0);
    await dialog.getByRole("button", { name: "Cancel" }).click();
    expect(dbUserExists(me.id)).toBe(true);

    // Act
    await deleteAccountFromProfile(page, account.password);

    // Assert — signed out, home, the account gone with every way back into it
    await expect(page).toHaveURL(new URL("/", page.url()).href, { timeout: 15_000 });
    await expect(page.getByRole("link", { name: "Log in", exact: true }).first()).toBeVisible({ timeout: 15_000 });
    expect(dbUserExists(me.id)).toBe(false);
    await expectApiError(await rawPost("/api/v1/auth/login", { email: account.email, password: account.password }), 401, "errors.api.invalidCredentials");
    expect((await rawGetMe(token!)).status).toBe(401);

    // ...and the login page refuses it
    await page.goto(ROUTES.login);
    await page.locator('input[id="email"]').fill(account.email);
    await page.locator('input[id="password"]').fill(account.password);
    await page.locator('button[type="submit"]').click();
    await expect(page.getByTestId("form-error")).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/auth\/login/);

    await page.context().close();
  });

  test("a player who deletes the account mid-game leaves it, and the others play on", async ({ browser }) => {
    test.setTimeout(120_000);

    // Prepare — four players at the describing table (one undercover, three civilians)
    const accounts = await generateTestAccounts(4);
    const setup = await setupRoomWithPlayers(browser, accounts);
    const gameId = await startGameViaAPI(setup.players, "undercover", setup.roomId);
    await dismissRoleRevealAll(setup.players);
    const roles = await undercoverRoles(setup.players, gameId);
    // A civilian who is not the host leaves: the game is not decided by it
    const leaver = setup.players.slice(1).find((p) => roles.get(p.login.user.id) === "civilian")!;
    const stayers = setup.players.filter((p) => p !== leaver);
    const leaverName = leaver.login.user.username;

    // Act — the leaver opens the profile in their tab and deletes the account
    await deleteAccountFromProfile(leaver.page, leaver.account.password);

    // Assert — the others see the seat emptied, at once (pushed), and the game runs on
    for (const player of stayers) {
      const seat = player.page
        .getByRole("list", { name: "Who said what, in speaking order" })
        .getByRole("listitem")
        .filter({ hasText: leaverName });
      await expect(seat.filter({ hasText: "Eliminated" })).toBeVisible({ timeout: 15_000 });
      await expect(player.page.locator('h2:has-text("Game Over")')).toHaveCount(0);
    }
    const after = await apiGetUndercoverState(gameId, stayers[0].login.access_token);
    expect(after.winner ?? null).toBeNull();
    expect(after.players.find((p) => p.user_id === leaver.login.user.id)?.is_alive).toBe(false);
    expect(after.description_order?.[after.current_describer_index ?? 0]?.user_id).not.toBe(leaver.login.user.id);

    // The three who stayed describe, vote the undercover out, and the civilians win
    await submitDescriptionsForAllPlayersViaUI(stayers);
    const voting = await apiGetUndercoverState(gameId, stayers[0].login.access_token);
    const alive = voting.players.filter((p) => p.is_alive);
    expect(alive).toHaveLength(3);
    const undercover = alive.find((p) => roles.get(p.user_id) === "undercover")!;
    await voteOut(stayers, alive, undercover, alive.find((p) => p.user_id !== undercover.user_id)!);
    for (const player of stayers) {
      await expect(player.page.locator('h2:has-text("Game Over")')).toBeVisible({ timeout: 30_000 });
    }
    expect((await apiGetUndercoverState(gameId, stayers[0].login.access_token)).winner).toBe("civilians");

    await setup.cleanup();
  });
});

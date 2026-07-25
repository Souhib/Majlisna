import { test, expect } from "../../fixtures/auth.fixture";
import { ROUTES } from "../../helpers/constants";

test.describe("Profile — Edit Username", () => {
  test("profile page shows edit button next to username", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.profile);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Edit button (pencil icon) should be visible
    const editButton = authenticatedPage.locator(
      'button[aria-label="Edit Username"]',
    );
    await expect(editButton).toBeVisible({ timeout: 10_000 });
  });

  test("clicking edit button shows username input field", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.profile);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const editButton = authenticatedPage.locator(
      'button[aria-label="Edit Username"]',
    );
    await expect(editButton).toBeVisible({ timeout: 10_000 });
    await editButton.click();

    // Input field should appear
    const input = authenticatedPage.locator('input[type="text"]');
    await expect(input).toBeVisible();
    await expect(input).toBeFocused();
  });

  test("pressing Escape cancels editing", async ({ authenticatedPage }) => {
    await authenticatedPage.goto(ROUTES.profile);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    const editButton = authenticatedPage.locator(
      'button[aria-label="Edit Username"]',
    );
    await expect(editButton).toBeVisible({ timeout: 10_000 });
    await editButton.click();

    // Input is visible
    const input = authenticatedPage.locator('input[type="text"]');
    await expect(input).toBeVisible();

    // Press Escape to cancel
    await input.press("Escape");

    // Input should disappear, edit button should return
    await expect(input).not.toBeVisible();
    await expect(editButton).toBeVisible();
  });
});

test.describe("Profile — Change Password", () => {
  test("profile page shows change password button", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.profile);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    await expect(
      authenticatedPage.getByText("Change Password"),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("clicking change password shows form", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.profile);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    await authenticatedPage.getByText("Change Password").click();

    // Both password inputs must appear. Target them by placeholder: changing a
    // password now requires the CURRENT one too, so the form renders two
    // input[type="password"] elements and a bare locator on that selector is a
    // Playwright strict-mode violation.
    await expect(
      authenticatedPage.locator('input[placeholder="Current Password"]'),
    ).toBeVisible();
    await expect(
      authenticatedPage.locator('input[placeholder="New Password"]'),
    ).toBeVisible();
  });
});

test.describe("Profile — Quick Links", () => {
  test("profile quick links use i18n text instead of hardcoded strings", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.goto(ROUTES.profile);
    await authenticatedPage.waitForLoadState("domcontentloaded");

    // Should see translated description text (not hardcoded English)
    await expect(
      authenticatedPage.getByText("View your game statistics"),
    ).toBeVisible({ timeout: 10_000 });

    await expect(
      authenticatedPage.getByText("View your earned badges"),
    ).toBeVisible();

    await expect(
      authenticatedPage.getByText("Join or create a game room"),
    ).toBeVisible();
  });
});

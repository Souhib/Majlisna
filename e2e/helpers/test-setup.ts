import { randomUUID } from "crypto";
import { apiRegister } from "./api-client";

// ─── Dynamic Test Accounts ─────────────────────────────────

export interface TestAccount {
  email: string;
  password: string;
  username: string;
}

export const TEST_ACCOUNT_PASSWORD = "testpass1";

/**
 * Register N fresh test accounts with unique emails/usernames.
 * Returns account credentials that can be passed to setupRoomWithPlayers.
 */
export async function generateTestAccounts(count: number): Promise<TestAccount[]> {
  return Promise.all(
    Array.from({ length: count }, async () => {
      const id = randomUUID().slice(0, 8);
      const account = { email: `e2e-${id}@test.com`, password: TEST_ACCOUNT_PASSWORD, username: `e2e-${id}` };
      await apiRegister(account.username, account.email, account.password);
      return account;
    }),
  );
}

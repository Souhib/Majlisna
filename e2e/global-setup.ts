import { execSync } from "child_process";
import { waitForBackend, waitForFrontend } from "./helpers/api-client";
import { API_URL, FRONTEND_URL } from "./helpers/constants";

/**
 * The ONE place the E2E database is reset and seeded, before every Playwright run
 * (`run-local.sh` runs Playwright once per gate run, so each run starts identical).
 *
 * It used to happen twice: `run-local.sh` reseeded, then this file deleted and reseeded
 * again, inside a 3-attempt retry loop that would have hidden a timeout (INFRA-19). A
 * failing step now fails the run, loudly: a run against a half-seeded database reports
 * missing test accounts, which reads like a product bug.
 */

const BACKEND_CONTAINER = "majlisna-e2e-backend";
const PGBOUNCER_CONTAINER = "majlisna-e2e-pgbouncer";
const DB_CONTAINER = "majlisna-e2e-db";

/**
 * The seed reaches PostgreSQL directly (DIRECT_DATABASE_URL in docker-compose.e2e.yml):
 * it runs DDL, and through PgBouncer's transaction pooling asyncpg's stale per-connection
 * type cache makes the follow-up bulk inserts fail ("could not resolve query result
 * and/or argument types").
 */
const seedScript = (flag: string) =>
  `docker exec -w /app ${BACKEND_CONTAINER} env PYTHONPATH=/app python scripts/generate_fake_data.py ${flag}`;

/**
 * Restart the disposable PgBouncer and backend with a 1 s stop timeout. PgBouncer waits
 * for its connected clients until SIGKILL, so a plain `docker restart` spent its whole
 * 10 s grace there on every run; nothing in either container needs a graceful stop.
 * Restarting clears the prepared statements and type caches that point at the tables
 * the --delete just dropped.
 */
function restartPoolAndBackend(): void {
  execSync(`docker restart -t 1 ${PGBOUNCER_CONTAINER} ${BACKEND_CONTAINER}`, { stdio: "inherit", timeout: 60_000 });
}

function restartBackend(): void {
  execSync(`docker restart -t 1 ${BACKEND_CONTAINER}`, { stdio: "inherit", timeout: 60_000 });
}

/** The stack's own addresses (docker-compose.e2e.yml publishes them on loopback). */
const STACK_PORTS = { api: "5049", frontend: "3049" } as const;

/**
 * Refuse to reset the stack on behalf of a run aimed elsewhere. The steps below `docker
 * exec` into the majlisna-e2e-* containers whatever API_URL and FRONTEND_URL say, so a run
 * pointed at another backend used to drop and reseed the shared E2E database under any gate
 * run in progress (four times in one afternoon, from runs against a private stack).
 */
function assertRunTargetsTheStack(): void {
  for (const [what, url, port] of [
    ["API_URL", API_URL, STACK_PORTS.api],
    ["FRONTEND_URL", FRONTEND_URL, STACK_PORTS.frontend],
  ] as const) {
    const { hostname, port: actual } = new URL(url);
    if (!["localhost", "127.0.0.1"].includes(hostname) || actual !== port) {
      throw new Error(
        `[E2E Setup] ${what}=${url} is not the E2E stack (localhost:${port}). This setup drops and reseeds the ` +
          "majlisna-e2e-* containers' database, so it only runs against that stack.",
      );
    }
  }
}

async function globalSetup(): Promise<void> {
  assertRunTargetsTheStack();
  console.log("[E2E Setup] Waiting for backend and frontend...");
  await waitForBackend();
  await waitForFrontend(FRONTEND_URL);

  // Stale connections hold locks the drop below would wait on.
  console.log("[E2E Setup] Terminating stale DB connections...");
  execSync(
    `docker exec ${DB_CONTAINER} psql -U majlisna -d majlisna -v ON_ERROR_STOP=1 -c ` +
      `"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid();"`,
    { stdio: "inherit", timeout: 15_000 },
  );

  console.log("[E2E Setup] Dropping and recreating the tables...");
  execSync(seedScript("--delete"), { stdio: "inherit", timeout: 120_000 });

  console.log("[E2E Setup] Restarting PgBouncer + backend (stale caches after the DDL)...");
  restartPoolAndBackend();
  await waitForBackend(60, 1_000);

  console.log("[E2E Setup] Seeding...");
  execSync(seedScript("--create-db"), { stdio: "inherit", timeout: 180_000 });

  // A fresh backend for the run: no connection or worker cache from before the seed.
  console.log("[E2E Setup] Restarting the backend...");
  restartBackend();
  await waitForBackend(60, 1_000);
  console.log(`[E2E Setup] Ready: ${API_URL} and ${FRONTEND_URL}.`);
}

export default globalSetup;

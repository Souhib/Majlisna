import { execSync } from "child_process";
import { waitForBackend, waitForFrontend } from "./helpers/api-client";
import { FRONTEND_URL } from "./helpers/constants";

function runDockerExec(command: string, timeout = 120_000): void {
  try {
    execSync(command, { stdio: "inherit", timeout });
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    // If it's a timeout, retry once
    if (msg.includes("ETIMEDOUT") || msg.includes("timed out")) {
      console.log("[E2E Setup] Command timed out, retrying...");
      execSync(command, { stdio: "inherit", timeout });
    } else {
      throw error;
    }
  }
}

async function globalSetup(): Promise<void> {
  console.log("[E2E Setup] Waiting for backend to be healthy...");
  await waitForBackend();
  console.log("[E2E Setup] Backend is healthy.");

  console.log("[E2E Setup] Waiting for frontend to be reachable...");
  await waitForFrontend(FRONTEND_URL);
  console.log("[E2E Setup] Frontend is reachable.");

  // Terminate stale DB connections before dropping tables (prevents lock deadlocks)
  console.log("[E2E Setup] Terminating stale DB connections...");
  try {
    execSync(
      'docker exec ipg-e2e-db psql -U ipg -d ipg -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid();"',
      { stdio: "inherit", timeout: 15_000 },
    );
  } catch {
    // Ignore — DB might not have stale connections
  }

  console.log("[E2E Setup] Resetting and seeding database via docker exec...");
  runDockerExec(
    "docker exec -w /app ipg-e2e-backend " +
      "env PYTHONPATH=/app python scripts/generate_fake_data.py --delete",
  );
  runDockerExec(
    "docker exec -w /app ipg-e2e-backend " +
      "env PYTHONPATH=/app python scripts/generate_fake_data.py --create-db",
  );
  console.log("[E2E Setup] Database seeded.");

  // Only restart backend if it can't serve requests (avoids ~30-60s delay)
  let backendOk = false;
  try {
    const res = await fetch(
      `${process.env.API_URL || "http://localhost:5049"}/api/v1/stats/leaderboard?limit=1`,
    );
    backendOk = res.ok;
  } catch {}

  if (backendOk) {
    console.log("[E2E Setup] Backend already healthy, skipping restart.");
  } else {
    console.log("[E2E Setup] Restarting backend to refresh DB connections...");
    execSync("docker restart ipg-e2e-backend", {
      stdio: "inherit",
      timeout: 30_000,
    });
    await waitForBackend();
    console.log("[E2E Setup] Backend restarted and healthy.");
  }
}

export default globalSetup;

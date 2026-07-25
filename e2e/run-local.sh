#!/usr/bin/env bash
#
# The authoritative E2E gate: the full Playwright suite against the isolated
# local docker stack.
#
# This exists because running the suite by hand is a five-step dance (bring up
# the stack, wait for health, drop the DB, reseed, run) and skipping any step
# gives a misleading result — a run against an unseeded database fails on
# missing test accounts, which looks like a product bug.
#
# Usage:
#   ./run-local.sh                # one full run
#   ./run-local.sh -n 3           # the pre-push gate: 3 consecutive clean runs
#   ./run-local.sh -n 1 --down    # run once, then tear the stack down
#   ./run-local.sh --no-build     # reuse the images already built
#   ./run-local.sh -- --grep @x   # everything after `--` goes to playwright
#
# Exits non-zero on ANY failure. Retries are OFF locally (playwright.config.ts
# only enables them when CI is set), so a test that only passes on a second
# attempt is reported as a failure — which is the intent: a flaky test is a
# failing test.
set -uo pipefail

cd "$(dirname "$0")"

COMPOSE_FILE=docker-compose.e2e.yml
BACKEND_HEALTH=http://localhost:5049/health
FRONTEND_URL=http://localhost:3049
BACKEND_CONTAINER=majlisna-e2e-backend

RUNS=1
BUILD=1
TEARDOWN=0
PW_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    -n) RUNS="${2:?-n needs a count}"; shift 2 ;;
    --no-build) BUILD=0; shift ;;
    --down) TEARDOWN=1; shift ;;
    --) shift; PW_ARGS=("$@"); break ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1;36m▶ %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m✖ %s\033[0m\n' "$1" >&2; exit 1; }

# ── Stack ────────────────────────────────────────────────────────────────────

step "Bringing up the isolated e2e stack"
if [ "$BUILD" -eq 1 ]; then
  docker compose -f "$COMPOSE_FILE" up -d --build --wait || fail "stack failed to come up"
else
  docker compose -f "$COMPOSE_FILE" up -d --wait || fail "stack failed to come up"
fi

step "Waiting for backend + frontend"
for _ in $(seq 1 60); do
  if curl -sf "$BACKEND_HEALTH" >/dev/null 2>&1 && curl -sf "$FRONTEND_URL" >/dev/null 2>&1; then
    echo "  both reachable"
    break
  fi
  sleep 2
done
curl -sf "$BACKEND_HEALTH" >/dev/null 2>&1 || fail "backend never became healthy — docker compose -f $COMPOSE_FILE logs backend"
curl -sf "$FRONTEND_URL" >/dev/null 2>&1 || fail "frontend never became reachable"

# ── Seed ─────────────────────────────────────────────────────────────────────
#
# Reseeded before EVERY run so each one starts from an identical database. The
# script drops and recreates the schema, which also means a model change is
# picked up here without any migration.
#
# The seed reaches PostgreSQL directly via DIRECT_DATABASE_URL (set in the e2e
# compose): it runs DDL, and through PgBouncer's transaction pooling asyncpg's
# stale per-connection type cache makes the follow-up bulk inserts fail with
# "could not resolve query result and/or argument types".
seed() {
  docker exec -w /app "$BACKEND_CONTAINER" env PYTHONPATH=/app \
    python scripts/generate_fake_data.py --delete >/dev/null 2>&1 || return 1
  docker exec -w /app "$BACKEND_CONTAINER" env PYTHONPATH=/app \
    python scripts/generate_fake_data.py --create-db 2>&1 | tail -1
}

# ── Runs ─────────────────────────────────────────────────────────────────────

failed_runs=()
for run in $(seq 1 "$RUNS"); do
  step "Seeding database (run $run/$RUNS)"
  seed || fail "seeding failed — the suite would report false failures on missing test accounts"

  step "Playwright run $run/$RUNS"
  out=$(mktemp)
  if npx playwright test "${PW_ARGS[@]+"${PW_ARGS[@]}"}" 2>&1 | tee "$out"; then
    :
  fi
  # Trust playwright's exit code via PIPESTATUS, not the tee.
  status=${PIPESTATUS[0]}

  # Belt and braces: `flaky` only appears when retries are enabled, but if
  # someone runs this with CI set we still refuse to call a rescued test a pass.
  if grep -qE '[0-9]+ flaky' "$out"; then
    echo "  flaky tests detected — treated as failure"
    status=1
  fi

  if [ "$status" -ne 0 ]; then
    failed_runs+=("$run")
    echo "  run $run FAILED"
  else
    echo "  run $run clean"
  fi
  rm -f "$out"
done

if [ "$TEARDOWN" -eq 1 ]; then
  step "Tearing down the stack"
  docker compose -f "$COMPOSE_FILE" down -v
fi

# ── Verdict ──────────────────────────────────────────────────────────────────

printf '\n'
if [ ${#failed_runs[@]} -ne 0 ]; then
  fail "E2E gate FAILED — runs ${failed_runs[*]} of $RUNS were not clean. Report: npx playwright show-report"
fi
printf '\033[1;32m✔ E2E gate passed — %s/%s consecutive clean run(s)\033[0m\n' "$RUNS" "$RUNS"

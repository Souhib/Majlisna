#!/usr/bin/env bash
#
# The E2E gate: the full Playwright suite against the isolated local docker stack.
#
# This exists because running the suite by hand is a five-step dance (bring up
# the stack, wait for health, drop the DB, reseed, run) and skipping any step
# gives a misleading result — a run against an unseeded database fails on
# missing test accounts, which looks like a product bug.
#
# CI RUNS THIS SAME SCRIPT (the `e2e` job in .github/workflows/pipeline.yml, with
# CI=true), and that job blocks the production deploy. So a change here changes
# what gates production — it is not a local-only convenience.
#
# Usage:
#   ./run-local.sh                # one full run
#   ./run-local.sh -n 3           # the pre-push gate: 3 consecutive clean runs
#   ./run-local.sh -n 1 --down    # run once, then tear the stack down
#   ./run-local.sh --no-build     # reuse the images already built
#   ./run-local.sh -w 4           # 4 Playwright workers (= E2E_WORKERS=4; default 2)
#   ./run-local.sh -- --grep @x   # everything after `--` goes to playwright
#
# Exits non-zero on ANY failure. Retries are OFF, locally and in CI
# (playwright.config.ts), so a test that only passes on a second attempt is
# reported as a failure — which is the intent: a flaky test is a failing test.
set -uo pipefail

cd "$(dirname "$0")"

COMPOSE_FILE=docker-compose.e2e.yml
BACKEND_HEALTH=http://localhost:5049/health
FRONTEND_URL=http://localhost:3049

RUNS=1
BUILD=1
TEARDOWN=0
PW_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    -n) RUNS="${2:?-n needs a count}"; shift 2 ;;
    --no-build) BUILD=0; shift ;;
    --down) TEARDOWN=1; shift ;;
    -w) E2E_WORKERS="${2:?-w needs a count}"; export E2E_WORKERS; shift 2 ;;
    --) shift; PW_ARGS=("$@"); break ;;
    -h|--help) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1;36m▶ %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m✖ %s\033[0m\n' "$1" >&2; exit 1; }

# Launch playwright through bunx, with npx only as a fallback.
#
# bunx first because the self-hosted CI runner has Bun (via setup-bun) but NO
# Node — hardcoding npx made the job die with "npx: command not found" *after*
# bringing the stack up and seeding. Preferring bunx also means CI and local
# invoke the suite identically, which is the whole point of sharing this script.
if command -v bunx >/dev/null 2>&1; then
  PW=(bunx playwright)
elif command -v npx >/dev/null 2>&1; then
  PW=(npx playwright)
else
  fail "neither bunx nor npx is available — install Bun (https://bun.sh) to run the suite"
fi

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
# Seeding is global-setup.ts's job, and only its: Playwright runs it before EVERY run
# below, so each run starts from an identical database (drop, recreate, reseed). This
# script used to reseed as well, then global-setup did it again, so every run seeded
# twice (INFRA-19). The schema is dropped and recreated each time, so a model change is
# picked up without any migration.

# ── Runs ─────────────────────────────────────────────────────────────────────

failed_runs=()
for run in $(seq 1 "$RUNS"); do
  # E2E_WORKERS reaches playwright.config.ts through the environment (unset = its default, 2)
  step "Playwright run $run/$RUNS (workers: ${E2E_WORKERS:-2})"
  out=$(mktemp)
  started=$(date +%s)
  "${PW[@]}" test "${PW_ARGS[@]+"${PW_ARGS[@]}"}" 2>&1 | tee "$out"
  # Capture immediately: an enclosing `if` overwrites PIPESTATUS and can turn
  # failed Playwright runs into a green deployment gate.
  status=${PIPESTATUS[0]}
  elapsed=$(( $(date +%s) - started ))
  took="$(( elapsed / 60 ))m$(( elapsed % 60 ))s"

  # Belt and braces: `flaky` only appears when retries are enabled, which
  # playwright.config.ts never does; if someone turns them on, a rescued test
  # still is not a pass.
  if grep -qE '[0-9]+ flaky' "$out"; then
    echo "  flaky tests detected — treated as failure"
    status=1
  fi

  if [ "$status" -ne 0 ]; then
    failed_runs+=("$run")
    echo "  run $run FAILED (${took})"
  else
    echo "  run $run clean (${took})"
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
  fail "E2E gate FAILED — runs ${failed_runs[*]} of $RUNS were not clean. Report: ${PW[*]} show-report"
fi
printf '\033[1;32m✔ E2E gate passed — %s/%s consecutive clean run(s)\033[0m\n' "$RUNS" "$RUNS"

#!/usr/bin/env bash
# Exercise exit propagation without starting containers or browsers.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
cat > "$fixture/bunx" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "${PW_RESULT:-1 passed}"
printf '%s' "${E2E_WORKERS:-unset}" > "$(dirname "$0")/workers.seen"
exit "${PW_EXIT:-0}"
MOCK
printf '#!/usr/bin/env bash\nexit 0\n' > "$fixture/docker"
cp "$fixture/docker" "$fixture/curl"
chmod +x "$fixture/bunx" "$fixture/docker" "$fixture/curl"
for outcome in success failure flaky; do
  case "$outcome" in
    success) code=0; result='1 passed'; expected=0 ;;
    failure) code=1; result='1 failed'; expected=1 ;;
    flaky) code=0; result='1 flaky'; expected=1 ;;
  esac
  status=0
  PATH="$fixture:$PATH" PW_EXIT="$code" PW_RESULT="$result" \
    bash "$here/run-local.sh" --no-build > "$fixture/result.log" 2>&1 || status=$?
  if [ "$status" -ne "$expected" ]; then
    cat "$fixture/result.log"
    echo "Unexpected gate exit for $outcome: $status, expected $expected" >&2
    exit 1
  fi
done
echo 'E2E gate exit propagation: 3 cases passed'

# -w reaches Playwright as E2E_WORKERS (playwright.config.ts reads it), and without -w the
# caller's own E2E_WORKERS (the CI job's) is passed through untouched.
PATH="$fixture:$PATH" bash "$here/run-local.sh" --no-build -w 4 > "$fixture/result.log" 2>&1
if [ "$(cat "$fixture/workers.seen")" != 4 ]; then
  cat "$fixture/result.log"
  echo "run-local.sh -w 4 gave Playwright E2E_WORKERS=$(cat "$fixture/workers.seen"), expected 4" >&2
  exit 1
fi
PATH="$fixture:$PATH" E2E_WORKERS=6 bash "$here/run-local.sh" --no-build > "$fixture/result.log" 2>&1
if [ "$(cat "$fixture/workers.seen")" != 6 ]; then
  cat "$fixture/result.log"
  echo "E2E_WORKERS=6 reached Playwright as $(cat "$fixture/workers.seen"), expected 6" >&2
  exit 1
fi
echo 'E2E gate worker count: 2 cases passed'

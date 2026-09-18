#!/usr/bin/env bash
# Exercise exit propagation without starting containers or browsers.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
cat > "$fixture/bunx" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "${PW_RESULT:-1 passed}"
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

#!/usr/bin/env bash
# Container command: wait (bounded) until majlisna-db and SeaweedFS accept connections,
# then start the Dagu scheduler.
#
# Why: the scheduler's first act after a start can be the catch-up of a missed 03:45 run.
# After a host reboot Docker restarts every container at once, so majlisna-db may not be
# up yet; and an engine older than API 1.44 attaches a container's second network only
# after it starts. Either way that catch-up run would fail and the day would have no
# backup. This gate is not a retry of a failure: it delays the start, says so in the
# container log, and gives up after STARTUP_WAIT_SECONDS by starting anyway, so a real
# outage still yields a failed, visible run (and no heartbeat).
set -euo pipefail

reachable() { timeout 3 bash -c "exec 3<>/dev/tcp/$1/$2" 2>/dev/null; }

s3_url="${S3_ENDPOINT:-}"
s3_hostport="${s3_url#*://}"
s3_hostport="${s3_hostport%%/*}"
s3_host="${s3_hostport%%:*}"
s3_port="${s3_hostport##*:}"
[[ "${s3_port}" != "${s3_hostport}" ]] || s3_port=80
db_host="${PGHOST:-}"
db_port="${PGPORT:-5432}"

wait_seconds="${STARTUP_WAIT_SECONDS:-300}"
start="$(date +%s)"
next_note=0
while true; do
  if reachable "${db_host}" "${db_port}" && reachable "${s3_host}" "${s3_port}"; then
    echo "start-scheduler: ${db_host}:${db_port} and ${s3_host}:${s3_port} reachable after $(($(date +%s) - start))s"
    break
  fi
  waited="$(($(date +%s) - start))"
  if [[ "${waited}" -ge "${wait_seconds}" ]]; then
    echo "start-scheduler: WARNING ${db_host}:${db_port} or ${s3_host}:${s3_port} still unreachable after ${waited}s; starting anyway" >&2
    break
  fi
  if [[ "${waited}" -ge "${next_note}" ]]; then
    echo "start-scheduler: waiting for ${db_host}:${db_port} and ${s3_host}:${s3_port}"
    next_note=$((waited + 30))
  fi
  sleep 2
done
echo "start-scheduler: starting the Dagu scheduler"
exec dagu scheduler

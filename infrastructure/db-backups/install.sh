#!/usr/bin/env bash
# Install or update the Majlisna DB backup on the VPS. Idempotent. Run it from its own
# directory, a copy of infrastructure/db-backups/ at /home/ubuntu/majlisna-backups/, as the
# ubuntu user (uid 1001, docker group):
#
#   ./install.sh          # install or update; no backup run
#   ./install.sh --run    # the same, then run the backup once and list the bucket
#
# What it changes, and nothing else:
#   - secrets.env in this directory: created once (chmod 600), never overwritten; later
#     runs only append names a newer secrets.env.example introduced;
#   - the role majlisna_backup in majlisna-db: created or re-asserted, password set from
#     secrets.env as a SCRAM verifier (backup-role.sql, set-role-password.py);
#   - the container majlisna-backup-dagu: built and (re)started by docker compose;
#   - the bucket majlisna-db-backups in LaTabdhir's SeaweedFS: created if missing.
# It never stops, restarts or reconfigures a majlisna-* or LaTabdhir container, never
# writes table data, and never prints a secret.
set -euo pipefail
umask 077
cd "$(dirname "$0")"

DB_CONTAINER="${MAJLISNA_DB_CONTAINER:-majlisna-db}"
SEAWEEDFS_CONTAINER="${SEAWEEDFS_CONTAINER:-latabdhir-backup-seaweedfs}"
LATABDHIR_SECRETS="${LATABDHIR_SECRETS:-/home/ubuntu/latabdhir-backups/secrets.env}"
export MAJLISNA_DB_NETWORK="${MAJLISNA_DB_NETWORK:-compose-index-cross-platform-capacitor-27v2m5_internal}"
export SEAWEEDFS_NETWORK="${SEAWEEDFS_NETWORK:-latabdhir-backups_internal}"
export BACKUP_CONTAINER="${BACKUP_CONTAINER:-majlisna-backup-dagu}"
OWNER_FPR="9E6AC949274F12B4B803F4A52967A96B8DFE7D92"
SERVER_MAJOR="16"
RUN_ONCE="no"
TMP_SECRETS=""

say() { printf '==> %s\n' "$*"; }
die() { printf 'install: %s\n' "$*" >&2; exit 1; }
trap '[[ -z "${TMP_SECRETS}" ]] || rm -f -- "${TMP_SECRETS}"' EXIT

case "${1:-}" in
  "") ;;
  --run) RUN_ONCE="yes" ;;
  *) die "usage: ./install.sh [--run]" ;;
esac

running() { [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" == "true" ]]; }
on_network() { docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}' "$1" | tr ' ' '\n' | grep -qx "$2"; }
db_psql() {
  # Local socket inside the DB container, as its POSTGRES_USER: nothing crosses a network.
  docker exec -i "${DB_CONTAINER}" sh -c 'psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
}

say "preflight"
[[ "$(id -u)" -ne 0 ]] || die "run as the ubuntu user, not root"
if [[ "$(uname -s)" == "Linux" && "$(id -u)" -ne 1001 ]]; then
  die "run as uid 1001 (ubuntu): the container writes dagu-config/ as 1001"
fi
for tool in docker python3 openssl gpg; do
  command -v "${tool}" >/dev/null || die "${tool} is missing"
done
docker compose version >/dev/null || die "docker compose v2 is missing"
running "${DB_CONTAINER}" || die "${DB_CONTAINER} is not running"
running "${SEAWEEDFS_CONTAINER}" || die "${SEAWEEDFS_CONTAINER} is not running"
on_network "${DB_CONTAINER}" "${MAJLISNA_DB_NETWORK}" || die "${DB_CONTAINER} is not on ${MAJLISNA_DB_NETWORK} (Dokploy renamed the project?)"
on_network "${SEAWEEDFS_CONTAINER}" "${SEAWEEDFS_NETWORK}" || die "${SEAWEEDFS_CONTAINER} is not on ${SEAWEEDFS_NETWORK}"
major="$(docker exec "${DB_CONTAINER}" sh -c 'printf %s "${PG_MAJOR:-}"')"
[[ "${major}" == "${SERVER_MAJOR}" ]] \
  || die "${DB_CONTAINER} runs PostgreSQL ${major}; the image ships pg_dump ${SERVER_MAJOR}: update dagu-image/Dockerfile first"
gnupg_tmp="$(mktemp -d)"
fpr="$(gpg --homedir "${gnupg_tmp}" --batch --with-colons --show-keys dagu-image/backup-public-key.asc 2>/dev/null | awk -F: '$1=="fpr"{print $10; exit}')"
rm -rf -- "${gnupg_tmp}"
[[ "${fpr}" == "${OWNER_FPR}" ]] || die "dagu-image/backup-public-key.asc is not the owner's key ${OWNER_FPR}"
used="$(df -P . | awk 'NR==2{gsub("%","",$5); print $5}')"
[[ "${used}" -lt "${MAX_DISK_PERCENT:-95}" ]] || die "the disk is ${used}% full"
say "  ${DB_CONTAINER} (PostgreSQL ${major}), ${SEAWEEDFS_CONTAINER}, networks, owner key ${fpr}, disk ${used}%: ok"

if [[ ! -f secrets.env ]]; then
  say "creating secrets.env (values are never shown)"
  [[ -r "${LATABDHIR_SECRETS}" ]] || die "cannot read ${LATABDHIR_SECRETS} (the SeaweedFS keys)"
  S3_ACCESS_VALUE="$(sed -n 's/^S3_ACCESS_KEY=//p' "${LATABDHIR_SECRETS}" | tail -n 1)"
  S3_SECRET_VALUE="$(sed -n 's/^S3_SECRET_KEY=//p' "${LATABDHIR_SECRETS}" | tail -n 1)"
  [[ -n "${S3_ACCESS_VALUE}" && -n "${S3_SECRET_VALUE}" ]] || die "no S3 keys in ${LATABDHIR_SECRETS}"
  DB_NAME_VALUE="$(docker exec "${DB_CONTAINER}" sh -c 'printf %s "$POSTGRES_DB"')"
  [[ "${DB_NAME_VALUE}" =~ ^[A-Za-z0-9_]+$ ]] || die "unexpected POSTGRES_DB in ${DB_CONTAINER}"
  TMP_SECRETS="$(mktemp secrets.env.XXXXXX)"
  # Values go through the environment of one python process, never through argv.
  PGPASSWORD_VALUE="$(openssl rand -hex 24)" S3_ACCESS_VALUE="${S3_ACCESS_VALUE}" \
    S3_SECRET_VALUE="${S3_SECRET_VALUE}" DB_NAME_VALUE="${DB_NAME_VALUE}" \
    PGHOST_VALUE="${DB_CONTAINER}" S3_ENDPOINT_VALUE="http://${SEAWEEDFS_CONTAINER}:8333" \
    python3 - secrets.env.example "${TMP_SECRETS}" <<'PY'
import os, sys
template, target = sys.argv[1:3]
values = {
    "PGHOST": os.environ["PGHOST_VALUE"],
    "PGDATABASE": os.environ["DB_NAME_VALUE"],
    "PGPASSWORD": os.environ["PGPASSWORD_VALUE"],
    "S3_ENDPOINT": os.environ["S3_ENDPOINT_VALUE"],
    "S3_ACCESS_KEY": os.environ["S3_ACCESS_VALUE"],
    "S3_SECRET_KEY": os.environ["S3_SECRET_VALUE"],
}
out = []
for line in open(template).read().splitlines():
    key = line.split("=", 1)[0]
    if not line.startswith("#") and "=" in line and key in values:
        line = f"{key}={values[key]}"
    out.append(line)
with open(target, "w") as handle:
    handle.write("\n".join(out) + "\n")
PY
  unset S3_ACCESS_VALUE S3_SECRET_VALUE
  chmod 600 "${TMP_SECRETS}"
  mv -- "${TMP_SECRETS}" secrets.env
  TMP_SECRETS=""
else
  chmod 600 secrets.env
  # A newer template may introduce names the DAG reads: add them with their defaults.
  added="$(python3 - secrets.env.example secrets.env <<'PY'
import sys
template, target = sys.argv[1:3]
have = {l.split("=", 1)[0] for l in open(target).read().splitlines() if "=" in l and not l.startswith("#")}
new = [l for l in open(template).read().splitlines()
       if "=" in l and not l.startswith("#") and l.split("=", 1)[0] not in have]
if new:
    with open(target, "a") as handle:
        handle.write("\n".join(new) + "\n")
print(" ".join(l.split("=", 1)[0] for l in new))
PY
)"
  say "secrets.env kept${added:+ (added: ${added})}"
fi
grep -q '^PGPASSWORD=[A-Za-z0-9]\{32,\}$' secrets.env || die "secrets.env has no usable PGPASSWORD"

say "re-asserting the read-only role majlisna_backup in ${DB_CONTAINER}"
db_psql <backup-role.sql >/dev/null
python3 set-role-password.py secrets.env | db_psql >/dev/null

say "building and starting ${BACKUP_CONTAINER}"
mkdir -p dagu-config/dags
compose_log="$(mktemp)"
if ! docker compose up -d --build >"${compose_log}" 2>&1; then
  tail -n 30 "${compose_log}" >&2
  rm -f -- "${compose_log}"
  die "docker compose up failed"
fi
rm -f -- "${compose_log}"
# The container's own gate (start-scheduler.sh) waits until majlisna-db and SeaweedFS
# answer before starting the scheduler; the checks below run once it has.
gate="no"
for _ in $(seq 1 180); do
  if docker logs "${BACKUP_CONTAINER}" 2>&1 | grep -q "start-scheduler: starting the Dagu scheduler"; then
    gate="yes"
    break
  fi
  running "${BACKUP_CONTAINER}" || break
  sleep 2
done
[[ "${gate}" == "yes" ]] || die "${BACKUP_CONTAINER} did not start its scheduler (docker logs ${BACKUP_CONTAINER})"

in_container() { docker exec "${BACKUP_CONTAINER}" "$@" </dev/null; }
say "checking the DAG, the role and the bucket from ${BACKUP_CONTAINER}"
in_container dagu validate /config/dags/majlisna-db-backup.yaml >/dev/null 2>&1 || die "the DAG does not validate"
who="$(in_container psql -X -At -c 'select current_user' 2>/dev/null)" \
  || die "cannot log in to ${DB_CONTAINER} as majlisna_backup"
[[ "${who}" == "majlisna_backup" ]] || die "logged in as ${who}, expected majlisna_backup"
in_container python3 /usr/local/bin/s3.py --target primary ensure-bucket \
  || die "SeaweedFS refused the bucket (keys or endpoint in secrets.env?)"
bucket="$(sed -n 's/^S3_BUCKET=//p' secrets.env | tail -n 1)"
say "  role majlisna_backup logs in; bucket ${bucket}: $(in_container python3 /usr/local/bin/s3.py --target primary count majlisna) majlisna- object(s)"

if grep -q '^OFFSITE_S3_BUCKET=.\+' secrets.env; then
  if docker exec "${BACKUP_CONTAINER}" python3 /usr/local/bin/s3.py --target offsite count probe </dev/null >/dev/null 2>&1; then
    say "  off-host bucket: reachable"
  else
    say "  WARNING: the off-host bucket is configured but not reachable: every run will fail"
  fi
else
  say "  off-host copy: not configured (owner step, docs/operations/backups.md)"
fi
if ! grep -q '^BACKUP_HEARTBEAT_URL=.\+' secrets.env; then
  say "  WARNING: BACKUP_HEARTBEAT_URL is empty: a stopped backup would go unnoticed (owner step)"
fi

if [[ "${RUN_ONCE}" == "yes" ]]; then
  say "running the backup once"
  docker exec "${BACKUP_CONTAINER}" dagu start majlisna-db-backup </dev/null || die "the backup run failed (see above)"
  docker exec "${BACKUP_CONTAINER}" python3 /usr/local/bin/s3.py --target primary list majlisna </dev/null | tail -n 3
fi
say "done: schedule $(sed -n 's/^schedule: //p' dagu-config/dags/majlisna-db-backup.yaml) (UTC)"

#!/usr/bin/env bash
# Daily encrypted backup of the Majlisna PostgreSQL (majlisna-db), run by the Dagu DAG
# majlisna-db-backup. Configured by environment only (see secrets.env.example):
#
#   pg_dump -Fc as the read-only role majlisna_backup
#     -> passthru.py (checks the PGDMP magic and counts bytes, in memory)
#     -> gpg, encrypted to the owner's PUBLIC key
#     -> SeaweedFS, verified -> optional off-host S3, verified
#     -> rotation (newest RETENTION_VERSIONS "majlisna-" objects)
#     -> Uptime Kuma push heartbeat -> optional Discord summary.
#
# No plaintext dump ever touches disk and the private key is never on this host. Any
# failure exits non-zero and sends no heartbeat: a missing heartbeat is the alert.
set -euo pipefail
umask 077

# An unresolved Dagu reference ("${NAME}", left when secrets.env lacks NAME) counts as unset.
setting() {
  local value="${!1:-}"
  if [[ "${value}" == "\${"* ]]; then value=""; fi
  printf '%s' "${value}"
}

TS="$(date -u +%Y%m%dT%H%M%SZ)"
PREFIX="$(setting BACKUP_NAME_PREFIX)"; PREFIX="${PREFIX:-majlisna}"
NAME="${PREFIX}-${TS}.dump.gpg"
STAGE="setup"
TMP_ROOT="${TMPDIR:-/tmp}"
WORK=""
OUT=""

notify() { python3 /usr/local/bin/notify.py "$1"; }
fail() {
  trap - ERR
  echo "backup FAILED (${STAGE}): $1" >&2
  notify "🔴 **Majlisna DB backup FAILED** — $1 (\`${NAME}\`). Check the Dagu log on the VPS; do not delete older backups." >/dev/null 2>&1 || true
  exit 1
}
cleanup() {
  local status="$1"
  trap - EXIT HUP INT TERM ERR
  set +e
  # WORK comes from mktemp with a fixed prefix: refuse to clean anything else.
  if [[ -n "${WORK}" && "${WORK}" == "${TMP_ROOT%/}/majlisna-db-backup."* && -d "${WORK}" && ! -L "${WORK}" ]]; then
    rm -rf -- "${WORK}"
  fi
  exit "${status}"
}
trap 'cleanup "$?"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'fail "unexpected error"' ERR

for required in PGHOST PGUSER PGDATABASE PGPASSWORD S3_ENDPOINT S3_BUCKET S3_ACCESS_KEY S3_SECRET_KEY; do
  [[ -n "$(setting "${required}")" ]] || fail "${required} is not set in secrets.env"
done
PGPORT_VALUE="$(setting PGPORT)"; PGPORT_VALUE="${PGPORT_VALUE:-5432}"
RECIPIENT="$(setting BACKUP_RECIPIENT_FILE)"; RECIPIENT="${RECIPIENT:-/etc/majlisna/backup-public-key.asc}"
KEEP="$(setting RETENTION_VERSIONS)"; KEEP="${KEEP:-30}"
MIN_BYTES="$(setting MIN_DUMP_BYTES)"; MIN_BYTES="${MIN_BYTES:-10000}"
HEARTBEAT="$(setting BACKUP_HEARTBEAT_URL)"
OFFSITE_BUCKET="$(setting OFFSITE_S3_BUCKET)"
OFFSITE_PREFIX="$(setting OFFSITE_S3_PREFIX)"
OFFSITE_KEEP="$(setting OFFSITE_RETENTION_VERSIONS)"; OFFSITE_KEEP="${OFFSITE_KEEP:-0}"
[[ "${PREFIX}" =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "BACKUP_NAME_PREFIX must be lowercase letters, digits and dashes"
[[ "${KEEP}" =~ ^[1-9][0-9]*$ ]] || fail "RETENTION_VERSIONS must be a positive integer"
[[ "${OFFSITE_KEEP}" =~ ^[0-9]+$ ]] || fail "OFFSITE_RETENTION_VERSIONS must be an integer (0 = lifecycle rule)"
[[ "${MIN_BYTES}" =~ ^[0-9]+$ ]] || fail "MIN_DUMP_BYTES must be an integer"
[[ "${OFFSITE_PREFIX}" =~ ^[A-Za-z0-9._/-]*$ ]] || fail "OFFSITE_S3_PREFIX has unexpected characters"
[[ -r "${RECIPIENT}" ]] || fail "the recipient public key ${RECIPIENT} is missing"

WORK="$(mktemp -d -- "${TMP_ROOT%/}/majlisna-db-backup.XXXXXXXXXX")"
export GNUPGHOME="${WORK}/gnupg"
mkdir -m 700 -- "${GNUPGHOME}"
OUT="${WORK}/${NAME}"
STATS="${WORK}/plain.stats"
DUMP_ERR="${WORK}/pg_dump.err"
GPG_ERR="${WORK}/gpg.err"
START="$(date +%s)"

STAGE="recipient"
# Exactly one public key, and log its fingerprint: a swapped key shows in every summary.
mapfile -t KEYS < <(gpg --batch --with-colons --show-keys "${RECIPIENT}" 2>/dev/null | awk -F: '$1=="pub"{p=1} p && $1=="fpr"{print $10; p=0}')
[[ "${#KEYS[@]}" -eq 1 ]] || fail "the recipient file must hold exactly one public key"
if grep -q -- "PRIVATE KEY" "${RECIPIENT}"; then fail "the recipient file holds a private key"; fi
FPR="${KEYS[0]}"

STAGE="dump"
# pg_dump runs in one REPEATABLE READ, READ ONLY transaction (a consistent snapshot). The
# server closes sessions idle in a transaction after 60 s; a dump is never idle, but the
# backup session opts out so a slow consumer can never cut it.
export PGOPTIONS="-c idle_in_transaction_session_timeout=0"
export PGAPPNAME="majlisna-backup"
export PGCONNECT_TIMEOUT=15
if ! pg_dump --format=custom --lock-wait-timeout=120s --no-password \
    -h "$(setting PGHOST)" -p "${PGPORT_VALUE}" -U "$(setting PGUSER)" -d "$(setting PGDATABASE)" 2>"${DUMP_ERR}" \
  | python3 /usr/local/bin/passthru.py "${STATS}" \
  | gpg --batch --yes --no-tty --quiet --trust-model always --compress-algo none \
      --recipient-file "${RECIPIENT}" --encrypt --output "${OUT}" 2>"${GPG_ERR}"; then
  # Private job log only (Dagu, on the VPS): pg_dump/gpg errors never contain a password.
  sed -n '1,20s/^/pg_dump: /p' "${DUMP_ERR}" >&2
  sed -n '1,20s/^/gpg: /p' "${GPG_ERR}" >&2
  fail "pg_dump or encryption failed"
fi
read -r MAGIC PLAIN_BYTES <"${STATS}" || fail "no dump statistics"
[[ "${MAGIC}" == "PGDMP" ]] || fail "the dump is not a pg_dump custom-format archive"
[[ "${PLAIN_BYTES}" -ge "${MIN_BYTES}" ]] || fail "dump too small (${PLAIN_BYTES} bytes < ${MIN_BYTES})"
[[ "$(head -c 5 "${OUT}" | tr -d '\0')" != "PGDMP" ]] || fail "the output is not encrypted"
SIZE="$(stat -c%s "${OUT}")"

STAGE="upload"
# Idempotent (one HEAD when the bucket exists): a first run never depends on install order.
python3 /usr/local/bin/s3.py --target primary ensure-bucket || fail "the SeaweedFS bucket is unavailable"
python3 /usr/local/bin/s3.py --target primary put "${OUT}" "${NAME}" || fail "upload to SeaweedFS failed"
python3 /usr/local/bin/s3.py --target primary verify "${NAME}" "${SIZE}" || fail "the SeaweedFS object is missing or truncated"
WHERE="SeaweedFS"
if [[ -n "${OFFSITE_BUCKET}" ]]; then
  STAGE="offsite"
  OFFSITE_KEY="${OFFSITE_PREFIX}${NAME}"
  python3 /usr/local/bin/s3.py --target offsite put "${OUT}" "${OFFSITE_KEY}" \
    || fail "off-host upload failed (the SeaweedFS copy is stored)"
  python3 /usr/local/bin/s3.py --target offsite verify "${OFFSITE_KEY}" "${SIZE}" \
    || fail "the off-host object is missing or truncated (the SeaweedFS copy is stored)"
  if [[ "${OFFSITE_KEEP}" -gt 0 ]]; then
    python3 /usr/local/bin/s3.py --target offsite rotate "${OFFSITE_PREFIX}${PREFIX}" "${OFFSITE_KEEP}" >/dev/null \
      || fail "off-host rotation failed"
  fi
  WHERE="SeaweedFS + off-host"
fi

STAGE="rotate"
KEPT="$(python3 /usr/local/bin/s3.py --target primary rotate "${PREFIX}" "${KEEP}")" || fail "rotation failed"
# A clock that went backwards would name this object older than the kept ones.
python3 /usr/local/bin/s3.py --target primary verify "${NAME}" "${SIZE}" || fail "rotation removed the new object (clock skew?)"
DUR="$(($(date +%s) - START))"
HSIZE="$(numfmt --to=iec "${SIZE}")"
HPLAIN="$(numfmt --to=iec "${PLAIN_BYTES}")"
trap - ERR

STAGE="heartbeat"
# The heartbeat certifies dump + encryption + upload(s) + retention, not a restore test.
if [[ -n "${HEARTBEAT}" ]]; then
  if ! curl -fsS --max-time 15 -o /dev/null "${HEARTBEAT}" 2>/dev/null; then
    echo "backup: ${NAME} is stored, but the Kuma heartbeat could not be delivered" >&2
    notify "🟠 Majlisna backup \`${NAME}\` stored, but the Kuma heartbeat failed. Check Dagu and Kuma." >/dev/null 2>&1 || true
    exit 1
  fi
else
  echo "backup: BACKUP_HEARTBEAT_URL is unset, no freshness heartbeat sent" >&2
fi
if ! notify "🟢 **Majlisna PostgreSQL backup stored** — \`${NAME}\` (${HSIZE} encrypted, ${HPLAIN} dump, ${DUR}s) → ${WHERE}. ${KEPT} kept (limit ${KEEP} versions). Encrypted to ${FPR}. A restore drill is a separate check." >/dev/null; then
  echo "backup: ${NAME} is stored, but the Discord summary failed" >&2
  exit 1
fi
echo "OK ${NAME} ${SIZE} ${PLAIN_BYTES} ${DUR}s ${KEPT} ${FPR}"

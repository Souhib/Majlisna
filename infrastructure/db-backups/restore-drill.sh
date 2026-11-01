#!/usr/bin/env bash
# Restore drill for the Majlisna DB backup. Runs on the OPERATOR's machine (docker, gpg,
# python3, and ssh to the VPS through Tailscale). Read-only on production.
#
#   ./restore-drill.sh [--object KEY] [--strict]   owner mode: the newest backup, owner key
#   ./restore-drill.sh --temp-key [--strict]       first-drill mode: no owner key needed
#
# Owner mode downloads the newest "majlisna-" object (still encrypted) through the backup
# container, checks it is encrypted to the owner key and to it only, decrypts it HERE with
# the owner's private key (GNUPGHOME; pinentry asks for the passphrase, or pass
# GPG_DECRYPT_OPTS="--pinentry-mode loopback --passphrase-file FILE") and streams it into
# a throwaway postgres:16-alpine that has NO network and no published port. It then
# compares the exact row count of every table with the live database (read-only role,
# read-only transaction) and removes the container. The plaintext never touches a disk.
#
# --temp-key generates a throwaway key pair here, has the VPS make one drill backup
# encrypted to it (same backup.sh, a "drill-majlisna-" object, no heartbeat, no Discord,
# no off-host copy), restores that the same way, then deletes the drill object and the
# key pair. It also checks that the newest scheduled object is encrypted to the owner key.
#
# Exit 0 when the archive restores with no error and both sides have the same tables.
# Row deltas are printed (live writes since the dump); --strict makes any delta fatal.
#
# Env: BACKUP_EXEC     how to run a command in the backup container
#                      (default: ssh ubuntu@latabdhir-tools docker exec -i majlisna-backup-dagu)
#      EXPECTED_KEY_ID owner key id the backups must be encrypted to (2967A96B8DFE7D92)
#      DRILL_IMAGE     restore target (the production image, by digest)
#      GNUPGHOME, GPG_DECRYPT_OPTS   owner mode only
#      GNUPG_TMP_ROOT  where the throwaway gpg homes go (default /tmp, short on purpose)
set -euo pipefail
umask 077

HERE="$(cd "$(dirname "$0")" && pwd)"
read -r -a EXEC <<<"${BACKUP_EXEC:-ssh ubuntu@latabdhir-tools docker exec -i majlisna-backup-dagu}"
EXPECTED_KEY_ID="${EXPECTED_KEY_ID:-2967A96B8DFE7D92}"
DRILL_IMAGE="${DRILL_IMAGE:-postgres:16-alpine@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685}"
read -r -a DECRYPT_OPTS <<<"${GPG_DECRYPT_OPTS:-}"
MODE="owner"
STRICT="no"
OBJECT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --temp-key) MODE="temp-key" ;;
    --strict) STRICT="yes" ;;
    --object) OBJECT="${2:?--object needs a key}"; shift ;;
    -h | --help) awk 'NR > 1 && /^#/ {sub(/^# ?/, ""); print; next} NR > 1 {exit}' "$0"; exit 0 ;;
    *) echo "restore-drill: unknown argument $1" >&2; exit 2 ;;
  esac
  shift
done
[[ "${MODE}" == "owner" || -z "${OBJECT}" ]] || { echo "restore-drill: --object is for owner mode" >&2; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/majlisna-restore-drill.XXXXXX")"
# gpg-agent's socket lives in the gpg home: keep it short (macOS caps socket paths at
# 104 characters, and TMPDIR there is long).
GPG_ROOT="$(mktemp -d "${GNUPG_TMP_ROOT:-/tmp}/mdrill.XXXXXX")"
EMPTY_HOME="${GPG_ROOT}/empty"
TEMP_HOME="${GPG_ROOT}/temp"
mkdir -m 700 "${EMPTY_HOME}"
CONTAINER="majlisna-restore-drill-$$"
DRILL_OBJECT=""
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

remote() { "${EXEC[@]}" "$@"; }
die() { echo "restore-drill: $*" >&2; exit 1; }
cleanup() {
  local status=$?
  set +e
  docker rm -f -v "${CONTAINER}" >/dev/null 2>&1
  if [[ -n "${DRILL_OBJECT}" ]]; then
    if remote python3 /usr/local/bin/s3.py delete-drill "${DRILL_OBJECT}" </dev/null; then
      echo "drill object ${DRILL_OBJECT} deleted"
    else
      echo "WARNING: could not delete the drill object ${DRILL_OBJECT}" >&2
    fi
  fi
  for home in "${TEMP_HOME}" "${EMPTY_HOME}"; do
    [[ -d "${home}" ]] && gpgconf --homedir "${home}" --kill gpg-agent >/dev/null 2>&1
  done
  rm -rf -- "${WORK}" "${GPG_ROOT}"
  exit "${status}"
}
trap cleanup EXIT

# Key ids a file is encrypted to. An empty keyring: gpg lists the packets, cannot decrypt.
recipients() {
  { gpg --homedir "${EMPTY_HOME}" --batch --list-packets "$1" 2>/dev/null || true; } \
    | awk '/^:pubkey enc packet:/{print $NF}' | sort -u | tr '\n' ' ' | sed 's/ $//'
}
download() {
  remote python3 /usr/local/bin/s3.py --target primary get "$1" - </dev/null >"$2" || die "cannot download $1"
  [[ -s "$2" ]] || die "$1 is empty"
}
check_owner_encryption() {
  local key="$1" file="$2" ids
  ids="$(recipients "${file}")"
  [[ "${ids}" == "${EXPECTED_KEY_ID}" ]] || die "${key} is encrypted to [${ids}], expected ${EXPECTED_KEY_ID} only"
  echo "scheduled object ${key} ($(wc -c <"${file}" | tr -d ' ') bytes) is encrypted to ${EXPECTED_KEY_ID} only"
}
newest_scheduled() {
  local key
  key="$(remote python3 /usr/local/bin/s3.py --target primary latest majlisna </dev/null)" || die "no scheduled backup in the bucket"
  [[ "${key}" =~ ^majlisna-[0-9]{8}T[0-9]{6}Z\.dump\.gpg$ ]] || die "unexpected object name ${key}"
  printf '%s' "${key}"
}

if [[ "${MODE}" == "owner" ]]; then
  OBJECT="${OBJECT:-$(newest_scheduled)}"
  download "${OBJECT}" "${WORK}/backup.gpg"
  check_owner_encryption "${OBJECT}" "${WORK}/backup.gpg"
  # The ${x[@]+...} form keeps an empty array legal under set -u in macOS's bash 3.2.
  DECRYPT=(gpg ${DECRYPT_OPTS[@]+"${DECRYPT_OPTS[@]}"} --quiet --decrypt "${WORK}/backup.gpg")
else
  scheduled="$(newest_scheduled)"
  download "${scheduled}" "${WORK}/scheduled.gpg"
  check_owner_encryption "${scheduled}" "${WORK}/scheduled.gpg"
  rm -f -- "${WORK}/scheduled.gpg"
  mkdir -m 700 "${TEMP_HOME}"
  gpg --homedir "${TEMP_HOME}" --batch --passphrase '' --quick-gen-key \
    "Majlisna restore drill <drill@majlisna.invalid>" future-default default 1d 2>/dev/null
  gpg --homedir "${TEMP_HOME}" --batch --armor --export >"${WORK}/drill-public.asc"
  TEMP_KEY_ID="$(gpg --homedir "${TEMP_HOME}" --batch --with-colons --list-keys \
    | awk -F: '$1=="sub" && $12 ~ /e/ {print $5; exit}')"
  echo "temporary key ${TEMP_KEY_ID} generated (its private half stays on this machine, deleted at exit)"
  drill_out="$(remote /usr/local/bin/drill-backup.sh <"${WORK}/drill-public.asc")" || die "the drill backup failed on the VPS"
  OBJECT="$(awk '$1=="OK"{print $2}' <<<"${drill_out}")"
  [[ "${OBJECT}" =~ ^drill-majlisna-[0-9]{8}T[0-9]{6}Z\.dump\.gpg$ ]] || die "unexpected drill output"
  DRILL_OBJECT="${OBJECT}"
  download "${OBJECT}" "${WORK}/backup.gpg"
  ids="$(recipients "${WORK}/backup.gpg")"
  [[ "${ids}" == "${TEMP_KEY_ID}" ]] || die "the drill object is encrypted to [${ids}], expected ${TEMP_KEY_ID}"
  DECRYPT=(gpg --homedir "${TEMP_HOME}" --batch --quiet --decrypt "${WORK}/backup.gpg")
fi
ENCRYPTED_BYTES="$(wc -c <"${WORK}/backup.gpg" | tr -d ' ')"

echo "starting ${CONTAINER} (no network) from ${DRILL_IMAGE}"
docker run -d --rm --name "${CONTAINER}" --network none \
  -e POSTGRES_USER=majlisna -e POSTGRES_DB=majlisna_drill -e POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
  "${DRILL_IMAGE}" >/dev/null
ready="no"
for _ in $(seq 1 90); do
  if docker logs "${CONTAINER}" 2>&1 | grep -q "PostgreSQL init process complete" \
    && docker exec "${CONTAINER}" pg_isready -q -U majlisna >/dev/null 2>&1; then
    ready="yes"
    break
  fi
  sleep 1
done
[[ "${ready}" == "yes" ]] || die "the drill postgres did not start"

RESTORE_START="$(date +%s)"
if ! "${DECRYPT[@]}" 2>"${WORK}/gpg.err" \
  | python3 "${HERE}/dagu-image/passthru.py" "${WORK}/plain.stats" \
  | docker exec -i "${CONTAINER}" pg_restore -U majlisna -d majlisna_drill \
    --no-owner --no-privileges --exit-on-error --single-transaction 2>"${WORK}/restore.err"; then
  sed -n '1,20s/^/gpg: /p' "${WORK}/gpg.err" >&2
  sed -n '1,20s/^/pg_restore: /p' "${WORK}/restore.err" >&2
  die "decryption or restore failed"
fi
RESTORE_SECONDS="$(($(date +%s) - RESTORE_START))"
read -r MAGIC PLAIN_BYTES <"${WORK}/plain.stats"
[[ "${MAGIC}" == "PGDMP" ]] || die "the decrypted stream is not a pg_dump custom archive"

docker exec -i "${CONTAINER}" psql -X -q -At -F '|' -v ON_ERROR_STOP=1 -U majlisna -d majlisna_drill \
  <"${HERE}/dagu-image/table-counts.sql" >"${WORK}/restored.counts"
remote /usr/local/bin/live-table-counts.sh </dev/null >"${WORK}/live.counts" || die "cannot count the live tables"
SERVER_VERSION="$(docker exec "${CONTAINER}" postgres --version)"

echo
echo "restore drill ${STARTED} (${MODE} mode)"
echo "  object        ${OBJECT}"
echo "  encrypted     ${ENCRYPTED_BYTES} bytes, dump ${PLAIN_BYTES} bytes, restored in ${RESTORE_SECONDS}s"
echo "  target        ${SERVER_VERSION}, no network"
echo
python3 - "${WORK}/restored.counts" "${WORK}/live.counts" "${STRICT}" <<'PY'
import sys

def load(path):
    rows = {}
    for line in open(path).read().splitlines():
        if line:
            name, count = line.rsplit("|", 1)
            rows[name] = int(count)
    return rows

restored, live, strict = load(sys.argv[1]), load(sys.argv[2]), sys.argv[3] == "yes"
names = sorted(set(restored) | set(live))
width = max([len(n) for n in names] + [5])
print(f"  {'table':<{width}} {'backup':>9} {'live':>9} {'delta':>7}")
for name in names:
    b, l = restored.get(name), live.get(name)
    delta = "" if b is None or l is None else f"{l - b:+d}"
    print(f"  {name:<{width}} {'-' if b is None else b:>9} {'-' if l is None else l:>9} {delta:>7}")
missing = sorted(set(live) - set(restored))
extra = sorted(set(restored) - set(live))
drift = [n for n in names if n in restored and n in live and restored[n] != live[n]]
print(f"\n  {len(restored)} tables restored, {sum(restored.values())} rows (live: {len(live)} tables, {sum(live.values())} rows)")
if missing or extra:
    print(f"  FAIL: tables only live {missing}, only in the backup {extra}")
    raise SystemExit(1)
if drift:
    print(f"  {len(drift)} table(s) changed since the dump: {', '.join(drift)}")
    if strict:
        print("  FAIL: --strict and the counts differ")
        raise SystemExit(1)
print("  PASS")
PY

#!/usr/bin/env bash
# Local end-to-end test of the Majlisna DB backup (WP-BK). Never touches production and
# never uses the shared E2E stack: every container, network and key here is throwaway.
#
#   bash infrastructure/db-backups/test/test-backup-restore.sh
#
# What it proves, against a seeded postgres:16-alpine, a local SeaweedFS and a mock Kuma:
#   - install.sh: creates secrets.env (0600) and the read-only role without printing a
#     secret, builds and starts the scheduler, is idempotent;
#   - the scheduler really fires the DAG (a copy scheduled every minute);
#   - a manual run uploads one encrypted object (primary + off-host), sends one heartbeat;
#   - the object is not plaintext, is encrypted to the configured key only, and decrypts
#     to a pg_dump custom archive;
#   - restore-drill.sh (owner mode and --temp-key mode) restores it into a container with
#     no network and finds the exact seeded row counts;
#   - retention keeps the newest 30 "majlisna-" objects and nothing else is touched;
#   - every failure (wrong DB host, missing key, off-host or heartbeat failure) exits
#     non-zero and sends no heartbeat;
#   - the backup role cannot write, and no work file is left behind.
#
# Requires: docker (with compose v2), gpg, python3. Takes about 3 minutes.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
ID="mbk$$"
TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/majlisna-backup-test.XXXXXX")"
# gpg homes need a short path (gpg-agent socket, 104-character cap on macOS).
SHORT_TMP="$(mktemp -d /tmp/mbk.XXXXXX)"
INSTALL_DIR="${TEST_TMP}/install"
DBNET="${ID}-dbnet"
SWNET="${ID}-swnet"
DB="${ID}-db"
SW="${ID}-seaweedfs"
HB="${ID}-heartbeat"
BK="${ID}-backup"
BACKUP_IMAGE="majlisna-backup-dagu:test"
PG_IMAGE="postgres:16-alpine@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685"
SW_IMAGE="chrislusf/seaweedfs:4.47@sha256:ce9e796f1fe6f06968f4c04bdaf8f678dad9c8acdfef3d244133d71bfa6bf882"
SHELLCHECK_IMAGE="koalaman/shellcheck:v0.10.0"
S3_KEY="test-access-$(openssl rand -hex 6)"
S3_SECRET="test-secret-$(openssl rand -hex 16)"
PASSED=0
FAILED=0

ok() { echo "  ok    $1"; PASSED=$((PASSED + 1)); }
ko() { echo "  FAIL  $1"; FAILED=$((FAILED + 1)); }
check() {
  local description="$1"
  shift
  if "$@"; then ok "${description}"; else ko "${description}"; fi
}
check_fails() {
  local description="$1"
  shift
  if "$@"; then ko "${description}"; else ok "${description}"; fi
}
section() { printf '\n== %s\n' "$1"; }

compose_env() {
  env MAJLISNA_DB_CONTAINER="${DB}" MAJLISNA_DB_NETWORK="${DBNET}" \
    SEAWEEDFS_CONTAINER="${SW}" SEAWEEDFS_NETWORK="${SWNET}" \
    LATABDHIR_SECRETS="${TEST_TMP}/latabdhir-secrets.env" \
    BACKUP_CONTAINER="${BK}" BACKUP_IMAGE="${BACKUP_IMAGE}" \
    COMPOSE_PROJECT_NAME="${ID}" COMPOSE_FILE="docker-compose.yml:compose.test.yml" \
    TEST_RECIPIENT_FILE="${TEST_TMP}/test-owner.asc" MAX_DISK_PERCENT=101 "$@"
}

cleanup() {
  local status=$?
  set +e
  if [[ "${KEEP:-}" == "1" ]]; then
    echo "KEEP=1: left ${DB} ${SW} ${HB} ${BK}, networks ${DBNET} ${SWNET}, ${TEST_TMP}, ${SHORT_TMP}"
    exit "${status}"
  fi
  if [[ -d "${INSTALL_DIR}" ]]; then
    (cd "${INSTALL_DIR}" && compose_env docker compose down --remove-orphans >/dev/null 2>&1)
  fi
  docker rm -f "${DB}" "${SW}" "${HB}" "${BK}" >/dev/null 2>&1
  docker ps -aq --filter "name=majlisna-restore-drill" | xargs docker rm -f >/dev/null 2>&1
  docker network rm "${DBNET}" "${SWNET}" >/dev/null 2>&1
  [[ -d "${SHORT_TMP}/owner" ]] && gpgconf --homedir "${SHORT_TMP}/owner" --kill gpg-agent >/dev/null 2>&1
  rm -rf -- "${TEST_TMP}" "${SHORT_TMP}"
  exit "${status}"
}
trap cleanup EXIT
trap 'echo "harness: unexpected error at line ${LINENO}" >&2' ERR

wait_for_postgres() {
  local container="$1"
  for _ in $(seq 1 90); do
    if docker logs "${container}" 2>&1 | grep -q "PostgreSQL init process complete" \
      && docker exec "${container}" pg_isready -q -U majlisna >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "postgres ${container} did not become ready" >&2
  return 1
}

s3() { docker exec "${BK}" python3 /usr/local/bin/s3.py "$@"; }
count_prefix() { s3 --target "$1" count "$2"; }
heartbeats() { docker logs "${HB}" 2>/dev/null | grep -c "^HIT $1\$" || true; }
dagu_run() { docker exec "$@" "${BK}" dagu start majlisna-db-backup >"${TEST_TMP}/dagu.log" 2>&1; }
set_secret() {
  python3 - "${INSTALL_DIR}/secrets.env" "$1" "$2" <<'PY'
import sys
path, key, value = sys.argv[1:4]
lines = open(path).read().splitlines()
out, done = [], False
for line in lines:
    if line.split("=", 1)[0] == key:
        out.append(f"{key}={value}")
        done = True
    else:
        out.append(line)
if not done:
    out.append(f"{key}={value}")
open(path, "w").write("\n".join(out) + "\n")
PY
}

# ─────────────────────────────────────────────────────────────────────────────
section "static checks"
check "every script exists" test -f "${HERE}/install.sh" -a -f "${HERE}/restore-drill.sh" \
  -a -f "${HERE}/dagu-image/backup.sh" -a -f "${HERE}/dagu-image/drill-backup.sh" \
  -a -f "${HERE}/dagu-image/live-table-counts.sh" -a -f "${HERE}/dagu-image/start-scheduler.sh"
if [[ "${FAILED}" -gt 0 ]]; then
  echo "Backup scripts are missing; nothing else can be tested."
  exit 1
fi
check "shellcheck is clean on every script" docker run --rm -v "${HERE}:/mnt:ro" "${SHELLCHECK_IMAGE}" \
  /mnt/install.sh /mnt/restore-drill.sh /mnt/dagu-image/backup.sh /mnt/dagu-image/drill-backup.sh \
  /mnt/dagu-image/live-table-counts.sh /mnt/dagu-image/start-scheduler.sh /mnt/test/test-backup-restore.sh
check "python helpers compile" python3 -m py_compile "${HERE}/dagu-image/s3.py" \
  "${HERE}/dagu-image/notify.py" "${HERE}/dagu-image/passthru.py" "${HERE}/set-role-password.py" \
  "${HERE}/test/make_test_dags.py" "${HERE}/test/heartbeat_server.py"
check "the committed recipient is the owner's public key (9E6A…7D92), public only" sh -c "
  G=\$(mktemp -d) && gpg --homedir \"\$G\" --batch --with-colons --show-keys '${HERE}/dagu-image/backup-public-key.asc' 2>/dev/null \
  | grep -q '^fpr:::::::::9E6AC949274F12B4B803F4A52967A96B8DFE7D92:' && ! grep -q 'PRIVATE KEY' '${HERE}/dagu-image/backup-public-key.asc'; s=\$?; rm -rf \"\$G\"; exit \$s"
check "the DAG pins the recipient file and the object prefix" sh -c "
  grep -q 'BACKUP_RECIPIENT_FILE: /etc/majlisna/backup-public-key.asc' '${HERE}/dagu-config/dags/majlisna-db-backup.yaml' &&
  grep -q 'BACKUP_NAME_PREFIX: majlisna\$' '${HERE}/dagu-config/dags/majlisna-db-backup.yaml'"
check "every \${VAR} the DAG reads is defined in secrets.env.example" sh -c "
  for v in \$(grep -v '^ *#' '${HERE}/dagu-config/dags/majlisna-db-backup.yaml' | grep -o '\${[A-Z_]*}' | tr -d '\${}' | sort -u); do
    grep -q \"^\$v=\" '${HERE}/secrets.env.example' || { echo \"missing \$v\" >&2; exit 1; }
  done"
check "the backup never uses a passphrase or symmetric encryption" sh -c "
  ! grep -E -- '--symmetric|--passphrase' '${HERE}/dagu-image/backup.sh'"
check "no secret file is versioned" sh -c "
  ! test -e '${HERE}/secrets.env' && grep -qx 'secrets.env' '${HERE}/.gitignore'"

# ─────────────────────────────────────────────────────────────────────────────
section "prepare a throwaway stack"
docker network create "${DBNET}" >/dev/null
docker network create "${SWNET}" >/dev/null
docker run -d --name "${DB}" --network "${DBNET}" -e POSTGRES_USER=majlisna \
  -e POSTGRES_PASSWORD="$(openssl rand -hex 16)" -e POSTGRES_DB=majlisna "${PG_IMAGE}" >/dev/null
printf '{"identities":[{"name":"backup","credentials":[{"accessKey":"%s","secretKey":"%s"}],"actions":["Admin","Read","Write","List","Tagging"]}]}\n' \
  "${S3_KEY}" "${S3_SECRET}" >"${TEST_TMP}/s3.json"
chmod 644 "${TEST_TMP}/s3.json"
docker run -d --name "${SW}" --network "${SWNET}" -v "${TEST_TMP}/s3.json:/conf/s3.json:ro" "${SW_IMAGE}" \
  server -dir=/data "-ip=${SW}" -ip.bind=0.0.0.0 -s3 -s3.config=/conf/s3.json >/dev/null
# Test scaffolding only: the dependencies sit on BOTH test networks. Docker engines older
# than 25 (API < 1.44, e.g. Docker Desktop 24 + compose 2.19) sometimes attach a compose
# service to only one of its two networks (2 runs in 6 in a bare experiment); the VPS runs
# 29.x, which creates a container with all its networks at once. This keeps the test
# deterministic on such an engine; the static check below still proves the compose file
# declares exactly the two networks, and install.sh's checks prove the reachability.
docker network connect "${SWNET}" "${DB}"
docker network connect "${DBNET}" "${SW}"
# The LaTabdhir secrets file install.sh copies the SeaweedFS keys from (other lines must be ignored).
cat >"${TEST_TMP}/latabdhir-secrets.env" <<EOF
PGHOST=not-majlisna.invalid
PGPASSWORD=latabdhir-password-must-not-be-copied
S3_ENDPOINT=http://latabdhir-backup-seaweedfs:8333
S3_BUCKET=latabdhir-db-backups
S3_ACCESS_KEY=${S3_KEY}
S3_SECRET_KEY=${S3_SECRET}
EOF
chmod 600 "${TEST_TMP}/latabdhir-secrets.env"
wait_for_postgres "${DB}"
docker exec -i "${DB}" psql -X -q -v ON_ERROR_STOP=1 -U majlisna -d majlisna >/dev/null <<'SQL'
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE TABLE "user" (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), username text NOT NULL, bio text,
                     created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE game (id serial PRIMARY KEY, user_id uuid REFERENCES "user"(id), live_state jsonb);
CREATE TABLE notebook_entry (id bigserial PRIMARY KEY, word text NOT NULL, game_id int REFERENCES game(id));
CREATE TABLE empty_table (id int);
INSERT INTO "user" (username, bio) SELECT 'user' || g, repeat(md5(g::text), 4) FROM generate_series(1, 600) g;
INSERT INTO game (user_id, live_state)
  SELECT (SELECT id FROM "user" ORDER BY username LIMIT 1), jsonb_build_object('round', g, 'words', md5(g::text))
  FROM generate_series(1, 250) g;
INSERT INTO notebook_entry (word, game_id) SELECT 'word' || g, 1 + g % 250 FROM generate_series(1, 1234) g;
SQL
ok "seeded user=600 game=250 notebook_entry=1234 empty_table=0"

GNUPG_OWNER="${SHORT_TMP}/owner"
mkdir -m 700 "${GNUPG_OWNER}"
gpg --homedir "${GNUPG_OWNER}" --batch --passphrase '' --quick-gen-key \
  'Majlisna backup test owner <owner@test.invalid>' rsa3072 cert,sign,encr never 2>/dev/null
gpg --homedir "${GNUPG_OWNER}" --batch --armor --export >"${TEST_TMP}/test-owner.asc"
KEYID="$(gpg --homedir "${GNUPG_OWNER}" --batch --with-colons --list-keys | awk -F: '$1=="pub"{print $5; exit}')"
ok "test owner key pair ${KEYID} (stands in for the real owner key)"

# The install copy is what the VPS gets: the repo directory without its tests.
mkdir -p "${INSTALL_DIR}"
(cd "${HERE}" && tar --exclude=./test -cf - .) | (cd "${INSTALL_DIR}" && tar -xf -)
cat >"${INSTALL_DIR}/compose.test.yml" <<'YAML'
services:
  dagu:
    image: ${BACKUP_IMAGE}
    volumes:
      - ${TEST_RECIPIENT_FILE}:/etc/majlisna/backup-public-key.asc:ro
YAML
# The real DAG made manual-only, plus an every-minute and a catch-up variant (see the helper).
python3 "${HERE}/test/make_test_dags.py" "${HERE}/dagu-config/dags/majlisna-db-backup.yaml" \
  "${INSTALL_DIR}/dagu-config/dags"

# ─────────────────────────────────────────────────────────────────────────────
section "install.sh"
if (cd "${INSTALL_DIR}" && compose_env ./install.sh) >"${TEST_TMP}/install.log" 2>&1; then
  ok "install.sh succeeds on a fresh host"
else
  ko "install.sh succeeds on a fresh host"
  sed 's/^/    | /' "${TEST_TMP}/install.log"
  exit 1
fi
check "secrets.env was created with mode 600" sh -c "
  [ \"\$(python3 -c 'import os,sys;print(oct(os.stat(sys.argv[1]).st_mode & 0o777))' '${INSTALL_DIR}/secrets.env')\" = 0o600 ]"
PGPASS_VALUE="$(grep '^PGPASSWORD=' "${INSTALL_DIR}/secrets.env" | cut -d= -f2-)"
check "a strong backup-role password was generated" test "${#PGPASS_VALUE}" -ge 32
check "the LaTabdhir DB password was not copied" sh -c "! grep -q latabdhir-password-must-not-be-copied '${INSTALL_DIR}/secrets.env'"
check "SeaweedFS keys were copied from the LaTabdhir secrets" grep -q "^S3_SECRET_KEY=${S3_SECRET}\$" "${INSTALL_DIR}/secrets.env"
check "install output contains no secret" sh -c "
  ! grep -q -e '${PGPASS_VALUE}' -e '${S3_SECRET}' '${TEST_TMP}/install.log'"
check "the role is read-only (no superuser/createdb/createrole/replication/bypassrls)" sh -c "
  [ \"\$(docker exec '${DB}' psql -X -At -U majlisna -d majlisna -c \"select concat(rolcanlogin::int, rolsuper::int, rolcreatedb::int, rolcreaterole::int, rolreplication::int, rolbypassrls::int, rolconnlimit) from pg_roles where rolname='majlisna_backup'\")\" = 1000002 ]"
check "the role is a member of pg_read_all_data and nothing else" sh -c "
  [ \"\$(docker exec '${DB}' psql -X -At -U majlisna -d majlisna -c \"select string_agg(b.rolname, ',') from pg_auth_members m join pg_roles b on b.oid = m.roleid join pg_roles r on r.oid = m.member where r.rolname = 'majlisna_backup'\")\" = pg_read_all_data ]"
check "the stored password is a SCRAM verifier" sh -c "
  docker exec '${DB}' psql -X -At -U majlisna -d majlisna -c \"select starts_with(rolpassword, 'SCRAM-SHA-256' || chr(36) || '4096:') from pg_authid where rolname='majlisna_backup'\" | grep -qx t"
check "the service declares exactly the two external networks, production names by default" sh -c "
  [ \"\$(cd '${INSTALL_DIR}' && env -u MAJLISNA_DB_NETWORK -u SEAWEEDFS_NETWORK docker compose -f docker-compose.yml config --format json \
    | python3 -c 'import json,sys; c=json.load(sys.stdin); print(sorted(c[\"services\"][\"dagu\"][\"networks\"]), sorted((n[\"name\"], bool(n.get(\"external\"))) for n in c[\"networks\"].values()))')\" \
  = \"['majlisna-db', 'seaweedfs'] [('compose-index-cross-platform-capacitor-27v2m5_internal', True), ('latabdhir-backups_internal', True)]\" ]"
check "the test resolves them to the test networks" sh -c "
  [ \"\$(cd '${INSTALL_DIR}' && MAJLISNA_DB_NETWORK='${DBNET}' SEAWEEDFS_NETWORK='${SWNET}' docker compose -f docker-compose.yml config --format json \
    | python3 -c 'import json,sys; c=json.load(sys.stdin); print(sorted(n[\"name\"] for n in c[\"networks\"].values()))')\" = \"['${DBNET}', '${SWNET}']\" ]"
check "the scheduler started only once majlisna-db and SeaweedFS answered" sh -c "
  docker logs '${BK}' 2>&1 | grep -q 'start-scheduler: .* reachable after' && ! docker logs '${BK}' 2>&1 | grep -q 'start-scheduler: WARNING'"
check "the backup container runs as uid 1001 with no published port" sh -c "
  [ \"\$(docker exec '${BK}' id -u)\" = 1001 ] && [ -z \"\$(docker port '${BK}')\" ]"
check "the real DAG file (with its schedule) validates" sh -c "
  docker exec -i '${BK}' sh -c 'cat > /tmp/real-dag.yaml && dagu validate /tmp/real-dag.yaml' \
  < '${HERE}/dagu-config/dags/majlisna-db-backup.yaml' >/dev/null 2>&1"
check "the bucket majlisna-db-backups exists" sh -c "docker exec '${BK}' python3 /usr/local/bin/s3.py count majlisna >/dev/null"

section "the backup role cannot write"
check_fails "CREATE TABLE is refused, even with read-only turned off" docker exec "${BK}" psql -X -q \
  -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only = off" -c "CREATE TABLE public.probe (id int)"
check_fails "INSERT is refused, even with read-only turned off" docker exec "${BK}" psql -X -q \
  -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only = off" -c "INSERT INTO empty_table VALUES (1)"
check "SELECT works" sh -c "[ \"\$(docker exec '${BK}' psql -X -At -c 'SELECT count(*) FROM \"user\"')\" = 600 ]"

section "a scheduler that starts after a missed run replays it once (catch-up)"
caught=no
for _ in $(seq 1 30); do
  if [[ "$(count_prefix primary catchtest)" -ge 1 ]]; then
    caught=yes
    break
  fi
  sleep 2
done
check "the missed run was replayed" test "${caught}" = yes

# ─────────────────────────────────────────────────────────────────────────────
section "heartbeat and off-host target, then install.sh again (idempotent)"
docker run -d --name "${HB}" --network "${DBNET}" -v "${HERE}/test/heartbeat_server.py:/srv/hb.py:ro" \
  --entrypoint python3 "${BACKUP_IMAGE}" /srv/hb.py >/dev/null
docker network connect "${SWNET}" "${HB}"
set_secret BACKUP_HEARTBEAT_URL "http://${HB}:8080/api/push/real?status=up&msg=OK"
set_secret BACKUP_HEARTBEAT_URL_SCHED "http://${HB}:8080/api/push/sched?status=up&msg=OK"
set_secret OFFSITE_S3_ENDPOINT "http://${SW}:8333"
set_secret OFFSITE_S3_BUCKET offsite-test
set_secret OFFSITE_S3_ACCESS_KEY "${S3_KEY}"
set_secret OFFSITE_S3_SECRET_KEY "${S3_SECRET}"
set_secret OFFSITE_S3_ADDRESSING path
set_secret OFFSITE_S3_PREFIX "majlisna/"
set_secret OFFSITE_S3_REGION us-east-1
# The off-host bucket exists before the container gets the off-host settings.
docker exec -e S3_BUCKET=offsite-test "${BK}" python3 /usr/local/bin/s3.py ensure-bucket
if (cd "${INSTALL_DIR}" && compose_env ./install.sh) >"${TEST_TMP}/install2.log" 2>&1; then
  ok "install.sh is idempotent (second run succeeds)"
else
  ko "install.sh is idempotent (second run succeeds)"
  sed 's/^/    | /' "${TEST_TMP}/install2.log"
fi
check "the second run kept the generated password" grep -q "^PGPASSWORD=${PGPASS_VALUE}\$" "${INSTALL_DIR}/secrets.env"
check "ensure-bucket is idempotent" s3 --target offsite ensure-bucket
check "the restart did not replay the caught-up run again" test "$(count_prefix primary catchtest)" = 1
rm -f "${INSTALL_DIR}/dagu-config/dags/catchtest.yaml"

# ─────────────────────────────────────────────────────────────────────────────
section "the scheduler fires the DAG"
scheduled=no
for _ in $(seq 1 100); do
  if [[ "$(count_prefix primary schedtest)" -ge 1 && "$(heartbeats /api/push/sched)" -ge 1 ]]; then
    scheduled=yes
    break
  fi
  sleep 2
done
check "a scheduled run uploaded an object and sent its heartbeat" test "${scheduled}" = yes
rm -f "${INSTALL_DIR}/dagu-config/dags/schedtest.yaml"

# ─────────────────────────────────────────────────────────────────────────────
section "a manual run"
check "dagu start majlisna-db-backup succeeds" dagu_run
check "one majlisna- object in the primary bucket" test "$(count_prefix primary majlisna)" = 1
check "one copy in the off-host bucket, under its prefix" test "$(count_prefix offsite majlisna/majlisna)" = 1
check "exactly one heartbeat" test "$(heartbeats /api/push/real)" = 1
FIRST="$(s3 --target primary latest majlisna)"
s3 --target primary get "${FIRST}" - >"${TEST_TMP}/first.gpg"
check "the object is not a plaintext dump" sh -c "[ \"\$(head -c 5 '${TEST_TMP}/first.gpg')\" != PGDMP ]"
check "the object is encrypted to the configured key, and to it only" sh -c "
  G=\$(mktemp -d); ids=\$(gpg --homedir \"\$G\" --batch --list-packets '${TEST_TMP}/first.gpg' 2>/dev/null | awk '/:pubkey enc packet:/{print \$NF}'); rm -rf \"\$G\"; [ \"\$ids\" = '${KEYID}' ]"
check "it decrypts to a pg_dump custom archive" sh -c "
  [ \"\$(gpg --homedir '${GNUPG_OWNER}' --batch --quiet --decrypt '${TEST_TMP}/first.gpg' 2>/dev/null | head -c 5)\" = PGDMP ]"
check "the run left no work directory in the container" sh -c "
  ! docker exec '${BK}' sh -c 'ls -A /tmp' | grep -q majlisna-db-backup"

# ─────────────────────────────────────────────────────────────────────────────
section "restore-drill.sh, owner mode (what the owner runs with the real key)"
if env BACKUP_EXEC="docker exec -i ${BK}" GNUPGHOME="${GNUPG_OWNER}" EXPECTED_KEY_ID="${KEYID}" \
  DRILL_IMAGE="${PG_IMAGE}" TMPDIR="${TEST_TMP}" GNUPG_TMP_ROOT="${SHORT_TMP}" "${HERE}/restore-drill.sh" --strict >"${TEST_TMP}/drill.log" 2>&1; then
  ok "the drill restores the newest object with exact counts"
else
  ko "the drill restores the newest object with exact counts"
  sed 's/^/    | /' "${TEST_TMP}/drill.log"
fi
if [[ "${VERBOSE:-}" == "1" ]]; then sed 's/^/    | /' "${TEST_TMP}/drill.log"; fi
check "the drill saw the seeded counts" sh -c "
  grep -Eq '^ *user +600 +600' '${TEST_TMP}/drill.log' && grep -Eq '^ *notebook_entry +1234 +1234' '${TEST_TMP}/drill.log' &&
  grep -Eq '^ *empty_table +0 +0' '${TEST_TMP}/drill.log'"
check "no drill container is left" test -z "$(docker ps -aq --filter name=majlisna-restore-drill)"
check "no drill work directory is left" sh -c "
  ! ls -A '${TEST_TMP}' | grep -q majlisna-restore-drill && ! ls -A '${SHORT_TMP}' | grep -q mdrill"

# ─────────────────────────────────────────────────────────────────────────────
section "retention keeps the newest 30 majlisna- objects, nothing else"
docker exec "${BK}" sh -c '
  head -c 2048 /dev/urandom > /tmp/fake.bin
  for d in $(seq -w 1 32); do python3 /usr/local/bin/s3.py --target primary put /tmp/fake.bin "majlisna-202501${d}T000000Z.dump.gpg"; done
  python3 /usr/local/bin/s3.py --target primary put /tmp/fake.bin other-project-20250101T000000Z.dump.gpg
  python3 /usr/local/bin/s3.py --target primary put /tmp/fake.bin drill-majlisna-20250101T000000Z.dump.gpg
  rm -f /tmp/fake.bin' >/dev/null
check "33 majlisna- objects before the run (32 fake + 1 real; scheduled ones are schedtest-)" \
  test "$(count_prefix primary majlisna)" = 33
check "the run succeeds" dagu_run
check "30 majlisna- objects remain" test "$(count_prefix primary majlisna)" = 30
check "the 4 oldest were deleted, the 5th oldest kept" sh -c "
  list=\$(docker exec '${BK}' python3 /usr/local/bin/s3.py --target primary list majlisna)
  ! echo \"\$list\" | grep -q -e majlisna-20250101T -e majlisna-20250102T -e majlisna-20250103T -e majlisna-20250104T &&
  echo \"\$list\" | grep -q majlisna-20250105T"
check "the first real object is still there" sh -c "
  docker exec '${BK}' python3 /usr/local/bin/s3.py --target primary list majlisna | grep -q '${FIRST}'"
check "other prefixes are untouched" sh -c "
  [ \"\$(docker exec '${BK}' python3 /usr/local/bin/s3.py --target primary count other-project)\" = 1 ] &&
  [ \"\$(docker exec '${BK}' python3 /usr/local/bin/s3.py --target primary count drill-majlisna)\" = 1 ]"
check "the off-host copy is not rotated by the script (lifecycle rule's job)" \
  test "$(count_prefix offsite majlisna/majlisna)" = 2
check "two heartbeats so far" test "$(heartbeats /api/push/real)" = 2

# ─────────────────────────────────────────────────────────────────────────────
section "failures exit non-zero and send no heartbeat"
NEWEST="$(s3 --target primary latest majlisna)"
check_fails "wrong DB host fails" dagu_run -e PGHOST=no-such-db.invalid
check "  ...no new object" test "$(s3 --target primary latest majlisna)" = "${NEWEST}"
check "  ...no heartbeat" test "$(heartbeats /api/push/real)" = 2
check_fails "a missing recipient key fails" docker exec -e BACKUP_RECIPIENT_FILE=/nonexistent.asc "${BK}" /usr/local/bin/backup.sh
check "  ...no new object" test "$(s3 --target primary latest majlisna)" = "${NEWEST}"
# shellcheck disable=SC2016 # a literal, unresolved Dagu reference on purpose
check_fails "an unresolved \${VAR} for a required setting fails" docker exec -e 'PGHOST=${PGHOST}' "${BK}" /usr/local/bin/backup.sh
check_fails "an off-host failure fails" dagu_run -e OFFSITE_S3_ENDPOINT=http://no-such-s3.invalid:9
check "  ...no heartbeat" test "$(heartbeats /api/push/real)" = 2
check_fails "a heartbeat that cannot be delivered fails the job" dagu_run -e "BACKUP_HEARTBEAT_URL=http://${HB}:8080/fail/x"
check "  ...no successful heartbeat" test "$(heartbeats /api/push/real)" = 2
check "no work directory is left after the failures" sh -c "
  ! docker exec '${BK}' sh -c 'ls -A /tmp' | grep -q majlisna-db-backup"

# ─────────────────────────────────────────────────────────────────────────────
section "restore-drill.sh --temp-key (the first-drill mode, no owner key needed)"
if env BACKUP_EXEC="docker exec -i ${BK}" EXPECTED_KEY_ID="${KEYID}" DRILL_IMAGE="${PG_IMAGE}" \
  TMPDIR="${TEST_TMP}" GNUPG_TMP_ROOT="${SHORT_TMP}" "${HERE}/restore-drill.sh" --temp-key --strict >"${TEST_TMP}/drill2.log" 2>&1; then
  ok "the temp-key drill restores with exact counts"
else
  ko "the temp-key drill restores with exact counts"
  sed 's/^/    | /' "${TEST_TMP}/drill2.log"
fi
check "it checked that the scheduled object is encrypted to the owner key" grep -q "encrypted to ${KEYID} only" "${TEST_TMP}/drill2.log"
check "it removed its drill object (the planted one stays)" test "$(count_prefix primary drill-majlisna)" = 1
check "it sent no heartbeat" test "$(heartbeats /api/push/real)" = 2
check "no drill container is left" test -z "$(docker ps -aq --filter name=majlisna-restore-drill)"
check "no drill work directory or temp key is left" sh -c "
  ! ls -A '${TEST_TMP}' | grep -q majlisna-restore-drill && ! ls -A '${SHORT_TMP}' | grep -q mdrill"

printf '\n%d passed, %d failed\n' "${PASSED}" "${FAILED}"
[[ "${FAILED}" -eq 0 ]]

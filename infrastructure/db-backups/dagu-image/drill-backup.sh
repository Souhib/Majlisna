#!/usr/bin/env bash
# One restore-drill backup, encrypted to a THROWAWAY public key read on stdin.
#
# Used only by restore-drill.sh --temp-key, which keeps the matching private key on the
# operator's machine and deletes it afterwards. It is the very same backup.sh with four
# things changed for this one run:
#   - the recipient is the temporary key (never the owner's, which nobody here can read);
#   - the object is named "drill-majlisna-…", so the scheduled rotation ("majlisna-")
#     never counts or deletes it, and restore-drill.sh deletes it when done;
#   - no heartbeat, no Discord, no off-host copy: a drill is not a backup.
set -euo pipefail
umask 077
KEY_FILE="$(mktemp -- "${TMPDIR:-/tmp}/majlisna-drill-key.XXXXXXXXXX")"
trap 'rm -f -- "${KEY_FILE}"' EXIT
head -c 65536 >"${KEY_FILE}"
grep -q -- "-----BEGIN PGP PUBLIC KEY BLOCK-----" "${KEY_FILE}" || { echo "drill: stdin is not an armored public key" >&2; exit 2; }
if grep -q -- "PRIVATE KEY" "${KEY_FILE}"; then echo "drill: refusing a private key" >&2; exit 2; fi
BACKUP_RECIPIENT_FILE="${KEY_FILE}" BACKUP_NAME_PREFIX="drill-majlisna" RETENTION_VERSIONS=5 \
  BACKUP_HEARTBEAT_URL="" DISCORD_WEBHOOK="" OFFSITE_S3_BUCKET="" \
  /usr/local/bin/backup.sh

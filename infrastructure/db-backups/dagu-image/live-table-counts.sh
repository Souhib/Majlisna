#!/usr/bin/env bash
# Exact row counts of the live majlisna-db, for the restore drill. Runs inside the backup
# container with its env (PGHOST, PGUSER=majlisna_backup, ...): a read-only role in a
# read-only transaction, so this can only read.
set -euo pipefail
export PGOPTIONS="-c default_transaction_read_only=on"
export PGAPPNAME="majlisna-restore-drill"
exec psql -X -q -At -F '|' -v ON_ERROR_STOP=1 -f /etc/majlisna/table-counts.sql

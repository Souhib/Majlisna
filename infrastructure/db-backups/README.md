# Majlisna DB backups (Oracle VPS)

A daily, encrypted `pg_dump` of `majlisna-db`, sent to the SeaweedFS S3 on the VPS, with an
optional off-host S3 copy. A Dagu scheduler in its own container (`majlisna-backup-dagu`)
runs the job at 03:45 UTC.

This directory is the versioned config, with no secrets. On the VPS it is copied to
`/home/ubuntu/majlisna-backups/`, without `test/`.

**Read [`docs/operations/backups.md`](../../docs/operations/backups.md)** for the layout,
install, restore, drill, alerts and limits.

```bash
# install or update on the VPS (idempotent), then run once
rsync -a --exclude test --exclude secrets.env --exclude __pycache__ --exclude 'dagu-config/data' --exclude 'dagu-config/logs' \
  --exclude 'dagu-config/suspend' infrastructure/db-backups/ latabdhir-tools:/home/ubuntu/majlisna-backups/
ssh latabdhir-tools 'cd /home/ubuntu/majlisna-backups && ./install.sh --run'

# restore drill, from the operator machine
infrastructure/db-backups/restore-drill.sh            # owner key
infrastructure/db-backups/restore-drill.sh --temp-key # no owner key needed

# local end-to-end test (throwaway containers only)
bash infrastructure/db-backups/test/test-backup-restore.sh
```

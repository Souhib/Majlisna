# Database backups

The Majlisna production PostgreSQL (`majlisna-db`) gets a daily, encrypted `pg_dump`.
The dump goes to the SeaweedFS S3 store that already holds LaTabdhir's backups on the same
Oracle VPS. A second, off-host copy is optional.

The config lives in [`infrastructure/db-backups/`](../../infrastructure/db-backups/) and
holds no secret. It is modelled on LaTabdhir's VPS layer (Dagu + SeaweedFS, see
`LaTabdhir/infrastructure/CLAUDE.md` → "Database Backups"), with the differences listed
under [Design choices](#design-choices).

## Status (2026-10-31)

| Step | State |
|---|---|
| Config, scripts and local end-to-end test (`test/test-backup-restore.sh`) | done: 71/71 checks, 3 consecutive clean runs |
| Install on the VPS (`./install.sh --run`) | **pending: the lead runs it** (see [Install](#install-or-update)) |
| First backup in the bucket | **pending**, with the install |
| First restore drill (`./restore-drill.sh --temp-key`) | **pending**, right after the install |
| Kuma push monitor | **owner step** |
| Off-host copy (AWS S3) | **owner step** |

Until the first two pending rows are done, **production has no backup**. WP-01's seed
purge and any destructive operation must wait for them.

The first-time sequence for the lead (about 5 minutes):

```bash
# 1. install, first backup, and proof that the object is in the bucket (printed at the end)
rsync -a --exclude test --exclude secrets.env --exclude __pycache__ infrastructure/db-backups/ ubuntu@latabdhir-tools:/home/ubuntu/majlisna-backups/
ssh ubuntu@latabdhir-tools 'cd /home/ubuntu/majlisna-backups && ./install.sh --run'
# 2. first drill, from the repo on the operator machine (no owner key needed)
infrastructure/db-backups/restore-drill.sh --temp-key
# 3. record the drill's report in the "Drill log" table below
```

## What is backed up

- The whole `majlisna` database: every table, sequence, index, constraint and extension
  (`pg_stat_statements`), as one consistent snapshot (`pg_dump` runs in a single
  `REPEATABLE READ, READ ONLY` transaction).
- Not backed up:
  - cluster-level roles and passwords (the image recreates `POSTGRES_USER`; `install.sh`
    recreates `majlisna_backup`);
  - Redis (ephemeral by design);
  - the Dokploy env and secrets;
  - the monitoring stack;
  - the orphan volume `majlisna_postgres_data` (April 2026, unused, the owner's decision).

## Layout

```
                     compose-index-cross-platform-capacitor-27v2m5_internal
 majlisna-db:5432  ◄──────────────────────────────┐   (Majlisna's own network)
 monitoring-uptime-kuma:3001 ◄── heartbeat ────────┤
                                                   │
                                     majlisna-backup-dagu
                                     (Dagu scheduler, uid 1001,
                                      no UI, no published port)
                                                   │
 latabdhir-backup-seaweedfs:8333 ◄─────────────────┘   latabdhir-backups_internal
   bucket majlisna-db-backups                           (LaTabdhir's backup network)
   (bucket latabdhir-db-backups untouched)
```

- **Project on the VPS:** `/home/ubuntu/majlisna-backups/` holds a copy of
  `infrastructure/db-backups/` without `test/`, plus `secrets.env` (chmod 600) and the
  Dagu state under `dagu-config/`.
- **Container:** `majlisna-backup-dagu`, built from the same pinned Dagu image as
  LaTabdhir's, plus `postgresql-client-16`, `gnupg` and `python3-boto3`.
- **Networks:** both are declared as external networks in `docker-compose.yml`, never
  attached with `docker network connect` (a manual attachment is lost when a container is
  recreated). The Majlisna network name comes from the Dokploy compose project ID: if
  Dokploy ever renames the project, `install.sh` refuses to run and says so.
- **Role:** `majlisna_backup`, from `backup-role.sql`:
  - `LOGIN`, member of `pg_read_all_data` only;
  - no superuser, createdb, createrole, replication or bypassrls;
  - `CONNECTION LIMIT 2` and `default_transaction_read_only = on`;
  - owns nothing; its password is stored as a SCRAM verifier.

| File | Role |
|---|---|
| `docker-compose.yml` | the one service, its two external networks, resource limits |
| `dagu-image/Dockerfile` | the image (pinned base, PostgreSQL 16 client) |
| `dagu-image/start-scheduler.sh` | container command: waits (bounded) for the DB and SeaweedFS, then `dagu scheduler` |
| `dagu-image/backup.sh` | the job: dump, check, encrypt, upload, verify, rotate, heartbeat |
| `dagu-image/passthru.py` | checks the `PGDMP` magic and counts bytes between pipes, in memory |
| `dagu-image/s3.py` | boto3 helper for both targets (put, verify, rotate, list, get…) |
| `dagu-image/notify.py` | optional Discord summary |
| `dagu-image/drill-backup.sh` | one drill backup to a throwaway key (used by `restore-drill.sh --temp-key`) |
| `dagu-image/live-table-counts.sh`, `table-counts.sql` | exact per-table row counts, read-only |
| `dagu-image/backup-public-key.asc` | the owner's PUBLIC key (`9E6AC949274F12B4B803F4A52967A96B8DFE7D92`) |
| `dagu-config/dags/majlisna-db-backup.yaml` | the DAG: schedule, catch-up, the env it passes |
| `backup-role.sql`, `set-role-password.py` | the read-only role and its password |
| `install.sh` | install or update on the VPS (idempotent) |
| `restore-drill.sh` | the restore drill, run on the operator's machine |
| `secrets.env.example` | the env template; the real `secrets.env` exists only on the VPS |
| `test/test-backup-restore.sh` | local end-to-end test (throwaway containers only) |

## The job

`majlisna-db-backup`, daily at **03:45 UTC**:

- 45 minutes before LaTabdhir's 04:30 job on the same SeaweedFS;
- a quiet hour for Majlisna (04:45 in Paris in winter, 06:45 in Riyadh);
- the run takes seconds.

The steps:

1. `pg_dump --format=custom` as `majlisna_backup`, straight to `majlisna-db:5432` (not
   through PgBouncer).
2. Through `passthru.py`, which checks that the stream starts with `PGDMP` and is at least
   `MIN_DUMP_BYTES` long, without writing it anywhere.
3. `gpg --encrypt --recipient-file /etc/majlisna/backup-public-key.asc`. The recipient
   path is pinned in the DAG, not read from `secrets.env`, and the success summary prints
   its fingerprint.
4. The only file the job writes is the encrypted object, in a private `mktemp` directory
   that is removed on exit, on failure and on a signal. **No plaintext dump touches the
   disk.**
5. Upload to `s3://majlisna-db-backups/majlisna-<UTC stamp>.dump.gpg`, then check its size
   (HEAD).
6. If configured: the same object off-host, checked the same way.
7. Rotation: keep the newest `RETENTION_VERSIONS` (30) `majlisna-` objects. Other prefixes
   are never touched. After rotation the job checks that the new object is still there.
8. The Kuma push heartbeat, then the Discord summary (optional).

**Any failure exits non-zero and sends no heartbeat.** If a summary is configured, a
failure also posts a 🔴 Discord line.

- **Catch-up:** `catchup_window: 20h`. A scheduler that was down at 03:45 (for example a
  host reboot) replays the missed run once when it starts. It does not replay it again
  after a restart (tested). The first install between 03:45 and 23:45 UTC therefore takes
  a backup at once.
- **Startup gate:** the container waits up to 300 s for `majlisna-db` and SeaweedFS to
  accept connections before it starts the scheduler, and logs that it is waiting. After a
  reboot the catch-up run must not race the database's own start. Past the deadline it
  starts anyway, so an outage still shows up as a failed run.
- **Dagu env:** Dagu passes a step only the variables listed in the DAG, and leaves
  `${NAME}` as a literal when `NAME` is missing. So every name in `secrets.env.example`
  must stay in `secrets.env`. `install.sh` adds the ones a newer template introduces, and
  `backup.sh` treats a literal `${NAME}` as unset.

## Encryption and keys

- The dumps are encrypted to the owner's backup key, `9E6AC949274F12B4B803F4A52967A96B8DFE7D92`
  ("La Tabdhir DB backups"). It is the **same** key as LaTabdhir's backups: RSA 4096, no
  expiry.
- The **private key and its passphrase are not on the VPS.** They sit on the owner's
  machine and in the password manager. Losing them makes every Majlisna backup
  undecryptable.
- The VPS holds only the public half, so a compromised VPS cannot read the dumps it
  stores.
- Restoring therefore happens on the owner's machine, or anywhere the private key is
  brought for that moment and removed afterwards.

## Retention

- **SeaweedFS:** the newest 30 `majlisna-` objects. This is a **count**, not a number of
  days: 30 daily runs come to about 30 days, and every manual run uses up a version too.
  At about 2-3 MB per object, that is under 100 MB.
- **Off-host:** the script does not delete anything there (`OFFSITE_RETENTION_VERSIONS=0`).
  A bucket lifecycle rule does it, so a compromised VPS cannot erase the off-host history.

## Alerts

| Signal | Means | Where |
|---|---|---|
| Kuma push monitor "Majlisna DB backup" goes DOWN | no fully successful run for 26 h | Kuma notifications |
| Dagu run `failed` | that run failed: see its log | `docker exec majlisna-backup-dagu dagu history majlisna-db-backup` |
| 🔴 Discord line | a run failed (only if `DISCORD_WEBHOOK` is set) | the webhook's channel |
| `start-scheduler: WARNING` in the container log | the DB or SeaweedFS was unreachable at start | `docker logs majlisna-backup-dagu` |

A green heartbeat proves that the dump, encryption, upload and retention all worked. It
**does not prove a restore works.** That is what the drill is for.

## Install or update

The lead runs this on the VPS. It is idempotent: the same command installs and updates.

```bash
# from the repo root, on the operator machine
rsync -a --delete --exclude test --exclude secrets.env --exclude __pycache__ --exclude 'dagu-config/data' \
  --exclude 'dagu-config/logs' --exclude 'dagu-config/suspend' \
  infrastructure/db-backups/ ubuntu@latabdhir-tools:/home/ubuntu/majlisna-backups/
ssh ubuntu@latabdhir-tools 'cd /home/ubuntu/majlisna-backups && ./install.sh --run'
```

`install.sh` does the following, in this order:

1. **Preflight.** Checks that `majlisna-db` (PostgreSQL 16) and SeaweedFS are running on
   the expected networks, that the committed key is the owner's, and that the disk is
   under 95 %.
2. **`secrets.env`.** On the first install it creates the file (chmod 600):
   - it generates the role's password;
   - it copies the SeaweedFS S3 keys from `/home/ubuntu/latabdhir-backups/secrets.env`,
     without printing them;
   - it never overwrites an existing file.
3. **The role.** It applies `backup-role.sql` through `majlisna-db`'s local socket, then
   sets the password as a SCRAM verifier: the clear password never reaches SQL, argv or a
   log.
4. **The container.** It runs `docker compose up -d --build`, waits for the startup gate,
   then checks the DAG, the role's login and the bucket from inside the container.
5. **`--run`.** It runs the job once and lists the last objects.

What it never does:

- stop, restart or reconfigure a `majlisna-*` or LaTabdhir container;
- write table data;
- change LaTabdhir's DAGs, secrets or bucket.

Handy commands on the VPS:

```bash
docker exec majlisna-backup-dagu dagu start majlisna-db-backup        # a backup now
docker exec majlisna-backup-dagu dagu history majlisna-db-backup      # past runs
docker exec majlisna-backup-dagu dagu status majlisna-db-backup       # the last run, with its log path
docker exec majlisna-backup-dagu python3 /usr/local/bin/s3.py list majlisna   # objects and sizes
docker logs majlisna-backup-dagu                                      # scheduler and startup gate
```

## Restore drill (monthly)

The drill runs on the operator's machine. It needs `docker`, `gpg`, `python3` and
`ssh ubuntu@latabdhir-tools`, and it is read-only on production.

```bash
cd infrastructure/db-backups
./restore-drill.sh            # owner mode: the newest backup, decrypted with the owner key
./restore-drill.sh --temp-key # when the owner key is not at hand (also the first drill)
```

**Owner mode** works like this:

1. It downloads the newest `majlisna-` object, still encrypted, through the backup
   container.
2. It checks that the object is encrypted to `2967A96B8DFE7D92`, and to that key only.
3. It decrypts locally with the owner key. Set `GNUPGHOME` to the owner's backup keyring;
   pinentry asks for the passphrase, or set
   `GPG_DECRYPT_OPTS="--pinentry-mode loopback --passphrase-file FILE"`.
4. It streams the result into a throwaway `postgres:16-alpine`, the production image by
   digest, started with `--network none` and no published port. The restore uses
   `pg_restore --exit-on-error --single-transaction`.
5. It compares the exact row count of every table with the live database, which it reads
   through the read-only role in a read-only transaction.
6. It removes the container.

The plaintext only ever passes through pipes.

**`--temp-key` mode** first checks that the newest scheduled object is encrypted to the
owner key. Then:

1. It generates a throwaway key pair locally (valid 1 day).
2. It has the VPS run the **same** `backup.sh` once, encrypted to that key, as a
   `drill-majlisna-…` object:
   - no heartbeat, no Discord, no off-host copy;
   - the scheduled rotation never counts or deletes `drill-` objects.
3. It restores that object the same way.
4. It deletes the drill object and the key pair.

It proves everything except the owner's own decryption, which only owner mode can prove.

**Reading the result:**

- Exit 0 and `PASS`: the archive restored with no error, and both sides have the same
  tables.
- Row deltas are printed as live writes since the dump. `--strict` makes any delta fatal;
  the local test uses it.
- A table that exists on only one side fails the drill.

**Reminder:** a monthly calendar entry for the lead (first Monday of the month). Record
each drill below.

## Restore (an actual recovery)

Never restore over a database that still holds data you have not saved. Restore into a
scratch database first, check it, and only then swap.

1. Choose the object: `ssh ubuntu@latabdhir-tools docker exec majlisna-backup-dagu python3
   /usr/local/bin/s3.py list majlisna` (the newest is last).
2. Download it, still encrypted: `ssh ubuntu@latabdhir-tools docker exec -i majlisna-backup-dagu
   python3 /usr/local/bin/s3.py get <KEY> - > <KEY>`.
3. On the owner machine, check it with a drill: `./restore-drill.sh --object <KEY>`.
4. Have an empty `majlisna` database to restore into. If the volume is lost, redeploying
   the compose project in Dokploy recreates `majlisna-db` with an empty volume
   (`POSTGRES_USER`/`POSTGRES_DB` from the Dokploy env).
5. Stop writes: stop `majlisna-backend` in Dokploy.
6. Stream the decrypted archive into it. The plaintext crosses SSH (Tailscale) and never
   lands on a disk:

   ```bash
   gpg --decrypt <KEY> | ssh ubuntu@latabdhir-tools 'docker exec -i majlisna-db sh -c \
     "pg_restore -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" --no-owner --exit-on-error --single-transaction"'
   ```

7. Re-run `./install.sh` on the VPS: it recreates the `majlisna_backup` role, a cluster
   object the dump does not carry.
8. Start the backend (this also drops the per-worker caches), check `/health`, then
   sign in.
9. Run a backup straight away.

The recovery point is the last successful 03:45 run (up to 24 h of writes can be lost).
There is no point-in-time recovery: `archive_mode` is off.

## Before any destructive or schema operation

Every destructive operation, and every schema change, needs a fresh dump first. That
covers WP-01's `purge_seed_data.py --apply`, `generate_fake_data.py --delete` /
`--create-db` in production, and any manual DDL:

1. Run a backup and wait for `Succeeded`:
   `docker exec majlisna-backup-dagu dagu start majlisna-db-backup`.
2. The scripts' guard (`--dump-taken PATH`) also wants a local `pg_dump -Fc` file less than
   1 h old. Take it as its docstring says:
   - `docker exec majlisna-db pg_dump -U majlisna -Fc majlisna > majlisna.dump` (with
     `umask 077`);
   - then `docker cp` it into `majlisna-backend:/tmp/`.
3. That file is a **plaintext** copy of every account. Delete it from the host and from
   the container as soon as the operation is done. The encrypted copy from step 1 is the
   one to keep.

## Design choices

**Why a dedicated container, not LaTabdhir's Dagu:**

- Reusing `latabdhir-backup-dagu` would mean editing LaTabdhir's compose and recreating
  that container to attach Majlisna's network.
- It would mix two projects' secrets in one `env_file`.
- It would dump PostgreSQL 16 with LaTabdhir's `pg_dump` 18, and those archives restore
  only into a PostgreSQL 18.
- The dedicated container shares only the SeaweedFS store and the pinned base image.

**Why `pg_dump -Fc`, not plain SQL plus gzip (LaTabdhir's format):**

- WP-01's guard recognises a dump by the custom-format magic `PGDMP`.
- `pg_restore` can restore selectively.
- The archive is already compressed, so gpg's own compression is off.

**Why scheduler only:** no Dagu web UI listens. Manual runs and history go through
`docker exec`. Nothing new is exposed, even to the other containers on Majlisna's network.

**Why `docker exec` for row counts:** the drill reads the live counts through the backup
container, as `majlisna_backup`, under `default_transaction_read_only`. It never uses the
superuser.

## Limits

- **Not off-host until the owner adds the second target.** SeaweedFS runs on the same VPS
  and the same boot volume as `majlisna-db`. Losing the host or the disk loses both. No
  OCI-level boot or block-volume backup policy could be confirmed: there are no OCI CLI or
  credentials on the VPS or the operator machine, and instance metadata does not show
  one.
- **Shared SeaweedFS identity.** The job uses LaTabdhir's `backup` S3 key, which has Admin
  rights on every bucket. So the Majlisna container could delete LaTabdhir's backups, and
  LaTabdhir's container could delete Majlisna's. A bucket-scoped identity needs an edit of
  `s3.json` and a SeaweedFS restart, so it is an owner step.
- **SeaweedFS is a single node**, with no replication.
- **Recovery point:** up to 24 h of writes, and no point-in-time recovery.
- **Retention is a count**, so manual runs shorten the window.
- **Traffic on the Docker bridge is not TLS** (DB to job, job to SeaweedFS). It stays on
  the host, and the payload to SeaweedFS is already encrypted.
- **Roles and ownership:** the restore uses `--no-owner`. Cluster roles other than
  `POSTGRES_USER` must be recreated (`install.sh` does it for `majlisna_backup`).
- **The network name is tied to the Dokploy compose project ID.**
- **Old Docker engines.** An engine older than 25 (API < 1.44) sometimes attaches a compose
  service to only one of its two networks. This was seen on Docker Desktop 24.0.2 with
  compose 2.19.1, in 2 runs out of 6 of a bare experiment. The VPS runs Docker 29.8.1
  (API 1.56), which creates a container with all its networks at once. If it ever
  happens:
  - the startup gate logs `waiting for …`;
  - `install.sh` fails its login or bucket check;
  - `docker compose up -d --force-recreate` fixes it.

  Never fix it with `docker network connect`.
- **The heartbeat does not prove a restore works.** Only a drill does.

## Owner steps

1. **Kuma push monitor.** In Kuma (`kuma.majlisna.app`, behind SSO), add a monitor:
   - type **Push**, name "Majlisna DB backup", heartbeat interval **93600 s** (26 h),
     retries 0;
   - notifications as for the other production monitors.

   Then:
   - copy its push URL with the **internal** host:
     `http://monitoring-uptime-kuma:3001/api/push/<token>?status=up&msg=OK&ping=`;
   - put it in `/home/ubuntu/majlisna-backups/secrets.env` as `BACKUP_HEARTBEAT_URL`;
   - re-run `./install.sh --run`.
2. **Off-host copy (AWS S3, as LaTabdhir's other layer).** Create the bucket, for example
   `majlisna-db-backups-offsite` in `eu-west-3`:
   - versioning on, Block Public Access on;
   - a lifecycle rule that expires current objects after 35 days and noncurrent versions
     after 7 days.

   Create an IAM user (or role) whose policy allows only `s3:PutObject`, `s3:GetObject`
   and `s3:ListBucket` on that bucket, with no `DeleteObject`. Then:
   - fill `OFFSITE_S3_BUCKET`, `OFFSITE_S3_ACCESS_KEY`, `OFFSITE_S3_SECRET_KEY` and
     `OFFSITE_S3_REGION` in `secrets.env`, leaving `OFFSITE_S3_ENDPOINT` empty for AWS;
   - re-run `./install.sh --run` and check the object in the S3 console.

   Any S3-compatible store works too (OCI Object Storage, B2); set `OFFSITE_S3_ENDPOINT`.
3. **Discord (optional).** Create a webhook in a Majlisna channel, set `DISCORD_WEBHOOK`,
   and re-run `./install.sh`.
4. **Scoped SeaweedFS identity (optional, needs a SeaweedFS restart).** Add a
   `majlisna-backup` identity to `/home/ubuntu/latabdhir-backups/s3.json`, with actions
   `Read:majlisna-db-backups`, `Write:majlisna-db-backups`, `List:majlisna-db-backups`.
   Restart `latabdhir-backup-seaweedfs` in a quiet window, well away from 03:45 and 04:30.
   Then put the new keys in Majlisna's `secrets.env` and re-run `./install.sh`.
5. **Keep the private key safe.** It decrypts both projects' backups.

## Drill log

| Date (UTC) | Mode | Object | Encrypted / dump | Tables | Rows (backup / live) | Restore | Result |
|---|---|---|---|---|---|---|---|
| 2026-11-01 10:10 | `--temp-key` | drill-majlisna-20261101T101002Z.dump.gpg (deleted after) | 579 001 / 578 770 bytes | 31 / 31 | 1 727 / 1 727 | 1 s, PostgreSQL 16.15, no network | PASS |

The local end-to-end test of 2026-10-31 ran on a seeded throwaway database, not
production. Its owner-mode drill on that database:
- a 50 751-byte object, from a 50 285-byte dump, restored in under 1 s into PostgreSQL
  16.15 with no network;
- 4 tables and 2 084 rows, identical to the live side (`--strict`).

See [Local test](#local-test).

### Local test

`bash infrastructure/db-backups/test/test-backup-restore.sh` runs entirely in throwaway
containers. It never uses production or the shared E2E stack. It takes about 3 minutes;
its 71 checks passed in 3 consecutive runs on 2026-10-31. It covers:

- **Install:** `install.sh` on a fresh host and again on an installed one.
- **Role:** the backup role is read-only and holds a SCRAM verifier.
- **Scheduler:** it fires the DAG and passes it the env; catch-up replays a missed run
  once, and not again after a restart.
- **Backup:** one encrypted object primary plus off-host, one heartbeat. The object is not
  plaintext, is encrypted to the configured key only, and decrypts to `PGDMP`.
- **Drill:** both modes restore with exact counts (`--strict`).
- **Retention:** keeps the newest 30 and leaves other prefixes alone.
- **Failures:** wrong DB host, a missing key, an unresolved `${VAR}`, an off-host failure
  and a heartbeat failure all exit non-zero, send no heartbeat and leave no work file.

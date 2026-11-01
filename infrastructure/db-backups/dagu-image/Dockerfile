# Majlisna DB backup runner: the same pinned Dagu base as LaTabdhir's backup image (its layers
# are already on the VPS), plus the PostgreSQL 16 client, gnupg and boto3.
FROM ghcr.io/dagucloud/dagu:2.16.6@sha256:b242dc7b605aa20d6db78ba192beb82135d390025a7d9c8dfd7f08e14464c69f
USER root
# pg_dump must have the server's major version: majlisna-db runs PostgreSQL 16, which is
# exactly what Ubuntu noble ships (no PGDG repository needed, unlike LaTabdhir's 18).
RUN apt-get update && apt-get install -y --no-install-recommends \
      postgresql-client-16 gnupg python3 python3-boto3 curl ca-certificates coreutils \
    && rm -rf /var/lib/apt/lists/*
COPY backup.sh drill-backup.sh live-table-counts.sh start-scheduler.sh /usr/local/bin/
COPY s3.py notify.py passthru.py /usr/local/bin/
# The PUBLIC half of the owner's backup key (the same key as LaTabdhir's backups,
# fingerprint 9E6AC949274F12B4B803F4A52967A96B8DFE7D92). The private key is never on the VPS.
COPY backup-public-key.asc /etc/majlisna/backup-public-key.asc
COPY table-counts.sql /etc/majlisna/table-counts.sql
RUN chmod 0755 /usr/local/bin/backup.sh /usr/local/bin/drill-backup.sh /usr/local/bin/live-table-counts.sh \
      /usr/local/bin/start-scheduler.sh \
    && chmod 0644 /usr/local/bin/s3.py /usr/local/bin/notify.py /usr/local/bin/passthru.py \
      /etc/majlisna/backup-public-key.asc /etc/majlisna/table-counts.sql
# Fix the runtime identity at build time (uid 1001 = the VPS's ubuntu user, who owns
# dagu-config/): a docker exec must never create root-owned run state.
RUN groupmod -o -g 1001 dagu && usermod -o -u 1001 -g 1001 dagu \
    && chown -R 1001:1001 /home/dagu
USER 1001:1001
ENTRYPOINT ["/usr/local/bin/tini", "-g", "--"]
# Scheduler only (no web UI, so nothing listens here), started once its two dependencies answer.
CMD ["/usr/local/bin/start-scheduler.sh"]

"""Write the test's DAGs, all derived from the real one so they stay in sync with it.

    python3 make_test_dags.py REAL_DAG DAGS_DIR

- majlisna-db-backup.yaml: the real DAG made manual-only (no schedule, no catch-up), so a
  run never fires at an unpredictable moment of the test;
- schedtest.yaml: every minute, its own prefix and heartbeat: the scheduler process fires
  DAGs and passes them the environment, as it will at 03:45 UTC;
- catchtest.yaml: scheduled one hour ago, with the real catch-up window: a scheduler that
  starts after a missed run (a host reboot) replays it once.
"""

import datetime
import sys
from pathlib import Path


def variant(lines: list[str], schedule: str | None, prefix: str | None, heartbeat: str | None,
            keep_catchup: bool) -> str:
    out = []
    for line in lines:
        if line.startswith("schedule:"):
            if schedule:
                out.append(f'schedule: "{schedule}"')
            continue
        if line.startswith("catchup_window:") and not keep_catchup:
            continue
        if prefix and line.strip() == "- BACKUP_NAME_PREFIX: majlisna":
            line = line.replace("majlisna", prefix)
        if heartbeat:
            line = line.replace("${BACKUP_HEARTBEAT_URL}", "${" + heartbeat + "}")
        out.append(line)
    return "\n".join(out) + "\n"


def main(source: str, dags: str) -> None:
    lines = Path(source).read_text().splitlines()
    target = Path(dags)
    hour_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    (target / "majlisna-db-backup.yaml").write_text(variant(lines, None, None, None, False))
    (target / "schedtest.yaml").write_text(
        variant(lines, "* * * * *", "schedtest", "BACKUP_HEARTBEAT_URL_SCHED", False))
    (target / "catchtest.yaml").write_text(
        variant(lines, f"{hour_ago.minute} {hour_ago.hour} * * *", "catchtest", "BACKUP_HEARTBEAT_URL_CATCH", True))


if __name__ == "__main__":
    main(*sys.argv[1:3])

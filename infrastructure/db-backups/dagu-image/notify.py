"""Optional Discord summary for the Majlisna DB backup (same delivery rules as LaTabdhir's).

JSON-safe (no shell interpolation), mentions disabled, credential-free diagnostics, and
bounded retries only on an explicit HTTP 429. With ``DISCORD_WEBHOOK`` unset (or left as
an unresolved ``${DISCORD_WEBHOOK}``) it does nothing and succeeds: Discord is a summary,
the Kuma heartbeat is the alert.

    notify.py MESSAGE
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from http import HTTPStatus

MAX_ATTEMPTS = 3
MAX_DELAY = 10


def webhook() -> str:
    value = os.environ.get("DISCORD_WEBHOOK", "")
    return "" if value.startswith("${") else value


def notify(message: str) -> bool:
    url = webhook()
    if not url:
        print("Discord summary disabled: DISCORD_WEBHOOK is unset.", file=sys.stderr)  # noqa: T201
        return True
    request = urllib.request.Request(  # noqa: S310 -- operator-configured webhook
        url,
        data=json.dumps(
            {
                "username": "Majlisna · Backups",
                "content": message[:2000],
                "allowed_mentions": {"parse": []},
            }
        ).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "majlisna-backups/1.0 (+https://majlisna.app)",
        },
        method="POST",
    )
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=10):  # noqa: S310
                return True
        except urllib.error.HTTPError as exc:
            with exc:
                if exc.code == HTTPStatus.TOO_MANY_REQUESTS and attempt < MAX_ATTEMPTS - 1:
                    try:
                        delay = float(json.load(exc)["retry_after"])
                        if 0 <= delay <= MAX_DELAY:
                            time.sleep(delay + 0.1)
                            continue
                    except (ValueError, KeyError, TypeError):
                        pass
                print(f"Discord summary failed: HTTP {exc.code}.", file=sys.stderr)  # noqa: T201
                return False
        except (urllib.error.URLError, TimeoutError):
            print("Discord summary outcome unknown (network/timeout).", file=sys.stderr)  # noqa: T201
            return False
    return False


if __name__ == "__main__":
    raise SystemExit(0 if notify(sys.argv[1]) else 1)

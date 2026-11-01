"""Stand-in for the Uptime Kuma push endpoint, used only by test-backup-restore.sh.

Every request is logged as ``HIT <path>`` (query string dropped) on stdout, so the test
counts heartbeats with ``docker logs``. ``/api/push/*`` answers 200, anything else 500,
which lets a test point the job at a failing heartbeat.
"""

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8080


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        print(f"HIT {path}", flush=True)  # noqa: T201 -- the test reads this log
        status = 200 if path.startswith("/api/push/") else 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}' if status == 200 else b'{"ok":false}')

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()  # noqa: S104 -- test network only

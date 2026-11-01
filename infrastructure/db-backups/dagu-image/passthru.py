"""Copy stdin to stdout unchanged, then record what went through.

Sits between pg_dump and gpg (and between gpg and pg_restore in the drill), so the
plaintext is checked without ever being written to disk. The stats file gets one line:
``PGDMP <bytes>`` when the stream starts with the pg_dump custom-format magic,
``other <bytes>`` otherwise.

    pg_dump -Fc ... | python3 passthru.py STATS_FILE | gpg ...
"""

import sys

MAGIC = b"PGDMP"
CHUNK = 1 << 16


def main(stats_path: str) -> int:
    source, sink = sys.stdin.buffer, sys.stdout.buffer
    head = b""
    total = 0
    while chunk := source.read(CHUNK):
        if len(head) < len(MAGIC):
            head += chunk[: len(MAGIC) - len(head)]
        total += len(chunk)
        sink.write(chunk)
    sink.flush()
    with open(stats_path, "w") as stats:
        stats.write(f"{'PGDMP' if head == MAGIC else 'other'} {total}\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: passthru.py STATS_FILE", file=sys.stderr)  # noqa: T201
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))

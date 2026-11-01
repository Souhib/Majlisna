"""Print the SQL that sets majlisna_backup's password, as a SCRAM-SHA-256 verifier.

Reads PGPASSWORD from secrets.env and computes the verifier here, the way psql's
\\password does, so only the verifier reaches PostgreSQL: the clear password never appears
in SQL text, on a command line, in the process list or in a server log line.

    python3 set-role-password.py secrets.env | docker exec -i majlisna-db sh -c \\
      'psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
"""

import base64
import hashlib
import hmac
import os
import re
import sys

ITERATIONS = 4096
ROLE = "majlisna_backup"


def password_from(path: str) -> str:
    with open(path) as env_file:
        for line in env_file:
            key, _, value = line.rstrip("\n").partition("=")
            if key == "PGPASSWORD":
                return value
    raise SystemExit(f"set-role-password: PGPASSWORD is missing from {path}")


def scram_verifier(password: str) -> str:
    # install.sh generates an alphanumeric password, for which SASLprep is the identity.
    if not re.fullmatch(r"[A-Za-z0-9]{32,}", password):
        raise SystemExit("set-role-password: PGPASSWORD must be 32+ letters and digits")
    salt = os.urandom(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    client_key = hmac.new(salted, b"Client Key", "sha256").digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", "sha256").digest()

    def b64(raw: bytes) -> str:
        return base64.b64encode(raw).decode()

    return f"SCRAM-SHA-256${ITERATIONS}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: set-role-password.py SECRETS_ENV")
    verifier = scram_verifier(password_from(sys.argv[1]))
    print(f"ALTER ROLE {ROLE} PASSWORD '{verifier}';")  # noqa: T201 -- piped into psql

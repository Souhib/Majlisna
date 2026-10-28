"""Opaque keyset cursors: (instant, id) → a URL-safe string, and back.

A keyset page asks for the rows strictly after the last one it showed, so a row
deleted or inserted meanwhile neither skips nor repeats one — which an offset does.
"""

import base64
import binascii
from datetime import datetime
from uuid import UUID

_SEPARATOR = "|"


def encode_cursor(instant: datetime, row_id: UUID) -> str:
    """The cursor for the row at (``instant``, ``row_id``). ``instant`` must be aware."""
    raw = f"{instant.isoformat()}{_SEPARATOR}{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """The (instant, id) a cursor names.

    :raises ValueError: anything ``encode_cursor`` did not produce.
    """
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        instant_text, id_text = raw.split(_SEPARATOR)
        instant = datetime.fromisoformat(instant_text)
        row_id = UUID(id_text)
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"Not a cursor: {cursor!r}") from error
    if instant.tzinfo is None:
        raise ValueError(f"Not a cursor (naive instant): {cursor!r}")
    return instant, row_id

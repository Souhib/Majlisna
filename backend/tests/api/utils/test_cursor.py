"""Unit tests for the opaque keyset cursor (utils/cursor.py)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from majlisna.api.utils.cursor import decode_cursor, encode_cursor


def test_a_cursor_round_trips():
    """What encode hands out, decode reads back exactly — microseconds included."""
    # Prepare
    instant = datetime(2026, 10, 28, 12, 34, 56, 789012, tzinfo=UTC)
    row_id = uuid4()

    # Act
    cursor = encode_cursor(instant, row_id)

    # Assert
    assert decode_cursor(cursor) == (instant, row_id)
    assert "=" not in cursor
    assert "/" not in cursor
    assert "+" not in cursor


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "not base64 at all!",
        "Zm9v",  # "foo": no separator
        "Zm9vfGJhcg",  # "foo|bar": neither part parses
        encode_cursor(datetime(2026, 1, 1), uuid4()),  # naive instant: never handed out
    ],
)
def test_anything_else_is_rejected(cursor: str):
    # Act / Assert
    with pytest.raises(ValueError, match="Not a cursor"):
        decode_cursor(cursor)

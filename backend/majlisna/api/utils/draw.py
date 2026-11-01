"""Content draws that read the ids first, then only the rows they keep.

A draw used to load and hydrate a whole content table to keep a handful of rows —
every MCQ question (609 rows, 925 kB) on each MCQ start, every quiz word (191 rows,
332 kB) on each Kalimat round, inside the game lock. The controllers now select the
ids (and what the filters need), pick here with the shared `rng`, and fetch only
the chosen rows by id.

A `WHERE id IN (...)` fetch answers in the database's order, not the draw's, and the
order is part of the draw (the MCQ rounds, the Codenames card layout), so the rows
are put back in drawn order with `in_draw_order`.
"""

from collections.abc import Iterable, Sequence
from typing import Protocol
from uuid import UUID

from majlisna.api.schemas.room import DifficultyLevel
from majlisna.api.utils.rng import rng


class HasId(Protocol):
    @property
    def id(self) -> UUID: ...


def pick_ids(
    pool: Sequence[tuple[UUID, str]],
    count: int,
    exclude_ids: list[str] | None = None,
    difficulty: str | None = None,
) -> list[UUID]:
    """Draw up to `count` ids from `(id, difficulty)` pairs.

    Excluded ids are skipped; a difficulty (other than "mixed") narrows the pool when
    any id matches it. If fewer than `count` remain, the whole pool is used instead.
    """
    excluded = set(exclude_ids or ())
    available = [(item_id, level) for item_id, level in pool if str(item_id) not in excluded]
    if difficulty and difficulty != DifficultyLevel.MIXED:
        matching = [(item_id, level) for item_id, level in available if level == difficulty]
        if matching:
            available = matching
    if len(available) < count:
        available = list(pool)
    return rng.sample([item_id for item_id, _ in available], min(count, len(available)))


def in_draw_order[RowT: HasId](rows: Iterable[RowT], ids: Sequence[UUID]) -> list[RowT]:
    """The fetched rows in the order their ids were drawn.

    A drawn id with no row (deleted between the two reads) is skipped.
    """
    by_id = {row.id: row for row in rows}
    return [by_id[item_id] for item_id in ids if item_id in by_id]

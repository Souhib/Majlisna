from datetime import datetime
from uuid import UUID

from ipg.api.models.game import GameType
from ipg.api.schemas.shared import BaseModel


class GameHistoryEntry(BaseModel):
    """A game history row for a user's game list."""

    id: UUID
    type: GameType
    start_time: datetime
    end_time: datetime | None
    number_of_players: int

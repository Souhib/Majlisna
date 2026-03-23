from ipg.api.schemas.shared import BaseModel


class StatusResponse(BaseModel):
    status: str


class StatusMessageResponse(BaseModel):
    status: str
    message: str


class GameStartResponse(BaseModel):
    game_id: str
    room_id: str


class AdvanceRoundResponse(BaseModel):
    game_id: str
    room_id: str
    advanced: bool  # True if round actually advanced, False if just marked ready
    ready_players: list[str] = []  # user_ids of players who are ready
    ready_count: int = 0
    total_players: int = 0


class HintRecordResponse(BaseModel):
    game_id: str
    recorded: bool


class TimerExpiredResponse(BaseModel):
    game_id: str
    action: str

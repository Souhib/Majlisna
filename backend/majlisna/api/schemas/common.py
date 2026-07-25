from majlisna.api.schemas.shared import BaseModel


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


class UnlockedAchievement(BaseModel):
    """One badge a player just earned."""

    code: str
    name: str
    icon: str
    tier: int


class PlayerUnlockedAchievements(BaseModel):
    """Badges earned by one player at the end of a game.

    Every game controller wrote this into ``live_state["newly_unlocked_achievements"]``
    but no game-state schema declared it, and ``BaseModel`` is ``extra="forbid"`` — so
    it never left the server. The client has always been ready for it
    (``useAchievementNotifications`` + ``AchievementToast``); the toast simply had no
    data. Declaring the field is what connects the two.
    """

    user_id: str
    achievements: list[UnlockedAchievement]

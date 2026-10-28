from datetime import datetime
from enum import StrEnum

from majlisna.api.models.game import GamePauseReason
from majlisna.api.schemas.shared import BaseModel


class TimerExpiredAction(StrEnum):
    """Every answer ``POST /{game}/games/{id}/timer-expired`` can give.

    An enum rather than a bare ``str`` so the values reach OpenAPI and the generated
    client gets a union to switch on — a timer callback has to know which answers
    mean "stop firing" (``paused``, ``round_already_resolved``) without comparing
    hard-coded strings.
    """

    # The host has paused the game for the prayer: nothing happened, no clock runs.
    PAUSED = "paused"
    # The server's own clock says the timer has not run out yet.
    TIMER_NOT_EXPIRED = "timer_not_expired"
    # Quizzes: the round is not in its playing phase.
    NOT_PLAYING = "not_playing"
    # Quizzes: the round moved to its results.
    RESULTS = "results"
    # Codenames: the turn passed to the other team.
    AUTO_END_TURN = "auto_end_turn"
    # Undercover: the remaining describers were skipped; voting started.
    SKIP_TO_VOTING = "skip_to_voting"
    # Undercover: missing votes were filled at random and the round resolved.
    AUTO_VOTE = "auto_vote"
    # Undercover: Mr. White ran out of time to guess (a wrong guess).
    MR_WHITE_GUESS_TIMEOUT = "mr_white_guess_timeout"
    # Undercover: the round already produced its elimination; waiting on next-round.
    ROUND_ALREADY_RESOLVED = "round_already_resolved"
    # Undercover: the turn was in no timed phase.
    NONE = "none"


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
    action: TimerExpiredAction


class UnlockedAchievement(BaseModel):
    """One badge a player just earned."""

    code: str
    name: str
    icon: str
    tier: int


class PlayerUnlockedAchievements(BaseModel):
    """Badges earned by one player at the end of a game.

    Every game controller writes this into ``live_state["newly_unlocked_achievements"]``,
    and every game-state schema declares it: ``BaseModel`` is ``extra="forbid"``, so an
    undeclared field never leaves the server (it once did not). The client shows them as
    seals on the game-over colophon (``useAchievementSeals``), never as a toast mid-game.
    """

    user_id: str
    achievements: list[UnlockedAchievement]


class GamePause(BaseModel):
    """A running game the host has paused — for the prayer (وقفة الصلاة).

    While this is set no move is accepted and no clock runs: every timer the game
    measures from is moved forward by the paused duration on resume.

    The server computes what a paused screen shows, so the client never has to:
    ``remaining_seconds`` is the frozen countdown, ``paused_for_seconds`` the time
    since the pause on the server's clock (no client clock skew), and
    ``anyone_can_resume_at`` when the pause stops being the host's alone. Declared on
    all four game-state schemas: ``BaseModel`` is ``extra="forbid"``, so a
    ``live_state`` key no schema declares never reaches the client.
    """

    by_user_id: str
    by_username: str
    # The instant the clocks stopped (UTC).
    since: datetime
    reason: GamePauseReason
    # What was left of the current turn's (or round's) timer when the clocks stopped,
    # in [0, duration] — show it frozen. Null when the phase has no time limit (a
    # timer of 0, a resolved Undercover round, a quiz between rounds).
    remaining_seconds: float | None = None
    # How long the game has been paused, measured on the server when this was read.
    paused_for_seconds: float = 0.0
    # From this instant any player of the game may resume, not only the host
    # (PRAYER_PAUSE_MAX_SECONDS after `since`).
    anyone_can_resume_at: datetime


class GameColophon(BaseModel):
    """The game-over colophon's facts ("Yusuf's majlis · 3 rounds · 21:40").

    Built by ``BaseGameController._build_colophon`` and spread onto all four state
    schemas as ``host_username``, ``started_at`` and ``ended_at`` (none of them is a
    secret, so they are sent in every phase):

    * ``host_username`` — who hosted: the room owner when the game STARTED, kept in
      ``live_state`` so it survives a later host transfer; for a game started before
      the key existed, the current owner. Null when neither is known (orphaned room).
    * ``started_at`` / ``ended_at`` — ``Game.start_time`` / ``Game.end_time``, always
      UTC-aware (SQLite hands them back naive). ``ended_at`` is null while the game
      runs. Wall-clock: a prayer pause counts in the duration.
    """

    host_username: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


class PauseGameResponse(BaseModel):
    game_id: str
    paused: GamePause


class ResumeGameResponse(BaseModel):
    game_id: str
    # How long the game was paused; every clock of the game moved forward by this.
    paused_seconds: float


class PhaseTimer(BaseModel):
    """The timer of the phase a game is in (internal, never returned as is).

    Each game controller reports its own (``BaseGameController._phase_timer``), so
    the paused view can freeze the countdown server-side.
    """

    started_at: datetime
    duration_seconds: int

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from fastapi import status
from loguru import logger
from starlette.responses import JSONResponse

from majlisna.api.constants import CODENAMES_BOARD_SIZE


class LogLevel(StrEnum):
    """Enum for log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class BaseError(Exception):
    """Base error class for all custom errors.

    Provides automatic logging, i18n key generation, and structured error info.
    """

    @classmethod
    def _generate_error_key(cls) -> str:
        """Generate i18n key from class name (e.g., UserNotFoundError -> errors.api.userNotFound)."""
        name = cls.__name__
        if name.endswith("Error"):
            name = name[:-5]
        camel = re.sub(r"([A-Z])", r"_\1", name).strip("_")
        parts = camel.split("_")
        camel_case = parts[0].lower() + "".join(p.capitalize() for p in parts[1:])
        return f"errors.api.{camel_case}"

    def __init__(
        self,
        message: str,
        frontend_message: str | None = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str | None = None,
        error_key: str | None = None,
        error_params: dict[str, str | int | float] | None = None,
        details: dict[str, Any] | None = None,
        log_level: LogLevel | None = None,
    ):
        self.message = message
        self.frontend_message = frontend_message or message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        self.error_key = error_key or self._generate_error_key()
        self.error_params = error_params
        self.details = details or {}
        self.timestamp = datetime.now(UTC)

        if log_level is None:
            # 4xx are expected outcomes of normal play — a wrong room PIN, voting
            # twice, acting out of turn — so they log at INFO, not WARNING.
            #
            # This matters beyond log noise: app.py attaches a Sentry/GlitchTip
            # sink at WARNING+, so logging routine 4xx as warnings turned every
            # "You have already voted this round" into a tracked issue. Real
            # errors drowned in it and the error-tracker quota went with them.
            # Genuine server faults (5xx) still log at ERROR and still page.
            log_level = LogLevel.ERROR if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR else LogLevel.INFO

        log_function = {
            LogLevel.DEBUG: logger.debug,
            LogLevel.INFO: logger.info,
            LogLevel.WARNING: logger.warning,
            LogLevel.ERROR: logger.error,
            LogLevel.CRITICAL: logger.critical,
        }[log_level]

        log_function(
            f"{self.error_code}: {self.message}",
            error_code=self.error_code,
            status_code=self.status_code,
            details=self.details,
        )

        super().__init__(self.message)


# Authentication & Authorization Errors


class InvalidCredentialsError(BaseError):
    """Invalid login credentials."""

    def __init__(self, email: str | None = None):
        super().__init__(
            message=f"Invalid credentials for {email}" if email else "Invalid credentials",
            frontend_message="Please check your email and password and try again.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details={"email": email} if email else {},
        )


class EmailNotVerifiedError(BaseError):
    """Login blocked because the account's email has not been verified."""

    def __init__(self) -> None:
        super().__init__(
            message="Email address not verified",
            frontend_message="Please verify your email address before logging in.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class TokenExpiredError(BaseError):
    """JWT token has expired."""

    def __init__(self):
        super().__init__(
            message="Token has expired",
            frontend_message="Your session has expired. Please log in again.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class InvalidTokenError(BaseError):
    """JWT token is invalid."""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(
            message=message,
            frontend_message="Invalid authentication token.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenError(BaseError):
    """User lacks permission for this action."""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(
            message=message,
            frontend_message="You don't have permission to perform this action.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


# User Errors


class UserNotFoundError(BaseError):
    """User not found in the database."""

    def __init__(self, user_id: UUID):
        super().__init__(
            message=f"User with id {user_id} not found",
            frontend_message="User not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"user_id": str(user_id)},
        )


class UserAlreadyExistsError(BaseError):
    """User with this email already exists."""

    def __init__(self, email_address: str):
        super().__init__(
            message=f"User with email address {email_address} already exists",
            frontend_message="An account with this email already exists.",
            status_code=status.HTTP_409_CONFLICT,
            details={"email_address": email_address},
        )


class UsernameAlreadyTakenError(BaseError):
    """Another account already uses this username (compared case-insensitively).

    Raised by registration and by a profile rename. ``user.username`` carries no
    unique constraint (and there are no migrations to add one), so the controllers
    enforce it — see ``username_is_taken``.
    """

    def __init__(self, username: str):
        super().__init__(
            message=f"Username {username} is already taken",
            frontend_message="This username is already taken. Please choose another one.",
            status_code=status.HTTP_409_CONFLICT,
            error_params={"username": username},
            details={"username": username},
        )


class UserNotInRoomError(BaseError):
    """User is not in the specified room."""

    def __init__(self, user_id: UUID, room_id: UUID):
        super().__init__(
            message=f"User with id {user_id} is not in room with id {room_id}",
            frontend_message="You are not in this room.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"user_id": str(user_id), "room_id": str(room_id)},
        )


class UserAlreadyInRoomError(BaseError):
    """User is already in a room."""

    def __init__(self, user_id: UUID | str, room_id: UUID | str | None):
        super().__init__(
            message=f"User with id {user_id} is already in room with id {room_id}",
            frontend_message="You are already in a room.",
            status_code=status.HTTP_409_CONFLICT,
            details={"user_id": str(user_id), "room_id": str(room_id)},
        )


# Room Errors


class RoomNotFoundError(BaseError):
    """Room not found."""

    def __init__(self, room_id: UUID | str):
        super().__init__(
            message=f"Room with id {room_id} not found",
            frontend_message="Room not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"room_id": str(room_id)},
        )


class WrongRoomPasswordError(BaseError):
    """Incorrect room password."""

    def __init__(self, room_id: UUID):
        super().__init__(
            message=f"The password to join the room with id {room_id} is incorrect",
            frontend_message="Incorrect room password.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"room_id": str(room_id)},
        )


class RoomIsNotActiveError(BaseError):
    """Room is not active."""

    def __init__(self, room_id: UUID):
        super().__init__(
            message=f"Room with id {room_id} is not active",
            frontend_message="This room is no longer active.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"room_id": str(room_id)},
        )


# Game Errors


class GameNotFoundError(BaseError):
    """Game not found."""

    def __init__(self, game_id: UUID | str):
        super().__init__(
            message=f"Game with id {game_id} not found",
            frontend_message="Game not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"game_id": str(game_id)},
        )


class GameStillInProgressError(BaseError):
    """A post-game-only resource was requested while the game is still running."""

    def __init__(self, game_id: UUID | str):
        super().__init__(
            message=f"Game {game_id} is still in progress; this is only available once it ends",
            frontend_message="This game is still in progress.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"game_id": str(game_id)},
        )


class NotAGameParticipantError(BaseError):
    """The caller did not take part in the requested game."""

    def __init__(self, game_id: UUID | str, user_id: UUID | str):
        super().__init__(
            message=f"User {user_id} did not take part in game {game_id}",
            frontend_message="You didn't take part in this game.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"game_id": str(game_id), "user_id": str(user_id)},
        )


class NoTurnInsideGameError(BaseError):
    """No turn found inside the game."""

    def __init__(self, game_id: UUID | str):
        super().__init__(
            message=f"No turn inside game with id {game_id}",
            frontend_message="No active turn in this game.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"game_id": str(game_id)},
        )


# Undercover Game Errors


class WordAlreadyExistsError(BaseError):
    """Word already exists in the database."""

    def __init__(self, word: str):
        super().__init__(
            message=f"Word {word} already exists",
            frontend_message="This word already exists.",
            status_code=status.HTTP_409_CONFLICT,
            details={"word": word},
        )


class WordNotFoundByIdError(BaseError):
    """Word not found by ID."""

    def __init__(self, word_id: UUID):
        super().__init__(
            message=f"Word with id {word_id} not found",
            frontend_message="Word not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"word_id": str(word_id)},
        )


class WordNotFoundByNameError(BaseError):
    """Word not found by name."""

    def __init__(self, word: str):
        super().__init__(
            message=f"Word {word} not found",
            frontend_message="Word not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"word": word},
        )


class TermPairAlreadyExistsError(BaseError):
    """Term pair already exists."""

    def __init__(self, term1: str, term2: str):
        super().__init__(
            message=f"Term pair {term1} - {term2} already exists",
            frontend_message="This term pair already exists.",
            status_code=status.HTTP_409_CONFLICT,
            details={"term1": term1, "term2": term2},
        )


class TermPairNotFoundError(BaseError):
    """Term pair not found."""

    def __init__(self, term_pair_id: UUID):
        super().__init__(
            message=f"Term pair with id {term_pair_id} not found",
            frontend_message="Term pair not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"term_pair_id": str(term_pair_id)},
        )


# Voting Errors


class CantVoteBecauseYouDeadError(BaseError):
    """Dead players cannot vote."""

    def __init__(self, user_id: UUID | str):
        super().__init__(
            message=f"User with id {user_id} can't vote because they're dead",
            frontend_message="You can't vote because you've been eliminated.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"user_id": str(user_id)},
        )


class CantVoteForYourselfError(BaseError):
    """Players cannot vote for themselves."""

    def __init__(self, user_id: UUID | str):
        super().__init__(
            message=f"User with id {user_id} can't vote for themselves",
            frontend_message="You can't vote for yourself.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"user_id": str(user_id)},
        )


class CantVoteForDeadPersonError(BaseError):
    """Cannot vote for an eliminated player."""

    def __init__(self, user_id: UUID | str, dead_user_id: UUID | str):
        super().__init__(
            message=f"User with id {user_id} can't vote for dead user with id {dead_user_id}",
            frontend_message="You can't vote for an eliminated player.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"user_id": str(user_id), "dead_user_id": str(dead_user_id)},
        )


class PlayerRemovedFromGameError(BaseError):
    """Player was removed from a game due to inactivity (disconnect timeout)."""

    def __init__(self, user_id: str, game_id: str):
        super().__init__(
            message=f"Player {user_id} was removed from game {game_id} due to inactivity",
            frontend_message="You were removed from this game due to inactivity.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"user_id": user_id, "game_id": game_id},
        )


# Codenames Game Errors


class NotSpymasterError(BaseError):
    """Raised when a non-spymaster tries to give a clue."""

    def __init__(self, user_id: str):
        super().__init__(
            message=f"User {user_id} is not the spymaster for the current team",
            frontend_message="Only the spymaster can give clues.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"user_id": user_id},
        )


class NotOperativeError(BaseError):
    """Raised when a non-operative tries to guess a card."""

    def __init__(self, user_id: str):
        super().__init__(
            message=f"User {user_id} is not an operative for the current team",
            frontend_message="Only operatives can guess cards.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"user_id": user_id},
        )


class NotYourTurnError(BaseError):
    """Raised when a player acts out of turn."""

    def __init__(self, user_id: str):
        super().__init__(
            message=f"It is not user {user_id}'s team's turn",
            frontend_message="It's not your team's turn.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"user_id": user_id},
        )


class CardAlreadyRevealedError(BaseError):
    """Raised when trying to guess an already revealed card."""

    def __init__(self, card_index: int):
        super().__init__(
            message=f"Card at index {card_index} is already revealed",
            frontend_message="This card has already been revealed.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"card_index": card_index},
        )


class InvalidCardIndexError(BaseError):
    """Raised when the card index is out of range."""

    def __init__(self, card_index: int):
        super().__init__(
            message=f"Card index {card_index} is out of range (0-{CODENAMES_BOARD_SIZE - 1})",
            frontend_message="Invalid card selection.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"card_index": card_index},
        )


class NoClueGivenError(BaseError):
    """Raised when trying to guess before a clue has been given."""

    def __init__(self):
        super().__init__(
            message="No clue has been given yet for this turn",
            frontend_message="Wait for the spymaster to give a clue first.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class GameNotInProgressError(BaseError):
    """Raised when trying to take an action on a game that is not in progress."""

    def __init__(self, game_id: str):
        super().__init__(
            message=f"Game {game_id} is not in progress",
            frontend_message="This game is not currently in progress.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"game_id": game_id},
        )


class GameAlreadyOverError(BaseError):
    """Raised when a move or timer reaches a game that has already ended."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            frontend_message="This game is already over.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class NotEnoughPlayersError(BaseError):
    """Raised when there are not enough players to start a game.

    ``required`` used to be hardcoded to "4 players for Codenames" in both the log
    line and the user-facing message. Codenames was the only caller that could
    reach it (the quizzes need 1 player, and Undercover was not passing a minimum
    at all), so the moment Undercover started enforcing its own minimum of 3 the
    message told players the wrong number for the wrong game.
    """

    def __init__(self, player_count: int, required: int | None = None):
        needed = required if required is not None else 4
        super().__init__(
            message=f"Need at least {needed} players to start, got {player_count}",
            frontend_message=f"At least {needed} players are needed to start this game.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"player_count": player_count, "required": needed},
            error_params={"required": str(needed), "player_count": str(player_count)},
        )


class TooManyPlayersError(BaseError):
    """Raised when a room holds more players than the game supports."""

    def __init__(self, player_count: int, allowed: int):
        super().__init__(
            message=f"At most {allowed} players can play this game, got {player_count}",
            frontend_message=f"This game supports at most {allowed} players.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"player_count": player_count, "allowed": allowed},
            error_params={"allowed": str(allowed), "player_count": str(player_count)},
        )


class InvalidOrExpiredTokenError(BaseError):
    """Password reset or email verification token is invalid or expired."""

    def __init__(self, message: str = "Invalid or expired token"):
        super().__init__(
            message=message,
            frontend_message="This link is invalid or has expired. Please request a new one.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class ClueWordIsOnBoardError(BaseError):
    """Raised when the clue word matches a word on the board."""

    def __init__(self, clue_word: str):
        super().__init__(
            message=f"Clue word '{clue_word}' is on the board and cannot be used as a clue",
            frontend_message="Your clue word cannot be a word that's on the board.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"clue_word": clue_word},
        )


# ========== Word Quiz Errors ==========


class NoQuizWordsAvailableError(BaseError):
    """Raised when no quiz words are available for a game."""

    def __init__(self):
        super().__init__(
            message="No quiz words available in the database",
            frontend_message="No quiz words available. Please seed the database.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class AlreadyAnsweredError(BaseError):
    """Raised when a player has already correctly answered this round."""

    def __init__(self, user_id: UUID):
        super().__init__(
            message=f"User {user_id} has already answered this round",
            frontend_message="You have already answered this round.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"user_id": str(user_id)},
        )


class RoundNotPlayingError(BaseError):
    """Raised when an action is attempted outside the playing phase."""

    def __init__(self):
        super().__init__(
            message="Round is not in playing phase",
            frontend_message="Round is not in playing phase.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class SpectatorCannotAnswerError(BaseError):
    """Raised when a spectator tries to submit an answer."""

    def __init__(self, user_id: UUID):
        super().__init__(
            message=f"Spectator {user_id} cannot submit answers",
            frontend_message="Spectators cannot submit answers.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"user_id": str(user_id)},
        )


class EmptyAnswerError(BaseError):
    """Raised when an empty answer is submitted."""

    def __init__(self):
        super().__init__(
            message="Answer cannot be empty",
            frontend_message="Answer cannot be empty.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


# ========== MCQ Quiz Errors ==========


class NoMcqQuestionsAvailableError(BaseError):
    """Raised when no MCQ questions are available for a game."""

    def __init__(self):
        super().__init__(
            message="No MCQ questions available in the database",
            frontend_message="No MCQ questions available. Please seed the database.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class InvalidChoiceIndexError(BaseError):
    """Raised when an invalid choice index is submitted."""

    def __init__(self, choice_index: int):
        super().__init__(
            message=f"Invalid choice index: {choice_index}. Must be 0-3.",
            frontend_message="Invalid answer selection.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"choice_index": choice_index},
        )


# ========== Notebook (Kunnash) Errors ==========


class NotebookGameTypeNotSupportedError(BaseError):
    """The game's words cannot be kept: an MCQ round is a question, not a word."""

    def __init__(self, game_id: UUID | str, game_type: str):
        super().__init__(
            message=f"Words from game {game_id} ({game_type}) cannot be kept in the notebook",
            frontend_message="Words from this game can't be kept in your notebook.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"game_id": str(game_id), "game_type": game_type},
        )


class TermNotInGameError(BaseError):
    """A word was asked to be kept from a game that never dealt it."""

    def __init__(self, game_id: UUID | str, term: str):
        super().__init__(
            message=f"Term {term!r} was not part of game {game_id}",
            frontend_message="That word was not part of this game.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"game_id": str(game_id), "term": term},
        )


class NotebookEntryNotFoundError(BaseError):
    """No notebook entry with this id belongs to the caller.

    Also what another user's entry answers — a 403 would confirm the id exists.
    """

    def __init__(self, entry_id: UUID | str):
        super().__init__(
            message=f"Notebook entry {entry_id} not found",
            frontend_message="This word is not in your notebook.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"entry_id": str(entry_id)},
        )


class InvalidNotebookCursorError(BaseError):
    """The `cursor` of a notebook page is not one the server handed out."""

    def __init__(self, cursor: str):
        super().__init__(
            message=f"Invalid notebook cursor {cursor!r}",
            frontend_message="This page of your notebook could not be loaded.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"cursor": cursor},
        )


# ========== Word of the day (كلمة اليوم) Errors ==========
# None of them carries the word: they answer moves made before the reveal, too.


class DailyWordAlreadyFinishedError(BaseError):
    """A hint, guess or give-up on a word of the day the caller already solved or gave up."""

    def __init__(self, day: object):
        super().__init__(
            message=f"The word of the day {day} is already finished for this player",
            frontend_message="You have already finished today's word.",
            status_code=status.HTTP_409_CONFLICT,
            details={"day": str(day)},
        )


class DailyWordNoMoreHintsError(BaseError):
    """Another hint was asked for while every rung of the ladder is already revealed."""

    def __init__(self, day: object, max_hints: int):
        super().__init__(
            message=f"Every one of the {max_hints} hints of the word of the day {day} is already revealed",
            frontend_message="Every hint is already revealed.",
            status_code=status.HTTP_409_CONFLICT,
            details={"day": str(day), "max_hints": max_hints},
        )


class DailyWordNotFinishedError(BaseError):
    """Keeping a word of the day the caller has not finished: keeping it would reveal it."""

    def __init__(self, day: object):
        super().__init__(
            message=f"The word of the day {day} is not finished for this player",
            frontend_message="Find the word, or give up, before keeping it.",
            status_code=status.HTTP_409_CONFLICT,
            details={"day": str(day)},
        )


class DailyWordNotTodayError(BaseError):
    """A move on a day that is not today in Makkah — a page left open past midnight there.

    Without the check, a guess typed for yesterday's word would be judged against
    today's and counted as a wrong try on it.
    """

    def __init__(self, day: object, today: object):
        super().__init__(
            message=f"The word of the day {day} is over; today is {today}",
            frontend_message="A new word of the day is out.",
            status_code=status.HTTP_409_CONFLICT,
            details={"day": str(day), "today": str(today)},
        )


class InvalidLeaderboardSortError(BaseError):
    """The leaderboard was asked to rank by something it does not rank by."""

    def __init__(self, stat_field: str):
        super().__init__(
            message=f"Invalid leaderboard sort {stat_field!r}",
            frontend_message="The leaderboard cannot be sorted that way.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"stat_field": stat_field},
        )


# ========== Rate limiting ==========


class RateLimitExceededError(BaseError):
    """Too many requests for one endpoint in its window (slowapi's RateLimitExceeded).

    Raised by nothing: the 429 handler builds one so the body carries the same
    envelope — and an ``error_key`` the client translates — as every other error.
    """

    def __init__(self, limit: str):
        super().__init__(
            message=f"Rate limit exceeded: {limit}",
            frontend_message="Too many requests. Please wait a moment and try again.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"limit": limit},
        )


# ========== Prayer pause (وقفة الصلاة) Errors ==========


class GamePausedError(BaseError):
    """A move was attempted while the host has paused the game for the prayer."""

    def __init__(self, game_id: UUID | str):
        super().__init__(
            message=f"Game {game_id} is paused; no move is accepted until the host resumes it",
            frontend_message="The game is paused for the prayer.",
            status_code=status.HTTP_409_CONFLICT,
            details={"game_id": str(game_id)},
        )


class GameAlreadyPausedError(BaseError):
    """The host asked to pause a game that is already paused."""

    def __init__(self, game_id: UUID | str):
        super().__init__(
            message=f"Game {game_id} is already paused",
            frontend_message="The game is already paused.",
            status_code=status.HTTP_409_CONFLICT,
            details={"game_id": str(game_id)},
        )


class GameNotPausedError(BaseError):
    """The host asked to resume a game that is not paused."""

    def __init__(self, game_id: UUID | str):
        super().__init__(
            message=f"Game {game_id} is not paused",
            frontend_message="The game is not paused.",
            status_code=status.HTTP_409_CONFLICT,
            details={"game_id": str(game_id)},
        )


class OnlyHostCanPauseError(BaseError):
    """Someone other than the room's current host tried to pause or resume."""

    def __init__(self, user_id: UUID | str, game_id: UUID | str):
        super().__init__(
            message=f"User {user_id} is not the host of game {game_id} and cannot pause or resume it",
            frontend_message="Only the host can pause or resume the game.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"user_id": str(user_id), "game_id": str(game_id)},
        )


class SpectatorCannotPauseError(BaseError):
    """A spectator tried to pause a game they are only watching."""

    def __init__(self, user_id: UUID | str, game_id: UUID | str):
        super().__init__(
            message=f"Spectator {user_id} cannot pause game {game_id}",
            frontend_message="Spectators cannot pause the game.",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"user_id": str(user_id), "game_id": str(game_id)},
        )


# ─── Errors that used to be raised as a bare BaseError ──────────────────────────
#
# A bare `BaseError(...)` carries the key `errors.api.base`, which no locale can
# translate (its message varies), so Arabic and French players read the English
# `frontend_message`. Each of these keeps the old `message` (what logs and tests
# match on) and `frontend_message` (the client's fallback), and adds its own key.


class RoomHasActiveGameError(BaseError):
    """A game is started in a room that already has one running."""

    def __init__(self, room_id: UUID | str):
        super().__init__(
            message=f"Room {room_id} already has an active game",
            frontend_message="A game is already in progress.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"room_id": str(room_id)},
        )


class NotRoomHostError(BaseError):
    """A host-only action (start, kick, settings, rematch, delete) by someone else."""

    def __init__(self, message: str = "Only the host can do this.", frontend_message: str | None = None):
        super().__init__(
            message=message,
            frontend_message=frontend_message or "Only the host can do this.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class NotAGamePlayerError(BaseError):
    """The caller (or the player named) is not one of the game's players."""

    def __init__(self, message: str, status_code: int = status.HTTP_403_FORBIDDEN):
        super().__init__(
            message=message,
            frontend_message="You are not a player in this game.",
            status_code=status_code,
        )


class RoundNotInResultsError(BaseError):
    """A quiz round is advanced (or marked ready) before its results are shown."""

    def __init__(self) -> None:
        super().__init__(
            message="Can only advance from results phase.",
            frontend_message="Can only advance from results phase.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class GameNotInRoomError(BaseError):
    """An Undercover next-round names a room the game does not belong to."""

    def __init__(self, game_id: UUID | str, room_id: UUID | str):
        super().__init__(
            message=f"Game {game_id} does not belong to room {room_id}",
            frontend_message="This game does not belong to this room.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"game_id": str(game_id), "room_id": str(room_id)},
        )


class RoundNotResolvedError(BaseError):
    """The next Undercover round is requested before the current one has its elimination."""

    def __init__(self, game_id: UUID | str):
        super().__init__(
            message=f"Game {game_id}: the current round is not resolved yet",
            frontend_message="The current round is not over yet.",
            status_code=status.HTTP_409_CONFLICT,
            details={"game_id": str(game_id)},
        )


class NotDescribingPhaseError(BaseError):
    """A description arrives outside the describing phase."""

    def __init__(self) -> None:
        super().__init__(
            message="Not in description phase.",
            frontend_message="Not in description phase.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class AllDescriptionsSubmittedError(BaseError):
    """A description arrives after everyone has described."""

    def __init__(self) -> None:
        super().__init__(
            message="All descriptions already submitted.",
            frontend_message="All descriptions already submitted.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class NotYourTurnToDescribeError(BaseError):
    """A description from a player whose turn it is not."""

    def __init__(self) -> None:
        super().__init__(
            message="Not your turn to describe.",
            frontend_message="Not your turn to describe.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class InvalidDescriptionWordError(BaseError):
    """An Undercover description that is not one word of at most ``max_length`` characters."""

    def __init__(self, max_length: int):
        super().__init__(
            message=f"Word must be a single word (no spaces), max {max_length} characters.",
            frontend_message=f"Word must be a single word (no spaces), max {max_length} characters.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_params={"max": max_length},
        )


class DescriptionsNotCompleteError(BaseError):
    """A vote arrives before everyone has described."""

    def __init__(self) -> None:
        super().__init__(
            message="Descriptions are not complete yet.",
            frontend_message="Descriptions are not complete yet.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class VoteTargetNotInGameError(BaseError):
    """A vote for someone who is not a player of this game."""

    def __init__(self) -> None:
        super().__init__(
            message="Voted player not in game.",
            frontend_message="Voted player not in game.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class AlreadyVotedError(BaseError):
    """A second vote in the same round."""

    def __init__(self) -> None:
        super().__init__(
            message="You have already voted this round.",
            frontend_message="You have already voted this round.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class NotMrWhiteGuessingPhaseError(BaseError):
    """A Mr. White guess outside the guessing phase."""

    def __init__(self) -> None:
        super().__init__(
            message="Not in Mr. White guessing phase.",
            frontend_message="Not in Mr. White guessing phase.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class NotTheMrWhiteGuesserError(BaseError):
    """A guess from anyone but the eliminated Mr. White who owes it."""

    def __init__(self) -> None:
        super().__init__(
            message="Only the eliminated Mr. White can guess.",
            frontend_message="Only the eliminated Mr. White can guess.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ClueAlreadyGivenError(BaseError):
    """A second Codenames clue in the same turn."""

    def __init__(self) -> None:
        super().__init__(
            message="A clue has already been given this turn.",
            frontend_message="A clue has already been given this turn.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class RoomCodeUnavailableError(BaseError):
    """No free room code was found (503: try again)."""

    def __init__(self, attempts: int):
        super().__init__(
            message=f"Could not allocate a free room code after {attempts} attempts",
            frontend_message="Couldn't create a room right now. Please try again.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class PlayerCannotSpectateError(BaseError):
    """A player of the running game asks to become a spectator (see backend/CLAUDE.md)."""

    def __init__(self, user_id: UUID | str, room_id: UUID | str):
        super().__init__(
            message=f"User {user_id} is an active player in room {room_id} and cannot switch to spectator",
            frontend_message="You're playing this game — leave the room to stop playing.",
            status_code=status.HTTP_409_CONFLICT,
            details={"user_id": str(user_id), "room_id": str(room_id)},
        )


class CannotKickYourselfError(BaseError):
    """The host tries to kick themself."""

    def __init__(self) -> None:
        super().__init__(
            message="You cannot kick yourself.",
            frontend_message="You cannot kick yourself.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class InviterNotInRoomError(BaseError):
    """A room invite from someone not (connected) in the room."""

    def __init__(self) -> None:
        super().__init__(
            message="You must be in the room to invite friends.",
            frontend_message="You must be in the room to invite friends.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class CanOnlyInviteFriendsError(BaseError):
    """A room invite to someone who is not a friend."""

    def __init__(self) -> None:
        super().__init__(
            message="You can only invite friends.",
            frontend_message="You can only invite friends.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class FriendAlreadyInRoomError(BaseError):
    """A room invite to someone already in the room."""

    def __init__(self) -> None:
        super().__init__(
            message="User is already in the room.",
            frontend_message="This user is already in the room.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class CannotFriendYourselfError(BaseError):
    """A friend request to oneself."""

    def __init__(self) -> None:
        super().__init__(
            message="Cannot friend yourself",
            frontend_message="You cannot send a friend request to yourself.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class FriendRequestBlockedError(BaseError):
    """A friend request across a blocked friendship (deliberately unspecific)."""

    def __init__(self) -> None:
        super().__init__(
            message="Cannot send request",
            frontend_message="Cannot send friend request.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class AlreadyFriendsError(BaseError):
    """A friend request to someone already a friend."""

    def __init__(self) -> None:
        super().__init__(
            message="Already friends",
            frontend_message="You are already friends.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class FriendRequestAlreadySentError(BaseError):
    """A second friend request while the first is pending."""

    def __init__(self) -> None:
        super().__init__(
            message="Request already sent",
            frontend_message="Friend request already sent.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class FriendRequestFailedError(BaseError):
    """A friend request lost a race on the friendship's unique constraint."""

    def __init__(self) -> None:
        super().__init__(
            message="Friend request failed",
            frontend_message="Friend request failed.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class NotYourFriendRequestError(BaseError):
    """Accepting or rejecting a request that was sent to someone else."""

    def __init__(self, action: str):
        super().__init__(
            message="Not your request",
            frontend_message=f"You can only {action} requests sent to you.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class FriendRequestNotPendingError(BaseError):
    """Accepting a request that is no longer pending."""

    def __init__(self) -> None:
        super().__init__(
            message="Request not pending",
            frontend_message="This request is not pending.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class NotYourFriendshipError(BaseError):
    """Removing a friendship one is not part of."""

    def __init__(self) -> None:
        super().__init__(
            message="Not your friendship",
            frontend_message="You are not part of this friendship.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class FriendshipNotFoundError(BaseError):
    """No friendship (or request) with this id."""

    def __init__(self) -> None:
        super().__init__(
            message="Friendship not found",
            frontend_message="Friend request not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


# Statuses whose body carries the error's `details` (validation-style errors the
# client may act on); every other status answers an empty `details`.
_DETAILED_STATUS_CODES = {400, 409, 422, 429}


def error_response(exc: BaseError) -> JSONResponse:
    """The JSON envelope every ``BaseError`` is answered with.

    ``{error, error_key, message, error_params, details, timestamp}`` — ``error_key``
    is what the client translates; ``message`` is the English fallback.
    """
    should_include_details = exc.status_code in _DETAILED_STATUS_CODES
    serializable_details = {}
    if should_include_details and exc.details:
        serializable_details = {k: str(v) if isinstance(v, UUID) else v for k, v in exc.details.items()}

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "error_key": exc.error_key,
            "message": exc.frontend_message,
            "error_params": exc.error_params,
            "details": serializable_details if should_include_details else {},
            "timestamp": exc.timestamp.isoformat(),
        },
    )

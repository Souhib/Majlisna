import re
import unicodedata
from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.constants import (
    DEFAULT_WORD_QUIZ_HINT_INTERVAL,
    DEFAULT_WORD_QUIZ_MAX_HINTS,
    DEFAULT_WORD_QUIZ_ROUNDS,
    DEFAULT_WORD_QUIZ_TURN_DURATION,
    TIMER_EXPIRATION_TOLERANCE_SECONDS,
)
from ipg.api.controllers.base_game import BaseGameController
from ipg.api.controllers.game_lock import get_game_lock
from ipg.api.controllers.wordquiz import WordQuizController
from ipg.api.models.error import (
    AlreadyAnsweredError,
    EmptyAnswerError,
    NoQuizWordsAvailableError,
    PlayerRemovedFromGameError,
    RoundNotPlayingError,
    SpectatorCannotAnswerError,
)
from ipg.api.models.game import GameCreate, GameStatus, GameType
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game, Room
from ipg.api.schemas.common import AdvanceRoundResponse, GameStartResponse, HintRecordResponse, TimerExpiredResponse
from ipg.api.schemas.error import BaseError
from ipg.api.schemas.wordquiz import (
    SubmitAnswerResponse,
    WordQuizGameState,
    WordQuizPlayerState,
    WordQuizRoundResult,
    WordQuizTimerConfig,
)

# Arabic diacritics regex for normalization
_ARABIC_DIACRITICS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e8\u06ea-\u06ed]")


class WordQuizGameController(BaseGameController):
    """REST controller for Word Quiz game logic.

    All game state stored in Game.live_state JSON column in PostgreSQL.
    Uses advisory locks per game_id for concurrency control.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self._wordquiz_controller = WordQuizController(session)

    @staticmethod
    def _normalize_answer(answer: str) -> str:
        """Normalize an answer for comparison: strip diacritics, lowercase, collapse whitespace, remove hyphens/prefixes."""
        text = answer.strip()
        text = _ARABIC_DIACRITICS.sub("", text)
        # NFD decomposition splits accented Latin chars: ï → i + combining diaeresis, é → e + combining acute
        text = unicodedata.normalize("NFD", text)
        # Strip only Latin combining diacritical marks (U+0300–U+036F), preserving Arabic combining chars
        text = re.sub(r"[\u0300-\u036f]", "", text)
        # NFC recompose remaining characters (Arabic: alef + hamza → alef-with-hamza)
        text = unicodedata.normalize("NFC", text)
        text = text.lower()
        # Remove hyphens so "Al-Aqsa" matches "Al Aqsa" and vice versa
        text = text.replace("-", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _strip_article(text: str) -> str:
        """Strip common Arabic article prefix 'al ' for fuzzy matching."""
        if text.startswith("al "):
            return text[3:]
        return text

    @staticmethod
    def _answers_match(a: str, b: str) -> bool:
        """Compare two normalized answers, also trying without the 'al ' prefix."""
        if a == b:
            return True
        # Try stripping "al " from both sides for flexible matching
        a_stripped = WordQuizGameController._strip_article(a)
        b_stripped = WordQuizGameController._strip_article(b)
        return a_stripped == b_stripped

    @staticmethod
    def _check_answer(answer: str, word: dict) -> bool:
        """Check if the normalized answer matches any accepted form of the word."""
        normalized = WordQuizGameController._normalize_answer(answer)
        if not normalized:
            return False

        # Check direct word fields
        for field in ("word_en", "word_ar", "word_fr"):
            value = word.get(field)
            if value and WordQuizGameController._answers_match(
                WordQuizGameController._normalize_answer(value), normalized
            ):
                return True

        # Check accepted_answers lists
        accepted = word.get("accepted_answers") or {}
        for lang_answers in accepted.values():
            if isinstance(lang_answers, list):
                for variant in lang_answers:
                    if WordQuizGameController._answers_match(
                        WordQuizGameController._normalize_answer(variant), normalized
                    ):
                        return True

        return False

    async def create_and_start(self, room_id: UUID, user_id: UUID) -> GameStartResponse:
        """Start a new Word Quiz game in the given room."""
        async with get_game_lock(f"room:{room_id}", self.session):
            db_room, player_users = await self._prepare_game_start(room_id)

            num_players = len(player_users)

            # Read settings from room
            room_settings = getattr(db_room, "settings", None) or {}
            total_rounds = room_settings.get("word_quiz_rounds", DEFAULT_WORD_QUIZ_ROUNDS)
            turn_duration = room_settings.get("word_quiz_turn_duration", DEFAULT_WORD_QUIZ_TURN_DURATION)
            hint_interval = room_settings.get("word_quiz_hint_interval", DEFAULT_WORD_QUIZ_HINT_INTERVAL)

            # Pick first word
            random_words = await self._wordquiz_controller.get_random_words(1)
            if not random_words:
                raise NoQuizWordsAvailableError()
            first_word = random_words[0]

            players = [
                {
                    "user_id": str(u.id),
                    "username": u.username,
                    "total_score": 0,
                }
                for u in player_users
            ]

            live_state = {
                "players": players,
                "current_round": 1,
                "total_rounds": total_rounds,
                "current_word_id": str(first_word.id),
                "current_word": {
                    "word_en": first_word.word_en,
                    "word_ar": first_word.word_ar,
                    "word_fr": first_word.word_fr,
                    "accepted_answers": first_word.accepted_answers,
                },
                "hints": first_word.hints,
                "explanation": first_word.explanation,
                "hints_revealed": 1,
                "round_started_at": datetime.now(UTC).isoformat(),
                "hint_interval_seconds": hint_interval,
                "turn_duration_seconds": turn_duration,
                "round_phase": "playing",
                "answers": {},
                "round_results": [],
                "used_word_ids": [str(first_word.id)],
                "game_over": False,
                "winner": None,
                "hint_usage": {},
            }

            db_game = await self._game_controller.create_game(
                GameCreate(
                    room_id=db_room.id,
                    number_of_players=num_players,
                    type=GameType.WORD_QUIZ,
                    game_configurations={
                        "total_rounds": total_rounds,
                        "turn_duration": turn_duration,
                        "hint_interval": hint_interval,
                    },
                )
            )

            db_game.live_state = live_state
            db_game.game_status = GameStatus.IN_PROGRESS
            flag_modified(db_game, "live_state")
            self.session.add(db_game)

            db_room.active_game_id = db_game.id
            self.session.add(db_room)

            await self.session.commit()

            return GameStartResponse(
                game_id=str(db_game.id),
                room_id=str(db_room.id),
            )

    @staticmethod
    def _calculate_hints_revealed(state: dict) -> int:
        """Calculate how many hints should be revealed based on elapsed time."""
        max_hints = DEFAULT_WORD_QUIZ_MAX_HINTS
        if state["round_phase"] != "playing" or not state.get("round_started_at"):
            return state.get("hints_revealed", 1)
        hint_interval = state.get("hint_interval_seconds", DEFAULT_WORD_QUIZ_HINT_INTERVAL)
        if hint_interval <= 0:
            return max_hints
        started = datetime.fromisoformat(state["round_started_at"])
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - started).total_seconds()
        return min(max_hints, int(elapsed / hint_interval) + 1)

    @staticmethod
    def _resolve_hints(state: dict, lang: str) -> list[str]:
        """Resolve ALL hint dicts to strings in the requested language.

        Returns all hints so the client can control display timing locally
        using round_started_at and hint_interval_seconds.
        """
        hints_dict = state.get("hints", {})
        resolved = []
        for i in range(1, DEFAULT_WORD_QUIZ_MAX_HINTS + 1):
            hint_data = hints_dict.get(str(i), {})
            if not hint_data:
                break
            if isinstance(hint_data, dict):
                text = hint_data.get(lang) or hint_data.get("en") or next(iter(hint_data.values()), "")
            else:
                text = str(hint_data)
            resolved.append(text)
        return resolved

    @staticmethod
    def _build_player_states(state: dict) -> list[WordQuizPlayerState]:
        """Build player state list from live_state."""
        answers = state.get("answers", {})
        result = []
        for p in state["players"]:
            p_answer = answers.get(p["user_id"])
            result.append(
                WordQuizPlayerState(
                    user_id=p["user_id"],
                    username=p["username"],
                    total_score=p["total_score"],
                    current_round_answered=p_answer is not None,
                    current_round_points=p_answer["points"] if p_answer else 0,
                    answered_at_hint=p_answer["hint_number"] if p_answer else None,
                )
            )
        return result

    async def get_state(
        self, game_id: UUID, user_id: UUID, lang: str = "en", update_heartbeat: bool = True
    ) -> WordQuizGameState:
        """Get full game state for a player or spectator."""
        game = await self._get_game(game_id)
        state = game.live_state

        player = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
        is_spectator = await self._check_spectator(game, user_id, player)

        if update_heartbeat:
            await self._update_heartbeat_throttled(game.room_id, user_id)

        is_host = await self._check_is_host(game.room_id, user_id)
        hints_revealed = self._calculate_hints_revealed(state)
        resolved_hints = self._resolve_hints(state, lang)
        player_states = self._build_player_states(state)

        # Current player state
        answers = state.get("answers", {})
        my_answer = answers.get(str(user_id)) if not is_spectator else None
        my_answered = my_answer is not None
        my_points = my_answer["points"] if my_answer else 0

        # Round results, correct answer, and explanation — only visible during results/game_over
        round_results, correct_answer, explanation = self._build_round_results(state, lang)

        leaderboard = sorted(player_states, key=lambda p: p.total_score, reverse=True)

        return WordQuizGameState(
            game_id=str(game.id),
            room_id=str(game.room_id),
            is_host=is_host,
            is_spectator=is_spectator,
            current_round=state["current_round"],
            total_rounds=state["total_rounds"],
            round_phase=state["round_phase"],
            hints_revealed=hints_revealed,
            hints=resolved_hints,
            turn_duration_seconds=state.get("turn_duration_seconds", DEFAULT_WORD_QUIZ_TURN_DURATION),
            hint_interval_seconds=state.get("hint_interval_seconds", DEFAULT_WORD_QUIZ_HINT_INTERVAL),
            round_started_at=state.get("round_started_at"),
            players=player_states,
            my_answered=my_answered,
            my_points=my_points,
            round_results=round_results,
            correct_answer=correct_answer,
            explanation=explanation,
            winner=state.get("winner"),
            leaderboard=leaderboard,
            game_over=state.get("game_over", False),
            timer_config=WordQuizTimerConfig(
                turn_duration_seconds=state.get("turn_duration_seconds", DEFAULT_WORD_QUIZ_TURN_DURATION),
                hint_interval_seconds=state.get("hint_interval_seconds", DEFAULT_WORD_QUIZ_HINT_INTERVAL),
            ),
            ready_players=state.get("ready_players", []),
            ready_count=len(state.get("ready_players", [])),
            total_players=len(state["players"]),
        )

    async def submit_answer(self, game_id: UUID, user_id: UUID, answer: str) -> SubmitAnswerResponse:
        """Submit an answer for the current round."""
        logger.info("WordQuiz answer: game={} user={}", game_id, user_id)
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = game.live_state

            if state["round_phase"] != "playing":
                raise RoundNotPlayingError()

            player = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
            if not player:
                # Check if spectator
                link = (
                    await self.session.exec(
                        select(RoomUserLink)
                        .where(RoomUserLink.room_id == game.room_id)
                        .where(RoomUserLink.user_id == user_id)
                        .where(RoomUserLink.is_spectator == True)  # noqa: E712
                    )
                ).first()
                if link:
                    raise SpectatorCannotAnswerError(user_id=user_id)
                raise PlayerRemovedFromGameError(user_id=str(user_id), game_id=str(game_id))

            answers = state.setdefault("answers", {})
            if str(user_id) in answers:
                raise AlreadyAnsweredError(user_id=user_id)

            if not answer.strip():
                raise EmptyAnswerError()

            # Calculate current hint based on server time
            max_hints = DEFAULT_WORD_QUIZ_MAX_HINTS
            hint_interval = state.get("hint_interval_seconds", DEFAULT_WORD_QUIZ_HINT_INTERVAL)
            started = datetime.fromisoformat(state["round_started_at"])
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            elapsed = (datetime.now(UTC) - started).total_seconds()
            current_hint = max_hints if hint_interval <= 0 else min(max_hints, int(elapsed / hint_interval) + 1)

            correct = self._check_answer(answer, state["current_word"])
            points = 0

            if correct:
                points = max_hints - current_hint + 1
                answers[str(user_id)] = {
                    "correct": True,
                    "points": points,
                    "hint_number": current_hint,
                    "answer_time_ms": int(elapsed * 1000),
                }
                player["total_score"] += points
            else:
                # Wrong answer — don't record, allow retry
                game.live_state = state
                flag_modified(game, "live_state")
                self.session.add(game)
                await self.session.commit()
                return SubmitAnswerResponse(correct=False, points_earned=0, hint_number=current_hint)

            # Check if all players answered
            all_answered = len(answers) == len(state["players"])
            if all_answered:
                self._transition_to_results(state)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return SubmitAnswerResponse(correct=True, points_earned=points, hint_number=current_hint)

    async def handle_timer_expired(self, game_id: UUID, user_id: UUID) -> TimerExpiredResponse:
        """Handle timer expiration — transition to results phase."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = game.live_state

            if state["round_phase"] != "playing":
                return TimerExpiredResponse(game_id=str(game_id), action="not_playing")

            # Verify timer actually expired server-side
            if not self._is_timer_actually_expired(state):
                return TimerExpiredResponse(game_id=str(game_id), action="timer_not_expired")

            self._transition_to_results(state)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return TimerExpiredResponse(game_id=str(game_id), action="results")

    async def advance_to_next_round(self, game_id: UUID, user_id: UUID) -> AdvanceRoundResponse:
        """Advance to the next round or finalize the game.

        Host can always advance immediately. Non-host marks themselves as ready;
        round advances when all players are ready.
        """
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = game.live_state

            if state["round_phase"] != "results":
                raise BaseError(
                    message="Can only advance from results phase.",
                    frontend_message="Can only advance from results phase.",
                    status_code=400,
                )

            is_host = await self._check_is_host(game.room_id, user_id)
            total_players = len(state["players"])

            # Non-host: mark as ready
            if not is_host:
                ready_players = state.setdefault("ready_players", [])
                if str(user_id) not in ready_players:
                    ready_players.append(str(user_id))

                # Check if all players are now ready
                if len(ready_players) < total_players:
                    game.live_state = state
                    flag_modified(game, "live_state")
                    self.session.add(game)
                    await self.session.commit()
                    return AdvanceRoundResponse(
                        game_id=str(game_id),
                        room_id=str(game.room_id),
                        advanced=False,
                        ready_players=ready_players,
                        ready_count=len(ready_players),
                        total_players=total_players,
                    )
                # All ready — fall through to advance

            await self._do_advance_round(game, state)

        return AdvanceRoundResponse(
            game_id=str(game_id),
            room_id=str(game.room_id),
            advanced=True,
            ready_players=[],
            ready_count=total_players,
            total_players=total_players,
        )

    async def _do_advance_round(self, game: Game, state: dict) -> None:
        """Actually advance the round or end the game. Commits to DB."""
        current_round = state["current_round"]
        total_rounds = state["total_rounds"]

        # Clear ready_players for the new round
        state["ready_players"] = []

        if current_round >= total_rounds:
            # Game over
            state["round_phase"] = "game_over"
            state["game_over"] = True
            # Determine winner
            sorted_players = sorted(state["players"], key=lambda p: p["total_score"], reverse=True)
            if sorted_players:
                state["winner"] = sorted_players[0]["username"]

            game.game_status = GameStatus.FINISHED
            game.end_time = datetime.now(UTC)
            room = (await self.session.exec(select(Room).where(Room.id == game.room_id))).first()
            if room:
                room.active_game_id = None
                self.session.add(room)

            # Process stats
            await self._process_game_end_stats(state)
        else:
            # Pick new word
            used_ids = state.get("used_word_ids", [])
            random_words = await self._wordquiz_controller.get_random_words(1, exclude_ids=used_ids)
            if not random_words:
                random_words = await self._wordquiz_controller.get_random_words(1)
            if not random_words:
                raise NoQuizWordsAvailableError()
            new_word = random_words[0]

            state["current_round"] = current_round + 1
            state["current_word_id"] = str(new_word.id)
            state["current_word"] = {
                "word_en": new_word.word_en,
                "word_ar": new_word.word_ar,
                "word_fr": new_word.word_fr,
                "accepted_answers": new_word.accepted_answers,
            }
            state["hints"] = new_word.hints
            state["explanation"] = new_word.explanation
            state["hints_revealed"] = 1
            state["round_started_at"] = datetime.now(UTC).isoformat()
            state["round_phase"] = "playing"
            state["answers"] = {}
            state["round_results"] = []
            state["used_word_ids"].append(str(new_word.id))

        game.live_state = state
        flag_modified(game, "live_state")
        self.session.add(game)
        await self.session.commit()

    async def record_hint_view(self, game_id: UUID, user_id: UUID) -> HintRecordResponse:
        """Record that a player viewed a hint (for achievements)."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = game.live_state

            hint_usage = state.setdefault("hint_usage", {})
            user_key = str(user_id)
            current_round = str(state["current_round"])
            user_hints = hint_usage.setdefault(user_key, [])
            if current_round not in user_hints:
                user_hints.append(current_round)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return HintRecordResponse(game_id=str(game_id), recorded=True)

    def _transition_to_results(self, state: dict) -> None:
        """Transition from playing to results phase. Build round_results."""
        state["round_phase"] = "results"
        answers = state.get("answers", {})

        round_results = []
        for p in state["players"]:
            p_answer = answers.get(p["user_id"])
            if p_answer:
                round_results.append(
                    {
                        "user_id": p["user_id"],
                        "username": p["username"],
                        "answered_at_hint": p_answer["hint_number"],
                        "points": p_answer["points"],
                        "answer_time_ms": p_answer.get("answer_time_ms"),
                    }
                )
            else:
                round_results.append(
                    {
                        "user_id": p["user_id"],
                        "username": p["username"],
                        "answered_at_hint": None,
                        "points": 0,
                        "answer_time_ms": None,
                    }
                )

        # Sort by points desc, then by answer_time_ms asc
        round_results.sort(key=lambda r: (-r["points"], r.get("answer_time_ms") or float("inf")))
        state["round_results"] = round_results

    def _is_timer_actually_expired(self, state: dict) -> bool:
        """Check if the game timer has actually elapsed server-side."""
        timer_started = state.get("round_started_at")
        if not timer_started:
            return True
        turn_duration = state.get("turn_duration_seconds", DEFAULT_WORD_QUIZ_TURN_DURATION)
        started = datetime.fromisoformat(timer_started)
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - started).total_seconds()
        return elapsed >= turn_duration - TIMER_EXPIRATION_TOLERANCE_SECONDS

    def _get_correct_answer(self, state: dict, lang: str) -> str:
        """Get the correct answer in the requested language."""
        word = state.get("current_word", {})
        if lang == "ar" and word.get("word_ar"):
            return word["word_ar"]
        if lang == "fr" and word.get("word_fr"):
            return word["word_fr"]
        return word.get("word_en", "")

    def _build_round_results(self, state: dict, lang: str) -> tuple[list[WordQuizRoundResult], str | None, str | None]:
        """Build round results, correct answer, and explanation for results/game_over phases."""
        if state["round_phase"] not in ("results", "game_over"):
            return [], None, None
        correct_answer = self._get_correct_answer(state, lang)
        explanation = self._resolve_multilingual(state.get("explanation"), lang)
        round_results = [
            WordQuizRoundResult(
                user_id=rr["user_id"],
                username=rr["username"],
                answered_at_hint=rr.get("answered_at_hint"),
                points=rr["points"],
                answer_time_ms=rr.get("answer_time_ms"),
            )
            for rr in state.get("round_results", [])
        ]
        return round_results, correct_answer, explanation

    async def _process_game_end_stats(self, state: dict) -> None:
        """Update stats for all players after game ends."""
        sorted_players = sorted(state["players"], key=lambda p: p["total_score"], reverse=True)
        winner_id = sorted_players[0]["user_id"] if sorted_players else None

        for player in state["players"]:
            user_id = UUID(player["user_id"])
            won = player["user_id"] == winner_id
            try:
                await self._stats_controller.update_stats_after_game(
                    user_id=user_id, game_type="word_quiz", won=won, role="player"
                )
                logger.info("Stats updated: game=word_quiz user={}", user_id)
            except Exception:
                logger.exception("Failed to update stats for user {user_id}", user_id=user_id)

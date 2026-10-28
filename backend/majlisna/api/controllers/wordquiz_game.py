from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    DEFAULT_WORD_QUIZ_HINT_INTERVAL,
    DEFAULT_WORD_QUIZ_MAX_HINTS,
    DEFAULT_WORD_QUIZ_ROUNDS,
    DEFAULT_WORD_QUIZ_TURN_DURATION,
    HOST_USERNAME_STATE_KEY,
    TIMER_EXPIRATION_TOLERANCE_SECONDS,
    WORD_QUIZ_CATEGORY_KEYS,
    WORD_QUIZ_TYPED_ANSWER_MAX_LENGTH,
)
from majlisna.api.controllers.base_game import BaseGameController
from majlisna.api.controllers.game_end_stats import record_game_end, top_score_winners
from majlisna.api.controllers.game_lock import get_game_lock
from majlisna.api.controllers.wordquiz import WordQuizController
from majlisna.api.models.error import (
    AlreadyAnsweredError,
    EmptyAnswerError,
    NoQuizWordsAvailableError,
    PlayerRemovedFromGameError,
    RoundNotPlayingError,
    SpectatorCannotAnswerError,
)
from majlisna.api.models.game import GameCreate, GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Game, Room
from majlisna.api.schemas.common import (
    AdvanceRoundResponse,
    GameStartResponse,
    HintRecordResponse,
    PhaseTimer,
    TimerExpiredAction,
    TimerExpiredResponse,
)
from majlisna.api.schemas.error import (
    NotAGamePlayerError,
    RoundNotInResultsError,
)
from majlisna.api.schemas.wordquiz import (
    SubmitAnswerResponse,
    WordQuizCategory,
    WordQuizGameState,
    WordQuizPlayerState,
    WordQuizRoundResult,
    WordQuizTimerConfig,
)
from majlisna.api.utils.game_pause import clock_now, is_paused, parse_instant
from majlisna.api.utils.game_state import require_state
from majlisna.api.utils.text_match import answers_match, normalize_answer, strip_article


class WordQuizGameController(BaseGameController):
    """REST controller for Word Quiz game logic.

    All game state stored in Game.live_state JSON column in PostgreSQL.
    Uses advisory locks per game_id for concurrency control.
    """

    GAME_TYPE = GameType.WORD_QUIZ

    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self._wordquiz_controller = WordQuizController(session)

    @staticmethod
    def _normalize_answer(answer: str) -> str:
        """Normalize an answer for comparison. See ``utils.text_match.normalize_answer``."""
        return normalize_answer(answer)

    @staticmethod
    def _strip_article(text: str) -> str:
        """Strip common Arabic article prefix 'al ' for fuzzy matching."""
        return strip_article(text)

    @staticmethod
    def _answers_match(a: str, b: str) -> bool:
        """Compare two normalized answers, also trying without the 'al ' prefix."""
        return answers_match(a, b)

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
        """Start a new Word Quiz game in the given room. Host only."""
        async with get_game_lock(f"room:{room_id}", self.session):
            db_room, player_users = await self._prepare_game_start(room_id)
            self._require_room_host(db_room, user_id)

            num_players = len(player_users)

            # Read settings from room
            room_settings = getattr(db_room, "settings", None) or {}
            total_rounds = room_settings.get("word_quiz_rounds", DEFAULT_WORD_QUIZ_ROUNDS)
            turn_duration = room_settings.get("word_quiz_turn_duration", DEFAULT_WORD_QUIZ_TURN_DURATION)
            hint_interval = room_settings.get("word_quiz_hint_interval", DEFAULT_WORD_QUIZ_HINT_INTERVAL)
            difficulty = room_settings.get("word_quiz_difficulty")  # None/"mixed"/"easy"/"medium"/"hard"

            # Pick first word
            random_words = await self._wordquiz_controller.get_random_words(1, difficulty=difficulty)
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
                "difficulty": first_word.difficulty,
                "category": first_word.category,
                "hints": first_word.hints,
                "explanation": first_word.explanation,
                "hints_revealed": 1,
                "round_started_at": datetime.now(UTC).isoformat(),
                "hint_interval_seconds": hint_interval,
                "turn_duration_seconds": turn_duration,
                "round_phase": "playing",
                "answers": {},
                # Every answer typed this round, right or wrong, per player — shown in
                # the round's results, never before (see _record_attempt).
                "attempts": {},
                "round_results": [],
                "used_word_ids": [str(first_word.id)],
                "game_over": False,
                "winner": None,
                "hint_usage": {},
                HOST_USERNAME_STATE_KEY: await self._host_username_at_start(db_room, player_users),
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
                        "difficulty": difficulty,
                    },
                ),
                # One transaction: hold the room lock until active_game_id commits.
                commit=False,
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
        """Calculate how many hints should be revealed based on elapsed time.

        Elapsed time is read on the game's clock (``clock_now``), which stands still
        while the host has paused the game: a round paused for the prayer must not
        come back with the ladder five rungs further down.
        """
        max_hints = DEFAULT_WORD_QUIZ_MAX_HINTS
        if state["round_phase"] != "playing" or not state.get("round_started_at"):
            return state.get("hints_revealed", 1)
        hint_interval = state.get("hint_interval_seconds", DEFAULT_WORD_QUIZ_HINT_INTERVAL)
        if hint_interval <= 0:
            return max_hints
        started = datetime.fromisoformat(state["round_started_at"])
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        elapsed = (clock_now(state) - started).total_seconds()
        return min(max_hints, int(elapsed / hint_interval) + 1)

    @staticmethod
    def _resolve_hints(state: dict, lang: str, limit: int) -> list[str]:
        """Resolve the hints released so far, in the requested language.

        ``limit`` is the server's own ``_calculate_hints_revealed`` count, and it
        is load-bearing rather than cosmetic. This used to return the whole
        ladder "so the client can control display timing locally": every player
        received all six hints the instant a round began, while the score for a
        correct answer is ``max_hints - hint_number + 1`` computed from elapsed
        *server* time. Opening the network tab therefore showed the most specific
        hint at t=0 and paid 6 points for answering immediately — the same class
        of leak that got the raw game-state endpoints removed.

        The client still animates locally between hints; it just has to come back
        for each one (see the wordquiz page's hint effect).
        """
        hints_dict = state.get("hints", {})
        resolved = []
        for i in range(1, min(limit, DEFAULT_WORD_QUIZ_MAX_HINTS) + 1):
            hint_data = hints_dict.get(str(i), {})
            if not hint_data:
                break
            if isinstance(hint_data, dict):
                text = hint_data.get(lang) or hint_data.get("en") or next(iter(hint_data.values()), "")
            else:
                text = str(hint_data)
            resolved.append(text)
        # Hints come out of a JSON column — see McqQuizGameController._resolve_choices.
        return resolved  # ty: ignore[invalid-return-type]

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
        state = require_state(game)

        player = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
        is_spectator = await self._check_spectator(game, user_id, player)

        if update_heartbeat:
            await self._update_heartbeat_throttled(game.room_id, user_id)

        host_id, host_username = await self._get_room_host(game.room_id)
        is_host = host_id == user_id
        hints_revealed = self._calculate_hints_revealed(state)
        resolved_hints = self._resolve_hints(state, lang, hints_revealed)
        player_states = self._build_player_states(state)

        # Current player state
        answers = state.get("answers", {})
        my_answer = answers.get(str(user_id)) if not is_spectator else None
        my_answered = my_answer is not None
        my_points = my_answer["points"] if my_answer else 0

        # Round results, correct answer, and explanation — only visible during results/game_over
        round_results, correct_answer, explanation = self._build_round_results(state, lang)
        colophon = self._build_colophon(game, state, host_username)

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
            max_hints=DEFAULT_WORD_QUIZ_MAX_HINTS,
            difficulty=state.get("difficulty"),
            category=self._category_key(state.get("category")),
            turn_duration_seconds=state.get("turn_duration_seconds", DEFAULT_WORD_QUIZ_TURN_DURATION),
            hint_interval_seconds=state.get("hint_interval_seconds", DEFAULT_WORD_QUIZ_HINT_INTERVAL),
            round_started_at=state.get("round_started_at"),
            newly_unlocked_achievements=state.get("newly_unlocked_achievements"),
            paused=self._build_pause(game, state),
            can_pause=self._can_pause(game, state, user_id, host_id, is_spectator=is_spectator),
            can_resume=self._can_resume(game, state, user_id, host_id),
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
            total_players=self._ready_quorum(state, host_id),
            host_username=colophon.host_username,
            started_at=colophon.started_at,
            ended_at=colophon.ended_at,
        )

    @staticmethod
    def _category_key(category: object) -> WordQuizCategory | None:
        """The stored ``QuizWord.category`` label as its stable key (None when unknown)."""
        key = WORD_QUIZ_CATEGORY_KEYS.get(category) if isinstance(category, str) else None
        return WordQuizCategory(key) if key else None

    @staticmethod
    def _record_attempt(state: dict, user_id: str, typed: str, hint_number: int) -> None:
        """Count one submitted answer and keep it as the player's latest try this round."""
        attempts = state.setdefault("attempts", {})
        previous = attempts.get(user_id) or {}
        attempts[user_id] = {
            "count": int(previous.get("count", 0)) + 1,
            "last_text": typed,
            "last_hint": hint_number,
        }

    async def submit_answer(self, game_id: UUID, user_id: UUID, answer: str) -> SubmitAnswerResponse:
        """Submit an answer for the current round."""
        logger.info("WordQuiz answer: game={} user={}", game_id, user_id)
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = require_state(game)
            self._ensure_not_paused(game, state)

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
            typed = answer.strip()[:WORD_QUIZ_TYPED_ANSWER_MAX_LENGTH]
            self._record_attempt(state, str(user_id), typed, current_hint)

            if correct:
                points = max_hints - current_hint + 1
                answers[str(user_id)] = {
                    "correct": True,
                    "points": points,
                    "hint_number": current_hint,
                    "answer_time_ms": int(elapsed * 1000),
                    "answer_text": typed,
                }
                player["total_score"] += points
            else:
                # Wrong answer — not an answer (the player may retry), but kept as their
                # latest try for the round's results.
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

    def _phase_timer(self, state: dict) -> PhaseTimer | None:
        """The round's timer while it is being played; between rounds there is none.

        Same duration as ``_is_timer_actually_expired``.
        """
        started_at = state.get("round_started_at")
        if state.get("round_phase") != "playing" or not started_at:
            return None
        seconds = state.get("turn_duration_seconds", DEFAULT_WORD_QUIZ_TURN_DURATION)
        if not seconds:
            return None
        return PhaseTimer(started_at=parse_instant(started_at), duration_seconds=seconds)

    async def handle_timer_expired(self, game_id: UUID, user_id: UUID) -> TimerExpiredResponse:
        """Handle timer expiration — transition to results phase."""
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            self._check_game_in_progress(game)
            state = require_state(game)

            # No clock runs while the host has paused the game for the prayer. Not an
            # error: clients fire this from their own local timers.
            if is_paused(state):
                return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.PAUSED)

            if state["round_phase"] != "playing":
                return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.NOT_PLAYING)

            # Verify timer actually expired server-side
            if not self._is_timer_actually_expired(state):
                return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.TIMER_NOT_EXPIRED)

            self._transition_to_results(state)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return TimerExpiredResponse(game_id=str(game_id), action=TimerExpiredAction.RESULTS)

    async def advance_to_next_round(self, game_id: UUID, user_id: UUID) -> AdvanceRoundResponse:
        """Advance to the next round or finalize the game.

        Host can always advance immediately. Non-host marks themselves as ready;
        round advances when all players are ready.
        """
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            self._check_game_in_progress(game)
            state = require_state(game)
            self._ensure_not_paused(game, state)

            if state["round_phase"] != "results":
                raise RoundNotInResultsError()

            # Non-host must be a player in this game
            host_id = await self._get_room_owner_id(game.room_id)
            is_host = host_id == user_id
            if not is_host:
                player = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
                if not player:
                    raise NotAGamePlayerError(message=f"User {user_id} is not a player in this game.")
            # Paired with ready_count, so it reports what readiness is measured
            # against — everyone but the host. See BaseGameController._ready_quorum.
            total_players = self._ready_quorum(state, host_id)

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

            # Process stats and achievements
            newly_unlocked = await self._process_game_end_stats(state)
            if newly_unlocked:
                state["newly_unlocked_achievements"] = newly_unlocked
        else:
            # Pick new word
            used_ids = state.get("used_word_ids", [])
            game_difficulty = game.game_configurations.get("difficulty") if game.game_configurations else None
            random_words = await self._wordquiz_controller.get_random_words(
                1, exclude_ids=used_ids, difficulty=game_difficulty
            )
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
            state["difficulty"] = new_word.difficulty
            state["category"] = new_word.category
            state["hints"] = new_word.hints
            state["explanation"] = new_word.explanation
            state["hints_revealed"] = 1
            state["round_started_at"] = datetime.now(UTC).isoformat()
            state["round_phase"] = "playing"
            state["answers"] = {}
            state["attempts"] = {}
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
            # Hint views feed achievements ("won without hints"), so they must not
            # be accepted after the game has ended — the end-of-game stats have
            # already been computed from hint_usage.
            self._check_game_in_progress(game)
            state = require_state(game)

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
        attempts = state.get("attempts", {})

        round_results: list[dict] = []
        for p in state["players"]:
            p_answer = answers.get(p["user_id"])
            p_attempts = attempts.get(p["user_id"]) or {}
            if p_answer:
                round_results.append(
                    {
                        "user_id": p["user_id"],
                        "username": p["username"],
                        "answered_at_hint": p_answer["hint_number"],
                        "points": p_answer["points"],
                        "answer_time_ms": p_answer.get("answer_time_ms"),
                        "typed_answer": p_answer.get("answer_text"),
                        # Rows from before attempts were counted still found it once.
                        "attempts": p_attempts.get("count", 1),
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
                        "typed_answer": p_attempts.get("last_text"),
                        "attempts": p_attempts.get("count", 0),
                    }
                )

        # Sort by points desc, then by answer_time_ms asc. `round_results` is a
        # `list[dict]` of live_state JSON; `points` is an int written just above.
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
                typed_answer=rr.get("typed_answer"),
                attempts=rr.get("attempts", 0),
            )
            for rr in state.get("round_results", [])
        ]
        return round_results, correct_answer, explanation

    async def _process_game_end_stats(self, state: dict) -> list[dict]:
        """Stage the end-of-game stat and achievement writes. See game_end_stats.

        The quizzes used to update stats but never run the achievement check, so a
        player who only played quizzes had their counters rise while no badge ever
        unlocked. Hint tracking stays off: the quizzes have their own progressive
        hint mechanic, which is not what `games_without_hints` counts.
        """
        return await record_game_end(
            self.session,
            state,
            game_type="word_quiz",
            winners=top_score_winners(state["players"]),
            track_hints=False,
        )

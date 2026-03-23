from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.constants import (
    DEFAULT_MCQ_QUIZ_ROUNDS,
    DEFAULT_MCQ_QUIZ_TURN_DURATION,
    TIMER_EXPIRATION_TOLERANCE_SECONDS,
)
from ipg.api.controllers.base_game import BaseGameController
from ipg.api.controllers.game_lock import get_game_lock
from ipg.api.controllers.mcqquiz import McqQuizController
from ipg.api.models.error import (
    AlreadyAnsweredError,
    InvalidChoiceIndexError,
    NoMcqQuestionsAvailableError,
    PlayerRemovedFromGameError,
    RoundNotPlayingError,
    SpectatorCannotAnswerError,
)
from ipg.api.models.game import GameCreate, GameStatus, GameType
from ipg.api.models.mcqquiz import McqQuestion
from ipg.api.models.relationship import RoomUserLink
from ipg.api.models.table import Game, Room
from ipg.api.schemas.common import AdvanceRoundResponse, GameStartResponse, TimerExpiredResponse
from ipg.api.schemas.error import BaseError
from ipg.api.schemas.mcqquiz import (
    McqQuizGameState,
    McqQuizPlayerState,
    McqQuizRoundResult,
    McqSubmitAnswerResponse,
)


class McqQuizGameController(BaseGameController):
    """REST controller for MCQ Quiz game logic.

    All game state stored in Game.live_state JSON column in PostgreSQL.
    Uses advisory locks per game_id for concurrency control.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session)
        self._mcqquiz_controller = McqQuizController(session)

    async def create_and_start(self, room_id: UUID, user_id: UUID) -> GameStartResponse:
        """Start a new MCQ Quiz game in the given room."""
        async with get_game_lock(f"room:{room_id}", self.session):
            db_room, player_users = await self._prepare_game_start(room_id)

            num_players = len(player_users)

            # Read settings from room
            room_settings = getattr(db_room, "settings", None) or {}
            total_rounds = room_settings.get("mcq_quiz_rounds", DEFAULT_MCQ_QUIZ_ROUNDS)
            turn_duration = room_settings.get("mcq_quiz_turn_duration", DEFAULT_MCQ_QUIZ_TURN_DURATION)

            # Pick all questions upfront
            random_questions = await self._mcqquiz_controller.get_random_questions(total_rounds)
            if not random_questions:
                raise NoMcqQuestionsAvailableError()

            first_question = random_questions[0]

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
                "question_ids": [str(q.id) for q in random_questions],
                "current_question": {
                    "question_en": first_question.question_en,
                    "question_ar": first_question.question_ar,
                    "question_fr": first_question.question_fr,
                    "choices": first_question.choices,
                    "correct_answer_index": first_question.correct_answer_index,
                },
                "explanation": first_question.explanation,
                "round_started_at": datetime.now(UTC).isoformat(),
                "turn_duration_seconds": turn_duration,
                "round_phase": "playing",
                "answers": {},
                "round_results": [],
                "game_over": False,
                "winner": None,
            }

            db_game = await self._game_controller.create_game(
                GameCreate(
                    room_id=db_room.id,
                    number_of_players=num_players,
                    type=GameType.MCQ_QUIZ,
                    game_configurations={
                        "total_rounds": total_rounds,
                        "turn_duration": turn_duration,
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

    async def get_state(
        self, game_id: UUID, user_id: UUID, lang: str = "en", update_heartbeat: bool = True
    ) -> McqQuizGameState:
        """Get full game state for a player or spectator."""
        game = await self._get_game(game_id)
        state = game.live_state

        player = next((p for p in state["players"] if p["user_id"] == str(user_id)), None)
        is_spectator = await self._check_spectator(game, user_id, player)

        if update_heartbeat:
            await self._update_heartbeat_throttled(game.room_id, user_id)

        is_host = await self._check_is_host(game.room_id, user_id)
        player_states = self._build_player_states(state)

        # Current player state
        answers = state.get("answers", {})
        my_answer = answers.get(str(user_id)) if not is_spectator else None
        my_answered = my_answer is not None
        my_points = my_answer["points"] if my_answer else 0

        # Resolve question and choices to language
        question_text = self._resolve_question(state, lang)
        choices = self._resolve_choices(state, lang)

        # Round results, correct_answer_index, and explanation — only visible during results/game_over
        round_results, correct_answer_index, explanation = self._build_round_results(state, lang)

        leaderboard = sorted(player_states, key=lambda p: p.total_score, reverse=True)

        return McqQuizGameState(
            game_id=str(game.id),
            room_id=str(game.room_id),
            is_host=is_host,
            is_spectator=is_spectator,
            current_round=state["current_round"],
            total_rounds=state["total_rounds"],
            round_phase=state["round_phase"],
            question=question_text,
            choices=choices,
            correct_answer_index=correct_answer_index,
            explanation=explanation,
            turn_duration_seconds=state.get("turn_duration_seconds", DEFAULT_MCQ_QUIZ_TURN_DURATION),
            round_started_at=state.get("round_started_at"),
            players=player_states,
            my_answered=my_answered,
            my_points=my_points,
            round_results=round_results,
            winner=state.get("winner"),
            leaderboard=leaderboard,
            game_over=state.get("game_over", False),
            ready_players=state.get("ready_players", []),
            ready_count=len(state.get("ready_players", [])),
            total_players=len(state["players"]),
        )

    async def submit_answer(self, game_id: UUID, user_id: UUID, choice_index: int) -> McqSubmitAnswerResponse:
        """Submit an answer for the current round. One attempt only."""
        logger.info("McqQuiz answer: game={} user={}", game_id, user_id)
        async with get_game_lock(str(game_id), self.session):
            game = await self._get_game(game_id)
            state = game.live_state

            if state["round_phase"] != "playing":
                raise RoundNotPlayingError()

            if choice_index < 0 or choice_index > 3:
                raise InvalidChoiceIndexError(choice_index=choice_index)

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

            correct_index = state["current_question"]["correct_answer_index"]
            correct = choice_index == correct_index

            # Calculate points: 1 base + up to 2 bonus for fast answers
            if correct:
                elapsed = (datetime.now(UTC) - datetime.fromisoformat(state["round_started_at"])).total_seconds()
                turn_duration = state.get("turn_duration_seconds", DEFAULT_MCQ_QUIZ_TURN_DURATION)
                if turn_duration > 0:
                    time_ratio = max(0, 1 - elapsed / turn_duration)
                    bonus = round(time_ratio * 2)
                else:
                    bonus = 0
                points = 1 + bonus  # 1-3 points
            else:
                points = 0

            answers[str(user_id)] = {
                "choice_index": choice_index,
                "correct": correct,
                "points": points,
            }

            if correct:
                player["total_score"] += points

            # Check if all players answered → auto-transition to results
            all_answered = len(answers) == len(state["players"])
            if all_answered:
                self._transition_to_results(state)

            game.live_state = state
            flag_modified(game, "live_state")
            self.session.add(game)
            await self.session.commit()

        return McqSubmitAnswerResponse(correct=correct, points_earned=points)

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
            # Pick next pre-selected question
            question_ids = state.get("question_ids", [])
            next_question_id = question_ids[current_round] if current_round < len(question_ids) else None

            if next_question_id:
                q = (
                    await self.session.exec(select(McqQuestion).where(McqQuestion.id == UUID(next_question_id)))
                ).first()
            else:
                q = None

            if not q:
                # Fallback: pick a random question
                random_questions = await self._mcqquiz_controller.get_random_questions(1)
                q = random_questions[0] if random_questions else None

            if not q:
                raise NoMcqQuestionsAvailableError()

            state["current_round"] = current_round + 1
            state["current_question"] = {
                "question_en": q.question_en,
                "question_ar": q.question_ar,
                "question_fr": q.question_fr,
                "choices": q.choices,
                "correct_answer_index": q.correct_answer_index,
            }
            state["explanation"] = q.explanation
            state["round_started_at"] = datetime.now(UTC).isoformat()
            state["round_phase"] = "playing"
            state["answers"] = {}
            state["round_results"] = []

        game.live_state = state
        flag_modified(game, "live_state")
        self.session.add(game)
        await self.session.commit()

    # ── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_question(state: dict, lang: str) -> str:
        """Resolve question text to the requested language."""
        q = state.get("current_question", {})
        if lang == "ar" and q.get("question_ar"):
            return q["question_ar"]
        if lang == "fr" and q.get("question_fr"):
            return q["question_fr"]
        return q.get("question_en", "")

    @staticmethod
    def _resolve_choices(state: dict, lang: str) -> list[str]:
        """Resolve choice dicts to strings in the requested language."""
        q = state.get("current_question", {})
        choices_dict = q.get("choices", {})
        resolved = []
        for i in range(4):
            choice_data = choices_dict.get(str(i), {})
            if isinstance(choice_data, dict):
                text = choice_data.get(lang) or choice_data.get("en") or next(iter(choice_data.values()), "")
            else:
                text = str(choice_data)
            resolved.append(text)
        return resolved

    @staticmethod
    def _build_player_states(state: dict) -> list[McqQuizPlayerState]:
        """Build player state list from live_state."""
        answers = state.get("answers", {})
        result = []
        for p in state["players"]:
            p_answer = answers.get(p["user_id"])
            result.append(
                McqQuizPlayerState(
                    user_id=p["user_id"],
                    username=p["username"],
                    total_score=p["total_score"],
                    current_round_answered=p_answer is not None,
                    current_round_points=p_answer["points"] if p_answer else 0,
                )
            )
        return result

    def _build_round_results(self, state: dict, lang: str) -> tuple[list[McqQuizRoundResult], int | None, str | None]:
        """Build round results, correct_answer_index, and explanation for results/game_over phases."""
        if state["round_phase"] not in ("results", "game_over"):
            return [], None, None
        correct_answer_index = state["current_question"]["correct_answer_index"]
        explanation = self._resolve_multilingual(state.get("explanation"), lang)
        round_results = [
            McqQuizRoundResult(
                user_id=rr["user_id"],
                username=rr["username"],
                chose_correct=rr["chose_correct"],
                points=rr["points"],
            )
            for rr in state.get("round_results", [])
        ]
        return round_results, correct_answer_index, explanation

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
                        "chose_correct": p_answer["correct"],
                        "points": p_answer["points"],
                    }
                )
            else:
                round_results.append(
                    {
                        "user_id": p["user_id"],
                        "username": p["username"],
                        "chose_correct": False,
                        "points": 0,
                    }
                )

        # Sort by points desc
        round_results.sort(key=lambda r: -r["points"])
        state["round_results"] = round_results

    def _is_timer_actually_expired(self, state: dict) -> bool:
        """Check if the game timer has actually elapsed server-side."""
        timer_started = state.get("round_started_at")
        if not timer_started:
            return True
        turn_duration = state.get("turn_duration_seconds", DEFAULT_MCQ_QUIZ_TURN_DURATION)
        started = datetime.fromisoformat(timer_started)
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - started).total_seconds()
        return elapsed >= turn_duration - TIMER_EXPIRATION_TOLERANCE_SECONDS

    async def _process_game_end_stats(self, state: dict) -> None:
        """Update stats for all players after game ends."""
        sorted_players = sorted(state["players"], key=lambda p: p["total_score"], reverse=True)
        winner_id = sorted_players[0]["user_id"] if sorted_players else None

        for player in state["players"]:
            user_id = UUID(player["user_id"])
            won = player["user_id"] == winner_id
            try:
                await self._stats_controller.update_stats_after_game(
                    user_id=user_id, game_type="mcq_quiz", won=won, role="player"
                )
                logger.info("Stats updated: game=mcq_quiz user={}", user_id)
            except Exception:
                logger.exception("Failed to update stats for user {user_id}", user_id=user_id)

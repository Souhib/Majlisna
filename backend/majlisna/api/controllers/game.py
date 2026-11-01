from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import selectinload
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import DEFAULT_LANGUAGE
from majlisna.api.controllers.stats import did_user_win
from majlisna.api.controllers.term_script import TermScriptController
from majlisna.api.models.error import GameNotFoundError, RoomIsNotActiveError
from majlisna.api.models.game import GameCreate, GameStatus, GameType, GameUpdate
from majlisna.api.models.relationship import RoomGameLink, UserGameLink
from majlisna.api.models.room import RoomType
from majlisna.api.models.table import Game, Room
from majlisna.api.schemas.error import GameStillInProgressError, NotAGameParticipantError
from majlisna.api.schemas.game import (
    ClueGuess,
    ClueHistoryEntry,
    EliminatedInfo,
    GameHistoryEntry,
    GameSummary,
    GameSummaryPlayer,
    UndercoverWordExplanations,
    VoteHistoryEntry,
    VoteRound,
)
from majlisna.api.utils.multilingual import resolve_multilingual


class GameController:
    def __init__(self, session: AsyncSession):
        self.session = session
        self._term_script_controller = TermScriptController(session)

    async def _persist(self, *, commit: bool) -> None:
        """Commit when running standalone, or only flush when part of a caller's transaction.

        Passing commit=False lets a caller (e.g. create_and_start, which holds a room
        advisory lock) keep everything in ONE transaction so the lock and the
        active_game_id write are atomic. Committing mid-way would release the lock early.
        """
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

    async def create_game(self, game_create: GameCreate, *, commit: bool = True) -> Game:
        """
        Create a game. If the room is not active, raise an RoomIsNotActiveError exception.

        :param game_create: The game to create.
        :param commit: Commit when True (default); flush only when the caller owns the transaction.
        :return: The created game.
        """
        new_game = Game(**game_create.model_dump())
        room: Room = (
            await self.session.exec(select(Room).where(Room.id == new_game.room_id).options(selectinload(Room.users)))  # ty: ignore[invalid-argument-type]
        ).one()
        if room.type != RoomType.ACTIVE:
            raise RoomIsNotActiveError(room_id=room.id)
        self.session.add(new_game)
        await self.session.flush()
        await self.session.refresh(new_game)
        room_game_link = RoomGameLink(room_id=new_game.room_id, game_id=new_game.id)
        for user in room.users:
            user_game_link = UserGameLink(user_id=user.id, game_id=new_game.id)
            self.session.add(user_game_link)
        self.session.add(room_game_link)
        await self._persist(commit=commit)
        return new_game

    async def get_games(self) -> Sequence[Game]:
        """
        Get all games. If no games exist, return an empty list.

        :return: A list of all games.
        """
        return (await self.session.exec(select(Game))).all()

    async def update_game(self, game_id: UUID, game_update: GameUpdate) -> Game:
        """
        Update a game. If the game does not exist, raise a NoResultFound exception.

        :param game_id: The id of the game to update.
        :param game_update: The updated game.
        :return: The updated game.
        """
        db_game = (await self.session.exec(select(Game).where(Game.id == game_id))).one()
        db_game_data = game_update.model_dump(exclude_unset=True)
        db_game.sqlmodel_update(db_game_data)
        self.session.add(db_game)
        await self.session.commit()
        await self.session.refresh(db_game)
        return db_game

    async def end_game(self, game_id: UUID) -> Game:
        """
        End a game. If the game does not exist, raise a NoResultFound exception.

        :param game_id: The id of the game to end.
        :return: The ended game.
        """
        db_game = (await self.session.exec(select(Game).where(Game.id == game_id))).one()
        db_game.end_time = datetime.now(UTC)
        self.session.add(db_game)
        await self.session.commit()
        await self.session.refresh(db_game)
        return db_game

    async def delete_game(self, game_id: UUID) -> None:
        """
        Delete a game. If the game does not exist, raise a NoResultFound exception. If the room is not active, raise an RoomIsNotActiveError exception.

        :param game_id: The id of the game to delete.
        :return: None
        """
        db_game = (await self.session.exec(select(Game).where(Game.id == game_id))).one()
        await self.session.delete(db_game)
        await self.session.commit()

    async def get_games_by_user(
        self, user_id: UUID, limit: int = 20, *, requester_id: UUID | None = None
    ) -> Sequence[GameHistoryEntry]:
        """Get a user's game history with enriched data, most recent first.

        :param user_id: The id of the user whose history is requested.
        :param limit: Maximum number of results to return.
        :param requester_id: The authenticated caller. When it differs from
            ``user_id``, games that are still IN_PROGRESS are excluded: each entry
            carries ``user_role``, which for a live game is the subject's secret
            Undercover role. Without this filter an opponent could read
            ``/games/user/{victim_id}`` mid-game and learn who the undercover is.
        :return: A list of enriched GameHistoryEntry records.
        """
        statement = (
            select(Game).join(UserGameLink, Game.id == UserGameLink.game_id).where(UserGameLink.user_id == user_id)  # ty: ignore[invalid-argument-type]
        )
        if requester_id is not None and requester_id != user_id:
            statement = statement.where(Game.game_status != GameStatus.IN_PROGRESS)
        results = await self.session.exec(statement.order_by(desc(Game.start_time)).limit(limit))
        games = results.all()
        str_uid = str(user_id)
        entries: list[GameHistoryEntry] = []
        for game in games:
            state = game.live_state or {}
            winner = state.get("winner")
            game_status = game.game_status.value if game.game_status else None
            player = next((p for p in state.get("players", []) if p.get("user_id") == str_uid), None)
            user_role = player.get("role") if player else None
            # The same resolver as the chart and head-to-head, so the quizzes finally
            # show Won / Lost too (BR-19); null for a leaver or a solo game.
            user_won = did_user_win(game, user_id)

            entries.append(
                GameHistoryEntry(
                    id=game.id,
                    type=game.type,
                    start_time=game.start_time,
                    end_time=game.end_time,
                    number_of_players=game.number_of_players,
                    winner=winner,
                    user_role=user_role,
                    user_won=user_won,
                    game_status=game_status,
                )
            )
        return entries

    async def get_past_game_for_participant(self, game_id: UUID, requester_id: UUID) -> Game:
        """The game, once it is no longer running, for a caller who took part in it.

        The single gate for every read of a game's secrets after the fact — the
        summary and the notebook both reveal the words — answering the two
        questions any such endpoint must ask:

        * did this caller take part? (``UserGameLink``; ``NotAGameParticipantError``, 403);
        * is the game over? While it is IN_PROGRESS the words and roles are the
          secret the game is played for (``GameStillInProgressError``, 403).

        Participation is checked FIRST: the two answers carry different error keys,
        so asking a stranger "is it over?" first told them whether a game they never
        played is still running.

        :raises GameNotFoundError: no such game (404).
        """
        game = (await self.session.exec(select(Game).where(Game.id == game_id))).first()
        if not game:
            raise GameNotFoundError(game_id=game_id)

        participant = (
            await self.session.exec(
                select(UserGameLink).where(UserGameLink.game_id == game_id).where(UserGameLink.user_id == requester_id)
            )
        ).first()
        if participant is None:
            raise NotAGameParticipantError(game_id=game_id, user_id=requester_id)

        if game.game_status == GameStatus.IN_PROGRESS:
            raise GameStillInProgressError(game_id=game_id)
        return game

    async def get_game_summary(self, game_id: UUID, requester_id: UUID, lang: str = DEFAULT_LANGUAGE) -> GameSummary:
        """Get a detailed game summary for the post-game detail modal.

        This response deliberately contains every player's role plus the secret
        Undercover words and the full Codenames clue history, so it is gated
        twice:

        * the game must be OVER — while it is IN_PROGRESS this endpoint would be
          a straight cheat vector (read the summary, learn who the undercover is
          and what the civilian word is), bypassing the sanitised per-role
          ``get_state``;
        * the caller must have taken part in the game (``UserGameLink``), so one
          player cannot read the roles of a game they were never in.

        :param game_id: The id of the game.
        :param requester_id: The authenticated caller.
        :param lang: The language the words' meanings are resolved in (``resolve_multilingual``).
        :return: A GameSummary with full player list and history.
        """
        game = await self.get_past_game_for_participant(game_id, requester_id)

        state = game.live_state or {}
        players_data = state.get("players", [])

        summary_players = []
        for p in players_data:
            summary_players.append(
                GameSummaryPlayer(
                    user_id=p.get("user_id", ""),
                    username=p.get("username", ""),
                    role=p.get("role", ""),
                    team=p.get("team"),
                )
            )

        vote_history: list[VoteRound] | None = None
        clue_history: list[ClueHistoryEntry] | None = None
        word_explanations: UndercoverWordExplanations | None = None

        if game.type == GameType.UNDERCOVER:
            # Build vote history from turns
            turns = state.get("turns", [])
            eliminated = state.get("eliminated_players", [])
            players_map = {p.get("user_id", ""): p.get("username", "") for p in players_data}
            history: list[VoteRound] = []
            for i, turn in enumerate(turns):
                votes = turn.get("votes", {})
                if not votes:
                    continue
                vote_entries = [
                    VoteHistoryEntry(voter=players_map.get(vid, ""), target=players_map.get(tid, ""))
                    for vid, tid in votes.items()
                ]
                raw_elim = next((e for e in eliminated if e.get("round") == i + 1), None)
                if raw_elim is None and i < len(eliminated) and "round" not in eliminated[i]:
                    raw_elim = eliminated[i]  # pre-"round" rows: fall back to position
                elim_info = (
                    EliminatedInfo(
                        username=raw_elim.get("username", ""),
                        role=raw_elim.get("role", ""),
                        user_id=raw_elim.get("user_id"),
                    )
                    if raw_elim
                    else None
                )
                history.append(VoteRound(round=i + 1, votes=vote_entries, eliminated=elim_info))
            vote_history = history

            civilian_word = state.get("civilian_word")
            undercover_word = state.get("undercover_word")
            # One lookup for the pair. The game is over (checked above), so both
            # words — and therefore both Arabic forms — are public.
            scripts = await self._term_script_controller.get_forms([civilian_word, undercover_word])
            civilian_script = scripts.get(civilian_word) if civilian_word else None
            undercover_script = scripts.get(undercover_word) if undercover_word else None
            word_explanations = UndercoverWordExplanations(
                civilian_word=civilian_word,
                civilian_word_ar=civilian_script.ar if civilian_script else None,
                civilian_word_ar_vocalized=civilian_script.ar_vocalized if civilian_script else None,
                civilian_word_hint=resolve_multilingual(state.get("civilian_word_hint"), lang),
                undercover_word=undercover_word,
                undercover_word_ar=undercover_script.ar if undercover_script else None,
                undercover_word_ar_vocalized=undercover_script.ar_vocalized if undercover_script else None,
                undercover_word_hint=resolve_multilingual(state.get("undercover_word_hint"), lang),
            )

        elif game.type == GameType.CODENAMES:
            raw_clues = state.get("clue_history", [])
            word_hints = state.get("word_hints") or {}
            # One lookup for every guessed word across the whole history.
            scripts = await self._term_script_controller.get_forms(
                g.get("word") for c in raw_clues for g in c.get("guesses", [])
            )
            clue_history = [
                ClueHistoryEntry(
                    team=c.get("team", ""),
                    clue_word=c.get("clue_word", ""),
                    clue_number=c.get("clue_number", 0),
                    guesses=[
                        ClueGuess(
                            word=g.get("word", ""),
                            word_ar=scripts[g["word"]].ar if g.get("word") in scripts else None,
                            word_ar_vocalized=scripts[g["word"]].ar_vocalized if g.get("word") in scripts else None,
                            hint=resolve_multilingual(word_hints.get(g.get("word", "")), lang),
                            card_type=g.get("card_type", ""),
                            correct=g.get("correct", False),
                        )
                        for g in c.get("guesses", [])
                    ],
                )
                for c in raw_clues
            ]

        return GameSummary(
            id=game.id,
            type=game.type,
            start_time=game.start_time,
            end_time=game.end_time,
            number_of_players=game.number_of_players,
            winner=state.get("winner"),
            game_status=game.game_status.value if game.game_status else None,
            players=summary_players,
            vote_history=vote_history,
            clue_history=clue_history,
            word_explanations=word_explanations,
        )

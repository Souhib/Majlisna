from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload
from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.models.error import GameNotFoundError, NoTurnInsideGameError, RoomIsNotActiveError
from ipg.api.models.event import EventCreate
from ipg.api.models.game import GameCreate, GameUpdate
from ipg.api.models.relationship import GameTurnLink, RoomGameLink, TurnEventLink, UserGameLink
from ipg.api.models.room import RoomType
from ipg.api.models.table import Event, Game, Room, Turn
from ipg.api.schemas.game import GameHistoryEntry


class GameController:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_game(self, game_create: GameCreate) -> Game:
        """
        Create a game. If the room is not active, raise an RoomIsNotActiveError exception.

        :param game_create: The game to create.
        :return: The created game.
        """
        new_game = Game(**game_create.model_dump())
        room: Room = (
            await self.session.exec(select(Room).where(Room.id == new_game.room_id).options(selectinload(Room.users)))
        ).one()
        if room.type != RoomType.ACTIVE:
            raise RoomIsNotActiveError(room_id=room.id)  # type: ignore
        self.session.add(new_game)
        await self.session.commit()
        await self.session.refresh(new_game)
        room_game_link = RoomGameLink(room_id=new_game.room_id, game_id=new_game.id)
        for user in room.users:
            user_game_link = UserGameLink(user_id=user.id, game_id=new_game.id)
            self.session.add(user_game_link)
        self.session.add(room_game_link)
        await self.session.commit()
        return new_game

    async def get_games(self) -> Sequence[Game]:
        """
        Get all games. If no games exist, return an empty list.

        :return: A list of all games.
        """
        return (await self.session.exec(select(Game))).all()

    async def get_game_by_id(self, game_id: UUID) -> Game:
        """
        Get a game by its id. If the game does not exist, raise a NoResultFound exception.

        :param game_id: The id of the game to get.
        :return: The game.
        """
        return (
            await self.session.exec(
                select(Game).where(Game.id == game_id).options(selectinload(Game.turns), selectinload(Game.room))
            )
        ).one()

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
        db_game.end_time = datetime.now()
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

    async def get_games_by_user(self, user_id: UUID, limit: int = 20) -> Sequence[GameHistoryEntry]:
        """Get a user's game history, most recent first.

        :param user_id: The id of the user.
        :param limit: Maximum number of results to return.
        :return: A list of GameHistoryEntry records.
        """
        results = await self.session.exec(
            select(Game)
            .join(UserGameLink, Game.id == UserGameLink.game_id)
            .where(UserGameLink.user_id == user_id)
            .order_by(desc(Game.start_time))
            .limit(limit)
        )
        games = results.all()
        entries: list[GameHistoryEntry] = []
        for game in games:
            entries.append(
                GameHistoryEntry(
                    id=game.id,  # type: ignore[arg-type]
                    type=game.type,
                    start_time=game.start_time,
                    end_time=game.end_time,
                    number_of_players=game.number_of_players,
                )
            )
        return entries

    async def create_turn(self, game_id: UUID) -> Turn:
        """
        Create a turn. If the game does not exist, raise a NoResultFound exception.

        :param game_id: The id of the game to create a turn for.
        :return: None
        """
        try:
            db_game = (await self.session.exec(select(Game).where(Game.id == game_id))).one()
            turn = Turn(
                game_id=db_game.id,
            )
            self.session.add(turn)
            await self.session.commit()
            await self.session.refresh(turn)
            turn_game_link = GameTurnLink(game_id=db_game.id, turn_id=turn.id)
            self.session.add(turn_game_link)
            await self.session.commit()
            return turn
        except NoResultFound:
            raise GameNotFoundError(game_id=game_id) from None

    async def create_turn_event(self, game_id: UUID, event_create: EventCreate) -> Event:
        """
        Create an event. If the game does not exist, raise a NoResultFound exception.

        :param game_id: The id of the game to create an event for.
        :param event_create: The event to create.
        :return: Event (TurnEvent or RoomEvent)
        """
        try:
            db_game = (
                await self.session.exec(select(Game).where(Game.id == game_id).options(selectinload(Game.turns)))
            ).one()
            if not db_game.turns:
                raise NoTurnInsideGameError(game_id=game_id)
            latest_turn = (
                await self.session.exec(select(Turn).where(Turn.game_id == db_game.id).order_by(desc(Turn.start_time)))
            ).first()
            event = Event(
                turn_id=latest_turn.id,
                name=event_create.name,
                data=event_create.data,
                user_id=event_create.user_id,
            )
            self.session.add(event)
            await self.session.commit()
            await self.session.refresh(event)
            turn_event_link = TurnEventLink(turn_id=latest_turn.id, event_id=event.id)
            self.session.add(turn_event_link)
            await self.session.commit()
            return event
        except NoResultFound:
            raise GameNotFoundError(game_id=game_id) from None

    async def get_latest_turn(self, game_id: UUID) -> Turn:
        """
        Get the latest turn. If the game does not exist, raise a NoResultFound exception.

        :param game_id: The id of the game to get the latest turn for.
        :return: Turn
        """
        try:
            db_game = (
                await self.session.exec(select(Game).where(Game.id == game_id).options(selectinload(Game.turns)))
            ).one()
            if not db_game.turns:
                raise NoTurnInsideGameError(game_id=game_id)
            return (
                await self.session.exec(select(Turn).where(Turn.game_id == db_game.id).order_by(desc(Turn.start_time)))
            ).first()
        except NoResultFound:
            raise GameNotFoundError(game_id=game_id) from None

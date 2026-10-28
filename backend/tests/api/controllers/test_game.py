import datetime
from uuid import uuid4

import pytest
from freezegun import freeze_time
from sqlalchemy.exc import NoResultFound
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.game import GameController
from majlisna.api.models.event import EventCreate
from majlisna.api.models.game import GameCreate, GameStatus, GameType, GameUpdate
from majlisna.api.models.room import RoomType
from majlisna.api.models.table import Room, User
from majlisna.api.schemas.error import (
    GameNotFoundError,
    GameStillInProgressError,
    NotAGameParticipantError,
    NoTurnInsideGameError,
    RoomIsNotActiveError,
)


async def test_create_game_success(sample_room: Room, game_controller: GameController):
    """Creating a game in an active room returns a Game with all fields correctly populated."""
    # Arrange
    game_create = GameCreate(room_id=sample_room.id, type=GameType.UNDERCOVER, number_of_players=4)

    # Act
    game = await game_controller.create_game(game_create)

    # Assert
    assert game.id is not None
    assert game.room_id == sample_room.id
    assert game.type == GameType.UNDERCOVER
    assert game.number_of_players == 4
    assert game.start_time is not None
    assert game.end_time is None


async def test_create_game_inactive_room(
    create_user, create_room, game_controller: GameController, session: AsyncSession
):
    """Creating a game in an inactive room raises RoomIsNotActiveError."""
    # Arrange
    owner = await create_user(username="owner", email="owner@test.com")
    room = await create_room(owner=owner)
    db_room = (await session.exec(select(Room).where(Room.id == room.id))).one()
    db_room.type = RoomType.INACTIVE
    session.add(db_room)
    await session.commit()

    # Act & Assert
    with pytest.raises(RoomIsNotActiveError):
        await game_controller.create_game(GameCreate(room_id=room.id, type=GameType.UNDERCOVER, number_of_players=4))


async def test_get_games_empty(game_controller: GameController):
    """Getting all games when none exist returns an empty list."""
    # Arrange
    # (no games created)

    # Act
    games = await game_controller.get_games()

    # Assert
    assert len(games) == 0


async def test_get_games_multiple(sample_room: Room, game_controller: GameController):
    """Getting all games after creating two returns a list of length 2."""
    # Arrange
    await game_controller.create_game(GameCreate(room_id=sample_room.id, type=GameType.UNDERCOVER, number_of_players=4))
    await game_controller.create_game(GameCreate(room_id=sample_room.id, type=GameType.CODENAMES, number_of_players=6))

    # Act
    games = await game_controller.get_games()

    # Assert
    assert len(games) == 2


async def test_get_game_by_id_success(sample_room: Room, game_controller: GameController):
    """Getting a game by its ID returns the correct game with all fields matching."""
    # Arrange
    game_create = GameCreate(room_id=sample_room.id, type=GameType.UNDERCOVER, number_of_players=4)
    created_game = await game_controller.create_game(game_create)

    # Act
    found_game = await game_controller.get_game_by_id(created_game.id)

    # Assert
    assert found_game.id == created_game.id
    assert found_game.room_id == created_game.room_id
    assert found_game.type == created_game.type
    assert found_game.number_of_players == created_game.number_of_players
    assert found_game.start_time == created_game.start_time
    assert found_game.end_time is None


async def test_get_game_by_id_not_found(game_controller: GameController):
    """Getting a game by a non-existent ID raises NoResultFound."""
    # Arrange
    non_existent_id = uuid4()

    # Act & Assert
    with pytest.raises(NoResultFound):
        await game_controller.get_game_by_id(non_existent_id)


async def test_update_game_success(sample_game, game_controller: GameController):
    """Updating a game's number_of_players changes it while leaving other fields unchanged."""
    # Arrange
    original_type = sample_game.type

    # Act
    updated_game = await game_controller.update_game(sample_game.id, GameUpdate(number_of_players=8))

    # Assert
    assert updated_game.number_of_players == 8
    assert updated_game.type == original_type


async def test_end_game_success(sample_game, game_controller: GameController):
    """Ending a game sets end_time to the current datetime."""
    # Arrange
    now = datetime.datetime.now()

    # Act
    with freeze_time(now):
        ended_game = await game_controller.end_game(sample_game.id)

    # Assert
    assert ended_game.end_time is not None


async def test_delete_game_success(sample_game, game_controller: GameController):
    """Deleting a game removes it so that get_game_by_id raises NoResultFound."""
    # Arrange
    game_id = sample_game.id

    # Act
    await game_controller.delete_game(game_id)

    # Assert
    with pytest.raises(NoResultFound):
        await game_controller.get_game_by_id(game_id)


async def test_create_turn_success(sample_game, game_controller: GameController):
    """Creating a turn for an existing game returns a Turn with all fields correctly populated."""
    # Arrange
    game_id = sample_game.id

    # Act
    turn = await game_controller.create_turn(game_id)

    # Assert
    assert turn.id is not None
    assert turn.game_id == game_id
    assert turn.start_time is not None
    assert turn.completed is False


async def test_create_turn_game_not_found(game_controller: GameController):
    """Creating a turn for a non-existent game raises GameNotFoundError."""
    # Arrange
    non_existent_id = uuid4()

    # Act & Assert
    with pytest.raises(GameNotFoundError):
        await game_controller.create_turn(non_existent_id)


async def test_create_turn_event_success(sample_owner, sample_game, game_controller: GameController):
    """Creating an event for an existing turn returns an Event with all fields correctly populated."""
    # Arrange
    turn = await game_controller.create_turn(sample_game.id)
    event_create = EventCreate(name="vote", data={"target": "player1"}, user_id=sample_owner.id)

    # Act
    event = await game_controller.create_turn_event(sample_game.id, event_create)

    # Assert
    assert event.id is not None
    assert event.name == "vote"
    assert event.data == {"target": "player1"}
    assert event.turn_id == turn.id
    assert event.user_id == sample_owner.id


async def test_create_turn_event_no_turn(sample_owner, sample_game, game_controller: GameController):
    """Creating an event for a game with no turns raises NoTurnInsideGameError."""
    # Arrange
    event_create = EventCreate(name="vote", data={}, user_id=sample_owner.id)

    # Act & Assert
    with pytest.raises(NoTurnInsideGameError):
        await game_controller.create_turn_event(sample_game.id, event_create)


async def test_create_turn_event_game_not_found(game_controller: GameController):
    """Creating an event for a non-existent game raises GameNotFoundError."""
    # Arrange
    non_existent_id = uuid4()
    event_create = EventCreate(name="vote", data={}, user_id=uuid4())

    # Act & Assert
    with pytest.raises(GameNotFoundError):
        await game_controller.create_turn_event(non_existent_id, event_create)


async def test_get_latest_turn_success(sample_game, game_controller: GameController):
    """Getting the latest turn after creating three returns the third turn."""
    # Arrange
    await game_controller.create_turn(sample_game.id)
    await game_controller.create_turn(sample_game.id)
    turn3 = await game_controller.create_turn(sample_game.id)

    # Act
    latest = await game_controller.get_latest_turn(sample_game.id)

    # Assert
    assert latest.id == turn3.id


async def test_get_latest_turn_no_turns(sample_game, game_controller: GameController):
    """Getting the latest turn for a game with no turns raises NoTurnInsideGameError."""
    # Arrange
    game_id = sample_game.id

    # Act & Assert
    with pytest.raises(NoTurnInsideGameError):
        await game_controller.get_latest_turn(game_id)


# ========== get_game_summary authorization ==========
#
# The summary payload contains every player's role plus the secret Undercover
# words, so it is gated on (a) the game being over and (b) the caller having
# taken part. Without those gates any authenticated user could read it mid-game
# and learn who the undercover is — the same leak that got the raw
# GET /games/{id} endpoint removed.


async def test_get_game_summary_rejects_in_progress_game(
    sample_owner: User, sample_game, game_controller: GameController, session: AsyncSession
):
    """A summary for a game that is still IN_PROGRESS is refused, even to a participant."""
    # Arrange
    sample_game.game_status = GameStatus.IN_PROGRESS
    sample_game.live_state = {
        "players": [{"user_id": str(sample_owner.id), "username": "owner", "role": "undercover"}],
        "civilian_word": "mosque",
        "undercover_word": "church",
    }
    session.add(sample_game)
    await session.commit()

    # Act & Assert
    with pytest.raises(GameStillInProgressError):
        await game_controller.get_game_summary(sample_game.id, sample_owner.id)


async def test_get_game_summary_rejects_non_participant(
    sample_owner: User, sample_game, create_user, game_controller: GameController, session: AsyncSession
):
    """A user who never played the game cannot read its summary."""
    # Arrange
    outsider = await create_user(username="outsider", email="outsider@test.com")
    sample_game.game_status = GameStatus.FINISHED
    sample_game.live_state = {
        "players": [{"user_id": str(sample_owner.id), "username": "owner", "role": "undercover"}],
        "civilian_word": "mosque",
        "undercover_word": "church",
    }
    session.add(sample_game)
    await session.commit()

    # Act & Assert
    with pytest.raises(NotAGameParticipantError):
        await game_controller.get_game_summary(sample_game.id, outsider.id)


async def test_get_game_summary_allows_participant_after_game_ends(
    sample_owner: User, sample_game, game_controller: GameController, session: AsyncSession
):
    """A participant reading a finished game gets the full summary."""
    # Arrange
    sample_game.game_status = GameStatus.FINISHED
    sample_game.live_state = {
        "players": [{"user_id": str(sample_owner.id), "username": "owner", "role": "undercover"}],
        "civilian_word": "mosque",
        "undercover_word": "church",
        "winner": "undercovers",
    }
    session.add(sample_game)
    await session.commit()

    # Act
    summary = await game_controller.get_game_summary(sample_game.id, sample_owner.id)

    # Assert
    assert summary.winner == "undercovers"
    assert summary.word_explanations is not None
    assert summary.word_explanations.civilian_word == "mosque"


async def test_get_games_by_user_hides_in_progress_games_from_others(
    sample_owner: User, sample_game, create_user, game_controller: GameController, session: AsyncSession
):
    """Another user's history omits live games — each entry carries the subject's secret role."""
    # Arrange
    spy = await create_user(username="spy", email="spy@test.com")
    sample_game.game_status = GameStatus.IN_PROGRESS
    sample_game.live_state = {
        "players": [{"user_id": str(sample_owner.id), "username": "owner", "role": "undercover"}],
    }
    session.add(sample_game)
    await session.commit()

    # Act
    as_other = await game_controller.get_games_by_user(sample_owner.id, requester_id=spy.id)
    as_self = await game_controller.get_games_by_user(sample_owner.id, requester_id=sample_owner.id)

    # Assert
    assert as_other == []
    assert len(as_self) == 1
    assert as_self[0].user_role == "undercover"


# ========== get_game_summary — Arabic term forms ==========


async def test_get_game_summary_includes_both_undercover_words_in_arabic(
    sample_owner: User, sample_game, game_controller: GameController, session: AsyncSession, create_term_scripts
):
    """A finished game's summary names both words, so it carries both Arabic forms."""
    # Arrange
    await create_term_scripts({"mosque": ("مسجد", "مَسْجِد"), "church": ("كنيسة", None)})
    sample_game.game_status = GameStatus.FINISHED
    sample_game.live_state = {
        "players": [{"user_id": str(sample_owner.id), "username": "owner", "role": "undercover"}],
        "civilian_word": "mosque",
        "undercover_word": "church",
        "winner": "civilians",
    }
    session.add(sample_game)
    await session.commit()

    # Act
    summary = await game_controller.get_game_summary(sample_game.id, sample_owner.id)

    # Assert
    explanations = summary.word_explanations
    assert explanations is not None
    assert (explanations.civilian_word_ar, explanations.civilian_word_ar_vocalized) == ("مسجد", "مَسْجِد")
    assert (explanations.undercover_word_ar, explanations.undercover_word_ar_vocalized) == ("كنيسة", None)


async def test_get_game_summary_resolves_the_meanings_in_the_requested_language(
    sample_owner: User, sample_game, game_controller: GameController, session: AsyncSession
):
    """Both Undercover meanings, and each Codenames guess's, come back in `lang` (fallback chain: lang, en, any)."""
    # Arrange
    sample_game.game_status = GameStatus.FINISHED
    sample_game.live_state = {
        "players": [{"user_id": str(sample_owner.id), "username": "owner", "role": "civilian"}],
        "civilian_word": "Sabr",
        "undercover_word": "Shukr",
        "civilian_word_hint": {"en": "Patience", "ar": "الصبر", "fr": "La patience"},
        "undercover_word_hint": {"en": "Gratitude"},  # no Arabic → English
        "winner": "civilians",
    }
    session.add(sample_game)
    await session.commit()

    # Act
    summary_ar = await game_controller.get_game_summary(sample_game.id, sample_owner.id, lang="ar")
    summary_default = await game_controller.get_game_summary(sample_game.id, sample_owner.id)

    # Assert
    assert summary_ar.word_explanations is not None
    assert summary_ar.word_explanations.civilian_word_hint == "الصبر"
    assert summary_ar.word_explanations.undercover_word_hint == "Gratitude"
    assert summary_default.word_explanations is not None
    assert summary_default.word_explanations.civilian_word_hint == "Patience"


async def test_get_game_summary_gives_each_codenames_guess_its_meaning(
    sample_owner: User, sample_game, game_controller: GameController, session: AsyncSession
):
    """A guessed card's hint is in the clue history, in the requested language."""
    # Arrange
    sample_game.type = GameType.CODENAMES
    sample_game.game_status = GameStatus.FINISHED
    sample_game.live_state = {
        "players": [{"user_id": str(sample_owner.id), "username": "owner", "role": "operative", "team": "red"}],
        "winner": "red",
        "word_hints": {"Sabr": {"en": "Patience", "fr": "La patience"}},
        "clue_history": [
            {
                "team": "red",
                "clue_word": "virtue",
                "clue_number": 1,
                "guesses": [
                    {"word": "Sabr", "card_type": "red", "correct": True},
                    {"word": "Hajj", "card_type": "neutral", "correct": False},
                ],
            }
        ],
    }
    session.add(sample_game)
    await session.commit()

    # Act
    summary = await game_controller.get_game_summary(sample_game.id, sample_owner.id, lang="fr")

    # Assert
    assert summary.clue_history is not None
    assert [(g.word, g.hint) for g in summary.clue_history[0].guesses] == [("Sabr", "La patience"), ("Hajj", None)]


async def test_get_game_summary_includes_codenames_guesses_in_arabic(
    sample_owner: User,
    sample_game,
    game_controller: GameController,
    session: AsyncSession,
    create_term_scripts,
    count_statements,
):
    """Every guessed word in the clue history gets its Arabic forms (bare + vocalised), in one lookup."""
    # Arrange
    await create_term_scripts({"Sabr": ("صبر", "صَبْر"), "Hajj": ("حج", "حَجّ"), "Uhud": ("أحد", None)})
    sample_game.type = GameType.CODENAMES
    sample_game.game_status = GameStatus.FINISHED
    sample_game.live_state = {
        "players": [{"user_id": str(sample_owner.id), "username": "owner", "role": "operative", "team": "red"}],
        "winner": "red",
        "clue_history": [
            {
                "team": "red",
                "clue_word": "virtue",
                "clue_number": 2,
                "guesses": [
                    {"word": "Sabr", "card_type": "red", "correct": True},
                    {"word": "NoArabic", "card_type": "neutral", "correct": False},
                    {"word": "Uhud", "card_type": "red", "correct": True},
                ],
            },
            {
                "team": "blue",
                "clue_word": "pilgrim",
                "clue_number": 1,
                "guesses": [{"word": "Hajj", "card_type": "blue", "correct": True}],
            },
        ],
    }
    session.add(sample_game)
    await session.commit()
    counter = count_statements("term_script")

    # Act
    summary = await game_controller.get_game_summary(sample_game.id, sample_owner.id)

    # Assert
    assert counter.count == 1
    assert summary.clue_history is not None
    guesses = [(g.word, g.word_ar, g.word_ar_vocalized) for clue in summary.clue_history for g in clue.guesses]
    assert guesses == [("Sabr", "صبر", "صَبْر"), ("NoArabic", None, None), ("Uhud", "أحد", None), ("Hajj", "حج", "حَجّ")]
    assert summary.word_explanations is None

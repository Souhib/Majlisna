"""WP-00: the shared contracts every wave-1 package builds on.

- ``game_end_stats.top_score_winners``: owner rule (a) — every top scorer above 0
  shares the win; a solo game is never a win; a 0-0 game has no winner (BR-11, PD-10).
- ``utils/game_state.mark_player_left`` / ``left_player_ids`` and the
  ``scorable_players`` filter: owner rule (b) — a player who leaves before the end
  gets neither a win nor a loss (BR-12).
- ``BaseGameController._require_participant``: hint-viewed and timer-expired answer a
  player or a spectator only (BR-13, SEC F07, SEC F08).
- ``RoomBan`` / ``AuthSession``: purged with the account; ``revoke_user_sessions``.
"""

import ipaddress
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import CLOUDFLARE_IP_RANGES, LEFT_PLAYER_IDS_KEY
from majlisna.api.controllers.base_game import BaseGameController
from majlisna.api.controllers.game import GameController
from majlisna.api.controllers.game_end_stats import record_game_end, scorable_players, top_score_winners
from majlisna.api.controllers.user import UserController
from majlisna.api.models.auth_session import AuthSession, revoke_user_sessions
from majlisna.api.models.game import GameCreate, GameStatus, GameType
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room_ban import RoomBan
from majlisna.api.models.stats import UserStats
from majlisna.api.models.table import Game, Room, User
from majlisna.api.schemas.error import (
    AnswerAttemptsExhaustedError,
    BaseError,
    ClueMustBeOneWordError,
    DescriptionRevealsWordError,
    GoogleAccountMismatchError,
    InvalidAvatarUrlError,
    NotAGameParticipantError,
    NotAnAlivePlayerError,
    PasswordTooLongError,
    RoomBannedError,
    RoomBanNotFoundError,
    SessionRevokedError,
)
from majlisna.api.utils.game_state import as_utc, left_player_ids, mark_player_left


def _scores(*scores: int) -> list[dict]:
    return [{"user_id": f"u{i}", "total_score": score} for i, score in enumerate(scores)]


# ── top_score_winners: owner rule (a) ────────────────────────────


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        pytest.param((6, 6), {"u0", "u1"}, id="a tie at the top is a shared win"),
        pytest.param((6, 6, 2), {"u0", "u1"}, id="the tie shares, the third loses"),
        pytest.param((0, 0, 0), set(), id="a 0-0 game has no winner"),
        pytest.param((5,), set(), id="a solo game is never a win"),
        pytest.param((0,), set(), id="a solo game at 0 is never a win"),
        pytest.param((7, 3), {"u0"}, id="the top scorer wins alone"),
        pytest.param((3, 7), {"u1"}, id="seat order does not matter"),
        pytest.param((), set(), id="no players"),
    ],
)
def test_top_score_winners_follows_the_owners_rule(scores: tuple[int, ...], expected: set[str]):
    """Every top scorer above 0 shares the win, over a roster of at least two."""
    # Act
    winners = top_score_winners(_scores(*scores))

    # Assert
    assert winners == expected


def test_top_score_winners_counts_the_final_roster_without_leavers():
    """A game whose other players all left is a solo game: never a win (no farming
    with a second account that leaves)."""
    # Prepare
    players = _scores(5, 0)

    # Act
    winners = top_score_winners(players, left_ids={"u1"})

    # Assert
    assert winners == set()
    assert top_score_winners(players) == {"u0"}


# ── mark_player_left / left_player_ids ───────────────────────────


def test_mark_player_left_records_each_leaver_once():
    """Kick, leave, grace sweep and account deletion may all mark the same player."""
    # Prepare
    state: dict = {"players": []}
    leaver = str(uuid4())

    # Act
    mark_player_left(state, leaver)
    mark_player_left(state, leaver)
    mark_player_left(state, "other")

    # Assert
    assert state[LEFT_PLAYER_IDS_KEY] == [leaver, "other"]
    assert left_player_ids(state) == {leaver, "other"}


def test_left_player_ids_is_empty_for_a_state_without_leavers():
    """Old rows have no key at all."""
    # Act / Assert
    assert left_player_ids({}) == set()
    assert left_player_ids({"players": [{"user_id": "u1"}]}) == set()


def test_mark_player_left_accepts_a_uuid():
    """Callers hold a UUID; the state stores strings, like every other user id in it."""
    # Prepare
    state: dict = {}
    leaver = uuid4()

    # Act
    mark_player_left(state, leaver)

    # Assert
    assert state[LEFT_PLAYER_IDS_KEY] == [str(leaver)]


# ── scorable_players skips leavers: owner rule (b) ───────────────


@pytest.mark.asyncio
async def test_scorable_players_drops_a_player_marked_as_left(session: AsyncSession, create_user):
    """An Undercover drop-out stays in ``players`` (dead); it must still not be scored."""
    # Prepare
    stayer = await create_user(username="stayer", email="stayer@test.com")
    leaver = await create_user(username="leaver", email="leaver@test.com")
    state = {
        "players": [
            {"user_id": str(stayer.id), "role": "civilian", "is_alive": True},
            {"user_id": str(leaver.id), "role": "civilian", "is_alive": False},
        ]
    }
    mark_player_left(state, leaver.id)

    # Act
    scorable = await scorable_players(session, state)

    # Assert
    assert [p["user_id"] for p in scorable] == [str(stayer.id)]


@pytest.mark.asyncio
async def test_record_game_end_writes_nothing_for_a_leaver(session: AsyncSession, create_user):
    """Neither a win nor a loss: the leaver has no stats row change at all, even on the
    winning side (an Undercover drop-out never shares the win).

    The final roster keeps two players (the stayer and the undercover they beat): one
    alone would be a solo game, never a win (`MIN_PLAYERS_FOR_A_WIN`)."""
    # Prepare
    stayer = await create_user(username="stayer", email="stayer@test.com")
    leaver = await create_user(username="leaver", email="leaver@test.com")
    loser = await create_user(username="loser", email="loser@test.com")
    state = {
        "players": [
            {"user_id": str(stayer.id), "role": "civilian", "is_alive": True},
            {"user_id": str(leaver.id), "role": "civilian", "is_alive": False},
            {"user_id": str(loser.id), "role": "undercover", "is_alive": True},
        ]
    }
    mark_player_left(state, leaver.id)

    # Act
    await record_game_end(
        session,
        state,
        game_type=GameType.UNDERCOVER.value,
        winners={str(stayer.id), str(leaver.id)},
    )
    await session.commit()

    # Assert
    session.expunge_all()
    rows = {row.user_id: row for row in (await session.exec(select(UserStats))).all()}
    assert set(rows) == {stayer.id, loser.id}
    assert rows[stayer.id].total_games_played == 1
    assert rows[stayer.id].total_games_won == 1
    assert rows[loser.id].total_games_played == 1
    assert rows[loser.id].total_games_won == 0


# ── _require_participant ─────────────────────────────────────────


async def _game_with_players(session: AsyncSession, room: Room, players: list[dict]) -> Game:
    game = await GameController(session).create_game(
        GameCreate(room_id=room.id, type=GameType.UNDERCOVER, number_of_players=3, game_status=GameStatus.IN_PROGRESS)
    )
    game.live_state = {"players": players}
    flag_modified(game, "live_state")
    session.add(game)
    await session.commit()
    return game


@pytest.fixture(name="participants")
async def get_participants(session: AsyncSession, create_user, sample_room: Room) -> dict:
    alive = await create_user(username="alive", email="alive@test.com")
    dead = await create_user(username="dead", email="dead@test.com")
    spectator = await create_user(username="watcher", email="watcher@test.com")
    stranger = await create_user(username="stranger", email="stranger@test.com")
    latecomer = await create_user(username="latecomer", email="latecomer@test.com")
    session.add(RoomUserLink(room_id=sample_room.id, user_id=spectator.id, is_spectator=True))
    # Seated in the room, but joined after the deal: not in the game.
    session.add(RoomUserLink(room_id=sample_room.id, user_id=latecomer.id, is_spectator=False))
    await session.commit()
    game = await _game_with_players(
        session,
        sample_room,
        [
            {"user_id": str(alive.id), "username": "alive", "role": "civilian", "is_alive": True},
            {"user_id": str(dead.id), "username": "dead", "role": "undercover", "is_alive": False},
        ],
    )
    return {
        "game": game,
        "alive": alive,
        "dead": dead,
        "spectator": spectator,
        "stranger": stranger,
        "latecomer": latecomer,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["alive", "dead"])
async def test_require_participant_passes_a_player_alive_or_eliminated(
    session: AsyncSession, participants: dict, who: str
):
    """An eliminated Undercover player is still in ``players`` and still takes part."""
    # Prepare
    controller = BaseGameController(session)
    game: Game = participants["game"]
    user: User = participants[who]

    # Act
    player = await controller._require_participant(game, game.live_state or {}, user.id)

    # Assert
    assert player is not None
    assert player["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_require_participant_passes_a_spectator_of_the_games_room(session: AsyncSession, participants: dict):
    """A spectator is answered (None: no player entry), unless the caller forbids it."""
    # Prepare
    controller = BaseGameController(session)
    game: Game = participants["game"]
    spectator: User = participants["spectator"]

    # Act
    allowed = await controller._require_participant(game, game.live_state or {}, spectator.id)

    # Assert
    assert allowed is None
    with pytest.raises(NotAGameParticipantError):
        await controller._require_participant(game, game.live_state or {}, spectator.id, allow_spectator=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["stranger", "latecomer"])
async def test_require_participant_refuses_anyone_else(session: AsyncSession, participants: dict, who: str):
    """A stranger, or a room member dealt no role, is not a participant (403)."""
    # Prepare
    controller = BaseGameController(session)
    game: Game = participants["game"]
    user: User = participants[who]

    # Act / Assert
    with pytest.raises(NotAGameParticipantError) as excinfo:
        await controller._require_participant(game, game.live_state or {}, user.id)
    assert excinfo.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_require_participant_ignores_a_spectator_of_another_room(
    session: AsyncSession, participants: dict, create_user, create_room
):
    """Spectating some other room is not spectating this game."""
    # Prepare
    controller = BaseGameController(session)
    game: Game = participants["game"]
    other_owner = await create_user(username="otherhost", email="otherhost@test.com")
    other_room = await create_room(owner=other_owner)
    stranger: User = participants["stranger"]
    session.add(RoomUserLink(room_id=other_room.id, user_id=stranger.id, is_spectator=True))
    await session.commit()

    # Act / Assert
    with pytest.raises(NotAGameParticipantError):
        await controller._require_participant(game, game.live_state or {}, stranger.id)


# ── RoomBan / AuthSession: purged with the account ───────────────


def _auth_session(user: User, *, revoked: bool = False) -> AuthSession:
    now = datetime.now(UTC)
    return AuthSession(
        user_id=user.id,
        expires_at=now + timedelta(days=30),
        last_refreshed_at=now,
        current_refresh_jti=uuid4().hex,
        revoked_at=now - timedelta(hours=1) if revoked else None,
    )


@pytest.mark.asyncio
async def test_deleting_a_user_purges_their_bans_and_sessions(
    session: AsyncSession, create_user, create_room, sample_owner: User
):
    """The account is gone without an FK error: bans of the user deleted, bans BY the
    user kept with ``banned_by`` nulled, sessions deleted."""
    # Prepare
    doomed = await create_user(username="doomed", email="doomed@test.com")
    victim = await create_user(username="victim", email="victim@test.com")
    doomed_room = await create_room(owner=doomed)
    host_room = await create_room(owner=sample_owner)
    ban_of_doomed = RoomBan(room_id=host_room.id, user_id=doomed.id, banned_by=sample_owner.id)
    ban_by_doomed = RoomBan(room_id=doomed_room.id, user_id=victim.id, banned_by=doomed.id)
    session.add_all([ban_of_doomed, ban_by_doomed, _auth_session(doomed), _auth_session(victim)])
    await session.commit()
    ban_of_doomed_id, ban_by_doomed_id, doomed_id, victim_id = ban_of_doomed.id, ban_by_doomed.id, doomed.id, victim.id

    # Act
    await UserController(session).delete_user(doomed_id)

    # Assert
    session.expunge_all()
    assert (await session.exec(select(User).where(User.id == doomed_id))).first() is None
    assert (await session.exec(select(RoomBan).where(RoomBan.id == ban_of_doomed_id))).first() is None
    kept_ban = (await session.exec(select(RoomBan).where(RoomBan.id == ban_by_doomed_id))).one()
    assert kept_ban.user_id == victim_id
    assert kept_ban.banned_by is None
    sessions = (await session.exec(select(AuthSession))).all()
    assert [s.user_id for s in sessions] == [victim_id]


@pytest.mark.asyncio
async def test_a_room_bans_a_user_once(session: AsyncSession, create_user, sample_room: Room):
    """``UniqueConstraint(room_id, user_id)``: a second ban of the same player fails."""
    # Prepare
    user = await create_user(username="banned", email="banned@test.com")
    session.add(RoomBan(room_id=sample_room.id, user_id=user.id, banned_by=sample_room.owner_id))
    await session.commit()

    # Act / Assert
    session.add(RoomBan(room_id=sample_room.id, user_id=user.id, banned_by=sample_room.owner_id))
    with pytest.raises(Exception, match=r"(?i)unique"):
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_revoke_user_sessions_marks_only_live_rows_and_spares_one(session: AsyncSession, create_user):
    """An UPDATE of the user's non-revoked rows, optionally sparing the caller's own."""
    # Prepare
    owner = await create_user(username="owner2", email="owner2@test.com")
    other = await create_user(username="other2", email="other2@test.com")
    kept, live, already = _auth_session(owner), _auth_session(owner), _auth_session(owner, revoked=True)
    foreign = _auth_session(other)
    session.add_all([kept, live, already, foreign])
    await session.commit()
    already_revoked_at = already.revoked_at
    ids = {"kept": kept.id, "live": live.id, "already": already.id, "foreign": foreign.id}

    # Act
    count = await revoke_user_sessions(session, owner.id, except_session_id=ids["kept"])
    await session.commit()

    # Assert
    assert count == 1
    session.expunge_all()
    rows = {row.id: row for row in (await session.exec(select(AuthSession))).all()}
    assert rows[ids["kept"]].revoked_at is None
    assert rows[ids["live"]].revoked_at is not None
    assert rows[ids["foreign"]].revoked_at is None
    already_row = rows[ids["already"]].revoked_at
    assert already_row is not None
    assert already_revoked_at is not None
    # SQLite reads the column back naive; PostgreSQL aware: compare as UTC instants.
    assert as_utc(already_row) == as_utc(already_revoked_at)


@pytest.mark.asyncio
async def test_revoke_user_sessions_without_exception_revokes_every_live_row(session: AsyncSession, create_user):
    """Password reset or "sign out everywhere": every live session of the user goes."""
    # Prepare
    owner = await create_user(username="owner3", email="owner3@test.com")
    session.add_all([_auth_session(owner), _auth_session(owner)])
    await session.commit()

    # Act
    count = await revoke_user_sessions(session, owner.id)
    await session.commit()

    # Assert
    assert count == 2
    session.expunge_all()
    assert all(row.revoked_at is not None for row in (await session.exec(select(AuthSession))).all())


# ── The new error classes and constants ──────────────────────────


@pytest.mark.parametrize(
    ("error", "status_code", "key"),
    [
        (ClueMustBeOneWordError(), 400, "errors.api.clueMustBeOneWord"),
        (DescriptionRevealsWordError(), 400, "errors.api.descriptionRevealsWord"),
        (AnswerAttemptsExhaustedError(max_attempts=5), 409, "errors.api.answerAttemptsExhausted"),
        (RoomBannedError(room_id=uuid4()), 403, "errors.api.roomBanned"),
        (RoomBanNotFoundError(room_id=uuid4(), user_id=uuid4()), 404, "errors.api.roomBanNotFound"),
        (PasswordTooLongError(max_bytes=72), 400, "errors.api.passwordTooLong"),
        (SessionRevokedError(), 401, "errors.api.sessionRevoked"),
        (NotAnAlivePlayerError(user_id=uuid4(), game_id=uuid4()), 400, "errors.api.notAnAlivePlayer"),
        (InvalidAvatarUrlError(), 400, "errors.api.invalidAvatarUrl"),
        (GoogleAccountMismatchError(), 403, "errors.api.googleAccountMismatch"),
    ],
)
def test_the_new_errors_answer_their_status_and_key(error: BaseError, status_code: int, key: str):
    """Wave-1 packages raise these by name; their translations live under ``errors.api``."""
    # Assert
    assert error.status_code == status_code
    assert error.error_key == key


def test_the_banned_message_says_the_host_removed_you():
    """The two user-facing lines the owner wrote."""
    # Assert
    assert RoomBannedError(room_id=uuid4()).frontend_message == "The host removed you from this room."
    assert SessionRevokedError().frontend_message == "You were signed out. Sign in again."


def test_cloudflare_ranges_are_valid_networks_of_both_families():
    """Every entry parses as a CIDR, and both address families are covered."""
    # Act
    networks = [ipaddress.ip_network(cidr) for cidr in CLOUDFLARE_IP_RANGES]

    # Assert
    assert {net.version for net in networks} == {4, 6}
    assert len(set(CLOUDFLARE_IP_RANGES)) == len(CLOUDFLARE_IP_RANGES)

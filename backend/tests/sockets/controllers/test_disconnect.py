"""Tests for disconnect handlers (handle_undercover_disconnect, handle_codenames_disconnect).

Uses real Redis via testcontainers. Only external services (sio, send_event_to_client) are mocked.
"""

from unittest.mock import AsyncMock, patch
from uuid import UUID

from ibg.api.constants import EVENT_CODENAMES_GAME_OVER, EVENT_GAME_CANCELLED
from ibg.api.models.undercover import UndercoverRole
from ibg.socketio.controllers.disconnect import (
    handle_codenames_disconnect,
    handle_undercover_disconnect,
)
from ibg.socketio.models.codenames import (
    CodenamesGame,
    CodenamesGameStatus,
    CodenamesRole,
    CodenamesTeam,
)
from ibg.socketio.models.room import Room as RedisRoom
from ibg.socketio.models.socket import UndercoverGame, UndercoverTurn
from tests.sockets.conftest import make_codenames_board, make_codenames_player, make_undercover_player

# Fixed UUIDs for deterministic tests
U1 = "11111111-1111-1111-1111-111111111111"
U2 = "22222222-2222-2222-2222-222222222222"
U3 = "33333333-3333-3333-3333-333333333333"
U4 = "44444444-4444-4444-4444-444444444444"
U5 = "55555555-5555-5555-5555-555555555555"

ROOM_ID = "room-dc-1"
GAME_ID = "game-dc-1"


# ========== handle_undercover_disconnect ==========


async def test_undercover_disconnect_game_not_found(make_redis_room):
    """If the Undercover game is not found in Redis, the handler returns silently."""

    # Arrange
    room = await make_redis_room(ROOM_ID, active_game_id="nonexistent")
    sio = AsyncMock()

    # Act / Assert — no exception
    await handle_undercover_disconnect(sio, U1, room)


async def test_undercover_disconnect_player_not_found(make_undercover_game, make_redis_room):
    """If the disconnected user is not in the game, the handler returns silently."""

    # Arrange
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_undercover_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        players=[make_undercover_player(U2)],
    )
    sio = AsyncMock()

    # Act — looking for U1 which is not in game
    await handle_undercover_disconnect(sio, U1, room)


async def test_undercover_disconnect_already_dead(make_undercover_game, make_redis_room):
    """If the disconnected player is already dead, the handler returns silently."""

    # Arrange
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_undercover_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        players=[make_undercover_player(U1, alive=False), make_undercover_player(U2)],
    )
    sio = AsyncMock()

    # Act
    await handle_undercover_disconnect(sio, U1, room)

    # Assert — player stays dead, game unchanged
    refreshed = await UndercoverGame.get(GAME_ID)
    p1 = next(p for p in refreshed.players if str(p.user_id) == U1)
    assert p1.is_alive is False


@patch("ibg.socketio.controllers.disconnect.send_event_to_client", new_callable=AsyncMock)
async def test_undercover_disconnect_below_minimum_cancels_game(mock_send, make_undercover_game, make_redis_room):
    """If fewer than 3 players remain alive after disconnect, the game is cancelled."""

    # Arrange — 3 alive players, disconnect 1 -> 2 alive -> below minimum
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_undercover_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        players=[
            make_undercover_player(U1),
            make_undercover_player(U2),
            make_undercover_player(U3),
        ],
    )
    sio = AsyncMock()

    # Act
    await handle_undercover_disconnect(sio, U1, room)

    # Assert — sent to each player's SID individually
    assert mock_send.await_count == 3
    for call in mock_send.call_args_list:
        assert call.args[1] == EVENT_GAME_CANCELLED

    # Verify room was cleaned up in Redis
    refreshed_room = await RedisRoom.get(ROOM_ID)
    assert refreshed_room.active_game_id is None


@patch("ibg.socketio.controllers.disconnect.send_event_to_client", new_callable=AsyncMock)
async def test_undercover_disconnect_civilians_win(mock_send, make_undercover_game, make_redis_room):
    """If all undercovers are dead after disconnect, civilians win."""

    # Arrange — 4 players: 3 civilians + 1 undercover (disconnecting)
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_undercover_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        players=[
            make_undercover_player(U1, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U2, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U3, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U4, role=UndercoverRole.UNDERCOVER),
        ],
    )
    sio = AsyncMock()

    # Act
    await handle_undercover_disconnect(sio, U4, room)

    # Assert — civilians win message sent to each player's SID
    assert mock_send.await_count == 4
    for call in mock_send.call_args_list:
        assert "civilians have won" in call.args[2]["data"]

    # Verify room was cleaned up
    refreshed_room = await RedisRoom.get(ROOM_ID)
    assert refreshed_room.active_game_id is None


@patch("ibg.socketio.controllers.disconnect.send_event_to_client", new_callable=AsyncMock)
async def test_undercover_disconnect_triggers_vote_elimination(mock_send, make_undercover_game, make_redis_room):
    """If all alive players have voted after disconnect, elimination is triggered."""

    # Arrange — 5 players with mixed roles so no team wins after elimination
    # U1 disconnects -> 4 alive, all 4 have voted -> triggers elimination of U3
    turn = UndercoverTurn(votes={UUID(U2): U3, UUID(U3): U4, UUID(U4): U3, UUID(U5): U3})

    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_undercover_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        players=[
            make_undercover_player(U1, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U2, role=UndercoverRole.MR_WHITE),
            make_undercover_player(U3, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U4, role=UndercoverRole.UNDERCOVER),
            make_undercover_player(U5, role=UndercoverRole.CIVILIAN),
        ],
        turns=[turn],
    )
    sio = AsyncMock()

    # Act
    await handle_undercover_disconnect(sio, U1, room)

    # Assert
    assert any(call.args[1] == "player_eliminated" for call in mock_send.call_args_list)


# ========== handle_codenames_disconnect ==========


async def test_codenames_disconnect_game_not_found(make_redis_room):
    """If the Codenames game is not found in Redis, the handler returns silently."""

    # Arrange
    room = await make_redis_room(ROOM_ID, active_game_id="nonexistent")
    sio = AsyncMock()

    # Act / Assert — no exception
    await handle_codenames_disconnect(sio, U1, room)


async def test_codenames_disconnect_game_not_in_progress(make_codenames_game, make_redis_room):
    """If the game is finished, the handler returns silently."""

    # Arrange
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_codenames_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        board=make_codenames_board(),
        players=[make_codenames_player(U1), make_codenames_player(U2)],
        status=CodenamesGameStatus.FINISHED,
    )
    sio = AsyncMock()

    # Act
    await handle_codenames_disconnect(sio, U1, room)

    # Assert — game state unchanged
    refreshed = await CodenamesGame.get(GAME_ID)
    assert len(refreshed.players) == 2


async def test_codenames_disconnect_player_not_found(make_codenames_game, make_redis_room):
    """If the player is not in the game, the handler returns silently."""

    # Arrange
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_codenames_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        board=make_codenames_board(),
        players=[make_codenames_player(U2)],
    )
    sio = AsyncMock()

    # Act
    await handle_codenames_disconnect(sio, U1, room)

    # Assert — game unchanged
    refreshed = await CodenamesGame.get(GAME_ID)
    assert len(refreshed.players) == 1


@patch("ibg.socketio.controllers.disconnect.send_event_to_client", new_callable=AsyncMock)
async def test_codenames_disconnect_team_empty_other_wins(mock_send, make_codenames_game, make_redis_room):
    """If the disconnecting player's team becomes empty, the other team wins."""

    # Arrange — RED team has only 1 player (disconnecting)
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_codenames_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        board=make_codenames_board(),
        players=[
            make_codenames_player(U1, CodenamesTeam.RED),
            make_codenames_player(U2, CodenamesTeam.BLUE),
        ],
    )
    sio = AsyncMock()

    # Act
    await handle_codenames_disconnect(sio, U1, room)

    # Assert
    refreshed = await CodenamesGame.get(GAME_ID)
    assert refreshed.status == CodenamesGameStatus.FINISHED
    assert refreshed.winner == CodenamesTeam.BLUE
    mock_send.assert_awaited()
    assert any(call.args[1] == EVENT_CODENAMES_GAME_OVER for call in mock_send.call_args_list)

    # Verify room cleaned up
    refreshed_room = await RedisRoom.get(ROOM_ID)
    assert refreshed_room.active_game_id is None


async def test_codenames_disconnect_spymaster_promotes_operative(make_codenames_game, make_redis_room):
    """If the spymaster disconnects, the first operative is promoted to spymaster."""

    # Arrange
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_codenames_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        board=make_codenames_board(),
        players=[
            make_codenames_player(U1, CodenamesTeam.RED, CodenamesRole.SPYMASTER),
            make_codenames_player(U2, CodenamesTeam.RED, CodenamesRole.OPERATIVE),
            make_codenames_player(U3, CodenamesTeam.RED, CodenamesRole.OPERATIVE),
            make_codenames_player(U4, CodenamesTeam.BLUE, CodenamesRole.SPYMASTER),
        ],
    )
    sio = AsyncMock()

    # Act
    await handle_codenames_disconnect(sio, U1, room)

    # Assert — operative1 should be promoted
    refreshed = await CodenamesGame.get(GAME_ID)
    remaining_red = [p for p in refreshed.players if p.team == CodenamesTeam.RED]
    assert len(remaining_red) == 2  # spymaster removed
    promoted = next(p for p in remaining_red if str(p.user_id) == U2)
    assert promoted.role == CodenamesRole.SPYMASTER


async def test_codenames_disconnect_operative_leaves_no_promotion(make_codenames_game, make_redis_room):
    """If an operative disconnects, no spymaster promotion happens."""

    # Arrange
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_codenames_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        board=make_codenames_board(),
        players=[
            make_codenames_player(U1, CodenamesTeam.RED, CodenamesRole.SPYMASTER),
            make_codenames_player(U2, CodenamesTeam.RED, CodenamesRole.OPERATIVE),
            make_codenames_player(U3, CodenamesTeam.BLUE, CodenamesRole.SPYMASTER),
        ],
    )
    sio = AsyncMock()

    # Act
    await handle_codenames_disconnect(sio, U2, room)

    # Assert
    refreshed = await CodenamesGame.get(GAME_ID)
    remaining_red = [p for p in refreshed.players if p.team == CodenamesTeam.RED]
    assert len(remaining_red) == 1
    assert remaining_red[0].role == CodenamesRole.SPYMASTER


# ========== Missing disconnect branches (coverage) ==========


@patch("ibg.socketio.controllers.disconnect.send_event_to_client", new_callable=AsyncMock)
async def test_undercover_disconnect_undercovers_win(mock_send, make_undercover_game, make_redis_room):
    """If all civilians are dead after disconnect, undercovers win (lines 80-89)."""

    # Arrange — 5 players: 2 civilians (1 disconnecting) + 2 undercovers + 1 mr_white
    # After U1 disconnects → 4 alive: U2 (dead civilian), U3 (undercover), U4 (mr_white), U5 (undercover)
    # No alive civilians → undercovers win
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_undercover_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        players=[
            make_undercover_player(U1, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U2, role=UndercoverRole.CIVILIAN, alive=False),
            make_undercover_player(U3, role=UndercoverRole.UNDERCOVER),
            make_undercover_player(U4, role=UndercoverRole.MR_WHITE),
            make_undercover_player(U5, role=UndercoverRole.UNDERCOVER),
        ],
    )
    sio = AsyncMock()

    # Act — U1 (last alive civilian) disconnects → 3 alive, undercovers win
    await handle_undercover_disconnect(sio, U1, room)

    # Assert — undercovers win sent to each player's SID
    assert mock_send.await_count == 5
    for call in mock_send.call_args_list:
        assert "undercovers have won" in call.args[2]["data"]

    refreshed_room = await RedisRoom.get(ROOM_ID)
    assert refreshed_room.active_game_id is None


@patch("ibg.socketio.controllers.disconnect.send_event_to_client", new_callable=AsyncMock)
async def test_undercover_disconnect_vote_elimination_then_undercovers_win_via_mr_white(
    mock_send, make_undercover_game, make_redis_room,
):
    """Disconnect triggers vote elimination of mr_white, then undercovers win (lines 112-125).

    After U1 (civilian) disconnects, all 3 roles still have alive representatives so the
    first win check returns None.  All 4 remaining alive players have voted for U4 (mr_white),
    so elimination triggers.  After eliminating U4: num_alive_mr_white == 0 → undercovers win.
    """

    turn = UndercoverTurn(votes={UUID(U2): U4, UUID(U3): U4, UUID(U4): U2, UUID(U5): U4})

    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_undercover_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        players=[
            make_undercover_player(U1, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U2, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U3, role=UndercoverRole.UNDERCOVER),
            make_undercover_player(U4, role=UndercoverRole.MR_WHITE),
            make_undercover_player(U5, role=UndercoverRole.CIVILIAN),
        ],
        turns=[turn],
    )
    sio = AsyncMock()

    # Act — U1 disconnects → 4 alive (all 3 roles represented → no immediate winner)
    # 4 votes ≥ 4 alive → eliminate U4 (mr_white, 3 votes)
    # After: num_alive_mr_white == 0 → undercovers win
    await handle_undercover_disconnect(sio, U1, room)

    # Assert — should see player_eliminated AND game_over
    events = [call.args[1] for call in mock_send.call_args_list]
    assert "player_eliminated" in events
    assert "game_over" in events

    game_over_call = next(c for c in mock_send.call_args_list if c.args[1] == "game_over")
    assert "undercovers have won" in game_over_call.args[2]["data"]

    refreshed_room = await RedisRoom.get(ROOM_ID)
    assert refreshed_room.active_game_id is None


@patch("ibg.socketio.controllers.disconnect.send_event_to_client", new_callable=AsyncMock)
async def test_undercover_disconnect_vote_elimination_then_undercovers_win(
    mock_send, make_undercover_game, make_redis_room,
):
    """Disconnect triggers vote elimination of last civilian, undercovers win (lines 112-125)."""

    # Arrange — U1 disconnects, remaining vote eliminates U3 (last civilian)
    turn = UndercoverTurn(votes={UUID(U2): U3, UUID(U3): U2, UUID(U4): U3})

    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_undercover_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        players=[
            make_undercover_player(U1, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U2, role=UndercoverRole.UNDERCOVER),
            make_undercover_player(U3, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U4, role=UndercoverRole.MR_WHITE),
        ],
        turns=[turn],
    )
    sio = AsyncMock()

    # Act — U1 (civilian) disconnects → 3 alive, all 3 voted
    # Eliminate U3 (civilian, 2 votes) → no civilians alive → undercovers win
    await handle_undercover_disconnect(sio, U1, room)

    # Assert
    events = [call.args[1] for call in mock_send.call_args_list]
    assert "player_eliminated" in events
    assert "game_over" in events

    game_over_call = next(c for c in mock_send.call_args_list if c.args[1] == "game_over")
    assert "undercovers have won" in game_over_call.args[2]["data"]


# ========== Extended disconnect scenarios ==========


@patch("ibg.socketio.controllers.disconnect.send_event_to_client", new_callable=AsyncMock)
async def test_codenames_disconnect_blue_team_empty_red_wins(mock_send, make_codenames_game, make_redis_room):  # noqa: ARG001
    """If the BLUE team becomes empty, RED wins."""

    # Arrange
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_codenames_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        board=make_codenames_board(),
        players=[
            make_codenames_player(U1, CodenamesTeam.RED, CodenamesRole.SPYMASTER),
            make_codenames_player(U2, CodenamesTeam.BLUE, CodenamesRole.SPYMASTER),
        ],
    )
    sio = AsyncMock()

    # Act — blue player disconnects
    await handle_codenames_disconnect(sio, U2, room)

    # Assert
    refreshed = await CodenamesGame.get(GAME_ID)
    assert refreshed.status == CodenamesGameStatus.FINISHED
    assert refreshed.winner == CodenamesTeam.RED

    refreshed_room = await RedisRoom.get(ROOM_ID)
    assert refreshed_room.active_game_id is None


async def test_codenames_disconnect_multiple_operatives_leave(make_codenames_game, make_redis_room):
    """Multiple operatives disconnecting leaves team with just spymaster."""

    U6 = "66666666-6666-6666-6666-666666666666"  # noqa: N806

    # Arrange — RED has spymaster + 2 operatives, BLUE has spymaster + operative
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_codenames_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        board=make_codenames_board(),
        players=[
            make_codenames_player(U1, CodenamesTeam.RED, CodenamesRole.SPYMASTER),
            make_codenames_player(U2, CodenamesTeam.RED, CodenamesRole.OPERATIVE),
            make_codenames_player(U3, CodenamesTeam.RED, CodenamesRole.OPERATIVE),
            make_codenames_player(U4, CodenamesTeam.BLUE, CodenamesRole.SPYMASTER),
            make_codenames_player(U5, CodenamesTeam.BLUE, CodenamesRole.OPERATIVE),
        ],
    )
    sio = AsyncMock()

    # Act — both red operatives disconnect
    await handle_codenames_disconnect(sio, U2, room)
    # Re-fetch room after first disconnect
    room = await RedisRoom.get(ROOM_ID)
    await handle_codenames_disconnect(sio, U3, room)

    # Assert — red team has only spymaster left, game still in progress
    refreshed = await CodenamesGame.get(GAME_ID)
    remaining_red = [p for p in refreshed.players if p.team == CodenamesTeam.RED]
    assert len(remaining_red) == 1
    assert remaining_red[0].role == CodenamesRole.SPYMASTER
    assert refreshed.status == CodenamesGameStatus.IN_PROGRESS


async def test_codenames_disconnect_spymaster_no_operatives_left(make_codenames_game, make_redis_room):
    """If spymaster disconnects and only operatives remain, first operative becomes spymaster."""

    # Arrange — RED has spymaster + 1 operative
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_codenames_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        board=make_codenames_board(),
        players=[
            make_codenames_player(U1, CodenamesTeam.RED, CodenamesRole.SPYMASTER),
            make_codenames_player(U2, CodenamesTeam.RED, CodenamesRole.OPERATIVE),
            make_codenames_player(U3, CodenamesTeam.BLUE, CodenamesRole.SPYMASTER),
            make_codenames_player(U4, CodenamesTeam.BLUE, CodenamesRole.OPERATIVE),
        ],
    )
    sio = AsyncMock()

    # Act — spymaster disconnects
    await handle_codenames_disconnect(sio, U1, room)

    # Assert — U2 promoted to spymaster, game continues
    refreshed = await CodenamesGame.get(GAME_ID)
    remaining_red = [p for p in refreshed.players if p.team == CodenamesTeam.RED]
    assert len(remaining_red) == 1
    assert remaining_red[0].role == CodenamesRole.SPYMASTER
    assert str(remaining_red[0].user_id) == U2
    assert refreshed.status == CodenamesGameStatus.IN_PROGRESS


async def test_undercover_disconnect_no_votes_no_elimination(make_undercover_game, make_redis_room):
    """If no votes were cast, disconnect only marks player dead, no elimination triggered."""

    # Arrange — 4 alive, no votes, U1 disconnects → 3 alive, no votes → no elimination
    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_undercover_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        players=[
            make_undercover_player(U1, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U2, role=UndercoverRole.UNDERCOVER),
            make_undercover_player(U3, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U4, role=UndercoverRole.MR_WHITE),
        ],
        turns=[UndercoverTurn()],
    )
    sio = AsyncMock()

    # Act
    await handle_undercover_disconnect(sio, U1, room)

    # Assert — player marked dead, no elimination event
    refreshed = await UndercoverGame.get(GAME_ID)
    p1 = next(p for p in refreshed.players if str(p.user_id) == U1)
    assert p1.is_alive is False
    assert len(refreshed.eliminated_players) == 1  # just U1


async def test_undercover_disconnect_partial_votes_no_elimination(make_undercover_game, make_redis_room):
    """If only some players voted, disconnect doesn't trigger elimination."""

    # Arrange — 5 alive, only 2 voted, U1 disconnects → 4 alive, 2 voted → not all voted
    turn = UndercoverTurn(votes={UUID(U2): U3, UUID(U3): U4})

    room = await make_redis_room(ROOM_ID, active_game_id=GAME_ID)
    await make_undercover_game(
        game_id=GAME_ID, room_id=ROOM_ID,
        players=[
            make_undercover_player(U1, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U2, role=UndercoverRole.CIVILIAN),
            make_undercover_player(U3, role=UndercoverRole.UNDERCOVER),
            make_undercover_player(U4, role=UndercoverRole.MR_WHITE),
            make_undercover_player(U5, role=UndercoverRole.CIVILIAN),
        ],
        turns=[turn],
    )
    sio = AsyncMock()

    # Act
    await handle_undercover_disconnect(sio, U1, room)

    # Assert — player dead, but only 2 votes < 4 alive → no elimination
    refreshed = await UndercoverGame.get(GAME_ID)
    p1 = next(p for p in refreshed.players if str(p.user_id) == U1)
    assert p1.is_alive is False
    # Only the disconnect player is eliminated, not vote-based elimination
    assert len(refreshed.eliminated_players) == 1

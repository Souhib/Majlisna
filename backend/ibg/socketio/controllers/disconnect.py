from aredis_om import NotFoundError
from loguru import logger

from ibg.api.constants import EVENT_CODENAMES_GAME_OVER, EVENT_GAME_CANCELLED
from ibg.api.models.undercover import UndercoverRole
from ibg.socketio.controllers.undercover_game import check_if_a_team_has_win, eliminate_player_based_on_votes
from ibg.socketio.models.codenames import CodenamesGame, CodenamesGameStatus, CodenamesRole, CodenamesTeam
from ibg.socketio.models.room import Room as RedisRoom
from ibg.socketio.models.shared import IBGSocket, redis_connection
from ibg.socketio.models.socket import UndercoverGame
from ibg.socketio.routes.shared import send_event_to_client
from ibg.socketio.utils.redis_ttl import set_game_finished_ttl

MIN_ALIVE_PLAYERS_FOR_UNDERCOVER = 3


async def handle_undercover_disconnect(
    sio: IBGSocket,
    user_id: str,
    redis_room: RedisRoom,
) -> None:
    """Handle a permanent disconnect during an active Undercover game.

    Marks the player as dead, checks if game should be cancelled (< 3 alive),
    checks win condition, and checks if remaining alive players have all voted.

    Uses a Redis lock to prevent race conditions when multiple players
    disconnect simultaneously (concurrent cleanup tasks would otherwise
    read stale state and overwrite each other's saves).

    :param sio: The IBGSocket server instance.
    :param user_id: The user ID of the disconnected player.
    :param redis_room: The Redis room.
    """
    async with redis_connection.lock(f"game:{redis_room.active_game_id}:disconnect", timeout=10):
        try:
            redis_game = await UndercoverGame.get(redis_room.active_game_id)
        except NotFoundError:
            logger.warning(f"[Disconnect] Undercover game {redis_room.active_game_id} not found during disconnect cleanup")
            return

        # Find the player in the game
        player = next((p for p in redis_game.players if str(p.user_id) == user_id), None)
        if not player or not player.is_alive:
            return

        # Mark player as dead and add to eliminated
        player.is_alive = False
        redis_game.eliminated_players.append(player)
        await redis_game.save()

        alive_players = [p for p in redis_game.players if p.is_alive]

        # If fewer than 3 alive players, cancel the game
        if len(alive_players) < MIN_ALIVE_PLAYERS_FOR_UNDERCOVER:
            cancel_payload = {
                "message": "Game cancelled: not enough players.",
                "reason": "not_enough_players",
            }
            for p in redis_game.players:
                if p.sid:
                    await send_event_to_client(sio, EVENT_GAME_CANCELLED, cancel_payload, room=p.sid)
            redis_room.active_game_id = None
            redis_room.active_game_type = None
            await redis_room.save()
            await set_game_finished_ttl(redis_game)
            return

        # Check win condition
        team_that_won = await check_if_a_team_has_win(redis_game)
        if team_that_won == UndercoverRole.CIVILIAN:
            civilian_win_payload = {"data": "The civilians have won the game."}
            for p in redis_game.players:
                if p.sid:
                    await send_event_to_client(sio, "game_over", civilian_win_payload, room=p.sid)
            redis_room.active_game_id = None
            redis_room.active_game_type = None
            await redis_room.save()
            return
        elif team_that_won == UndercoverRole.UNDERCOVER:
            undercover_win_payload = {"data": "The undercovers have won the game."}
            for p in redis_game.players:
                if p.sid:
                    await send_event_to_client(sio, "game_over", undercover_win_payload, room=p.sid)
            redis_room.active_game_id = None
            redis_room.active_game_type = None
            await redis_room.save()
            return

        # Check if all remaining alive players have voted (trigger elimination)
        if redis_game.turns:
            current_turn = redis_game.turns[-1]
            alive_non_eliminated_count = len(alive_players)
            votes_count = len(current_turn.votes)
            if votes_count > 0 and votes_count >= alive_non_eliminated_count:
                eliminated_player, number_of_votes = await eliminate_player_based_on_votes(redis_game)
                elimination_payload = {
                    "message": (
                        f"Player {eliminated_player.username} is eliminated with {number_of_votes} votes against him."
                    ),
                    "eliminated_player_role": eliminated_player.role,
                }
                for p in redis_game.players:
                    if p.sid:
                        await send_event_to_client(sio, "player_eliminated", elimination_payload, room=p.sid)
                # Re-check win after elimination
                team_that_won = await check_if_a_team_has_win(redis_game)
                if team_that_won:
                    winner_msg = (
                        "The civilians have won the game."
                        if team_that_won == UndercoverRole.CIVILIAN
                        else "The undercovers have won the game."
                    )
                    game_over_payload = {"data": winner_msg}
                    for p in redis_game.players:
                        if p.sid:
                            await send_event_to_client(sio, "game_over", game_over_payload, room=p.sid)
                    redis_room.active_game_id = None
                    redis_room.active_game_type = None
                    await redis_room.save()


async def handle_codenames_disconnect(
    sio: IBGSocket,
    user_id: str,
    redis_room: RedisRoom,
) -> None:
    """Handle a permanent disconnect during an active Codenames game.

    Removes player from game. If team has 0 players, other team wins.
    If player was spymaster, promotes an operative.

    Uses a Redis lock to prevent race conditions when multiple players
    disconnect simultaneously (concurrent cleanup tasks would otherwise
    read stale state and overwrite each other's saves).

    :param sio: The IBGSocket server instance.
    :param user_id: The user ID of the disconnected player.
    :param redis_room: The Redis room.
    """
    async with redis_connection.lock(f"game:{redis_room.active_game_id}:disconnect", timeout=10):
        try:
            redis_game = await CodenamesGame.get(redis_room.active_game_id)
        except NotFoundError:
            logger.warning(f"[Disconnect] Codenames game {redis_room.active_game_id} not found during disconnect cleanup")
            return

        if redis_game.status != CodenamesGameStatus.IN_PROGRESS:
            return

        # Find and remove the player
        player = next((p for p in redis_game.players if str(p.user_id) == user_id), None)
        if not player:
            return

        disconnected_team = player.team
        was_spymaster = player.role == CodenamesRole.SPYMASTER

        # Remove the player from the game
        redis_game.players = [p for p in redis_game.players if str(p.user_id) != user_id]

        # Check if team is now empty
        team_players = [p for p in redis_game.players if p.team == disconnected_team]

        if len(team_players) == 0:
            # Other team wins
            other_team = CodenamesTeam.BLUE if disconnected_team == CodenamesTeam.RED else CodenamesTeam.RED
            redis_game.status = CodenamesGameStatus.FINISHED
            redis_game.winner = other_team
            await redis_game.save()
            await set_game_finished_ttl(redis_game)

            full_board = [
                {
                    "index": i,
                    "word": card.word,
                    "card_type": card.card_type.value,
                    "revealed": card.revealed,
                }
                for i, card in enumerate(redis_game.board)
            ]
            game_over_payload = {
                "game_id": redis_game.id,
                "winner": other_team.value,
                "reason": "team_empty",
                "board": full_board,
            }
            for p in redis_game.players:
                if p.sid:
                    await send_event_to_client(sio, EVENT_CODENAMES_GAME_OVER, game_over_payload, room=p.sid)

            redis_room.active_game_id = None
            redis_room.active_game_type = None
            await redis_room.save()
            return

        # If player was spymaster, promote first operative on same team
        if was_spymaster:
            operatives = [p for p in team_players if p.role == CodenamesRole.OPERATIVE]
            if operatives:
                operatives[0].role = CodenamesRole.SPYMASTER
                logger.info(
                    f"[Disconnect] Promoted {operatives[0].username} to spymaster on team {disconnected_team.value}"
                )

        await redis_game.save()

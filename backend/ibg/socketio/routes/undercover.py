from uuid import UUID

from aredis_om import NotFoundError
from pydantic import BaseModel

from ibg.api.constants import (
    EVENT_DESCRIPTION_SUBMITTED,
    EVENT_DESCRIPTIONS_COMPLETE,
    EVENT_TURN_STARTED,
    EVENT_UNDERCOVER_GAME_STATE,
    EVENT_YOUR_TURN_TO_DESCRIBE,
)
from ibg.api.models.error import GameNotFoundError, PlayerRemovedFromGameError
from ibg.api.models.undercover import UndercoverRole
from ibg.socketio.controllers.undercover_game import (
    check_if_a_team_has_win,
    create_undercover_game,
    eliminate_player_based_on_votes,
    generate_description_order,
    get_winning_team,
    set_vote,
    start_new_turn,
    submit_description,
)
from ibg.socketio.models.shared import IBGSocket, redis_connection
from ibg.socketio.models.socket import (
    StartGame,
    StartNewTurn,
    SubmitDescription,
    UndercoverGame,
    VoteForAPerson,
)
from ibg.socketio.models.user import User
from ibg.socketio.routes.shared import send_event_to_client, socketio_exception_handler
from ibg.socketio.utils.disconnect_tasks import cancel_disconnect_cleanup


class GetUndercoverState(BaseModel):
    game_id: UUID
    user_id: UUID


def undercover_events(sio: IBGSocket) -> None:

    @sio.event
    @socketio_exception_handler(sio)
    async def start_undercover_game(sid, data) -> None:
        """Start an Undercover Game in a Room with the given data."""
        # Validation
        start_game_input = StartGame(**data)

        # Function Logic
        db_room, db_game, redis_game = await create_undercover_game(sio, start_game_input)

        # Send Notification to each player to assign role
        for player in redis_game.players:
            if player.role == UndercoverRole.MR_WHITE:
                await send_event_to_client(
                    sio,
                    "role_assigned",
                    {
                        "role": player.role.value,
                        "word": "You are Mr. White. You have to guess the word.",
                    },
                    room=player.sid,
                )
            else:
                word = (
                    redis_game.undercover_word if player.role == UndercoverRole.UNDERCOVER else redis_game.civilian_word
                )
                await send_event_to_client(
                    sio,
                    "role_assigned",
                    {
                        "role": player.role.value,
                        "word": word,
                    },
                    room=player.sid,
                )

        # Send Notification to Room that game has started
        await send_event_to_client(
            sio,
            "game_started",
            {
                "game_id": str(db_game.id),
                "game_type": "undercover",
                "message": "Undercover Game has started. Check your role and word.",
                "players": [player.username for player in redis_game.players],
                "mayor": next(player.username for player in redis_game.players if player.is_mayor),
            },
            room=str(db_room.public_id),
        )

    @sio.event
    @socketio_exception_handler(sio)
    async def start_new_turn_event(sid, data) -> None:
        """Start a new turn in the game."""
        # Validation
        start_new_turn_data = StartNewTurn(**data)

        db_room = await sio.room_controller.get_room_by_id(start_new_turn_data.room_id)
        try:
            redis_game = await UndercoverGame.get(start_new_turn_data.game_id)
        except NotFoundError:
            raise GameNotFoundError(game_id=start_new_turn_data.game_id) from None
        db_game = await sio.game_controller.get_game_by_id(redis_game.id)

        # Function Logic
        await start_new_turn(sio, db_room, db_game, redis_game)

        # Re-fetch game to get updated turn state
        redis_game = await UndercoverGame.get(start_new_turn_data.game_id)
        current_turn = redis_game.turns[-1]

        # Build description order with usernames for the frontend
        description_order_with_names = []
        for uid in current_turn.description_order:
            p = next((p for p in redis_game.players if p.user_id == uid), None)
            if p:
                description_order_with_names.append({"user_id": str(uid), "username": p.username})

        first_describer_id = str(current_turn.description_order[0]) if current_turn.description_order else None

        # Send turn_started to each player's SID directly
        turn_started_payload = {
            "message": "Starting a new turn.",
            "description_order": description_order_with_names,
            "current_describer_index": 0,
            "phase": "describing",
        }
        for p in redis_game.players:
            if p.sid:
                await send_event_to_client(sio, EVENT_TURN_STARTED, turn_started_payload, room=p.sid)

        # Notify the first describer it's their turn
        if first_describer_id:
            first_player = next((p for p in redis_game.players if str(p.user_id) == first_describer_id), None)
            if first_player and first_player.sid:
                await send_event_to_client(
                    sio, EVENT_YOUR_TURN_TO_DESCRIBE, {"user_id": first_describer_id}, room=first_player.sid,
                )

    @sio.event
    @socketio_exception_handler(sio)
    async def submit_description_event(sid, data) -> None:
        """Submit a single-word description for the current turn."""
        desc_data = SubmitDescription(**data)
        try:
            game = await UndercoverGame.get(desc_data.game_id)
        except NotFoundError:
            raise GameNotFoundError(game_id=desc_data.game_id) from None

        current_turn = game.turns[-1]

        # Validate it's the describing phase
        if current_turn.phase != "describing":
            await sio.emit("error", {"message": "Not in description phase."}, room=sid)
            return

        # Validate it's this player's turn
        if current_turn.current_describer_index >= len(current_turn.description_order):
            await sio.emit("error", {"message": "All descriptions already submitted."}, room=sid)
            return
        if current_turn.description_order[current_turn.current_describer_index] != desc_data.user_id:
            await sio.emit("error", {"message": "Not your turn to describe."}, room=sid)
            return

        # Validate word (no spaces, not empty, max 50 chars)
        word = desc_data.word.strip()
        if not word or " " in word or len(word) > 50:
            await sio.emit("error", {"message": "Word must be a single word (no spaces), max 50 characters."}, room=sid)
            return

        # Store description and advance index
        all_done = submit_description(game, desc_data.user_id, word)
        await game.save()

        # Find the submitter's username
        submitter = next((p for p in game.players if p.user_id == desc_data.user_id), None)
        submitter_username = submitter.username if submitter else "Unknown"

        # Determine next describer
        next_describer_id = None
        next_describer_username = None
        if not all_done:
            next_idx = current_turn.current_describer_index
            if next_idx < len(current_turn.description_order):
                next_uid = current_turn.description_order[next_idx]
                next_describer_id = str(next_uid)
                next_player = next((p for p in game.players if p.user_id == next_uid), None)
                next_describer_username = next_player.username if next_player else None

        # Broadcast description to all players
        desc_payload = {
            "user_id": str(desc_data.user_id),
            "username": submitter_username,
            "word": word,
            "next_describer_id": next_describer_id,
            "next_describer_username": next_describer_username,
        }
        for p in game.players:
            if p.sid:
                await send_event_to_client(sio, EVENT_DESCRIPTION_SUBMITTED, desc_payload, room=p.sid)

        if all_done:
            # Transition to voting phase
            current_turn.phase = "voting"
            await game.save()

            # Build descriptions dict for the complete event
            descriptions = {
                str(uid): w for uid, w in current_turn.words.items()
            }
            complete_payload = {"descriptions": descriptions}
            for p in game.players:
                if p.sid:
                    await send_event_to_client(sio, EVENT_DESCRIPTIONS_COMPLETE, complete_payload, room=p.sid)
        else:
            # Notify next describer it's their turn
            if next_describer_id:
                next_player = next((p for p in game.players if str(p.user_id) == next_describer_id), None)
                if next_player and next_player.sid:
                    await send_event_to_client(
                        sio, EVENT_YOUR_TURN_TO_DESCRIBE, {"user_id": next_describer_id}, room=next_player.sid,
                    )

    @sio.event
    @socketio_exception_handler(sio)
    async def vote_for_a_player(sid, data) -> None:
        """Vote for a player in the game."""
        data = VoteForAPerson(**data)
        try:
            game = await UndercoverGame.get(data.game_id)
        except NotFoundError:
            raise GameNotFoundError(game_id=data.game_id) from None

        # Block voting during description phase
        if game.turns and game.turns[-1].phase != "voting":
            await sio.emit("error", {"message": "Descriptions are not complete yet."}, room=sid)
            return

        # Fetch db_room to get public_id for Socket.IO room broadcasts
        db_room = await sio.room_controller.get_room_by_id(data.room_id)

        player_to_vote, voted_player, game, all_voted = await set_vote(game, data)

        if all_voted:
            eliminated_player, number_of_vote = await eliminate_player_based_on_votes(game)

            elimination_payload = {
                "message": f"Player {eliminated_player.username} is eliminated with {number_of_vote} votes against him.",
                "eliminated_player_role": eliminated_player.role.value,
                "eliminated_player_username": eliminated_player.username,
                "eliminated_player_user_id": str(eliminated_player.user_id),
            }

            # Send elimination to each player's SID directly
            # (room broadcasts can be missed if sockets reconnected without rejoining the SIO room)
            for p in game.players:
                if p.sid:
                    await send_event_to_client(
                        sio, "player_eliminated", elimination_payload, room=p.sid,
                    )

            # Send Notification to the eliminated player
            await send_event_to_client(
                sio,
                "you_died",
                {"message": f"You have been eliminated with {number_of_vote} votes against you."},
                room=eliminated_player.sid,
            )
            team_that_won = await check_if_a_team_has_win(game)
            game_over_payload = None
            if team_that_won == UndercoverRole.CIVILIAN:
                game_over_payload = {
                    "data": "The civilians have won the game.",
                    "winner": "civilians",
                }
            elif team_that_won == UndercoverRole.UNDERCOVER:
                game_over_payload = {
                    "data": "The undercovers have won the game.",
                    "winner": "undercovers",
                }

            if game_over_payload:
                # Send game_over to each player's SID directly
                for p in game.players:
                    if p.sid:
                        await send_event_to_client(
                            sio, "game_over", game_over_payload, room=p.sid,
                        )

        else:
            players_that_voted = [player for player in game.players if player.user_id in game.turns[-1].votes]
            await send_event_to_client(
                sio,
                "vote_casted",
                {
                    "message": "Vote casted.",
                },
                room=sid,
            )
            await send_event_to_client(
                sio,
                "waiting_other_votes",
                {
                    "message": "Waiting for other players to vote.",
                    "players_that_voted": [
                        {
                            "username": player.username,
                            "user_id": str(player.user_id),
                        }
                        for player in players_that_voted
                    ],
                },
                room=sid,
            )

    @sio.event
    @socketio_exception_handler(sio)
    async def get_undercover_state(sid, data) -> None:
        """Return full game state for a reconnecting player.

        Used when a player refreshes the page during an Undercover game
        and has no sessionStorage data.
        """
        state_data = GetUndercoverState(**data)

        # Cancel any pending disconnect cleanup (player reconnecting via page reload)
        cancel_disconnect_cleanup(state_data.user_id)

        # Clear disconnect flag so permanent cleanup sees reconnection
        try:
            redis_user = await User.get(str(state_data.user_id))
            if redis_user.disconnected_at is not None:
                redis_user.disconnected_at = None
                await redis_user.save()
        except NotFoundError:
            pass  # User model may not exist yet

        try:
            game = await UndercoverGame.get(state_data.game_id)
        except NotFoundError:
            raise GameNotFoundError(game_id=state_data.game_id) from None

        # Check if the player is in the game
        player = next(
            (p for p in game.players if p.user_id == state_data.user_id),
            None,
        )
        if not player:
            raise PlayerRemovedFromGameError(
                user_id=state_data.user_id,
                game_id=state_data.game_id,
            )

        # Update player SID if reconnected with a new socket
        if player.sid != sid:
            async with redis_connection.lock(f"game:{state_data.game_id}:disconnect", timeout=5):
                # Re-fetch game inside lock to avoid overwriting concurrent changes
                game = await UndercoverGame.get(state_data.game_id)
                player = next((p for p in game.players if p.user_id == state_data.user_id), None)
                if player:
                    player.sid = sid
                    await game.save()

        # Determine word based on role
        if player.role == UndercoverRole.MR_WHITE:
            my_word = "You are Mr. White. You have to guess the word."
        elif player.role == UndercoverRole.UNDERCOVER:
            my_word = game.undercover_word
        else:
            my_word = game.civilian_word

        # Build voted info and description phase data
        current_turn_votes = {}
        has_voted = False
        turn_phase = "describing"
        description_order = []
        current_describer_index = 0
        descriptions = {}
        if game.turns:
            current_turn = game.turns[-1]
            current_turn_votes = {str(voter_id): str(voted_id) for voter_id, voted_id in current_turn.votes.items()}
            has_voted = state_data.user_id in current_turn.votes
            turn_phase = current_turn.phase
            description_order = [
                {
                    "user_id": str(uid),
                    "username": next((p.username for p in game.players if p.user_id == uid), "Unknown"),
                }
                for uid in current_turn.description_order
            ]
            current_describer_index = current_turn.current_describer_index
            descriptions = {str(uid): w for uid, w in current_turn.words.items()}

        # Detect game-over state for reconnecting players
        winning_team = get_winning_team(game)
        winner = None
        if winning_team == UndercoverRole.CIVILIAN:
            winner = "civilians"
        elif winning_team == UndercoverRole.UNDERCOVER:
            winner = "undercovers"

        # Ensure the (possibly reconnected) socket is in the correct SIO room
        try:
            db_room = await sio.room_controller.get_room_by_id(game.room_id)
            sio.enter_room(sid, str(db_room.public_id))
        except Exception:
            pass  # Best-effort room rejoin

        await send_event_to_client(
            sio,
            EVENT_UNDERCOVER_GAME_STATE,
            {
                "game_id": game.id,
                "room_id": game.room_id,
                "my_role": player.role.value,
                "my_word": my_word,
                "is_alive": player.is_alive,
                "players": [
                    {
                        "user_id": str(p.user_id),
                        "username": p.username,
                        "is_alive": p.is_alive,
                        "is_mayor": p.is_mayor,
                    }
                    for p in game.players
                ],
                "eliminated_players": [
                    {
                        "user_id": str(p.user_id),
                        "username": p.username,
                        "role": p.role.value,
                    }
                    for p in game.eliminated_players
                ],
                "turn_number": len(game.turns),
                "votes": current_turn_votes,
                "has_voted": has_voted,
                "winner": winner,
                "turn_phase": turn_phase,
                "description_order": description_order,
                "current_describer_index": current_describer_index,
                "descriptions": descriptions,
            },
            room=sid,
        )

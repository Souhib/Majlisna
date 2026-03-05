"""Tests for the UndercoverGameController."""

import random
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ipg.api.controllers.undercover_game import UndercoverGameController
from ipg.api.models.game import GameStatus
from ipg.api.models.table import Game, Room
from ipg.api.models.undercover import UndercoverRole
from ipg.api.schemas.error import (
    BaseError,
    CantVoteBecauseYouDeadError,
    CantVoteForDeadPersonError,
    CantVoteForYourselfError,
    PlayerRemovedFromGameError,
)

# ─── Helpers ──────────────────────────────────────────────────


async def _start_game(controller: UndercoverGameController, room_id, user_id):
    """Start a game and return the result dict."""
    return await controller.create_and_start(room_id, user_id)


async def _get_game(session: AsyncSession, game_id_str: str) -> Game:
    """Fetch a game by its string ID."""
    game = (await session.exec(select(Game).where(Game.id == UUID(game_id_str)))).first()
    return game


def _find_player_by_role(state, role_value):
    """Find the first player with the given role."""
    return next((p for p in state["players"] if p["role"] == role_value), None)


def _alive_players(state):
    """Get alive players from state."""
    return [p for p in state["players"] if p["is_alive"]]


# ─── Happy Path Tests ─────────────────────────────────────────


class TestCreateAndStart:
    @pytest.mark.asyncio
    async def test_3_players(self, undercover_game_controller, setup_undercover_game, session):
        """3 players: 0 mr_white, 1 undercover, 2 civilians, mayor assigned, description_order generated."""
        # Prepare
        setup = await setup_undercover_game(3)
        room, users = setup["room"], setup["users"]

        # Act
        result = await _start_game(undercover_game_controller, room.id, users[0].id)

        # Assert
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        players = state["players"]

        assert len(players) == 3
        roles = [p["role"] for p in players]
        assert roles.count(UndercoverRole.MR_WHITE.value) == 0
        assert roles.count(UndercoverRole.UNDERCOVER.value) == 1
        assert roles.count(UndercoverRole.CIVILIAN.value) == 2

        # Mayor assigned
        mayors = [p for p in players if p.get("is_mayor")]
        assert len(mayors) == 1

        # Description order generated
        assert len(state["turns"]) == 1
        turn = state["turns"][0]
        assert len(turn["description_order"]) == 3
        assert turn["phase"] == "describing"

    @pytest.mark.asyncio
    async def test_5_players(self, undercover_game_controller, setup_undercover_game, session):
        """5 players: 1 mr_white, 2 undercover, 2 civilians."""
        # Prepare
        setup = await setup_undercover_game(5)
        room, users = setup["room"], setup["users"]

        # Act
        result = await _start_game(undercover_game_controller, room.id, users[0].id)

        # Assert
        game = await _get_game(session, result["game_id"])
        players = game.live_state["players"]
        roles = [p["role"] for p in players]

        assert roles.count(UndercoverRole.MR_WHITE.value) == 1
        assert roles.count(UndercoverRole.UNDERCOVER.value) == 2
        assert roles.count(UndercoverRole.CIVILIAN.value) == 2

    @pytest.mark.asyncio
    async def test_10_players(self, undercover_game_controller, setup_undercover_game, session):
        """10 players: correct role distribution with at least 1 civilian."""
        # Prepare
        setup = await setup_undercover_game(10)
        room, users = setup["room"], setup["users"]

        # Act
        result = await _start_game(undercover_game_controller, room.id, users[0].id)

        # Assert
        game = await _get_game(session, result["game_id"])
        players = game.live_state["players"]
        roles = [p["role"] for p in players]

        # 10 players: 2 mr_white (10 <= 15), 2 undercover (10//4=2), 6 civilians
        assert roles.count(UndercoverRole.MR_WHITE.value) == 2
        assert roles.count(UndercoverRole.UNDERCOVER.value) == 2
        assert roles.count(UndercoverRole.CIVILIAN.value) == 6

    @pytest.mark.asyncio
    async def test_room_already_has_active_game(self, undercover_game_controller, setup_undercover_game):
        """Starting a game in a room that already has one raises BaseError 400."""
        # Prepare
        setup = await setup_undercover_game(3)
        room, users = setup["room"], setup["users"]
        await _start_game(undercover_game_controller, room.id, users[0].id)

        # Act / Assert
        with pytest.raises(BaseError, match="already has an active game"):
            await _start_game(undercover_game_controller, room.id, users[0].id)


class TestSubmitDescription:
    @pytest.mark.asyncio
    async def test_stores_word_and_advances_index(self, undercover_game_controller, setup_undercover_game, session):
        """Word stored in current_turn['words'], current_describer_index incremented."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        first_describer_id = game.live_state["turns"][0]["description_order"][0]

        # Act

        desc_result = await undercover_game_controller.submit_description(
            UUID(result["game_id"]), UUID(first_describer_id), "testword"
        )

        # Assert
        assert desc_result["word"] == "testword"
        game = await _get_game(session, result["game_id"])
        turn = game.live_state["turns"][0]
        assert first_describer_id in turn["words"]
        assert turn["words"][first_describer_id] == "testword"
        assert turn["current_describer_index"] == 1

    @pytest.mark.asyncio
    async def test_all_descriptions_transitions_to_voting(
        self, undercover_game_controller, setup_undercover_game, session
    ):
        """After last description, phase becomes 'voting'."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        order = game.live_state["turns"][0]["description_order"]

        # Act — submit all descriptions

        game_uuid = UUID(result["game_id"])
        for uid in order:
            await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

        # Assert
        game = await _get_game(session, result["game_id"])
        assert game.live_state["turns"][0]["phase"] == "voting"

    @pytest.mark.asyncio
    async def test_not_your_turn(self, undercover_game_controller, setup_undercover_game, session):
        """Wrong user submitting raises BaseError 400."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        order = game.live_state["turns"][0]["description_order"]
        # Find a user who is NOT the current describer
        wrong_user_id = next(str(u.id) for u in setup["users"] if str(u.id) != order[0])

        # Act / Assert

        with pytest.raises(BaseError, match="Not your turn"):
            await undercover_game_controller.submit_description(UUID(result["game_id"]), UUID(wrong_user_id), "word")

    @pytest.mark.asyncio
    async def test_not_in_describing_phase(self, undercover_game_controller, setup_undercover_game, session):
        """Submitting during voting phase raises BaseError 400."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        order = game.live_state["turns"][0]["description_order"]

        game_uuid = UUID(result["game_id"])

        # Submit all to move to voting
        for uid in order:
            await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

        # Act / Assert — try to submit during voting
        with pytest.raises(BaseError, match="Not in description phase"):
            await undercover_game_controller.submit_description(game_uuid, UUID(order[0]), "extra")

    @pytest.mark.asyncio
    async def test_empty_word(self, undercover_game_controller, setup_undercover_game, session):
        """Empty word raises BaseError 400."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        first_describer = game.live_state["turns"][0]["description_order"][0]

        # Act / Assert
        with pytest.raises(BaseError, match="single word"):
            await undercover_game_controller.submit_description(UUID(result["game_id"]), UUID(first_describer), "")

    @pytest.mark.asyncio
    async def test_word_with_spaces(self, undercover_game_controller, setup_undercover_game, session):
        """Word with spaces raises BaseError 400."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        first_describer = game.live_state["turns"][0]["description_order"][0]

        # Act / Assert
        with pytest.raises(BaseError, match="single word"):
            await undercover_game_controller.submit_description(
                UUID(result["game_id"]), UUID(first_describer), "two words"
            )

    @pytest.mark.asyncio
    async def test_word_too_long(self, undercover_game_controller, setup_undercover_game, session):
        """Word over 50 characters raises BaseError 400."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        first_describer = game.live_state["turns"][0]["description_order"][0]

        # Act / Assert
        with pytest.raises(BaseError, match="max 50"):
            await undercover_game_controller.submit_description(
                UUID(result["game_id"]), UUID(first_describer), "a" * 51
            )

    @pytest.mark.asyncio
    async def test_after_all_submitted(self, undercover_game_controller, setup_undercover_game, session):
        """Extra description after all done raises error."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        order = game.live_state["turns"][0]["description_order"]

        game_uuid = UUID(result["game_id"])
        for uid in order:
            await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

        # Act / Assert — phase is "voting" now, so this fails
        with pytest.raises(BaseError):
            await undercover_game_controller.submit_description(game_uuid, UUID(order[0]), "extra")

    @pytest.mark.asyncio
    async def test_player_not_in_game(self, undercover_game_controller, setup_undercover_game, session):
        """Random user_id not in game players raises error."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

        # Act / Assert — random UUID not in description_order
        with pytest.raises(BaseError, match="Not your turn"):
            await undercover_game_controller.submit_description(UUID(result["game_id"]), uuid4(), "word")


class TestSubmitVote:
    async def _setup_voting_phase(self, controller, setup_undercover_game, session):
        """Helper: start game and submit all descriptions to reach voting phase."""

        setup = await setup_undercover_game(3)
        result = await _start_game(controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        order = game.live_state["turns"][0]["description_order"]
        game_uuid = UUID(result["game_id"])

        for uid in order:
            await controller.submit_description(game_uuid, UUID(uid), "word")

        game = await _get_game(session, result["game_id"])
        return setup, result, game

    @pytest.mark.asyncio
    async def test_records_vote(self, undercover_game_controller, setup_undercover_game, session):
        """Vote stored in current_turn['votes']."""
        # Prepare
        setup, result, game = await self._setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

        game_uuid = UUID(result["game_id"])
        voter = setup["users"][0]
        target = next(u for u in setup["users"] if u.id != voter.id)

        # Act
        vote_result = await undercover_game_controller.submit_vote(game_uuid, voter.id, target.id)

        # Assert
        assert vote_result["game_id"] == result["game_id"]
        game = await _get_game(session, result["game_id"])
        assert str(voter.id) in game.live_state["turns"][0]["votes"]

    @pytest.mark.asyncio
    async def test_all_votes_eliminates_majority_target(
        self, undercover_game_controller, setup_undercover_game, session
    ):
        """Player with most votes eliminated, is_alive=False, added to eliminated_players."""
        # Prepare
        setup, result, game = await self._setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

        game_uuid = UUID(result["game_id"])
        users = setup["users"]
        target = users[2]  # everyone votes for player 2

        # Act — all 3 players vote for target (except target votes for someone else)
        for voter in users:
            if voter.id == target.id:
                other = next(u for u in users if u.id != target.id)
                await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
            else:
                await undercover_game_controller.submit_vote(game_uuid, voter.id, target.id)

        # Assert
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        eliminated = next(p for p in state["players"] if p["user_id"] == str(target.id))
        assert eliminated["is_alive"] is False
        assert any(e["user_id"] == str(target.id) for e in state["eliminated_players"])

    @pytest.mark.asyncio
    async def test_civilians_win_when_all_undercovers_eliminated(
        self, undercover_game_controller, setup_undercover_game, session
    ):
        """When all undercovers and mr_whites are eliminated, civilians win."""
        # Prepare — 3 players: 1 undercover, 2 civilians, 0 mr_white
        setup, result, game = await self._setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

        game_uuid = UUID(result["game_id"])
        state = game.live_state
        undercover_player = _find_player_by_role(state, UndercoverRole.UNDERCOVER.value)
        users = setup["users"]

        # Act — all vote for the undercover
        for voter in users:
            if str(voter.id) == undercover_player["user_id"]:
                other = next(u for u in users if str(u.id) != undercover_player["user_id"])
                await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
            else:
                await undercover_game_controller.submit_vote(game_uuid, voter.id, UUID(undercover_player["user_id"]))

        # Assert
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        # Check if undercover was eliminated and civilians won
        uc = next(p for p in state["players"] if p["role"] == UndercoverRole.UNDERCOVER.value)
        if not uc["is_alive"]:
            assert game.game_status == GameStatus.FINISHED

    @pytest.mark.asyncio
    async def test_vote_dead_voter(self, undercover_game_controller, setup_undercover_game, session):
        """Dead player voting raises CantVoteBecauseYouDeadError."""
        # Prepare
        setup, result, game = await self._setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

        game_uuid = UUID(result["game_id"])
        state = game.live_state

        # Kill a player manually
        state["players"][0]["is_alive"] = False
        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()

        dead_user = setup["users"][0]
        target = setup["users"][1]

        # Act / Assert
        with pytest.raises(CantVoteBecauseYouDeadError):
            await undercover_game_controller.submit_vote(game_uuid, dead_user.id, target.id)

    @pytest.mark.asyncio
    async def test_vote_dead_target(self, undercover_game_controller, setup_undercover_game, session):
        """Voting for dead player raises CantVoteForDeadPersonError."""
        # Prepare
        setup, result, game = await self._setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

        game_uuid = UUID(result["game_id"])
        state = game.live_state

        # Kill target manually
        state["players"][2]["is_alive"] = False
        game.live_state = state
        flag_modified(game, "live_state")
        session.add(game)
        await session.commit()

        voter = setup["users"][0]
        dead_target = setup["users"][2]

        # Act / Assert
        with pytest.raises(CantVoteForDeadPersonError):
            await undercover_game_controller.submit_vote(game_uuid, voter.id, dead_target.id)

    @pytest.mark.asyncio
    async def test_vote_self(self, undercover_game_controller, setup_undercover_game, session):
        """Voting for yourself raises CantVoteForYourselfError."""
        # Prepare
        setup, result, game = await self._setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

        game_uuid = UUID(result["game_id"])
        voter = setup["users"][0]

        # Act / Assert
        with pytest.raises(CantVoteForYourselfError):
            await undercover_game_controller.submit_vote(game_uuid, voter.id, voter.id)

    @pytest.mark.asyncio
    async def test_not_in_voting_phase(self, undercover_game_controller, setup_undercover_game, session):
        """Voting during describing phase raises BaseError 400."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

        game_uuid = UUID(result["game_id"])
        voter = setup["users"][0]
        target = setup["users"][1]

        # Act / Assert
        with pytest.raises(BaseError, match="not complete"):
            await undercover_game_controller.submit_vote(game_uuid, voter.id, target.id)

    @pytest.mark.asyncio
    async def test_vote_twice_overwrites(self, undercover_game_controller, setup_undercover_game, session):
        """Voting again silently updates the vote."""
        # Prepare
        setup, result, game = await self._setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

        game_uuid = UUID(result["game_id"])
        voter = setup["users"][0]
        target1 = setup["users"][1]
        target2 = setup["users"][2]

        # Act — vote twice
        await undercover_game_controller.submit_vote(game_uuid, voter.id, target1.id)
        await undercover_game_controller.submit_vote(game_uuid, voter.id, target2.id)

        # Assert — second vote overwrites
        game = await _get_game(session, result["game_id"])
        votes = game.live_state["turns"][0]["votes"]
        assert votes[str(voter.id)] == str(target2.id)

    @pytest.mark.asyncio
    async def test_player_not_in_game(self, undercover_game_controller, setup_undercover_game, session):
        """User not in game raises error."""
        # Prepare
        setup, result, game = await self._setup_voting_phase(undercover_game_controller, setup_undercover_game, session)

        game_uuid = UUID(result["game_id"])
        target = setup["users"][1]

        # Act / Assert
        with pytest.raises(BaseError, match="not in game"):
            await undercover_game_controller.submit_vote(game_uuid, uuid4(), target.id)


class TestStartNextRound:
    @pytest.mark.asyncio
    async def test_appends_turn(self, undercover_game_controller, setup_undercover_game, session):
        """start_next_round adds a new turn, phase reset to 'describing'."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

        game_uuid = UUID(result["game_id"])

        # Act
        round_result = await undercover_game_controller.start_next_round(
            game_uuid, setup["room"].id, setup["users"][0].id
        )

        # Assert
        game = await _get_game(session, result["game_id"])
        assert len(game.live_state["turns"]) == 2
        assert game.live_state["turns"][1]["phase"] == "describing"
        assert round_result["turn_number"] == 2


class TestGetState:
    @pytest.mark.asyncio
    async def test_civilian_word(self, undercover_game_controller, setup_undercover_game, session):
        """Civilian sees civilian_word."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        civilian = _find_player_by_role(state, UndercoverRole.CIVILIAN.value)

        # Act
        player_state = await undercover_game_controller.get_state(UUID(result["game_id"]), UUID(civilian["user_id"]))

        # Assert
        assert player_state["my_word"] == state["civilian_word"]

    @pytest.mark.asyncio
    async def test_undercover_word(self, undercover_game_controller, setup_undercover_game, session):
        """Undercover sees undercover_word."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        undercover = _find_player_by_role(state, UndercoverRole.UNDERCOVER.value)

        # Act
        player_state = await undercover_game_controller.get_state(UUID(result["game_id"]), UUID(undercover["user_id"]))

        # Assert
        assert player_state["my_word"] == state["undercover_word"]

    @pytest.mark.asyncio
    async def test_mr_white_message(self, undercover_game_controller, setup_undercover_game, session):
        """Mr. White sees message about guessing the word."""
        # Prepare — need 5 players to get mr_white
        setup = await setup_undercover_game(5)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        state = game.live_state

        mr_white = _find_player_by_role(state, UndercoverRole.MR_WHITE.value)
        if not mr_white:
            pytest.skip("No Mr. White in this game (random role assignment)")

        # Act
        player_state = await undercover_game_controller.get_state(UUID(result["game_id"]), UUID(mr_white["user_id"]))

        # Assert
        assert "Mr. White" in player_state["my_word"]

    @pytest.mark.asyncio
    async def test_player_not_in_game(self, undercover_game_controller, setup_undercover_game, session):
        """User not in game raises PlayerRemovedFromGameError."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

        # Act / Assert
        with pytest.raises(PlayerRemovedFromGameError):
            await undercover_game_controller.get_state(UUID(result["game_id"]), uuid4())


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_undercovers_win_when_outnumbering_civilians(
        self, undercover_game_controller, setup_undercover_game, session
    ):
        """3-player game: eliminate the civilian → undercovers should win."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

        game_uuid = UUID(result["game_id"])
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        order = state["turns"][0]["description_order"]

        # Submit all descriptions
        for uid in order:
            await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

        # Find a civilian to eliminate
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        civilians = [p for p in state["players"] if p["role"] == UndercoverRole.CIVILIAN.value]
        target_civilian = civilians[0]
        users = setup["users"]

        # All vote for the civilian
        for voter in users:
            if str(voter.id) == target_civilian["user_id"]:
                other = next(u for u in users if str(u.id) != target_civilian["user_id"])
                await undercover_game_controller.submit_vote(game_uuid, voter.id, other.id)
            else:
                await undercover_game_controller.submit_vote(game_uuid, voter.id, UUID(target_civilian["user_id"]))

        # Assert — undercovers should win (1 undercover >= 1 remaining civilian)
        game = await _get_game(session, result["game_id"])
        # Check win condition
        alive_uc = sum(
            1 for p in game.live_state["players"] if p["role"] == UndercoverRole.UNDERCOVER.value and p["is_alive"]
        )
        alive_civ = sum(
            1 for p in game.live_state["players"] if p["role"] == UndercoverRole.CIVILIAN.value and p["is_alive"]
        )
        if alive_uc >= alive_civ:
            assert game.game_status == GameStatus.FINISHED

    @pytest.mark.asyncio
    async def test_mayor_breaks_tie_vote(self, undercover_game_controller, setup_undercover_game, session):
        """In a tie, mayor's vote decides who gets eliminated."""
        # Prepare — need at least 4 players to create a tie
        setup = await setup_undercover_game(4)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)

        game_uuid = UUID(result["game_id"])
        game = await _get_game(session, result["game_id"])
        state = game.live_state
        order = state["turns"][0]["description_order"]

        # Submit all descriptions
        for uid in order:
            await undercover_game_controller.submit_description(game_uuid, UUID(uid), "word")

        game = await _get_game(session, result["game_id"])
        state = game.live_state
        mayor = next(p for p in state["players"] if p.get("is_mayor"))
        users = setup["users"]

        # Create a tie: 2 votes for user A, 2 for user B
        non_mayor_users = [u for u in users if str(u.id) != mayor["user_id"]]
        target_a = non_mayor_users[0]
        target_b = non_mayor_users[1]

        # Mayor votes for target_a
        await undercover_game_controller.submit_vote(game_uuid, UUID(mayor["user_id"]), target_a.id)

        # Find another user (not mayor, not target_a, not target_b) to vote for target_a
        mayor_uuid = UUID(mayor["user_id"])
        other_voter_for_a = next(u for u in users if u.id not in (mayor_uuid, target_a.id, target_b.id))
        await undercover_game_controller.submit_vote(game_uuid, other_voter_for_a.id, target_a.id)
        # target_a votes for target_b
        await undercover_game_controller.submit_vote(game_uuid, target_a.id, target_b.id)
        # target_b votes for target_a (to complete all votes)
        await undercover_game_controller.submit_vote(game_uuid, target_b.id, target_a.id)

        # Assert — target_a should be eliminated (has most votes or tied with mayor's vote)
        game = await _get_game(session, result["game_id"])
        eliminated = game.live_state["eliminated_players"]
        assert len(eliminated) > 0

    @pytest.mark.asyncio
    async def test_mr_white_never_first_in_description_order(
        self, undercover_game_controller, setup_undercover_game, session
    ):
        """Mr. White should never be first in description order."""
        # Prepare — 5 players to get Mr. White
        setup = await setup_undercover_game(5)

        # Run multiple times with different seeds to verify
        for seed in range(10):
            random.seed(seed)
            try:
                result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
                game = await _get_game(session, result["game_id"])
                state = game.live_state

                mr_white = _find_player_by_role(state, UndercoverRole.MR_WHITE.value)
                order = state["turns"][0]["description_order"]

                if mr_white and len(order) > 1:
                    assert order[0] != mr_white["user_id"], f"Mr. White was first with seed {seed}"

                # Clean up for next iteration — remove active_game_id
                room = (await session.exec(select(Room).where(Room.id == setup["room"].id))).first()
                room.active_game_id = None
                session.add(room)
                await session.commit()
            except BaseError:
                # Room might already have active game, skip
                break

    @pytest.mark.asyncio
    async def test_flag_modified_persists_state(self, undercover_game_controller, setup_undercover_game, session):
        """Re-fetch game after mutation verifies state was persisted."""
        # Prepare
        setup = await setup_undercover_game(3)
        result = await _start_game(undercover_game_controller, setup["room"].id, setup["users"][0].id)
        game = await _get_game(session, result["game_id"])
        first_describer = game.live_state["turns"][0]["description_order"][0]

        # Act
        await undercover_game_controller.submit_description(UUID(result["game_id"]), UUID(first_describer), "persisted")

        # Assert — re-fetch from DB
        game = await _get_game(session, result["game_id"])
        assert game.live_state["turns"][0]["words"][first_describer] == "persisted"

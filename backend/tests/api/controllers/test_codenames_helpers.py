"""Tests for codenames_helpers pure functions."""

import pytest

from ipg.api.controllers.codenames_helpers import (
    CodenamesCardType,
    CodenamesRole,
    CodenamesTeam,
    assign_players,
    build_board,
    get_board_for_player,
    get_player_from_game,
)


class TestBuildBoard:
    def test_builds_25_cards(self):
        """build_board returns exactly 25 cards."""
        words = [f"word{i}" for i in range(25)]
        board = build_board(words, CodenamesTeam.RED)
        assert len(board) == 25

    def test_card_distribution(self):
        """First team gets 9, second team gets 8, 7 neutral, 1 assassin."""
        words = [f"word{i}" for i in range(25)]
        board = build_board(words, CodenamesTeam.RED)

        red_count = sum(1 for c in board if c["card_type"] == CodenamesCardType.RED.value)
        blue_count = sum(1 for c in board if c["card_type"] == CodenamesCardType.BLUE.value)
        neutral_count = sum(1 for c in board if c["card_type"] == CodenamesCardType.NEUTRAL.value)
        assassin_count = sum(1 for c in board if c["card_type"] == CodenamesCardType.ASSASSIN.value)

        assert red_count == 9  # first team
        assert blue_count == 8  # second team
        assert neutral_count == 7
        assert assassin_count == 1

    def test_all_cards_unrevealed(self):
        """All cards start unrevealed."""
        words = [f"word{i}" for i in range(25)]
        board = build_board(words, CodenamesTeam.RED)

        assert all(not c["revealed"] for c in board)

    def test_blue_first_team_gets_9(self):
        """When blue goes first, blue gets 9 cards."""
        words = [f"word{i}" for i in range(25)]
        board = build_board(words, CodenamesTeam.BLUE)

        blue_count = sum(1 for c in board if c["card_type"] == CodenamesCardType.BLUE.value)
        red_count = sum(1 for c in board if c["card_type"] == CodenamesCardType.RED.value)

        assert blue_count == 9
        assert red_count == 8


class TestAssignPlayers:
    def test_4_players_balanced(self):
        """4 players: 2 per team, 1 spymaster each."""
        users = [{"user_id": f"u{i}", "username": f"user{i}"} for i in range(4)]
        players = assign_players(users, CodenamesTeam.RED)

        red_players = [p for p in players if p["team"] == CodenamesTeam.RED.value]
        blue_players = [p for p in players if p["team"] == CodenamesTeam.BLUE.value]

        assert len(red_players) == 2
        assert len(blue_players) == 2
        assert sum(1 for p in red_players if p["role"] == CodenamesRole.SPYMASTER.value) == 1
        assert sum(1 for p in blue_players if p["role"] == CodenamesRole.SPYMASTER.value) == 1

    def test_5_players_first_team_gets_more(self):
        """5 players: first team gets 3, second gets 2."""
        users = [{"user_id": f"u{i}", "username": f"user{i}"} for i in range(5)]
        players = assign_players(users, CodenamesTeam.RED)

        red_players = [p for p in players if p["team"] == CodenamesTeam.RED.value]
        blue_players = [p for p in players if p["team"] == CodenamesTeam.BLUE.value]

        assert len(red_players) == 3
        assert len(blue_players) == 2


class TestGetBoardForPlayer:
    def _make_board(self):
        words = [f"word{i}" for i in range(25)]
        return build_board(words, CodenamesTeam.RED)

    def test_spymaster_sees_all_types(self):
        """Spymaster sees card_type for all cards."""
        board = self._make_board()
        player = {"user_id": "u1", "team": "red", "role": CodenamesRole.SPYMASTER.value}
        view = get_board_for_player(board, player)

        assert all(c["card_type"] is not None for c in view)

    def test_operative_hides_unrevealed(self):
        """Operative sees card_type=None for unrevealed cards."""
        board = self._make_board()
        player = {"user_id": "u1", "team": "red", "role": CodenamesRole.OPERATIVE.value}
        view = get_board_for_player(board, player)

        assert all(c["card_type"] is None for c in view)

    def test_operative_sees_revealed(self):
        """Operative sees card_type for revealed cards."""
        board = self._make_board()
        board[0]["revealed"] = True
        player = {"user_id": "u1", "team": "red", "role": CodenamesRole.OPERATIVE.value}
        view = get_board_for_player(board, player)

        assert view[0]["card_type"] is not None
        assert all(c["card_type"] is None for c in view[1:])


class TestGetPlayerFromGame:
    def test_found(self):
        """Returns the correct player when found."""
        players = [
            {"user_id": "u1", "username": "alice"},
            {"user_id": "u2", "username": "bob"},
        ]
        result = get_player_from_game(players, "u2")
        assert result["username"] == "bob"

    def test_not_found_raises(self):
        """Raises ValueError when player not found."""
        players = [{"user_id": "u1", "username": "alice"}]
        with pytest.raises(ValueError, match="not found"):
            get_player_from_game(players, "unknown")

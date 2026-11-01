"""Tests for codenames_helpers pure functions."""

import pytest

from majlisna.api.constants import CODENAMES_CLUE_TURN_KEY, CODENAMES_REVEAL_LOG_KEY
from majlisna.api.controllers.codenames_helpers import (
    CodenamesCardType,
    CodenamesGameStatus,
    CodenamesRevealOutcome,
    CodenamesRole,
    CodenamesTeam,
    advance_clue_turn,
    apply_card_reveal,
    assign_players,
    build_board,
    clue_names_a_card,
    current_clue_turn,
    get_board_for_player,
    get_player_from_game,
    hint_is_visible,
    release_departed_operative,
    tally_operative_votes,
    top_voted_cards,
)
from majlisna.api.schemas.error import BaseError

# ========== Helpers ==========


def _make_board():
    words = [f"word{i}" for i in range(25)]
    return build_board(words, CodenamesTeam.RED)


# ========== TestBuildBoard ==========


def test_board_builds_25_cards():
    """build_board returns exactly 25 cards."""
    words = [f"word{i}" for i in range(25)]
    board = build_board(words, CodenamesTeam.RED)
    assert len(board) == 25


def test_board_card_distribution():
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


def test_board_all_cards_unrevealed():
    """All cards start unrevealed."""
    words = [f"word{i}" for i in range(25)]
    board = build_board(words, CodenamesTeam.RED)

    assert all(not c["revealed"] for c in board)


def test_board_blue_first_team_gets_9():
    """When blue goes first, blue gets 9 cards."""
    words = [f"word{i}" for i in range(25)]
    board = build_board(words, CodenamesTeam.BLUE)

    blue_count = sum(1 for c in board if c["card_type"] == CodenamesCardType.BLUE.value)
    red_count = sum(1 for c in board if c["card_type"] == CodenamesCardType.RED.value)

    assert blue_count == 9
    assert red_count == 8


# ========== TestAssignPlayers ==========


def test_assign_4_players_balanced():
    """4 players: 2 per team, 1 spymaster each."""
    users = [{"user_id": f"u{i}", "username": f"user{i}"} for i in range(4)]
    players = assign_players(users, CodenamesTeam.RED)

    red_players = [p for p in players if p["team"] == CodenamesTeam.RED.value]
    blue_players = [p for p in players if p["team"] == CodenamesTeam.BLUE.value]

    assert len(red_players) == 2
    assert len(blue_players) == 2
    assert sum(1 for p in red_players if p["role"] == CodenamesRole.SPYMASTER.value) == 1
    assert sum(1 for p in blue_players if p["role"] == CodenamesRole.SPYMASTER.value) == 1


def test_assign_5_players_first_team_gets_more():
    """5 players: first team gets 3, second gets 2."""
    users = [{"user_id": f"u{i}", "username": f"user{i}"} for i in range(5)]
    players = assign_players(users, CodenamesTeam.RED)

    red_players = [p for p in players if p["team"] == CodenamesTeam.RED.value]
    blue_players = [p for p in players if p["team"] == CodenamesTeam.BLUE.value]

    assert len(red_players) == 3
    assert len(blue_players) == 2


# ========== TestGetBoardForPlayer ==========


def test_board_view_spymaster_sees_all_types():
    """Spymaster sees card_type for all cards."""
    board = _make_board()
    player = {"user_id": "u1", "team": "red", "role": CodenamesRole.SPYMASTER.value}
    view = get_board_for_player(board, player)

    assert all(c["card_type"] is not None for c in view)


def test_board_view_operative_hides_unrevealed():
    """Operative sees card_type=None for unrevealed cards."""
    board = _make_board()
    player = {"user_id": "u1", "team": "red", "role": CodenamesRole.OPERATIVE.value}
    view = get_board_for_player(board, player)

    assert all(c["card_type"] is None for c in view)


def test_board_view_operative_sees_revealed():
    """Operative sees card_type for revealed cards."""
    board = _make_board()
    board[0]["revealed"] = True
    player = {"user_id": "u1", "team": "red", "role": CodenamesRole.OPERATIVE.value}
    view = get_board_for_player(board, player)

    assert view[0]["card_type"] is not None
    assert all(c["card_type"] is None for c in view[1:])


# ========== TestGetPlayerFromGame ==========


def test_player_lookup_found():
    """Returns the correct player when found."""
    players = [
        {"user_id": "u1", "username": "alice"},
        {"user_id": "u2", "username": "bob"},
    ]
    result = get_player_from_game(players, "u2")
    assert result["username"] == "bob"


def test_player_lookup_not_found_raises():
    """Raises BaseError when player not found."""
    players = [{"user_id": "u1", "username": "alice"}]
    with pytest.raises(BaseError, match="not found"):
        get_player_from_game(players, "unknown")


# ========== Votes, reveals and departures (WP-09: BR-09, the reveal log) ==========
#
# A hand-built game: red moves, red cards are 0-8, blue 9-16, neutral 17-23, the
# assassin 24. Red: spymaster "rs", operatives "ra", "rb", "rc". Blue: spymaster "bs",
# operatives "ba", "bb".

RED_CARDS = list(range(9))
BLUE_CARDS = list(range(9, 17))
NEUTRAL_CARDS = list(range(17, 24))
ASSASSIN_CARD = 24


def _player(user_id: str, team: str, role: CodenamesRole) -> dict:
    return {"user_id": user_id, "username": user_id, "team": team, "role": role.value}


def _game_state(*, card_votes: dict | None = None, clue_word: str | None = "Clue", clue_number: int = 2) -> dict:
    board = [{"word": f"word{i}", "card_type": CodenamesCardType.RED.value, "revealed": False} for i in RED_CARDS]
    board += [{"word": f"word{i}", "card_type": CodenamesCardType.BLUE.value, "revealed": False} for i in BLUE_CARDS]
    board += [
        {"word": f"word{i}", "card_type": CodenamesCardType.NEUTRAL.value, "revealed": False} for i in NEUTRAL_CARDS
    ]
    board.append({"word": "word24", "card_type": CodenamesCardType.ASSASSIN.value, "revealed": False})
    red, blue = CodenamesTeam.RED.value, CodenamesTeam.BLUE.value
    return {
        "board": board,
        "players": [
            _player("rs", red, CodenamesRole.SPYMASTER),
            _player("ra", red, CodenamesRole.OPERATIVE),
            _player("rb", red, CodenamesRole.OPERATIVE),
            _player("rc", red, CodenamesRole.OPERATIVE),
            _player("bs", blue, CodenamesRole.SPYMASTER),
            _player("ba", blue, CodenamesRole.OPERATIVE),
            _player("bb", blue, CodenamesRole.OPERATIVE),
        ],
        "current_team": red,
        "current_turn": {
            "team": red,
            "clue_word": clue_word,
            "clue_number": clue_number,
            "guesses_made": 0,
            "max_guesses": clue_number + 1,
            "card_votes": dict(card_votes or {}),
        },
        "red_remaining": len(RED_CARDS),
        "blue_remaining": len(BLUE_CARDS),
        "status": CodenamesGameStatus.IN_PROGRESS.value,
        "winner": None,
        "clue_history": [{"team": red, "clue_word": clue_word, "clue_number": clue_number, "guesses": []}]
        if clue_word
        else [],
        CODENAMES_CLUE_TURN_KEY: 1 if clue_word else 0,
        CODENAMES_REVEAL_LOG_KEY: [],
        "timer_started_at": "2026-10-31T12:00:00+00:00",
    }


def _without(state: dict, user_id: str) -> dict:
    """What the disconnect handler does first: the leaver is no longer in the roster."""
    state["players"] = [p for p in state["players"] if p["user_id"] != user_id]
    return state


def test_tally_ignores_the_vote_of_an_operative_no_longer_on_the_team():
    """BR-09: a departed operative's vote neither fills the quorum nor picks the card."""
    # Prepare: "ra" voted card 2 and left; "rb" voted card 5; "rc" has not voted
    state = _without(_game_state(card_votes={"ra": 2, "rb": 5}), "ra")

    # Act
    before_rc = tally_operative_votes(state)
    state["current_turn"]["card_votes"]["rc"] = 5
    after_rc = tally_operative_votes(state)

    # Assert
    assert before_rc is None  # rb alone is not the quorum of rb + rc
    assert after_rc == 5  # never ra's card 2


def test_tally_waits_for_every_operative_still_on_the_team():
    """No card while one operative of the team has not voted."""
    # Prepare
    state = _game_state(card_votes={"ra": 3, "rb": 3})

    # Act / Assert
    assert tally_operative_votes(state) is None
    state["current_turn"]["card_votes"]["rc"] = 4
    assert tally_operative_votes(state) == 3


def test_tally_breaks_a_tie_among_the_top_cards_only(monkeypatch):
    """A tie is drawn among the most-voted cards, never among the others."""
    # Prepare: 1 vote each for 3, 4 and 7 — a three-way tie
    state = _game_state(card_votes={"ra": 3, "rb": 4, "rc": 7})
    drawn: list[list[int]] = []
    monkeypatch.setattr("majlisna.api.controllers.codenames_helpers.rng.choice", lambda xs: drawn.append(xs) or xs[-1])

    # Act
    card = tally_operative_votes(state)

    # Assert
    assert sorted(drawn[0]) == [3, 4, 7]
    assert card == drawn[0][-1]
    assert top_voted_cards({"ra": 3, "rb": 3, "rc": 7}) == [3]


def test_tally_of_a_team_without_operatives_is_none():
    """A team whose operatives are all gone has no quorum to reach."""
    # Prepare
    state = _game_state(card_votes={"ra": 1})
    for leaver in ("ra", "rb", "rc"):
        _without(state, leaver)

    # Act / Assert
    assert tally_operative_votes(state) is None


def test_apply_card_reveal_logs_the_reveal():
    """One entry per card turned: the guessing team, the card, its voters and the clue's turn."""
    # Prepare
    state = _game_state(card_votes={"ra": 0, "rb": 0, "rc": 0})

    # Act
    outcome = apply_card_reveal(state, 0, ["ra", "rb", "rc"])

    # Assert
    assert outcome == CodenamesRevealOutcome.CORRECT
    assert state["board"][0]["revealed"] is True
    assert state["current_turn"]["guesses_made"] == 1
    assert state["current_turn"]["card_votes"] == {}  # a reveal consumes the votes
    assert state["red_remaining"] == len(RED_CARDS) - 1
    assert state["clue_history"][-1]["guesses"] == [{"word": "word0", "card_type": "red", "correct": True}]
    assert state[CODENAMES_REVEAL_LOG_KEY] == [
        {"card_index": 0, "team": "red", "card_type": "red", "voter_ids": ["ra", "rb", "rc"], "clue_turn": 1}
    ]
    assert state["current_team"] == "red"  # a right card keeps the turn


@pytest.mark.parametrize(
    ("card_index", "expected", "team_after"),
    [
        (NEUTRAL_CARDS[0], CodenamesRevealOutcome.NEUTRAL, "blue"),
        (BLUE_CARDS[0], CodenamesRevealOutcome.OPPONENT_CARD, "blue"),
    ],
)
def test_apply_card_reveal_of_a_wrong_card_hands_the_turn_over(card_index, expected, team_after):
    """A neutral or an opponent's card ends the team's turn; the log keeps who turned it."""
    # Prepare
    state = _game_state()

    # Act
    outcome = apply_card_reveal(state, card_index, ["ra"])

    # Assert
    assert outcome == expected
    assert state["current_team"] == team_after
    assert state["current_turn"]["clue_word"] is None
    assert state[CODENAMES_REVEAL_LOG_KEY][-1]["team"] == "red"
    assert state[CODENAMES_REVEAL_LOG_KEY][-1]["card_type"] == state["board"][card_index]["card_type"]


def test_apply_card_reveal_of_the_assassin_ends_the_game_for_the_other_team():
    """The assassin: the game is over and the other team wins; the turn does not move."""
    # Prepare
    state = _game_state()

    # Act
    outcome = apply_card_reveal(state, ASSASSIN_CARD, ["ra", "rb"])

    # Assert
    assert outcome == CodenamesRevealOutcome.ASSASSIN
    assert state["status"] == CodenamesGameStatus.FINISHED.value
    assert state["winner"] == "blue"
    assert state["current_team"] == "red"
    assert state[CODENAMES_REVEAL_LOG_KEY][-1]["voter_ids"] == ["ra", "rb"]


def test_apply_card_reveal_of_the_last_card_wins_and_max_guesses_passes():
    """The team's last card wins; the last allowed guess on a right card passes the turn."""
    # Prepare
    winning = _game_state()
    winning["red_remaining"] = 1
    passing = _game_state(clue_number=1)
    passing["current_turn"]["guesses_made"] = 1

    # Act
    win = apply_card_reveal(winning, 0, ["ra"])
    max_guesses = apply_card_reveal(passing, 0, ["ra"])

    # Assert
    assert win == CodenamesRevealOutcome.WIN
    assert winning["winner"] == "red" and winning["status"] == CodenamesGameStatus.FINISHED.value
    assert max_guesses == CodenamesRevealOutcome.MAX_GUESSES
    assert passing["current_team"] == "blue"


def test_reveal_log_starts_on_a_game_that_predates_it():
    """A game started before the log (no key, no counter) gets both on its first reveal."""
    # Prepare
    state = _game_state()
    del state[CODENAMES_REVEAL_LOG_KEY]
    del state[CODENAMES_CLUE_TURN_KEY]

    # Act
    apply_card_reveal(state, 0, ["ra"])

    # Assert: the clue in play is the first of clue_history
    assert state[CODENAMES_REVEAL_LOG_KEY][0]["clue_turn"] == 1


def test_clue_turn_counts_every_clue_given():
    """advance_clue_turn: +1 per clue; a game without the counter counts its clue history."""
    # Prepare
    fresh = {"clue_history": [], CODENAMES_CLUE_TURN_KEY: 0}
    legacy = {"clue_history": [{"team": "red"}, {"team": "blue"}]}

    # Act
    first = advance_clue_turn(fresh)
    third = advance_clue_turn(legacy)

    # Assert
    assert first == 1 and fresh[CODENAMES_CLUE_TURN_KEY] == 1
    assert third == 3 and legacy[CODENAMES_CLUE_TURN_KEY] == 3
    assert current_clue_turn({"clue_history": [{}, {}]}) == 2


def test_release_departed_operative_drops_their_vote_and_waits_for_the_others():
    """The leaver's vote disappears; with an operative still to vote, nothing is revealed."""
    # Prepare: ra voted 2, rb voted 5, rc has not voted; ra leaves
    state = _without(_game_state(card_votes={"ra": 2, "rb": 5}), "ra")

    # Act
    outcome = release_departed_operative(state, "ra")

    # Assert
    assert outcome is None
    assert state["current_turn"]["card_votes"] == {"rb": 5}
    assert not any(card["revealed"] for card in state["board"])
    assert state[CODENAMES_REVEAL_LOG_KEY] == []


def test_release_departed_operative_reveals_once_the_remaining_votes_complete_the_quorum():
    """The leaver was the last one the team waited on: the card the others agreed on turns."""
    # Prepare: ra and rb voted card 3; rc never voted, and leaves
    state = _without(_game_state(card_votes={"ra": 3, "rb": 3}), "rc")

    # Act
    outcome = release_departed_operative(state, "rc")

    # Assert
    assert outcome == CodenamesRevealOutcome.CORRECT
    assert state["board"][3]["revealed"] is True
    assert state["current_turn"]["card_votes"] == {}
    assert state[CODENAMES_REVEAL_LOG_KEY] == [
        {"card_index": 3, "team": "red", "card_type": "red", "voter_ids": ["ra", "rb"], "clue_turn": 1}
    ]


def test_release_departed_operative_never_reveals_the_leavers_card():
    """ra voted 2 and leaves; rb and rc voted 6: card 6 turns, never 2."""
    # Prepare: the leaver is still in the roster — the helper works either way
    state = _game_state(card_votes={"ra": 2, "rb": 6, "rc": 6})
    state["current_turn"]["card_votes"].pop("rc")  # rc has not voted yet...
    release_departed_operative(state, "ra")
    state["current_turn"]["card_votes"]["rc"] = 6  # ...then votes 6

    # Act
    card = tally_operative_votes(state, excluding="ra")

    # Assert
    assert card == 6
    assert state["board"][2]["revealed"] is False


def test_release_departed_operative_can_end_the_game():
    """A departure that completes a vote on the assassin ends the game; the outcome says so."""
    # Prepare
    state = _without(_game_state(card_votes={"ra": ASSASSIN_CARD, "rb": ASSASSIN_CARD}), "rc")

    # Act
    outcome = release_departed_operative(state, "rc")

    # Assert
    assert outcome == CodenamesRevealOutcome.ASSASSIN
    assert state["status"] == CodenamesGameStatus.FINISHED.value
    assert state["winner"] == "blue"


@pytest.mark.parametrize("case", ["no_clue", "finished", "other_team", "no_operative_left"])
def test_release_departed_operative_reveals_nothing_when_there_is_no_vote_to_settle(case):
    """No clue yet, a finished game, a leaver of the side not moving with votes still owed,
    or a team left with no operative: the vote is dropped and no card turns."""
    # Prepare
    state = _game_state(card_votes={"ra": 1}, clue_word=None if case == "no_clue" else "Clue")
    leaver = "ra"
    if case == "finished":
        state["current_turn"]["card_votes"] = {"ra": 1, "rb": 1}
        state["status"] = CodenamesGameStatus.FINISHED.value
        leaver = "rc"
    elif case == "other_team":
        leaver = "ba"
    elif case == "no_operative_left":
        _without(state, "rb")
        _without(state, "rc")
    _without(state, leaver)

    # Act
    outcome = release_departed_operative(state, leaver)

    # Assert
    assert outcome is None
    assert leaver not in state["current_turn"]["card_votes"]
    assert not any(card["revealed"] for card in state["board"])


def test_clue_names_a_card_in_any_case_spacing_or_script():
    """The clue check: the card's word in any case, with accents, without its article, or
    in Arabic; a different word passes."""
    # Prepare
    words = ["Wudu", "Al-Aqsa", "Sabr"]
    arabic = ["وضوء", "الأقصى", "صبر"]

    # Act / Assert
    assert clue_names_a_card("WUDU", words, arabic)
    assert clue_names_a_card("Wudū", words, arabic)
    assert clue_names_a_card("Aqsa", words, arabic)
    assert clue_names_a_card("الصبر", words, arabic)
    assert not clue_names_a_card("Water", words, arabic)


@pytest.mark.parametrize(
    ("player", "card_revealed", "visible"),
    [
        (_player("rs", "red", CodenamesRole.SPYMASTER), False, True),
        (_player("ra", "red", CodenamesRole.OPERATIVE), True, True),
        (_player("ra", "red", CodenamesRole.OPERATIVE), False, False),
    ],
)
def test_a_hint_is_visible_to_the_spymaster_and_on_turned_cards(player, card_revealed, visible):
    """The hint-viewed rule follows get_board: an operative sees a meaning once the card turns."""
    # Prepare
    card = {"word": "word0", "card_type": "red", "revealed": card_revealed}

    # Act / Assert
    assert hint_is_visible(card, player) is visible

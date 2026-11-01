"""Unit tests for the pure Undercover state rules (``controllers/undercover_rules``).

Every function there mutates a ``live_state`` dict and touches no session, so these
tests build the state by hand. The flows through the real controllers and the real
departure paths live in ``test_undercover_game.py`` and ``test_wp02_ready_quorum.py``.
"""

from datetime import UTC, datetime, timedelta

import pytest

from majlisna.api.constants import MR_WHITE_GUESS_RESULT_KEY, PAUSE_STATE_KEY, UNDERCOVER_READY_PLAYERS_KEY
from majlisna.api.controllers import undercover_rules
from majlisna.api.controllers.undercover_rules import (
    advance_describer,
    generate_description_order,
    open_next_round,
    open_next_round_if_ready,
    ready_required,
    repair_turn_after_dropout,
)
from majlisna.api.models.undercover import UndercoverRole
from majlisna.api.utils.rng import rng

CIVILIAN = UndercoverRole.CIVILIAN.value
UNDERCOVER = UndercoverRole.UNDERCOVER.value
MR_WHITE = UndercoverRole.MR_WHITE.value

_OLD_INSTANT = (datetime.now(UTC) - timedelta(hours=1)).isoformat()


def _player(user_id: str, role: str = CIVILIAN, *, alive: bool = True, mayor: bool = False) -> dict:
    return {"user_id": user_id, "username": user_id, "role": role, "is_alive": alive, "is_mayor": mayor}


def _state(players: list[dict], turn: dict) -> dict:
    return {
        "players": players,
        "eliminated_players": [],
        "turns": [turn],
        "timer_started_at": _OLD_INSTANT,
    }


def _describing_turn(order: list[str], index: int = 0) -> dict:
    return {
        "votes": {},
        "words": {},
        "description_order": order,
        "current_describer_index": index,
        "phase": "describing",
    }


def _voting_turn(order: list[str], votes: dict[str, str] | None = None, *, resolved: bool = False) -> dict:
    turn = {
        "votes": dict(votes or {}),
        "words": {uid: "w" for uid in order},
        "description_order": order,
        "current_describer_index": len(order),
        "phase": "voting",
    }
    if resolved:
        turn["resolved"] = True
    return turn


def _kill(state: dict, user_id: str) -> None:
    """What every departure path does before the repair: the leaver is dead."""
    next(p for p in state["players"] if p["user_id"] == user_id)["is_alive"] = False


# ========== advance_describer (BR-02) ==========


def test_advance_describer_steps_over_every_dead_seat():
    """The index moves past each seat no longer alive, however many sit together."""
    # Prepare — c and d left while a was describing
    players = [_player(uid) for uid in "abcdef"]
    turn = _describing_turn(list("abcdef"), index=2)
    state = _state(players, turn)
    _kill(state, "c")
    _kill(state, "d")

    # Act
    opened_voting = advance_describer(state, turn)

    # Assert
    assert opened_voting is False
    assert turn["current_describer_index"] == 4
    assert turn["phase"] == "describing"
    assert state["timer_started_at"] == _OLD_INSTANT


def test_advance_describer_past_the_end_opens_voting_and_restarts_the_clock():
    """Nobody alive is left to describe: the round goes to voting with a fresh timer."""
    # Prepare — the last two seats left
    players = [_player(uid) for uid in "abcd"]
    turn = _describing_turn(list("abcd"), index=2)
    state = _state(players, turn)
    _kill(state, "c")
    _kill(state, "d")

    # Act
    opened_voting = advance_describer(state, turn)

    # Assert
    assert opened_voting is True
    assert turn["current_describer_index"] == 4
    assert turn["phase"] == "voting"
    assert state["timer_started_at"] != _OLD_INSTANT


def test_a_later_describer_leaving_does_not_move_the_current_one():
    """The leaver sits later in the order: the current describer keeps the floor."""
    # Prepare
    players = [_player(uid) for uid in "abcde"]
    turn = _describing_turn(list("abcde"), index=0)
    state = _state(players, turn)
    _kill(state, "c")

    # Act
    repair_turn_after_dropout(state, "c")

    # Assert — the order is intact (it renders the descriptions) and a still speaks
    assert turn["description_order"] == list("abcde")
    assert turn["current_describer_index"] == 0
    assert turn["phase"] == "describing"


# ========== votes for a departed player (BR-07) ==========


def test_votes_for_the_leaver_are_returned_to_their_voters():
    """Every ballot naming the departed player is withdrawn, so its voter can vote again."""
    # Prepare — b, c, d voted for x; x leaves; e and f have not voted
    players = [_player(uid) for uid in ["a", "b", "c", "d", "e", "x"]]
    turn = _voting_turn(["a", "b", "c", "d", "e", "x"], {"b": "x", "c": "x", "d": "x", "a": "b", "x": "a"})
    state = _state(players, turn)
    _kill(state, "x")

    # Act
    awaiting_guess = repair_turn_after_dropout(state, "x")

    # Assert
    assert awaiting_guess is False
    assert turn["votes"] == {"a": "b"}
    assert not turn.get("resolved")
    assert state["eliminated_players"] == []


def test_a_tally_completed_by_subtraction_is_never_drawn_from_zero_votes():
    """Everyone voted for x and x left without voting: the round stays open, nobody is drawn."""
    # Prepare
    players = [_player(uid) for uid in ["a", "b", "c", "d", "x"]]
    turn = _voting_turn(["a", "b", "c", "d", "x"], {"a": "x", "b": "x", "c": "x", "d": "x"})
    state = _state(players, turn)
    _kill(state, "x")

    # Act
    repair_turn_after_dropout(state, "x")

    # Assert
    assert turn["votes"] == {}
    assert not turn.get("resolved")
    assert all(p["is_alive"] for p in state["players"] if p["user_id"] != "x")
    assert state["eliminated_players"] == []


def test_an_all_zero_tally_is_kept_open_even_when_every_ballot_is_in():
    """A complete tally in which no ballot names a living player never resolves at random.

    Reached by rows written before the departed player's ballots were withdrawn: the
    ballots still name a player who left an earlier round.
    """
    # Prepare — x left before (dead), and the three ballots still name him; d leaves now
    players = [_player(uid) for uid in ["a", "b", "c", "d"]] + [_player("x", alive=False)]
    turn = _voting_turn(["a", "b", "c", "d", "x"], {"a": "x", "b": "x", "c": "x"})
    state = _state(players, turn)
    _kill(state, "d")

    # Act
    repair_turn_after_dropout(state, "d")

    # Assert
    assert not turn.get("resolved")
    assert [p["user_id"] for p in state["players"] if p["is_alive"]] == ["a", "b", "c"]
    assert state["eliminated_players"] == []


def test_a_resolved_round_keeps_every_ballot_for_the_record():
    """A resolved round's votes are history: the departure does not touch them."""
    # Prepare
    players = [_player(uid) for uid in "abcd"] + [_player("x", alive=False)]
    votes = {"a": "x", "b": "x", "c": "a", "d": "x"}
    turn = _voting_turn(["a", "b", "c", "d", "x"], votes, resolved=True)
    state = _state(players, turn)
    _kill(state, "a")

    # Act
    repair_turn_after_dropout(state, "a")

    # Assert
    assert turn["votes"] == votes


# ========== a departure during the Mr. White guess (BR-08) ==========


def _guessing_state() -> dict:
    players = [
        _player("mw", MR_WHITE, alive=False),
        _player("uc", UNDERCOVER, alive=False),
        _player("c1"),
        _player("c2"),
        _player("c3"),
    ]
    turn = _voting_turn(["mw", "c1", "c2", "c3"], {"c1": "mw", "c2": "mw", "c3": "mw", "mw": "c1"}, resolved=True)
    turn["phase"] = "mr_white_guessing"
    state = _state(players, turn)
    state["mr_white_guesser"] = "mw"
    return state


@pytest.mark.parametrize("leaver", ["c1", "uc"])
def test_someone_else_leaving_during_the_guess_leaves_the_guess_owed(leaver: str):
    """A civilian, or the already-eliminated undercover, leaves: the guess still decides."""
    # Prepare
    state = _guessing_state()
    _kill(state, leaver)

    # Act
    awaiting_guess = repair_turn_after_dropout(state, leaver)

    # Assert — True tells the departure path not to decide a winner, nor to cancel
    assert awaiting_guess is True
    assert state["mr_white_guesser"] == "mw"
    assert state["turns"][-1]["phase"] == "mr_white_guessing"
    assert MR_WHITE_GUESS_RESULT_KEY not in state


def test_the_guesser_leaving_closes_his_guess_as_wrong():
    """Mr. White himself leaves: his guess is closed as wrong and the round can be left."""
    # Prepare
    state = _guessing_state()

    # Act
    awaiting_guess = repair_turn_after_dropout(state, "mw")

    # Assert
    assert awaiting_guess is False
    assert "mr_white_guesser" not in state
    turn = state["turns"][-1]
    assert turn["phase"] == "voting"
    assert turn["mr_white_guess"] == {"word": None, "correct": False}
    assert state[MR_WHITE_GUESS_RESULT_KEY] == {"user_id": "mw", "correct": False}


# ========== the ready quorum (owner rule (d)) ==========


def _resolved_state(*, ready: list[str] | None = None) -> dict:
    """Six players, b eliminated in round 1, the round resolved, no winner."""
    players = [_player("host"), _player("a"), _player("b", alive=False), _player("c"), _player("d")]
    players.append(_player("u", UNDERCOVER))
    turn = _voting_turn(["host", "a", "b", "c", "d", "u"], {}, resolved=True)
    if ready is not None:
        turn[UNDERCOVER_READY_PLAYERS_KEY] = list(ready)
    return _state(players, turn)


def test_the_quorum_is_every_alive_player_but_the_host():
    """The host forces; readiness is asked of everyone else still alive."""
    # Prepare
    state = _resolved_state()

    # Act / Assert
    assert ready_required(state, "host") == {"a", "c", "d", "u"}
    # A room whose host deleted their account (owner NULL) asks every alive player.
    assert ready_required(state, None) == {"host", "a", "c", "d", "u"}


def test_the_round_opens_only_once_the_whole_quorum_is_ready():
    """Three of four is not enough; the fourth mark opens the next round."""
    # Prepare
    state = _resolved_state(ready=["a", "c", "d"])

    # Act
    opened = open_next_round_if_ready(state, "host")

    # Assert
    assert opened is False
    assert len(state["turns"]) == 1

    # Act — the last one
    state["turns"][-1][UNDERCOVER_READY_PLAYERS_KEY].append("u")
    opened = open_next_round_if_ready(state, "host")

    # Assert
    assert opened is True
    assert len(state["turns"]) == 2


def test_open_next_round_deals_a_fresh_describing_turn_to_the_living():
    """Only the alive are in the order, Mr. White is never first, the clock restarts."""
    # Prepare
    state = _resolved_state(ready=["a", "c"])

    # Act
    new_turn = open_next_round(state)

    # Assert
    assert state["turns"][-1] is new_turn
    assert new_turn["phase"] == "describing"
    assert new_turn["current_describer_index"] == 0
    assert new_turn["votes"] == {}
    assert new_turn["words"] == {}
    assert sorted(new_turn["description_order"]) == ["a", "c", "d", "host", "u"]
    assert UNDERCOVER_READY_PLAYERS_KEY not in new_turn
    # The marks were for the round that is now over.
    assert UNDERCOVER_READY_PLAYERS_KEY not in state["turns"][0]
    assert state["timer_started_at"] != _OLD_INSTANT


def test_a_departure_that_completes_the_quorum_opens_the_next_round():
    """Everyone else was ready and the one player they waited on (a civilian) leaves."""
    # Prepare
    state = _resolved_state(ready=["a", "c", "u"])
    _kill(state, "d")

    # Act
    awaiting_guess = repair_turn_after_dropout(state, "d", host_id="host")

    # Assert
    assert awaiting_guess is False
    assert len(state["turns"]) == 2
    assert state["turns"][-1]["phase"] == "describing"
    assert sorted(state["turns"][-1]["description_order"]) == ["a", "c", "host", "u"]


def test_a_departure_without_the_host_known_never_opens_early():
    """Without ``host_id`` the quorum is every alive player: the host's absence of a mark holds it."""
    # Prepare
    state = _resolved_state(ready=["a", "c", "u"])
    _kill(state, "d")

    # Act
    repair_turn_after_dropout(state, "d")

    # Assert
    assert len(state["turns"]) == 1


def test_the_leavers_ready_mark_is_dropped():
    """A departed player's mark must not count toward the quorum."""
    # Prepare
    state = _resolved_state(ready=["a", "c"])
    _kill(state, "a")

    # Act
    repair_turn_after_dropout(state, "a", host_id="host")

    # Assert
    assert state["turns"][-1][UNDERCOVER_READY_PLAYERS_KEY] == ["c"]
    assert len(state["turns"]) == 1


def test_a_departure_that_decides_the_game_opens_no_round():
    """The last undercover leaves: the departure path ends the game, no round is dealt."""
    # Prepare
    state = _resolved_state(ready=["a", "c", "d"])
    _kill(state, "u")
    state["players"].append(_player("u2", UNDERCOVER, alive=False))

    # Act
    repair_turn_after_dropout(state, "u", host_id="host")

    # Assert — no impostor is alive: the civilians win, which the caller records
    assert undercover_rules.winning_team(state) == CIVILIAN
    assert len(state["turns"]) == 1


def test_a_departure_during_the_prayer_pause_opens_no_round():
    """Nothing moves while the host has paused the game; the next round waits for the resume."""
    # Prepare
    state = _resolved_state(ready=["a", "c", "d"])
    state[PAUSE_STATE_KEY] = {"by": "host", "by_username": "host", "at": datetime.now(UTC).isoformat()}
    _kill(state, "u")

    # Act
    repair_turn_after_dropout(state, "u", host_id="host")

    # Assert
    assert len(state["turns"]) == 1


# ========== the description order ==========


def test_mr_white_is_moved_off_the_first_seat(monkeypatch: pytest.MonkeyPatch):
    """A shuffle that seats Mr. White first is corrected — deterministically, not by luck."""
    # Prepare — the draw puts Mr. White first every time
    players = [_player("a"), _player("b"), _player("mw", MR_WHITE), _player("c", UNDERCOVER)]
    monkeypatch.setattr(rng, "shuffle", lambda seq: seq.sort(key=lambda uid: uid != "mw"))

    # Act
    order = generate_description_order(players)

    # Assert
    assert order[0] != "mw"
    assert sorted(order) == ["a", "b", "c", "mw"]

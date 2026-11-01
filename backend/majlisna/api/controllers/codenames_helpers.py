"""Codenames rules on ``live_state`` alone: no session, no lock, no commit.

The controller (``codenames_game``) and the disconnect handler (``disconnect``) both
change a Codenames game, and ``disconnect`` cannot import a controller (``base_game`` →
``room`` → ``disconnect``), so the rules they share live here: how a team's vote is
counted, what turning a card does, and what a departing operative leaves behind.
"""

import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum

from majlisna.api.constants import (
    CODENAMES_ASSASSIN_CARDS,
    CODENAMES_CLUE_TURN_KEY,
    CODENAMES_FIRST_TEAM_CARDS,
    CODENAMES_NEUTRAL_CARDS,
    CODENAMES_REVEAL_LOG_KEY,
    CODENAMES_SECOND_TEAM_CARDS,
)
from majlisna.api.schemas.error import (
    NotAGamePlayerError,
)
from majlisna.api.utils.rng import rng
from majlisna.api.utils.text_match import matches_any


class CodenamesTeam(StrEnum):
    RED = "red"
    BLUE = "blue"


class CodenamesCardType(StrEnum):
    RED = "red"
    BLUE = "blue"
    NEUTRAL = "neutral"
    ASSASSIN = "assassin"


class CodenamesRole(StrEnum):
    SPYMASTER = "spymaster"
    OPERATIVE = "operative"


class CodenamesGameStatus(StrEnum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class CodenamesRevealOutcome(StrEnum):
    """What turning a card did (``GuessCardResponse.result`` carries the value)."""

    CORRECT = "correct"  # the team's own card, guesses left
    MAX_GUESSES = "max_guesses"  # the team's own card, the last guess the clue allowed
    WIN = "win"  # the team's last card
    NEUTRAL = "neutral"
    OPPONENT_CARD = "opponent_card"
    OPPONENT_WINS = "opponent_wins"  # the other team's last card
    ASSASSIN = "assassin"  # the other team wins


# The outcomes after which the turn goes to the other team, when the game goes on.
TURN_ENDING_OUTCOMES = frozenset(
    {CodenamesRevealOutcome.NEUTRAL, CodenamesRevealOutcome.OPPONENT_CARD, CodenamesRevealOutcome.MAX_GUESSES}
)


def build_board(words: list[str], first_team: CodenamesTeam) -> list[dict]:
    """Build a 25-card Codenames board with assigned card types.

    Returns list of dicts: [{word, card_type, revealed}, ...]
    """
    second_team = CodenamesTeam.BLUE if first_team == CodenamesTeam.RED else CodenamesTeam.RED

    first_team_card_type = CodenamesCardType(first_team.value)
    second_team_card_type = CodenamesCardType(second_team.value)

    card_types = (
        [first_team_card_type.value] * CODENAMES_FIRST_TEAM_CARDS
        + [second_team_card_type.value] * CODENAMES_SECOND_TEAM_CARDS
        + [CodenamesCardType.NEUTRAL.value] * CODENAMES_NEUTRAL_CARDS
        + [CodenamesCardType.ASSASSIN.value] * CODENAMES_ASSASSIN_CARDS
    )
    rng.shuffle(card_types)

    board = []
    for word, card_type in zip(words, card_types, strict=True):
        board.append({"word": word, "card_type": card_type, "revealed": False})

    return board


def assign_players(
    room_user_links: list[dict],
    first_team: CodenamesTeam,
) -> list[dict]:
    """Assign players to teams and roles for a Codenames game.

    room_user_links: list of dicts with user_id and username.
    Returns list of player dicts with user_id, username, team, role.
    """
    second_team = CodenamesTeam.BLUE if first_team == CodenamesTeam.RED else CodenamesTeam.RED

    shuffled = list(room_user_links)
    rng.shuffle(shuffled)

    mid = len(shuffled) // 2
    first_team_users = shuffled[: mid + (len(shuffled) % 2)]
    second_team_users = shuffled[mid + (len(shuffled) % 2) :]

    players = []

    for i, user in enumerate(first_team_users):
        role = CodenamesRole.SPYMASTER if i == 0 else CodenamesRole.OPERATIVE
        players.append(
            {
                "user_id": str(user["user_id"]),
                "username": user["username"],
                "team": first_team.value,
                "role": role.value,
            }
        )

    for i, user in enumerate(second_team_users):
        role = CodenamesRole.SPYMASTER if i == 0 else CodenamesRole.OPERATIVE
        players.append(
            {
                "user_id": str(user["user_id"]),
                "username": user["username"],
                "team": second_team.value,
                "role": role.value,
            }
        )

    return players


def get_board_for_player(board: list[dict], player: dict) -> list[dict]:
    """Get the board state appropriate for the player's role.

    Spymasters see all card types. Operatives only see revealed cards' types.
    """
    board_view = []
    for i, card in enumerate(board):
        card_data = {
            "index": i,
            "word": card["word"],
            "revealed": card["revealed"],
        }

        if player["role"] == CodenamesRole.SPYMASTER.value or card["revealed"]:
            card_data["card_type"] = card["card_type"]
        else:
            card_data["card_type"] = None

        board_view.append(card_data)

    return board_view


def get_player_from_game(players: list[dict], user_id: str) -> dict:
    """Find a player in the game by user_id."""
    for player in players:
        if player["user_id"] == user_id:
            return player
    raise NotAGamePlayerError(message=f"Player {user_id} not found in game.", status_code=400)


def other_team(team: str) -> str:
    """The side that is not ``team``."""
    return CodenamesTeam.BLUE.value if team == CodenamesTeam.RED.value else CodenamesTeam.RED.value


def new_turn(team: str) -> dict:
    """The turn a team starts with: no clue yet, no guess, no vote."""
    return {
        "team": team,
        "clue_word": None,
        "clue_number": 0,
        "guesses_made": 0,
        "max_guesses": 0,
        "card_votes": {},
    }


def switch_turn(state: dict) -> None:
    """Hand the turn to the other team; its clue timer starts now."""
    next_team = other_team(state["current_team"])
    state["current_team"] = next_team
    state["current_turn"] = new_turn(next_team)
    state["timer_started_at"] = datetime.now(UTC).isoformat()


def current_clue_turn(state: dict) -> int:
    """How many clues the game has had: ``state[CODENAMES_CLUE_TURN_KEY]``.

    A game started before the counter existed counts its clue history, which has one
    entry per clue, so a reveal's ``clue_turn`` is always that clue's 1-based position
    in ``clue_history``.
    """
    counter = state.get(CODENAMES_CLUE_TURN_KEY)
    if isinstance(counter, int):
        return counter
    return len(state.get("clue_history") or [])


def advance_clue_turn(state: dict) -> int:
    """Count one more clue (``give_clue``, before it appends to ``clue_history``)."""
    turn = current_clue_turn(state) + 1
    state[CODENAMES_CLUE_TURN_KEY] = turn
    return turn


def clue_names_a_card(clue: str, board_words: Iterable[str], arabic_forms: Iterable[str | None]) -> bool:
    """Whether ``clue`` (already stripped) is one of the cards' own words (BR-14).

    The Latin word in its casefolded NFKD form, or through ``matches_any`` (accents,
    the "al-" article, hyphens), and each card's Arabic form, which is printed on the
    card too: "صبر" for the Sabr card is the card's own word.
    """
    folded = unicodedata.normalize("NFKD", clue).casefold()
    latin = list(board_words)
    if any(unicodedata.normalize("NFKD", word).casefold() == folded for word in latin):
        return True
    return matches_any(clue, latin) or matches_any(clue, arabic_forms)


def hint_is_visible(card: dict, player: dict) -> bool:
    """Whether ``player`` can open this card's meaning: the spymaster always, an
    operative once the card is turned (the rule of ``get_board``)."""
    return player.get("role") == CodenamesRole.SPYMASTER.value or bool(card.get("revealed"))


def current_operative_ids(state: dict, *, excluding: str | None = None) -> list[str]:
    """The operatives on the team to move, as the roster lists them now.

    ``excluding`` leaves out a player who is leaving, so a departure counts the same
    whether or not the caller has already taken them out of ``state["players"]``.
    """
    team = state["current_team"]
    return [
        p["user_id"]
        for p in state["players"]
        if p["team"] == team and p["role"] == CodenamesRole.OPERATIVE.value and p["user_id"] != excluding
    ]


def counted_operative_votes(state: dict, *, excluding: str | None = None) -> dict[str, int]:
    """The card votes that count: only those of operatives still on the team (BR-09).

    A departed operative's ballot used to stay in ``card_votes``, fill the quorum
    before every remaining operative had voted, and could be the card revealed.
    """
    operatives = set(current_operative_ids(state, excluding=excluding))
    votes = (state.get("current_turn") or {}).get("card_votes") or {}
    return {voter: card for voter, card in votes.items() if voter in operatives}


def top_voted_cards(votes: dict[str, int]) -> list[int]:
    """The most-voted cards (several: a tie). Their order means nothing: ``card_votes``
    is JSONB on PostgreSQL, which keeps no insertion order."""
    counts: dict[int, int] = {}
    for card in votes.values():
        counts[card] = counts.get(card, 0) + 1
    if not counts:
        return []
    best = max(counts.values())
    return [card for card, count in counts.items() if count == best]


def tally_operative_votes(state: dict, *, excluding: str | None = None) -> int | None:
    """The card the team turns, once every operative still on it has voted; else None.

    The quorum is the team's current operatives and only their votes count. A tie is
    drawn at random among the top cards. A team without an operative has no quorum.
    """
    operatives = current_operative_ids(state, excluding=excluding)
    votes = counted_operative_votes(state, excluding=excluding)
    if not operatives or len(votes) < len(operatives):
        return None
    return rng.choice(top_voted_cards(votes))


def _resolve_card(state: dict, card: dict) -> CodenamesRevealOutcome:
    """Score a card just turned for the team to move; sets ``status``/``winner`` on a finish."""
    team = state["current_team"]
    if card["card_type"] == CodenamesCardType.ASSASSIN.value:
        state["status"] = CodenamesGameStatus.FINISHED.value
        state["winner"] = other_team(team)
        return CodenamesRevealOutcome.ASSASSIN

    if card["card_type"] == team:
        if _decrement_remaining(state, team) == 0:
            state["status"] = CodenamesGameStatus.FINISHED.value
            state["winner"] = team
            return CodenamesRevealOutcome.WIN
        turn = state["current_turn"]
        return (
            CodenamesRevealOutcome.MAX_GUESSES
            if turn["guesses_made"] >= turn["max_guesses"]
            else CodenamesRevealOutcome.CORRECT
        )

    if card["card_type"] != CodenamesCardType.NEUTRAL.value:
        opponent = other_team(team)
        if _decrement_remaining(state, opponent) == 0:
            state["status"] = CodenamesGameStatus.FINISHED.value
            state["winner"] = opponent
            return CodenamesRevealOutcome.OPPONENT_WINS
        return CodenamesRevealOutcome.OPPONENT_CARD

    return CodenamesRevealOutcome.NEUTRAL


def _decrement_remaining(state: dict, team: str) -> int:
    """One card fewer to find for ``team``; returns how many are left."""
    key = "red_remaining" if team == CodenamesTeam.RED.value else "blue_remaining"
    state[key] -= 1
    return state[key]


def apply_card_reveal(state: dict, card_index: int, voter_ids: list[str]) -> CodenamesRevealOutcome:
    """Turn ``card_index`` for the team to move, and log it. Returns what it did.

    Marks the card, counts the guess, clears the turn's votes (they chose this card),
    scores it (a finish sets ``status`` and ``winner``; the caller ends the Game row and
    records the stats), adds it to the clue history and to
    ``state[CODENAMES_REVEAL_LOG_KEY]`` — ``{card_index, team, card_type, voter_ids,
    clue_turn}``, which the achievements read (assassin_finder, sweep_victory) — and,
    when the game goes on, passes the turn after a wrong card or the last guess.

    ``voter_ids``: the operatives whose vote was this card (the lone operative of a
    team of one), stored sorted. The caller has validated the card (in range, not yet
    turned).
    """
    team = state["current_team"]
    card = state["board"][card_index]
    card["revealed"] = True
    turn = state["current_turn"]
    turn["guesses_made"] += 1
    turn["card_votes"] = {}

    outcome = _resolve_card(state, card)

    clue_history = state.get("clue_history") or []
    if clue_history:
        clue_history[-1]["guesses"].append(
            {"word": card["word"], "card_type": card["card_type"], "correct": card["card_type"] == team}
        )
    state.setdefault(CODENAMES_REVEAL_LOG_KEY, []).append(
        {
            "card_index": card_index,
            "team": team,
            "card_type": card["card_type"],
            # Sorted: card_votes is JSONB on PostgreSQL, which keeps no key order.
            "voter_ids": sorted(voter_ids),
            "clue_turn": current_clue_turn(state),
        }
    )

    if outcome in TURN_ENDING_OUTCOMES and state["status"] == CodenamesGameStatus.IN_PROGRESS.value:
        switch_turn(state)
    return outcome


def release_departed_operative(state: dict, user_id: str) -> CodenamesRevealOutcome | None:
    """Take a departing player's card vote out of the turn, and settle the vote if that
    completed it (BR-09). Returns the outcome of the card turned, or None.

    For the disconnect handler, under the game lock, on every departure (leave, kick,
    the grace sweep). It works whether or not ``user_id`` is still in
    ``state["players"]``: they are left out of the quorum either way.

    - The leaver's vote is dropped, whoever they were.
    - When the votes of the operatives still on the team to move now make the quorum —
      the leaver was the last one the team was waiting on — the card they chose turns,
      exactly as in ``guess_card`` (``apply_card_reveal``: the reveal log included).
      Nobody can vote again to trigger it otherwise: everyone left has voted.
    - Nothing turns before a clue, in a finished game, or for a team with no operative
      left (the handler ends that game: a team needs both roles).

    A finishing outcome (``state["status"]`` is then FINISHED) leaves the Game row to
    the caller: ``FINISHED``, ``end_time``, ``detach_room_if_current`` and
    ``record_game_end``, as the guess path does. The votes were all cast before the
    departure, so this applies during a prayer pause too, like an Undercover vote a
    departure completes; any clock it restarts is moved past the pause on resume.
    """
    turn = state.get("current_turn") or {}
    votes = turn.get("card_votes")
    if isinstance(votes, dict):
        votes.pop(user_id, None)
    if state.get("status") != CodenamesGameStatus.IN_PROGRESS.value or not turn.get("clue_word"):
        return None

    card_index = tally_operative_votes(state, excluding=user_id)
    if card_index is None:
        return None
    voter_ids = [
        voter for voter, card in counted_operative_votes(state, excluding=user_id).items() if card == card_index
    ]
    return apply_card_reveal(state, card_index, voter_ids)

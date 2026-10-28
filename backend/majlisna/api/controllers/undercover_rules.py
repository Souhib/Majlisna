"""Pure state rules for Undercover, shared by the controller and the disconnect path.

These live outside ``undercover_game`` for an import reason, exactly like
``game_end_stats``: ``base_game`` imports ``RoomController``, which imports
``disconnect``, so ``disconnect`` importing the controller closes a cycle. This
module reaches only the models and the RNG.

Everything here mutates the ``live_state`` dict in place and never touches the
session — the caller owns the lock, the ``flag_modified`` and the single commit.
"""

from datetime import UTC, datetime

from majlisna.api.models.undercover import UndercoverRole
from majlisna.api.schemas.error import GameAlreadyOverError
from majlisna.api.utils.rng import rng


def winning_team(state: dict) -> str | None:
    """Return the winning role value, or None if the game is still open.

    Mr. White only counts where the game actually has one: checking
    ``num_alive_mr_white == 0`` unconditionally would hand civilians the win at
    the start of every 3-player game, which is dealt without a Mr. White.
    """
    players = state["players"]
    num_alive_undercover = sum(1 for p in players if p["role"] == UndercoverRole.UNDERCOVER.value and p["is_alive"])
    num_alive_civilian = sum(1 for p in players if p["role"] == UndercoverRole.CIVILIAN.value and p["is_alive"])
    num_alive_mr_white = sum(1 for p in players if p["role"] == UndercoverRole.MR_WHITE.value and p["is_alive"])

    if num_alive_undercover == 0 and num_alive_mr_white == 0:
        return UndercoverRole.CIVILIAN.value
    if num_alive_civilian == 0:
        return UndercoverRole.UNDERCOVER.value
    if num_alive_undercover + num_alive_mr_white >= num_alive_civilian:
        return UndercoverRole.UNDERCOVER.value
    return None


def eliminate_player_based_on_votes(state: dict) -> tuple[dict, int]:
    """Eliminate the alive player with the most votes. Returns (player, vote_count).

    Marks the turn ``resolved`` so the round can never be counted twice — see
    ``UndercoverGameController.handle_timer_expired``.

    Candidates are restricted to ALIVE players. Seeding the tally with every
    player (dead included) meant a dead player could win the tally and be
    "eliminated" a second time: with one alive player left,
    ``_auto_fill_missing_votes`` cannot record a vote (no one to vote for), so
    every count was 0 and the tie-break picked at random from the whole roster,
    corpses included.
    """
    current_turn = state["turns"][-1]
    votes = current_turn["votes"]
    vote_counts: dict[str, int] = {p["user_id"]: 0 for p in state["players"] if p["is_alive"]}
    if not vote_counts:
        raise GameAlreadyOverError("No alive players left to eliminate.")
    for voted_id in votes.values():
        if voted_id in vote_counts:
            vote_counts[voted_id] += 1

    max_votes = max(vote_counts.values())
    players_with_max_votes = [pid for pid, count in vote_counts.items() if count == max_votes]

    if len(players_with_max_votes) > 1:
        # Mayor breaks tie
        mayor = next((p for p in state["players"] if p.get("is_mayor")), None)
        if mayor and mayor.get("is_alive"):
            mayor_vote = votes.get(mayor["user_id"])
            player_with_most_vote = (
                mayor_vote if mayor_vote in players_with_max_votes else rng.choice(players_with_max_votes)
            )
        else:
            player_with_most_vote = rng.choice(players_with_max_votes)
    else:
        player_with_most_vote = players_with_max_votes[0]

    eliminated_player = next(p for p in state["players"] if p["user_id"] == player_with_most_vote)
    eliminated_player["is_alive"] = False
    state["eliminated_players"].append(
        {
            "user_id": eliminated_player["user_id"],
            "username": eliminated_player["username"],
            "role": eliminated_player["role"],
            # Which turn eliminated them. Vote history and the post-game summary
            # used to pair eliminated_players[i] with turns[i] by POSITION, an
            # implicit invariant that silently produced a wrong history the
            # moment anything appended out of step. Readers prefer this field
            # and fall back to the index for rows written before it existed.
            "round": len(state["turns"]),
        }
    )
    # This round's votes have now produced their elimination and must never
    # produce another one. See handle_timer_expired.
    current_turn["resolved"] = True

    return eliminated_player, vote_counts[player_with_most_vote]


def enter_mr_white_guess(state: dict, eliminated_player: dict) -> None:
    """Put the turn into the Mr. White guessing phase for the player just eliminated."""
    state["turns"][-1]["phase"] = "mr_white_guessing"
    state["mr_white_guesser"] = eliminated_player["user_id"]
    state["timer_started_at"] = datetime.now(UTC).isoformat()


def repair_turn_after_dropout(state: dict, user_id: str) -> bool:
    """Unblock the current turn after ``user_id`` left the game. Returns True if a
    Mr. White now owes a guess (the caller must not decide a winner yet).

    A drop-out — a leave, a kick, or a grace-period expiry — used to mark the
    player dead and stop there, which left three ways to wedge a round for good:

    - **Describing.** ``current_describer_index`` still pointed at the departed
      player, and ``submit_description`` only accepts the player at that index.
      Nobody could describe, so the phase never reached voting. The index now
      steps over anyone no longer alive; the order itself is left intact because
      it is also what renders the descriptions already given.
    - **Voting.** ``all_voted`` is only ever evaluated inside ``submit_vote``. If
      the drop-out was the last player anyone was waiting on, every remaining
      alive player had already voted and no further vote could arrive — the
      tally was complete and nothing ever counted it.
    - **Mr. White guessing.** ``mr_white_guesser`` still named the departed
      player, so guessing 403'd for everyone and both other actions rejected the
      phase.

    None of these were rescued by the timer: ``description_timer`` and
    ``voting_timer`` both default to **0**, which means "no time limit", so
    ``handle_timer_expired`` answers ``timer_not_expired`` forever. The room's
    only escape was the host cancelling the game with a rematch.
    """
    turns = state.get("turns") or []
    if not turns:
        return False
    turn = turns[-1]

    _release_turn_from_player(state, turn, user_id)
    return _resolve_round_if_every_vote_is_in(state, turn)


def _release_turn_from_player(state: dict, turn: dict, user_id: str) -> None:
    """Move the current turn off a player who can no longer act on it."""
    # Their vote must not keep the tally artificially full. Only for a round still
    # open: a resolved round's votes are history, and the recap and vote panel
    # both read them back.
    if not turn.get("resolved"):
        turn.get("votes", {}).pop(user_id, None)

    phase = turn.get("phase")
    if phase == "describing":
        # Advance past anyone who can no longer speak rather than deleting them
        # from the order: the order is also what renders the descriptions already
        # given, so removing an entry would wipe a departed player's word off
        # everyone's screen — and their word is evidence the table votes on.
        # Looping handles several dead players sitting next to each other.
        order = turn.get("description_order") or []
        alive_ids = {p["user_id"] for p in state["players"] if p["is_alive"]}
        index = turn.get("current_describer_index", 0)
        while index < len(order) and order[index] not in alive_ids:
            index += 1
        turn["current_describer_index"] = index
        if index >= len(order):
            turn["phase"] = "voting"
            state["timer_started_at"] = datetime.now(UTC).isoformat()
    elif phase == "mr_white_guessing" and state.get("mr_white_guesser") == user_id:
        # Land where a wrong guess and a guess timeout both land.
        state.pop("mr_white_guesser", None)
        turn["phase"] = "voting"
        state["timer_started_at"] = datetime.now(UTC).isoformat()


def _resolve_round_if_every_vote_is_in(state: dict, turn: dict) -> bool:
    """Count the tally if every living player has now voted. True if a Mr. White owes a guess.

    ``all_voted`` is otherwise only ever evaluated inside ``submit_vote``, so a
    tally that became complete by *subtraction* — the last outstanding voter
    leaving — was never counted by anything.
    """
    if turn.get("phase") != "voting" or turn.get("resolved"):
        return False

    alive_ids = {p["user_id"] for p in state["players"] if p["is_alive"]}
    if not alive_ids:
        return False
    cast = [voter for voter in turn.get("votes", {}) if voter in alive_ids]
    if len(cast) < len(alive_ids):
        return False

    eliminated_player, _ = eliminate_player_based_on_votes(state)
    if eliminated_player["role"] == UndercoverRole.MR_WHITE.value:
        enter_mr_white_guess(state, eliminated_player)
        return True
    return False

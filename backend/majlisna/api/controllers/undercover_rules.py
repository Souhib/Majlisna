"""Pure state rules for Undercover, shared by the controller and the disconnect path.

These live outside ``undercover_game`` for an import reason, exactly like
``game_end_stats``: ``base_game`` imports ``RoomController``, which imports
``disconnect``, so ``disconnect`` importing the controller closes a cycle. This
module reaches only the models and the RNG.

Everything here mutates the ``live_state`` dict in place and never touches the
session — the caller owns the lock, the ``flag_modified`` and the single commit.
"""

from datetime import UTC, datetime

from majlisna.api.constants import MR_WHITE_GUESS_RESULT_KEY, UNDERCOVER_READY_PLAYERS_KEY
from majlisna.api.models.undercover import UndercoverRole
from majlisna.api.schemas.error import GameAlreadyOverError
from majlisna.api.utils.game_pause import is_paused
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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _alive_ids(state: dict) -> set[str]:
    return {p["user_id"] for p in state["players"] if p["is_alive"]}


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
    state["timer_started_at"] = _now()


def record_mr_white_guess(state: dict, turn: dict, guesser_id: str | None, word: str | None, *, correct: bool) -> None:
    """Close the pending guess: no guesser any more, and the result in both records.

    ``turn["mr_white_guess"]`` is the round's verdict every player reads (``word`` is
    None when the guess never came: the clock ran out, or he left).
    ``state[MR_WHITE_GUESS_RESULT_KEY]`` is the game's, read by the end-of-game stats
    (``mr_white_correct_guesses``). A correct guess ends the game, so the last result
    is the one that counts. The caller moves the phase on.
    """
    state.pop("mr_white_guesser", None)
    turn["mr_white_guess"] = {"word": word, "correct": correct}
    if guesser_id:
        state[MR_WHITE_GUESS_RESULT_KEY] = {"user_id": guesser_id, "correct": correct}


def advance_describer(state: dict, turn: dict) -> bool:
    """Move ``current_describer_index`` past every seat no longer alive. True if voting opened.

    The index never stops on a departed player's seat: ``submit_description`` only
    accepts the player at the index, so a seat nobody can speak from locked the round
    for good — the timers default to 0 ("no limit"), and next-round needs a resolved
    round. The skip used to run only at the moment of a departure, from the index as
    it stood then, so a player who left LATER in the order than the current describer
    wedged the round as soon as the turn reached their seat (BR-02). It now runs after
    every description and after every departure.

    Past the end of the order, the round goes to voting and its clock restarts. The
    order itself is never edited: it also renders the descriptions already given, and
    a departed player's word is evidence the table votes on.
    """
    order = turn.get("description_order") or []
    alive_ids = _alive_ids(state)
    index = turn.get("current_describer_index", 0)
    while index < len(order) and order[index] not in alive_ids:
        index += 1
    turn["current_describer_index"] = index
    if index < len(order):
        return False
    turn["phase"] = "voting"
    state["timer_started_at"] = _now()
    return True


def generate_description_order(players: list[dict]) -> list[str]:
    """A randomized description order of the alive players. Mr. White is never first."""
    alive_ids = [p["user_id"] for p in players if p["is_alive"]]
    rng.shuffle(alive_ids)

    if len(alive_ids) > 1:
        mr_white_ids = {p["user_id"] for p in players if p["role"] == UndercoverRole.MR_WHITE.value and p["is_alive"]}
        if alive_ids[0] in mr_white_ids:
            swap_candidates = [i for i in range(1, len(alive_ids)) if alive_ids[i] not in mr_white_ids]
            if swap_candidates:
                swap_idx = rng.choice(swap_candidates)
                alive_ids[0], alive_ids[swap_idx] = alive_ids[swap_idx], alive_ids[0]

    return alive_ids


def open_next_round(state: dict) -> dict:
    """Deal the next round: a describing turn over the alive players, its clock started.

    The ONE place a round opens after the first — the host's call, a completed ready
    quorum and a departure that completes it all come here. The previous round's ready
    marks are cleared with it. Returns the new turn.
    """
    if state["turns"]:
        state["turns"][-1].pop(UNDERCOVER_READY_PLAYERS_KEY, None)
    new_turn = {
        "votes": {},
        "words": {},
        "description_order": generate_description_order(state["players"]),
        "current_describer_index": 0,
        "phase": "describing",
    }
    state["turns"].append(new_turn)
    state["timer_started_at"] = _now()
    return new_turn


def ready_required(state: dict, host_id: str | None) -> set[str]:
    """Who must be ready before the next round opens: every alive player but the host.

    The host forces the round with the same call and is never asked. With no host
    (``Room.owner_id`` NULL: the host deleted their account) nobody can force, so every
    alive player is asked.
    """
    return _alive_ids(state) - ({host_id} if host_id else set())


def ready_marks(turn: dict) -> list[str]:
    """The ready marks recorded on a turn, in the order they came."""
    marks = turn.get(UNDERCOVER_READY_PLAYERS_KEY)
    return marks if isinstance(marks, list) else []


def mark_ready(turn: dict, user_id: str) -> None:
    """Record ``user_id`` as ready on this turn, once."""
    marks = turn.setdefault(UNDERCOVER_READY_PLAYERS_KEY, [])
    if user_id not in marks:
        marks.append(user_id)


def ready_count(state: dict, turn: dict, host_id: str | None) -> int:
    """How many of the players asked (``ready_required``) are ready."""
    return len(ready_required(state, host_id) & set(ready_marks(turn)))


def round_awaits_next(turn: dict) -> bool:
    """A resolved round with nothing else owed: the only state a next round may follow."""
    return bool(turn.get("resolved")) and turn.get("phase") != "mr_white_guessing"


def open_next_round_if_ready(state: dict, host_id: str | None) -> bool:
    """Open the next round when every player asked is ready. True if it opened.

    Checked against the full set, not a running count: a mark left by someone who has
    since become the host, or by someone no longer alive, is simply not asked for.
    """
    turns = state.get("turns") or []
    if not turns or not round_awaits_next(turns[-1]):
        return False
    required = ready_required(state, host_id)
    if not required or not required <= set(ready_marks(turns[-1])):
        return False
    open_next_round(state)
    return True


def repair_turn_after_dropout(state: dict, user_id: str, *, host_id: str | None = None) -> bool:
    """Unblock the current turn after ``user_id`` left the game. Returns True while a
    Mr. White still owes a guess — the caller must then decide no winner and cancel
    nothing: the guess, or its timeout, decides.

    ``host_id`` is the room's owner (None for none, and when unknown): it is who the
    ready quorum does not ask. Unknown, the quorum asks every alive player, which can
    only make the departure open the next round LATER, never early.

    A drop-out — a leave, a kick, or a grace-period expiry — used to mark the
    player dead and stop there, which left these ways to wedge a round for good:

    - **Describing.** ``current_describer_index`` still pointed at the departed
      player (``advance_describer``).
    - **Voting.** ``all_voted`` is only ever evaluated inside ``submit_vote``. If
      the drop-out was the last player anyone was waiting on, every remaining
      alive player had already voted and no further vote could arrive — the
      tally was complete and nothing ever counted it. And the ballots cast FOR the
      leaver stayed cast, so their voters could not vote again (BR-07).
    - **Mr. White guessing.** ``mr_white_guesser`` still named the departed
      player, so guessing 403'd for everyone and both other actions rejected the
      phase. Anyone ELSE leaving during the guess decided the game without it
      (BR-08): with no impostor alive the winner check said civilians.
    - **Between rounds.** The ready quorum the round was waiting on may now be
      complete, and no mark would arrive to notice.

    None of these were rescued by the timer: ``description_timer`` and
    ``voting_timer`` both default to **0**, which means "no time limit", so
    ``handle_timer_expired`` answers ``timer_not_expired`` forever.
    """
    turns = state.get("turns") or []
    if not turns:
        return False
    turn = turns[-1]

    _release_turn_from_player(state, turn, user_id)
    if _resolve_round_if_every_vote_is_in(state, turn):
        return True
    if turn.get("phase") == "mr_white_guessing" and state.get("mr_white_guesser"):
        return True
    _open_next_round_after_departure(state, host_id)
    return False


def _release_turn_from_player(state: dict, turn: dict, user_id: str) -> None:
    """Move the current turn off a player who can no longer act on it."""
    if not turn.get("resolved"):
        # Their own vote must not keep the tally artificially full, and every ballot
        # naming a player who is gone is returned to its voter, who may vote again —
        # otherwise the players who had not voted yet decided the round alone, and a
        # tally whose every ballot named the leaver drew a random player from zero
        # votes. Only for a round still open: a resolved round's votes are history,
        # read back by the recap and the vote panel. (While a round is open nobody
        # dies but by leaving, so "not alive" is exactly "departed".)
        alive_ids = _alive_ids(state)
        votes = turn.get("votes", {})
        for voter, target in list(votes.items()):
            if voter == user_id or target not in alive_ids:
                votes.pop(voter)
    else:
        # A departed player's ready mark must not count toward the quorum.
        marks = ready_marks(turn)
        if user_id in marks:
            marks.remove(user_id)

    phase = turn.get("phase")
    if phase == "describing":
        advance_describer(state, turn)
    elif phase == "mr_white_guessing" and state.get("mr_white_guesser") == user_id:
        # He left instead of guessing: a wrong guess, landing where a wrong guess and
        # a guess timeout both land.
        record_mr_white_guess(state, turn, user_id, None, correct=False)
        turn["phase"] = "voting"
        state["timer_started_at"] = _now()


def _resolve_round_if_every_vote_is_in(state: dict, turn: dict) -> bool:
    """Count the tally if every living player has now voted. True if a Mr. White owes a guess.

    ``all_voted`` is otherwise only ever evaluated inside ``submit_vote``, so a
    tally that became complete by *subtraction* — the last outstanding voter
    leaving — was never counted by anything.

    A ballot counts only when it names a living player. A complete tally in which
    none does is never resolved: every count would be 0, and the tie-break would
    eliminate a random player nobody voted for. The round stays open instead.
    """
    if turn.get("phase") != "voting" or turn.get("resolved"):
        return False

    alive_ids = _alive_ids(state)
    if not alive_ids:
        return False
    ballots = {voter: target for voter, target in turn.get("votes", {}).items() if voter in alive_ids}
    if len(ballots) < len(alive_ids):
        return False
    if not any(target in alive_ids for target in ballots.values()):
        return False

    eliminated_player, _ = eliminate_player_based_on_votes(state)
    if eliminated_player["role"] == UndercoverRole.MR_WHITE.value:
        enter_mr_white_guess(state, eliminated_player)
        return True
    return False


def _open_next_round_after_departure(state: dict, host_id: str | None) -> None:
    """Open the next round when the departure completed the ready quorum of a resolved round.

    The quizzes settle a round a departure completes the same way. Not when the
    departure decided the game (the caller ends it), and not during the prayer pause —
    nothing moves then, as ``start_next_round`` refuses every mark; the resume opens it
    (``UndercoverGameController._settle_after_resume``).
    """
    if is_paused(state) or winning_team(state) is not None:
        return
    open_next_round_if_ready(state, host_id)

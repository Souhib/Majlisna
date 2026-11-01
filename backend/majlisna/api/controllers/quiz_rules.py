"""Round rules for the two quizzes, shared by the controllers and the disconnect path.

These live outside ``wordquiz_game`` / ``mcqquiz_game`` for the import reason of
``undercover_rules``: ``base_game`` imports ``RoomController``, which imports
``disconnect``, so ``disconnect`` importing a quiz controller closes a cycle. This
module reaches only the models and the pause helpers.

Everything here mutates the ``live_state`` dict in place and never touches the
session — the caller owns the lock, the ``flag_modified`` and the single commit.
"""

from collections.abc import Callable, Collection, Sequence

from majlisna.api.constants import WORDQUIZ_MAX_ATTEMPTS_PER_ROUND, WORDQUIZ_WRONG_ANSWER_RUNG_PENALTY
from majlisna.api.models.game import GameType
from majlisna.api.utils.game_pause import is_paused


def wordquiz_tries_used(state: dict, user_id: str) -> int:
    """How many answers ``user_id`` has submitted in the open Word Quiz round (right or wrong).

    Read from ``live_state["attempts"]`` (``_record_attempt``, reset each round). MCQ has no
    such record, so this is 0 there.
    """
    record = (state.get("attempts") or {}).get(user_id) or {}
    return int(record.get("count", 0))


def wordquiz_wrong_tries(state: dict, user_id: str) -> int:
    """The tries that missed: every try, minus the one that found the word if there is one."""
    used = wordquiz_tries_used(state, user_id)
    found = user_id in (state.get("answers") or {})
    return max(used - 1, 0) if found else used


def wordquiz_rungs_lost(state: dict, user_id: str) -> int:
    """How many rungs ``user_id``'s wrong tries have cost them this round (owner rule (e))."""
    return wordquiz_wrong_tries(state, user_id) * WORDQUIZ_WRONG_ANSWER_RUNG_PENALTY


def wordquiz_out_of_tries(state: dict, user_id: str) -> bool:
    """Whether ``user_id`` has used all ``WORDQUIZ_MAX_ATTEMPTS_PER_ROUND`` tries of the round."""
    return wordquiz_tries_used(state, user_id) >= WORDQUIZ_MAX_ATTEMPTS_PER_ROUND


def everyone_has_answered(state: dict) -> bool:
    """Whether every player still in the game is done with the open round.

    One rule for both quizzes, read through each game's own ``answers``: MCQ records
    every lock-in there (one attempt, right or wrong), Word Quiz only the answer that
    found the word (a wrong try is an ``attempt``, and the player may type again). So
    "done" means "answered" in MCQ and "found the word" in Word Quiz — or, in Word
    Quiz, "has used every try of the round" (owner rule (e)): such a player can type
    nothing more, so waiting for them would only hold the round open until its timer.

    A game with nobody left is not done: the departure path cancels it instead.
    """
    players = state.get("players") or []
    answers = state.get("answers") or {}
    return bool(players) and all(
        player["user_id"] in answers or wordquiz_out_of_tries(state, player["user_id"]) for player in players
    )


def quiz_winner_label(players: Sequence[dict], winner_ids: Collection[str]) -> str | None:
    """``live_state["winner"]`` of a finished quiz: the one winner's username, else None.

    None for a shared win (a tie at the top), a 0-0 game and a solo game (owner rule (a));
    every top scorer is then in ``live_state[WINNER_IDS_KEY]``. It used to be the first
    seated of the top scorers, so a 6-6 game named one player and a solo 0 named a winner.
    """
    if len(winner_ids) != 1:
        return None
    (only,) = winner_ids
    return next((p["username"] for p in players if p["user_id"] == only), None)


def mcq_transition_to_results(state: dict) -> None:
    """Move an MCQ round from playing to results and build its ``round_results``."""
    state["round_phase"] = "results"
    answers = state.get("answers", {})

    round_results: list[dict] = []
    for p in state["players"]:
        p_answer = answers.get(p["user_id"])
        if p_answer:
            round_results.append(
                {
                    "user_id": p["user_id"],
                    "username": p["username"],
                    "chose_correct": p_answer["correct"],
                    "points": p_answer["points"],
                    "choice_index": p_answer.get("choice_index"),
                    "answer_time_ms": p_answer.get("answer_time_ms"),
                }
            )
        else:
            round_results.append(
                {
                    "user_id": p["user_id"],
                    "username": p["username"],
                    "chose_correct": False,
                    "points": 0,
                    "choice_index": None,
                    "answer_time_ms": None,
                }
            )

    # Sort by points desc
    round_results.sort(key=lambda r: -r["points"])
    state["round_results"] = round_results


def wordquiz_transition_to_results(state: dict) -> None:
    """Move a Word Quiz round from playing to results and build its ``round_results``."""
    state["round_phase"] = "results"
    answers = state.get("answers", {})
    attempts = state.get("attempts", {})

    round_results: list[dict] = []
    for p in state["players"]:
        p_answer = answers.get(p["user_id"])
        p_attempts = attempts.get(p["user_id"]) or {}
        if p_answer:
            round_results.append(
                {
                    "user_id": p["user_id"],
                    "username": p["username"],
                    "answered_at_hint": p_answer["hint_number"],
                    "points": p_answer["points"],
                    "answer_time_ms": p_answer.get("answer_time_ms"),
                    "typed_answer": p_answer.get("answer_text"),
                    # Rows from before attempts were counted still found it once.
                    "attempts": p_attempts.get("count", 1),
                }
            )
        else:
            round_results.append(
                {
                    "user_id": p["user_id"],
                    "username": p["username"],
                    "answered_at_hint": None,
                    "points": 0,
                    "answer_time_ms": None,
                    "typed_answer": p_attempts.get("last_text"),
                    "attempts": p_attempts.get("count", 0),
                }
            )

    # Sort by points desc, then by answer_time_ms asc. `round_results` is a
    # `list[dict]` of live_state JSON; `points` is an int written just above.
    round_results.sort(key=lambda r: (-r["points"], r.get("answer_time_ms") or float("inf")))
    state["round_results"] = round_results


_TRANSITIONS_TO_RESULTS: dict[GameType, Callable[[dict], None]] = {
    GameType.WORD_QUIZ: wordquiz_transition_to_results,
    GameType.MCQ_QUIZ: mcq_transition_to_results,
}


def settle_round_if_everyone_answered(state: dict, game_type: GameType) -> bool:
    """Move the open round to results when nobody left in it still owes an answer.

    ``submit_answer`` makes this move when the last answer arrives. A departure can
    complete a round too — the one player everybody was waiting on leaves, is kicked
    or is removed by the grace sweep — and nothing else would notice: every remaining
    player had answered, so no answer could arrive, and the round sat open until its
    timer ran out. The departure path (``disconnect``) and ``resume_game`` call this.

    Never while paused: the departure is recorded but the round stays as the prayer
    found it, and the resume settles it.

    :return: whether the round moved to results.
    """
    if state.get("round_phase") != "playing" or is_paused(state) or not everyone_has_answered(state):
        return False
    _TRANSITIONS_TO_RESULTS[game_type](state)
    return True

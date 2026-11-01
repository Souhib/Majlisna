"""End-of-game stat and achievement writes, shared by the normal and disconnect paths.

This lives in its own module rather than on ``BaseGameController`` because
``disconnect.py`` needs it too, and ``base_game`` imports ``RoomController``, which
imports ``disconnect`` — so a controller import from there is a cycle. Only
``stats``, ``achievement``, ``challenge``, ``codenames_helpers`` (enums) and the models
are imported here, none of which reach back into rooms or games.

What a game end writes, for every scorable player (``scorable_players``: leavers and
deleted accounts are skipped — owner rule (b)):

- ``live_state[WINNER_IDS_KEY]``: the winners, for every game type. ``stats.did_user_win``
  (history, chart, head-to-head) reads it, so all of them agree with ``UserStats``;
- the ``UserStats`` counters, including the three nothing used to write: ``games_hosted``,
  ``mr_white_correct_guesses`` and ``codenames_perfect_rounds`` (PD-05);
- the stat achievements, then the five special ones (``SPECIAL_ACHIEVEMENT_RULES``,
  owner rule (f)), computed from the final ``live_state``;
- the daily and weekly challenges (owner rule (g)): missing ones are assigned first,
  so a player's first games count before they ever open /challenges.

**Nothing in here commits.** Every caller runs inside ``get_game_lock``, which on
PostgreSQL is ``pg_try_advisory_xact_lock`` — transaction scoped. A commit here would
release the game lock in the middle of the end-of-game critical section. The caller's
single ``commit()`` persists these writes.

**SQLAlchemy errors are not swallowed either.** After a failed statement the session
needs a rollback, so catching-and-continuing made every later query in the loop and
the caller's commit raise ``PendingRollbackError``, losing the whole game-end write.
"""

from collections.abc import Callable, Collection, Sequence
from typing import NamedTuple
from uuid import UUID

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    CODENAMES_REVEAL_LOG_KEY,
    HOST_USERNAME_STATE_KEY,
    MIN_PLAYERS_FOR_A_WIN,
    MR_WHITE_GUESS_RESULT_KEY,
    UNANIMOUS_VOTE_MIN_VOTES,
    UNDERCOVER_AUTO_VOTERS_KEY,
    WINNER_IDS_KEY,
)
from majlisna.api.controllers.achievement import AchievementController
from majlisna.api.controllers.challenge import ChallengeController
from majlisna.api.controllers.codenames_helpers import CodenamesCardType, CodenamesRole
from majlisna.api.controllers.stats import StatsController
from majlisna.api.models.game import GameType
from majlisna.api.models.stats import AchievementDefinition, UserStats
from majlisna.api.models.table import User
from majlisna.api.models.undercover import UndercoverRole
from majlisna.api.utils.game_state import left_player_ids


async def scorable_players(session: AsyncSession, state: dict) -> list[dict]:
    """The players from live_state who stayed to the end and whose User row still exists.

    **Leavers are not scored** (owner rule (b)): every id ``mark_player_left`` recorded
    in ``state[LEFT_PLAYER_IDS_KEY]`` is dropped, so ``record_game_end`` writes nothing
    for them — no stats row change (neither a win nor a loss), no achievement, no
    challenge progress — in all four games. An Undercover drop-out stays in
    ``state["players"]`` (dead), and this is what keeps it from sharing the win.

    ``live_state["players"]`` is a snapshot frozen at game start, so a player who
    deletes their account mid-game stays in it — and ``UserStats(user_id=<gone>)``
    then fails the foreign key, which (since the stats loop no longer swallows
    SQLAlchemy errors) would make the game impossible to ever finish.

    One query for the whole set, not one per player.
    """
    left = left_player_ids(state)
    players = [p for p in state.get("players", []) if p["user_id"] not in left]
    if not players:
        return []
    player_ids = [UUID(p["user_id"]) for p in players]
    existing = set(
        (
            await session.exec(
                select(User.id).where(User.id.in_(player_ids))  # ty: ignore[unresolved-attribute]
            )
        ).all()
    )
    scorable = [p for p in players if UUID(p["user_id"]) in existing]
    if len(scorable) != len(players):
        missing = [p["user_id"] for p in players if UUID(p["user_id"]) not in existing]
        logger.warning("Skipping stats for deleted users {}", missing)
    return scorable


async def record_game_end(
    session: AsyncSession,
    state: dict,
    *,
    game_type: str,
    winners: set[str],
    default_role: str = "player",
    track_hints: bool = True,
) -> list[dict]:
    """Stage the stat and achievement writes for a finished game.

    Also writes ``state[WINNER_IDS_KEY]`` (the caller writes ``live_state`` back and
    flags it, as it already does for ``newly_unlocked_achievements``).

    :param winners: the ``user_id`` strings of the players who won. Each game decides
        that differently (role vs. winning label in Undercover, team in Codenames,
        top score in the quizzes), so the caller resolves it and passes the answer.
        Only the scorable ones are kept, and none at all when the final roster is
        below ``MIN_PLAYERS_FOR_A_WIN`` (a game is a win only against someone).
    :param track_hints: whether this game type feeds the hint achievements.
    :return: ``[{user_id, achievements: [{code, name, icon, tier}]}]`` for newly
        unlocked achievements, for the client to toast.
    """
    stats_controller = StatsController(session)
    achievement_controller = AchievementController(session)
    challenge_controller = ChallengeController(session)
    hint_usage = state.get("hint_usage", {}) if track_hints else {}
    newly_unlocked_all: list[dict] = []

    players = await scorable_players(session, state)
    winner_ids = resolve_winner_ids(state, winners, scorable_ids={p["user_id"] for p in players})
    state[WINNER_IDS_KEY] = winner_ids
    winning = frozenset(winner_ids)
    host_id = _host_player_id(state, players)
    special_rules = [(code, rule) for code, rule in SPECIAL_ACHIEVEMENT_RULES.items() if rule.game_type == game_type]

    # One read per table for the whole table of players (BDP-07): this runs inside the
    # game lock, and per-player reads made a 12-player game end ~110 statements.
    user_ids = [UUID(p["user_id"]) for p in players]
    stats_by_user = await stats_controller.get_or_create_many(user_ids)
    achievements_by_user = await achievement_controller.load_user_achievements(user_ids)
    challenges_by_user = await challenge_controller.load_active(user_ids)

    # A solo final roster is no result (owner rule (a)): neither a win nor a loss, as
    # ``stats.did_user_win`` answers for the chart and history (reviews R4, INT-03).
    has_result = len(final_roster(state)) >= MIN_PLAYERS_FOR_A_WIN
    for player in players:
        user_id = UUID(player["user_id"])
        won = player["user_id"] in winning
        role = player.get("role", default_role)
        known = achievements_by_user[user_id]
        stats = await stats_controller.update_stats_after_game(
            user_id=user_id,
            game_type=game_type,
            won=won if has_result else None,
            role=role,
            commit=False,
            stats=stats_by_user[user_id],
        )
        # Before the achievement check, so mr_white_guess_1 unlocks in the game that earned it.
        _add_game_counters(stats, state, player, game_type=game_type, is_host=player["user_id"] == host_id)

        if track_hints:
            hints_viewed_count = len(hint_usage.get(str(user_id), []))
            if hints_viewed_count > 0:
                stats.total_hints_viewed += hints_viewed_count
            if won and hints_viewed_count == 0:
                stats.games_without_hints += 1
        session.add(stats)

        unlocked: list[AchievementDefinition] = list(
            await achievement_controller.check_achievements(user_id, stats, commit=False, known=known)
        )
        for code, rule in special_rules:
            if rule.applies(state, player, winning):
                special = await achievement_controller.unlock_special(user_id, code, commit=False, known=known)
                if special is not None:
                    unlocked.append(special)
        if unlocked:
            newly_unlocked_all.append(
                {
                    "user_id": str(user_id),
                    "achievements": [
                        {"code": a.code, "name": a.name, "icon": a.icon, "tier": a.tier} for a in unlocked
                    ],
                }
            )

        active = challenges_by_user[user_id]
        await challenge_controller.assign_missing_challenges(user_id, commit=False, active=active)
        await challenge_controller.check_progress(user_id, game_type, won, role, commit=False, active=active)
        logger.info("Stats updated: game={} user={}", game_type, user_id)

    return newly_unlocked_all


def final_roster(state: dict) -> list[dict]:
    """The players still at the table at the end: ``state["players"]`` minus the leavers.

    An Undercover player eliminated by vote is in it (they played to the end, dead);
    one who walked out is not (owner rule (b)).
    """
    left = left_player_ids(state)
    return [p for p in state.get("players", []) if p["user_id"] not in left]


def resolve_winner_ids(state: dict, winners: Collection[str], *, scorable_ids: Collection[str]) -> list[str]:
    """The sorted ids written to ``state[WINNER_IDS_KEY]``: the winners who are scorable
    (no leaver, no deleted account), and nobody when the final roster is a solo one."""
    if len(final_roster(state)) < MIN_PLAYERS_FOR_A_WIN:
        return []
    return sorted(w for w in winners if w in scorable_ids)


def _host_player_id(state: dict, players: Sequence[dict]) -> str | None:
    """The scorable player who hosted the game (``games_hosted``), or None.

    The host is the room owner when the game STARTED, recorded by name in
    ``state[HOST_USERNAME_STATE_KEY]`` next to the players' own start-time names
    (usernames are unique case-insensitively), so a later host transfer does not move
    the credit. A host who spectated, or left, is not in ``players`` and is not credited.
    """
    host_username = state.get(HOST_USERNAME_STATE_KEY)
    if not host_username:
        return None
    return next((p["user_id"] for p in players if p.get("username") == host_username), None)


def _add_game_counters(stats: UserStats, state: dict, player: dict, *, game_type: str, is_host: bool) -> None:
    """The per-game counters ``update_stats_after_game`` cannot see from (won, role) alone."""
    if is_host:
        stats.games_hosted += 1
    if game_type == GameType.UNDERCOVER.value and guessed_the_civilian_word(state, player["user_id"]):
        stats.mr_white_correct_guesses += 1
    if game_type == GameType.CODENAMES.value:
        stats.codenames_perfect_rounds += codenames_perfect_rounds(state, player.get("team"))


def guessed_the_civilian_word(state: dict, user_id: str) -> bool:
    """Whether ``user_id`` is the Mr. White whose guess was right (``MR_WHITE_GUESS_RESULT_KEY``).

    A right guess ends the game, so the last result recorded is the one that counts.
    """
    result = state.get(MR_WHITE_GUESS_RESULT_KEY)
    return isinstance(result, dict) and result.get("user_id") == user_id and bool(result.get("correct"))


def codenames_perfect_rounds(state: dict, team: str | None) -> int:
    """How many of ``team``'s clue turns were perfect: its operatives turned exactly
    ``clue_number`` cards, all of them their own (an unlimited clue, number 0, is never one).

    Read from ``clue_history``: each entry is one clue turn, with its team, its
    ``clue_number`` and every card turned under it. The reveal log carries the turn
    (``clue_turn``) but not the number the spymaster gave, which is the whole test.
    """
    perfect = 0
    for clue in state.get("clue_history") or []:
        if team is None or clue.get("team") != team:
            continue
        number = clue.get("clue_number") or 0
        guesses = clue.get("guesses") or []
        if number >= 1 and len(guesses) == number and all(g.get("card_type") == team for g in guesses):
            perfect += 1
    return perfect


def codenames_reveals(state: dict) -> list[dict]:
    """Every card turned, in order, as ``state[CODENAMES_REVEAL_LOG_KEY]`` entries.

    A game that predates the log has its reveals rebuilt from ``clue_history``, without
    the voters (nobody recorded who pointed at a card), so it can still be a sweep but
    never an assassin find.
    """
    log = state.get(CODENAMES_REVEAL_LOG_KEY)
    if isinstance(log, list):
        return log
    return [
        {"team": clue.get("team"), "card_type": guess.get("card_type"), "voter_ids": [], "clue_turn": turn}
        for turn, clue in enumerate(state.get("clue_history") or [], start=1)
        for guess in clue.get("guesses") or []
    ]


# ── The five special achievements (owner rule (f)) ────────────────────────────
# Each rule reads the FINAL live_state, the player's entry and the winner ids, and is
# asked only for a scorable player (never a leaver) of its own game type.


def _undercover_side(winner_label: str | None) -> frozenset[str]:
    """The roles of the side an Undercover ``state["winner"]`` label names."""
    if winner_label == "civilians":
        return frozenset({UndercoverRole.CIVILIAN.value})
    if winner_label == "undercovers":
        return frozenset({UndercoverRole.UNDERCOVER.value, UndercoverRole.MR_WHITE.value})
    return frozenset()


def _is_perfect_undercover(state: dict, player: dict, winner_ids: frozenset[str]) -> bool:
    """perfect_undercover: an undercover who won, and no vote of any turn ever named them."""
    user_id = player["user_id"]
    if player.get("role") != UndercoverRole.UNDERCOVER.value or user_id not in winner_ids:
        return False
    return all(target != user_id for turn in state.get("turns") or [] for target in (turn.get("votes") or {}).values())


def _unanimous_target(turn: dict) -> str | None:
    """The player every other ballot of ``turn`` named, if the table was unanimous.

    The target's own ballot is left out: nobody can vote for themselves, and every alive
    player votes (or is voted for by the timer), so "every ballot names one player" could
    never happen. At least ``UNANIMOUS_VOTE_MIN_VOTES`` such ballots, none of them drawn
    by the timer (``UNDERCOVER_AUTO_VOTERS_KEY``): a draw that agreed is not the table.
    """
    votes = turn.get("votes") or {}
    drawn = set(turn.get(UNDERCOVER_AUTO_VOTERS_KEY) or [])
    for target in set(votes.values()):
        ballots = {voter: named for voter, named in votes.items() if voter != target}
        if (
            len(ballots) >= UNANIMOUS_VOTE_MIN_VOTES
            and all(named == target for named in ballots.values())
            and not drawn & ballots.keys()
        ):
            return target
    return None


def _was_in_a_unanimous_vote(state: dict, player: dict, winner_ids: frozenset[str]) -> bool:  # noqa: ARG001
    """unanimous_vote: this player cast one of the ballots of a resolved, unanimous round
    (``_unanimous_target``); the target does not earn it."""
    user_id = player["user_id"]
    for turn in state.get("turns") or []:
        if not turn.get("resolved") or user_id not in (turn.get("votes") or {}):
            continue
        target = _unanimous_target(turn)
        if target is not None and target != user_id:
            return True
    return False


def _is_last_survivor(state: dict, player: dict, winner_ids: frozenset[str]) -> bool:
    """last_survivor: alive at the end, on the winning side, and its only living member."""
    if player["user_id"] not in winner_ids or not player.get("is_alive"):
        return False
    side = _undercover_side(state.get("winner"))
    alive_on_side = [p["user_id"] for p in state.get("players", []) if p.get("is_alive") and p.get("role") in side]
    return alive_on_side == [player["user_id"]]


def _is_sweep_victory(state: dict, player: dict, winner_ids: frozenset[str]) -> bool:
    """sweep_victory: the player's team won, and every card it turned was its own
    (no neutral, no opponent card, no assassin). A team that turned nothing — it won
    because the other side found the assassin — swept nothing."""
    team = player.get("team")
    if player["user_id"] not in winner_ids or team is None:
        return False
    turned = [r.get("card_type") for r in codenames_reveals(state) if r.get("team") == team]
    return bool(turned) and all(card_type == team for card_type in turned)


def _found_the_assassin(state: dict, player: dict, winner_ids: frozenset[str]) -> bool:  # noqa: ARG001
    """assassin_finder: an operative whose card vote was the assassin that got turned,
    whether or not the team lost."""
    if player.get("role") != CodenamesRole.OPERATIVE.value:
        return False
    return any(
        r.get("card_type") == CodenamesCardType.ASSASSIN.value and player["user_id"] in (r.get("voter_ids") or [])
        for r in codenames_reveals(state)
    )


class SpecialRule(NamedTuple):
    """When a special achievement (``stat_field: None``) unlocks."""

    game_type: str
    applies: Callable[[dict, dict, frozenset[str]], bool]


# Every ACHIEVEMENT_DEFINITIONS code with stat_field None, and only those
# (tests/api/controllers/test_wp03_specials.py checks both directions).
SPECIAL_ACHIEVEMENT_RULES: dict[str, SpecialRule] = {
    "perfect_undercover": SpecialRule(GameType.UNDERCOVER.value, _is_perfect_undercover),
    "unanimous_vote": SpecialRule(GameType.UNDERCOVER.value, _was_in_a_unanimous_vote),
    "last_survivor": SpecialRule(GameType.UNDERCOVER.value, _is_last_survivor),
    "sweep_victory": SpecialRule(GameType.CODENAMES.value, _is_sweep_victory),
    "assassin_finder": SpecialRule(GameType.CODENAMES.value, _found_the_assassin),
}


def undercover_winners(state: dict, winner_label: str) -> set[str]:
    """The user_ids on the winning side of an Undercover game (drop-outs included:
    ``record_game_end`` keeps only the scorable ones)."""
    winning_roles = _undercover_side(winner_label)
    return {p["user_id"] for p in state.get("players", []) if p.get("role", "civilian") in winning_roles}


def codenames_winners(state: dict, winning_team: str) -> set[str]:
    """The user_ids on the winning team of a Codenames game."""
    return {p["user_id"] for p in state.get("players", []) if p.get("team") == winning_team}


def top_score_winners(players: Sequence[dict], *, left_ids: Collection[str] = ()) -> set[str]:
    """The winners of a quiz game, by owner rule (a).

    - Every player with the maximum ``total_score`` shares the win (a tie is a shared
      win, never "whoever is seated first").
    - Only when that score is above 0: a 0-0 game has no winner.
    - Only over a final roster of at least ``MIN_PLAYERS_FOR_A_WIN``: a solo game is
      never a win. The roster is ``players`` minus ``left_ids`` (pass
      ``left_player_ids(state)``), so a game whose other players all left is a solo
      game — which also stops farming wins with a second account that leaves.

    It used to return ``{max(players).user_id}``: one arbitrary winner for a tie, a
    winner at 0-0, and a win for every solo 1-question quiz answered wrong, all of
    which fed the leaderboard and the win-streak achievements (BR-11, PD-10).
    """
    roster = [p for p in players if p["user_id"] not in left_ids]
    if len(roster) < MIN_PLAYERS_FOR_A_WIN:
        return set()
    best = max(p["total_score"] for p in roster)
    if best <= 0:
        return set()
    return {p["user_id"] for p in roster if p["total_score"] == best}

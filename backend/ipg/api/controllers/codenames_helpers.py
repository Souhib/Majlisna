import random
from enum import StrEnum

from ipg.api.constants import (
    CODENAMES_ASSASSIN_CARDS,
    CODENAMES_FIRST_TEAM_CARDS,
    CODENAMES_NEUTRAL_CARDS,
    CODENAMES_SECOND_TEAM_CARDS,
)


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
    random.shuffle(card_types)

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
    random.shuffle(shuffled)

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
    raise ValueError(f"Player with user_id {user_id} not found in game")
